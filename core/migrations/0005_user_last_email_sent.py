# Generated by Django 5.1.1 on 2024-09-08 14:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_user_verification_code_user_verified'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='last_email_sent',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
