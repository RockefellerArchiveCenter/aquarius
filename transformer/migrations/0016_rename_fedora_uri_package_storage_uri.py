# Generated by Django 4.2.1 on 2023-06-26 16:00

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transformer', '0015_alter_package_origin'),
    ]

    operations = [
        migrations.RenameField(
            model_name='package',
            old_name='fedora_uri',
            new_name='storage_uri',
        ),
    ]
