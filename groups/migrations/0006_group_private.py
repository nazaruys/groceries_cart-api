# Generated by Django 5.0.6 on 2024-07-11 08:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0005_remove_product_active_product_date_buyed'),
    ]

    operations = [
        migrations.AddField(
            model_name='group',
            name='private',
            field=models.BooleanField(default=False),
        ),
    ]
