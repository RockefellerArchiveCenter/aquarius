from django.contrib.postgres.fields import JSONField
from django.db import models

from client.clients import AuroraClient


class DataObject(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    TYPE_CHOICES = (
        ('accession', 'Accession'),
        ('agent', 'Agent'),
        ('collection', 'Collection'),
        ('component', 'Component'),
        ('term', 'Term'),
    )
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    data = JSONField()


class SourceObject(models.Model):
    SOURCE_CHOICES = (
        ('aurora', 'Aurora'),
    )
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES)

    def update_data(self):
        client = AuroraClient().client
        data = client.get(self.data['url'])
        self.data = data
        self.save()


class ConsumerObject(DataObject):
    source_object = models.ForeignKey(SourceObject, on_delete=models.CASCADE, related_name='source_object')
    CONSUMER_CHOICES = (
        ('archivesspace', 'ArchivesSpace'),
        ('fedora', 'Fedora')
    )
    consumer = models.CharField(max_length=50, choices=CONSUMER_CHOICES)