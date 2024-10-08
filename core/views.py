from django.contrib.auth import get_user_model, authenticate, login, logout
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework import mixins
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.decorators import api_view
from django.utils import timezone
from datetime import timedelta
from groups.models import Group
from .serializers import UserSerializer, LoginSerializer, VerifyEmailSerializer, ResendVerificationEmailSerializer, FeedbackSerializer
from .functions import is_valid_password
from .permissions import IsUsersProfileOrGroupAdmin
from .utils import send_email



User = get_user_model()


class UserViewSet(mixins.CreateModelMixin,
                   mixins.RetrieveModelMixin,
                   mixins.UpdateModelMixin,
                   mixins.ListModelMixin,
                   GenericViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.request.user and self.request.user.is_staff:
            self.permission_classes = [AllowAny]
        else:
            if self.action == 'list':
                self.permission_classes = [IsAdminUser]
            elif self.action == 'retrieve':
                self.permission_classes = [IsAuthenticated]
            elif self.action == 'update' or self.action == 'partial_update':
                self.permission_classes = [IsUsersProfileOrGroupAdmin]
            elif self.action == 'create':
                self.permission_classes = [AllowAny]
            else:
                self.permission_classes = [IsAuthenticated]
        return super().get_permissions()

        
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        errors = {}
        password = request.data['password']
        if not is_valid_password(password):
            errors['password'] = 'Password must be at least 8 characters long and have at least one number, capital and lower letter.'
        group_id = request.data.get('group_id')
        if group_id and not Group.objects.filter(code=group_id).exists():
            errors['group'] = 'Group does not exist.'
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        self.perform_create(serializer)

        user = serializer.instance
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        response_data = {
            'user': serializer.data,
            'token': {
                'refresh': str(refresh),
                'access': access_token,
            }
        }

        headers = self.get_success_headers(serializer.data)
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        errors = {}

        password = request.data.get('password')
        if password and not is_valid_password(password):
            errors['password'] = 'Password must be at least 8 characters long and have at least one number, capital and lower letter.'
        
        group_id = request.data.get('group_id')
        if group_id and not Group.objects.filter(code=group_id).exists():
            errors['group_id'] = 'Group does not exist.'

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        
        if group_id:
            group = Group.objects.get(code=group_id)
            if group.private:
                return Response({"detail": 'You do not have permission to access this group. It is private.'}, status=status.HTTP_403_FORBIDDEN)
            if group.users_blacklist.filter(id=instance.id).exists():
                return Response({"detail": 'You do not have permission to access this group. You are blacklisted.'}, status=status.HTTP_403_FORBIDDEN)
        
        # if instance is changing group_id
        if 'group_id' in request.data and instance.group_id and group_id != instance.group_id:
            previous_group = Group.objects.get(code=instance.group_id)
            # If user is an admin of previous group:
            if instance == previous_group.admin:
                instance.admin_of = None
                new_admin = previous_group.members.exclude(pk=instance.pk).first()
                if new_admin:
                    previous_group.admin = new_admin
                    previous_group.save()
                else:
                    previous_group.delete()
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data['username']
        password = serializer.validated_data['password']
        user = authenticate(request, username=username, password=password)

        if user is not None:
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token)
            })
        
        return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
def verify_email_code(request):
    serializer = VerifyEmailSerializer(data=request.data)
    permission_classes = [IsAuthenticated]
    
    if serializer.is_valid():
        email = serializer.validated_data['email']
        verification_code = serializer.validated_data['verification_code']
        
        try:
            user = User.objects.get(email=email, verification_code=verification_code)
            
            # Update user's verification status
            user.verified = True
            user.verification_code = None  # Clear the code to prevent reuse
            user.save()
            
            return Response({'message': 'Email successfully verified.'}, status=status.HTTP_200_OK)
        
        except User.DoesNotExist:
            return Response({'error': 'Invalid verification code.'}, status=status.HTTP_400_BAD_REQUEST)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResendVerificationEmailView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = ResendVerificationEmailSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
                if not (user.verified):
                    # Check for email timeout
                    TIMEOUT = timedelta(minutes=5)
                    if user.last_email_sent: 
                        time_elapsed = timezone.now() - user.last_email_sent
                        if time_elapsed < TIMEOUT:
                            remaining_time = (TIMEOUT - time_elapsed).total_seconds()
                            minutes, seconds = divmod(remaining_time, 60)
                            return Response(
                                {'error': f'You can request a new email in {int(minutes)} minutes and {int(seconds)} seconds.'}, 
                                status=status.HTTP_429_TOO_MANY_REQUESTS
                            )
                    user.last_email_sent = timezone.now()

                    # Send the welcome email
                    subject = "Verification code"
                    message = f"Hi {user.username},\n\nHere is your verification code: {user.verification_code}"
                    send_email(subject, message, [user.email], from_name_email='PickFast <noreply@pick-fast.com>')

                    return Response({'message': 'Email resent successfully.'}, status=status.HTTP_200_OK)
                return Response({'error': 'You are already verified.'}, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                return Response({'error': 'User with this email does not exist.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class FeedbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FeedbackSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            message = serializer.validated_data['message']

            user = User.objects.get(email=email)

            TIMEOUT = timedelta(minutes=5)
            print('Boolean', user.last_email_sent)
            if user.last_email_sent:
                print('Last email ', user.last_email_sent)
                time_elapsed = timezone.now() - user.last_email_sent
                print('Time elapsed: ', time_elapsed)
                if time_elapsed < TIMEOUT:
                    remaining_time = (TIMEOUT - time_elapsed).total_seconds()
                    print('Time remaining: ', remaining_time)
                    minutes, seconds = divmod(remaining_time, 60)
                    return Response(
                        {'error': f'You can send a new feedback in {int(minutes)} minutes and {int(seconds)} seconds.'}, 
                        status=status.HTTP_429_TOO_MANY_REQUESTS
                    )
            user.last_email_sent = timezone.now()

            user.save()

            print('user time set: ', user.last_email_sent)

            # Send the email
            send_email(
                subject="New Feedback PickFast",
                message=f"Feedback message:\n\n{message}\n\nRespond to: {email}",
                from_name_email=email,
                recipient_list=['nazary.box@gmail.com', 'support@pick-fast.com'],
            )

            return Response({'message': 'Feedback sent successfully.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)