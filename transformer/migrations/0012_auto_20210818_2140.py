# Generated by Django 3.2.5 on 2021-08-18 21:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transformer', '0011_auto_20210713_2054'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='package',
            name='accession_data',
        ),
        migrations.AddField(
            model_name='package',
            name='archivesspace_accession',
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
        migrations.AddField(
            model_name='package',
            name='archivesspace_group',
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
        migrations.AddField(
            model_name='package',
            name='archivesspace_transfer',
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
        migrations.AddField(
            model_name='package',
            name='aurora_accession',
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
        migrations.AddField(
            model_name='package',
            name='aurora_transfer',
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
    ]