# Generated by Django 2.2.6 on 2020-01-13 18:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transformer', '0005_auto_20190919_2321'),
    ]

    operations = [
        migrations.AddField(
            model_name='package',
            name='origin',
            field=models.CharField(choices=[('aurora', 'Aurora'), ('legacy_digital', 'Legacy Digital Processing'), ('digitization', 'Digitization')], default='aurora', max_length=20),
        ),
    ]