import json

from aquarius import settings
from odin.codecs import json_codec

from .clients import ArchivesSpaceClient, AuroraClient, UrsaMajorClient
from .mappings import (SourceAccessionToArchivesSpaceAccession,
                       SourceAccessionToGroupingComponent,
                       SourcePackageToDigitalObject,
                       SourceTransferToTransferComponent)
from .models import Package
from .resources.source import SourceAccession, SourcePackage, SourceTransfer


class RoutineError(Exception):
    pass


class UpdateRequestError(Exception):
    pass


class Routine:
    """
    Base class which is inherited by all other routines.

    Provides default clients for ArchivesSpace and Ursa Major, and instantiates
    a DataTransformer class.

    The `apply_transformations` method in the `run` function is intended to be
    overriden by routines which interact with specific types of objects.
    Requires the following variables to be overriden as well:
        start_status - the status of the objects to be acted on.
        end_status - the status to be applied to Package objects once the
                        routine has completed successfully.
        object_type - a string containing the object type of the routine.
        from_resource - an odin.Resource which represents source data.
        mapping - an odin.Mapping which mapps the from_resource to the desired
                    output.
    """

    def __init__(self):
        self.aspace_client = ArchivesSpaceClient(settings.ARCHIVESSPACE['baseurl'],
                                                 settings.ARCHIVESSPACE['username'],
                                                 settings.ARCHIVESSPACE['password'],
                                                 settings.ARCHIVESSPACE['repo_id'])
        self.ursa_major_client = UrsaMajorClient(settings.URSA_MAJOR['baseurl'])

    def run(self):
        package_ids = []

        for package in Package.objects.filter(process_status=self.start_status):
            try:
                package.refresh_from_db()
                initial_data = self.get_data(package)
                transformed = self.get_transformed_object(initial_data, self.from_resource, self.mapping)
                obj_uri = self.save_transformed_object(transformed)
                if obj_uri:
                    self.post_save_actions(package, initial_data, transformed, obj_uri)
                package.process_status = self.end_status
                package.save()
                package_ids.append(package.bag_identifier)
            except Exception as e:
                raise RoutineError("{} error: {}".format(self.object_type, e), package.bag_identifier)
        message = ("{} created.".format(self.object_type) if (len(package_ids) > 0)
                   else "{} updated.".format(self.object_type))
        return (message, package_ids)

    def get_transformed_object(self, data, from_resource, mapping):
        from_obj = json_codec.loads(json.dumps(data), resource=from_resource)
        return json.loads(json_codec.dumps(mapping.apply(from_obj)))


class AccessionRoutine(Routine):
    """Transforms accession data stored in Ursa Major and delivers the
       transformed data to ArchivesSpace where it is saved as an accession record."""

    start_status = Package.SAVED
    end_status = Package.ACCESSION_CREATED
    object_type = "Accession"
    from_resource = SourceAccession
    mapping = SourceAccessionToArchivesSpaceAccession

    def get_data(self, package):
        package.data = self.ursa_major_client.find_bag_by_id(package.bag_identifier)
        self.discover_sibling_data(package)
        if not package.accession_data:
            package.accession_data = self.ursa_major_client.retrieve(package.data["accession"])
        package.accession_data["data"]["accession_number"] = self.aspace_client.next_accession_number()
        return package.accession_data["data"]

    def save_transformed_object(self, transformed):
        if not transformed.get("archivesspace_identifier"):
            return self.aspace_client.create(transformed, 'accession').get('uri')

    def post_save_actions(self, package, full_data, transformed, accession_uri):
        package.accession_data['data']['archivesspace_identifier'] = accession_uri
        package.accession_data['data']['accession_number'] = full_data.get("accession_number")
        for p in package.accession_data['data']['transfers']:
            for sibling in Package.objects.filter(bag_identifier=p['identifier']):
                sibling.accession_data = package.accession_data
                sibling.save()

    def discover_sibling_data(self, package):
        if Package.objects.filter(
                data__accession=package.data['accession'], accession_data__isnull=False).exists():
            sibling = Package.objects.filter(
                data__accession=package.data['accession'], accession_data__isnull=False)[0]
            package.accession_data = sibling.accession_data
            package.data['data']['archivesspace_parent_identifier'] = \
                sibling.data['data'].get('archivesspace_parent_identifier')


class GroupingComponentRoutine(Routine):
    """Transforms accession data stored in Ursa Major into a grouping component
       and delivers the transformed data to ArchivesSpace where it is saved
       as an archival object record."""

    start_status = Package.ACCESSION_UPDATE_SENT
    end_status = Package.GROUPING_COMPONENT_CREATED
    object_type = "Grouping component"
    from_resource = SourceAccession
    mapping = SourceAccessionToGroupingComponent

    def get_data(self, package):
        data = package.accession_data["data"]
        data["level"] = "recordgrp"
        return data

    def save_transformed_object(self, transformed):
        if not transformed.get("archivesspace_identifier"):
            return self.aspace_client.create(transformed, 'component').get('uri')

    def post_save_actions(self, package, full_data, transformed, parent_uri):
        for p in package.accession_data['data']['transfers']:
            for sibling in Package.objects.filter(bag_identifier=p['identifier']):
                sibling.data['data']['archivesspace_parent_identifier'] = parent_uri
                sibling.save()


class TransferComponentRoutine(Routine):
    """Transforms transfer data stored in Ursa Major and delivers the
       transformed data to ArchivesSpace where it is saved as an archival object record."""

    start_status = Package.GROUPING_COMPONENT_CREATED
    end_status = Package.TRANSFER_COMPONENT_CREATED
    object_type = "Transfer component"
    from_resource = SourceTransfer
    mapping = SourceTransferToTransferComponent

    def get_data(self, package):
        data = package.data["data"]
        data["resource"] = package.accession_data['data']['resource']
        data["level"] = "file"
        return data

    def save_transformed_object(self, transformed):
        if not transformed.get("archivesspace_identifier"):
            return self.aspace_client.create(transformed, 'component').get('uri')

    def post_save_actions(self, package, full_data, transformed, transfer_uri):
        package.data['data']['archivesspace_identifier'] = transfer_uri
        for sibling in Package.objects.filter(bag_identifier=package.bag_identifier):
            sibling.data['data']['archivesspace_identifier'] = transfer_uri
            sibling.save()


class DigitalObjectRoutine(Routine):
    """Transforms transfer data stored in Ursa Major and delivers the
       transformed data to ArchivesSpace where it is saved as a digital object record."""

    start_status = Package.TRANSFER_COMPONENT_CREATED
    end_status = Package.DIGITAL_OBJECT_CREATED
    object_type = "Digital object"
    from_resource = SourcePackage
    mapping = SourcePackageToDigitalObject

    def get_data(self, package):
        return {"fedora_uri": package.fedora_uri, "use_statement": package.use_statement}

    def save_transformed_object(self, transformed):
        return self.aspace_client.create(transformed, 'digital object').get('uri')

    def post_save_actions(self, package, full_data, transformed, do_uri):
        transfer_component = self.aspace_client.retrieve(package.data['data']['archivesspace_identifier'])
        transfer_component['instances'].append(
            {"instance_type": "digital_object",
             "jsonmodel_type": "instance",
             "digital_object": {"ref": do_uri}
             })
        self.aspace_client.update(package.data['data']['archivesspace_identifier'], transfer_component)


class AuroraUpdater:
    """
    Base class for routines that interact with Aurora. Provides a web client
    and a `run` method.

    To use this class, override the `update_data` method. This method specifies
    the data object to be delivered to Aurora, as well as any changes to that
    object. Classes inheriting this class should also specify a `start_status`
    and an `end_status`, which determine the queryset of objects acted on and
    the status to which those objects are updated, respectively.
    """

    def __init__(self):
        self.client = AuroraClient(baseurl=settings.AURORA['baseurl'],
                                   username=settings.AURORA['username'],
                                   password=settings.AURORA['password'])

    def run(self):
        update_ids = []
        for obj in Package.objects.filter(process_status=self.start_status, origin='aurora'):
            try:
                data = self.update_data(obj)
                identifier = data['url'].rstrip('/').split('/')[-1]
                prefix = data['url'].rstrip('/').split('/')[-2]
                url = "/".join([prefix, "{}/".format(identifier.lstrip('/'))])
                self.client.update(url, data=data)
                obj.process_status = self.end_status
                obj.save()
                update_ids.append(obj.bag_identifier)
            except Exception as e:
                raise UpdateRequestError(e)
        return ("Update requests sent.", update_ids)


class TransferUpdateRequester(AuroraUpdater):
    """Updates transfer data in Aurora."""
    start_status = Package.DIGITAL_OBJECT_CREATED
    end_status = Package.UPDATE_SENT

    def update_data(self, obj):
        data = obj.data['data']
        data['process_status'] = 90
        return data


class AccessionUpdateRequester(AuroraUpdater):
    """Updates accession data in Aurora."""
    start_status = Package.ACCESSION_CREATED
    end_status = Package.ACCESSION_UPDATE_SENT

    def update_data(self, obj):
        data = obj.accession_data['data']
        data['process_status'] = 30
        return data
