from rest_framework import serializers

from .models import Package


class PackageSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = Package
        fields = ('url', 'bag_identifier', 'type', 'origin', 'process_status',
                  'aurora_accession', 'aurora_transfer', 'archivesspace_accession',
                  'archivesspace_group', 'archivesspace_transfer', 'ursa_major_accession')
