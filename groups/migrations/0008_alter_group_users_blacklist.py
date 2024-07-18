# Generated by Django 5.0.6 on 2024-07-13 08:19

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0007_group_users_blacklist'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='group',
            name='users_blacklist',
            field=models.ManyToManyField(blank=True, related_name='blacklisted_groups', to=settings.AUTH_USER_MODEL),
        ),
    ]