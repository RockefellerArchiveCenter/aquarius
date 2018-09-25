# Generated by Django 2.0 on 2018-09-25 00:52

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Identifier',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('last_modified', models.DateTimeField(auto_now=True)),
                ('identifier', models.CharField(max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name='Transfer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('last_modified', models.DateTimeField(auto_now=True)),
                ('fedora_uri', models.CharField(max_length=512)),
                ('internal_sender_identifier', models.CharField(max_length=256)),
                ('package_type', models.CharField(choices=[('aip', 'AIP'), ('dip', 'DIP')], max_length=10)),
                ('transfer_data', django.contrib.postgres.fields.jsonb.JSONField()),
                ('accession_data', django.contrib.postgres.fields.jsonb.JSONField()),
            ],
        ),
        migrations.AddField(
            model_name='identifier',
            name='transfer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='identifier', to='transformer.Transfer'),
        ),
    ]
