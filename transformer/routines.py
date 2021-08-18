import json
import time

from aquarius import settings
from odin.codecs import json_codec

from .clients import ArchivesSpaceClient, AuroraClient, UrsaMajorClient
from .mappings import (SourceAccessionToArchivesSpaceAccession,
                       SourceAccessionToGroupingComponent,
                       SourcePackageToDigitalObject,
                       SourceTransferToTransferComponent, map_agents)
from .models import Package
from .resources.source import (SourceAccession, SourceCreator, SourcePackage,
                               SourceTransfer)


class Routine:
    """Base routine class which is inherited by all other routines.

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
        self.aspace_client = ArchivesSpaceClient(settings.ARCHIVESSPACE["baseurl"],
                                                 settings.ARCHIVESSPACE["username"],
                                                 settings.ARCHIVESSPACE["password"],
                                                 settings.ARCHIVESSPACE["repo_id"])
        self.ursa_major_client = UrsaMajorClient(settings.URSA_MAJOR["baseurl"])
        self.start_time = int(time.time())

    def run(self):
        package_ids = []
        for package in Package.objects.filter(process_status=self.start_status):
            try:
                self.transform_object(package)
                package.process_status = self.end_status
                package.save()
                package_ids.append(package.bag_identifier)
            except Exception as e:
                raise Exception("{} error: {}".format(self.object_type, e), package.bag_identifier)
        message = ("{} created.".format(self.object_type) if len(package_ids)
                   else "No {}s to process.".format(self.object_type))
        return (message, package_ids)

    def get_transformed_object(self, data, from_resource, mapping):
        from_obj = json_codec.loads(json.dumps(data), resource=from_resource)
        return json.loads(json_codec.dumps(mapping.apply(from_obj)))

    def get_linked_agents(self, agents):
        linked_agents = []
        for agent in agents:
            agent_data = map_agents(SourceCreator(type=agent["type"], name=agent["name"]))
            agent_ref = self.aspace_client.get_or_create(
                agent["type"], "title", agent["name"],
                self.start_time, json.loads(json_codec.dumps(agent_data)))
            linked_agents.append({"uri": agent_ref})
        return linked_agents


class AccessionRoutine(Routine):
    """Transforms and saves accession data."""

    start_status = Package.SAVED
    end_status = Package.ACCESSION_CREATED
    object_type = "Accession"

    def transform_object(self, package):
        package_data = self.ursa_major_client.find_bag_by_id(package.bag_identifier)
        first_sibling = self.first_sibling(package_data["accession"])
        if first_sibling:
            archivesspace_accession_uri = first_sibling.archivesspace_accession
        else:
            data = self.ursa_major_client.retrieve(package_data["accession"]).get("data")
            data["accession_number"] = self.aspace_client.next_accession_number()
            data["linked_agents"] = self.get_linked_agents(
                data["creators"] + [{"name": data["organization"], "type": "organization"}])
            transformed = self.get_transformed_object(data, SourceAccession, SourceAccessionToArchivesSpaceAccession)
            archivesspace_accession_uri = self.aspace_client.create(transformed, "accession").get("uri")
        package.aurora_accession = package_data["accession"]
        package.aurora_transfer = package_data["url"]
        package.archivesspace_accession = archivesspace_accession_uri

    def first_sibling(self, accession_identifier):
        if Package.objects.filter(aurora_accession=accession_identifier).exists():
            return Package.objects.filter(aurora_accession=accession_identifier).first()
        return None


class GroupingComponentRoutine(Routine):
    """Transforms and saves grouping component data."""

    start_status = Package.ACCESSION_UPDATE_SENT
    end_status = Package.GROUPING_COMPONENT_CREATED
    object_type = "Grouping component"

    def transform_object(self, package):
        first_sibling = self.first_sibling(package.aurora_accession)
        if first_sibling:
            archivesspace_group_uri = first_sibling.archivesspace_group
        else:
            data = self.ursa_major_client.retrieve(package.aurora_accession).get("data")
            data["level"] = "recordgrp"
            data["linked_agents"] = self.get_linked_agents(
                data["creators"] + [{"name": data["organization"], "type": "organization"}])
            transformed = self.get_transformed_object(data, SourceAccession, SourceAccessionToGroupingComponent)
            archivesspace_group_uri = self.aspace_client.create(transformed, "component").get("uri")
        package.archivesspace_group = archivesspace_group_uri

    def first_sibling(self, accession_identifier):
        if Package.objects.filter(aurora_accession=accession_identifier, archivesspace_group__isnull=False).exists():
            return Package.objects.filter(aurora_accession=accession_identifier, archivesspace_group__isnull=False).first()
        return None


class TransferComponentRoutine(Routine):
    """Transforms and saves transfer component data."""

    start_status = Package.GROUPING_COMPONENT_CREATED
    end_status = Package.TRANSFER_COMPONENT_CREATED
    object_type = "Transfer component"

    def transform_object(self, package):
        first_sibling = self.first_sibling(package.aurora_accession)
        if first_sibling:
            archivesspace_transfer_uri = first_sibling.archivesspace_transfer
        else:
            data = self.ursa_major_client.find_bag_by_id(package.bag_identifier)
            data["resource"] = package.accession_data["data"].get("resource")
            data["level"] = "file"
            data["linked_agents"] = self.get_linked_agents(
                data["metadata"]["record_creators"] + [{"name": data["metadata"]["source_organization"], "type": "organization"}])
            transformed = self.get_transformed_object(data, SourceTransfer, SourceTransferToTransferComponent)
            archivesspace_transfer_uri = self.aspace_client.create(transformed, "component").get("uri")
        package.archivesspace_transfer = archivesspace_transfer_uri

    def first_sibling(self, accession_identifier):
        if Package.objects.filter(aurora_accession=accession_identifier, archivesspace_transfer__isnull=False).exists():
            return Package.objects.filter(aurora_accession=accession_identifier, archivesspace_transfer__isnull=False).first()
        return None


class DigitalObjectRoutine(Routine):
    """Transforms and saves digital object data."""

    start_status = Package.TRANSFER_COMPONENT_CREATED
    end_status = Package.DIGITAL_OBJECT_CREATED
    object_type = "Digital object"
    from_resource = SourcePackage
    mapping = SourcePackageToDigitalObject

    def get_data(self, package):
        return {"fedora_uri": package.fedora_uri, "use_statement": package.use_statement}

    def save_transformed_object(self, transformed):
        return self.aspace_client.create(transformed, "digital object").get("uri")

    def post_save_actions(self, package, full_data, transformed, do_uri):
        transfer_component = self.aspace_client.retrieve(package.data["data"]["archivesspace_identifier"])
        transfer_component["instances"].append(
            {"instance_type": "digital_object",
             "jsonmodel_type": "instance",
             "digital_object": {"ref": do_uri}
             })
        self.aspace_client.update(package.data["data"]["archivesspace_identifier"], transfer_component)


class AuroraUpdater:
    """Base class for routines that interact with Aurora.

    Provides a web client and a `run` method.

    To use this class, override the `update_data` method. This method specifies
    the data object to be delivered to Aurora, as well as any changes to that
    object. Classes inheriting this class should also specify a `start_status`
    and an `end_status`, which determine the queryset of objects acted on and
    the status to which those objects are updated, respectively.
    """

    def __init__(self):
        self.client = AuroraClient(baseurl=settings.AURORA["baseurl"],
                                   username=settings.AURORA["username"],
                                   password=settings.AURORA["password"])

    def run(self):
        update_ids = []
        for package in Package.objects.filter(process_status=self.start_status, origin="aurora"):
            try:
                data = self.update_data()
                url = getattr(package, self.url_attribute)
                self.client.update(url, data=data)
                package.process_status = self.end_status
                package.save()
                update_ids.append(package.bag_identifier)
            except Exception as e:
                raise Exception(e)
        message = "Update requests sent." if len(update_ids) else "No update requests pending"
        return (message, update_ids)


class TransferUpdateRequester(AuroraUpdater):
    """Updates transfer data in Aurora."""
    start_status = Package.DIGITAL_OBJECT_CREATED
    end_status = Package.UPDATE_SENT
    url_attribute = "aurora_transfer"

    def update_data(self):
        return {"process_status": 90}


class AccessionUpdateRequester(AuroraUpdater):
    """Updates accession data in Aurora."""
    start_status = Package.ACCESSION_CREATED
    end_status = Package.ACCESSION_UPDATE_SENT
    url_attribute = "aurora_accession"

    def update_data(self):
        return {"process_status": 30}
