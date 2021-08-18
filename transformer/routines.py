import json
import time

from aquarius import settings
from odin.codecs import json_codec

from .clients import ArchivesSpaceClient, AuroraClient, UrsaMajorClient
from .mappings import (SourceAccessionToArchivesSpaceAccession,
                       SourceAccessionToGroupingComponent,
                       SourcePackageToDigitalObject,
                       SourceRightsStatementToArchivesSpaceRightsStatement,
                       SourceTransferToTransferComponent, map_agents)
from .models import Package
from .resources.source import (SourceAccession, SourceCreator, SourcePackage,
                               SourceRightsStatement, SourceTransfer)


class RoutineError(Exception):
    pass


class UpdateRequestError(Exception):
    pass


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
        try:
            from_obj = json_codec.loads(json.dumps(data), resource=from_resource)
            return json.loads(json_codec.dumps(mapping.apply(from_obj)))
        except Exception as e:
            raise Exception("get_transformed_object Exception: {}".format(e))

    def get_linked_agents(self, agents):
        try:
            linked_agents = []
            for agent in agents:
                agent_data = map_agents(SourceCreator(type=agent["type"], name=agent["name"]))
                agent_ref = self.aspace_client.get_or_create(
                    agent["type"], "title", agent["name"],
                    self.start_time, json.loads(json_codec.dumps(agent_data)))
                linked_agents.append({"uri": agent_ref})
            return linked_agents
        except Exception as e:
            raise Exception("get_linked_agents Exception: {}".format(e))


class AccessionRoutine(Routine):
    """Transforms and saves accession data."""

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
        package.accession_data["data"]["linked_agents"] = self.get_linked_agents(
            package.accession_data["data"]["creators"] + [
                {"name": package.accession_data["data"]["organization"], "type": "organization"}])
        return package.accession_data["data"]

    def save_transformed_object(self, transformed):
        if not transformed.get("archivesspace_identifier"):
            return self.aspace_client.create(transformed, "accession").get("uri")

    def post_save_actions(self, package, full_data, transformed, accession_uri):
        package.accession_data["data"]["archivesspace_identifier"] = accession_uri
        package.accession_data["data"]["accession_number"] = full_data.get("accession_number")
        for p in package.accession_data["data"]["transfers"]:
            for sibling in Package.objects.filter(bag_identifier=p["identifier"]):
                sibling.accession_data = package.accession_data
                sibling.save()

    def discover_sibling_data(self, package):
        if Package.objects.filter(
                data__accession=package.data["accession"], accession_data__isnull=False).exists():
            sibling = Package.objects.filter(
                data__accession=package.data["accession"], accession_data__isnull=False)[0]
            package.accession_data = sibling.accession_data
            package.data["data"]["archivesspace_parent_identifier"] = \
                sibling.data["data"].get("archivesspace_parent_identifier")


class GroupingComponentRoutine(Routine):
    """Transforms and saves grouping component data."""

    start_status = Package.ACCESSION_UPDATE_SENT
    end_status = Package.GROUPING_COMPONENT_CREATED
    object_type = "Grouping component"
    from_resource = SourceAccession
    mapping = SourceAccessionToGroupingComponent

    def get_data(self, package):
        try:
            data = package.accession_data["data"]
            data["level"] = "recordgrp"
            data["linked_agents"] = self.get_linked_agents(
                data["creators"] + [
                    {"name": data["organization"], "type": "organization"}])
            return data
        except Exception as e:
            raise Exception("get_data Exception: {}".format(e))

    def save_transformed_object(self, transformed):
        if not transformed.get("archivesspace_identifier"):
            return self.aspace_client.create(transformed, "component").get("uri")

    def post_save_actions(self, package, full_data, transformed, parent_uri):
        try:
            for p in package.accession_data["data"]["transfers"]:
                for sibling in Package.objects.filter(bag_identifier=p["identifier"], data__isnull=False):
                    sibling.data["data"]["archivesspace_parent_identifier"] = parent_uri
                    sibling.save()
        except Exception as e:
            raise Exception("post_save_actions Exception: {}".format(e))


class TransferComponentRoutine(Routine):
    """Transforms and saves transfer component data."""

    start_status = Package.GROUPING_COMPONENT_CREATED
    end_status = Package.TRANSFER_COMPONENT_CREATED
    object_type = "Transfer component"
    from_resource = SourceTransfer
    mapping = SourceTransferToTransferComponent

    def get_data(self, package):
        try:
            data = package.data["data"]
            data["resource"] = package.accession_data["data"].get("resource")
            data["level"] = "file"
            data["linked_agents"] = self.get_linked_agents(
                data["metadata"]["record_creators"] + [
                    {"name": data["metadata"]["source_organization"], "type": "organization"}])
            return data
        except Exception as e:
            raise Exception("get_data Exception: {}".format(e))

    def save_transformed_object(self, transformed):
        if not transformed.get("archivesspace_identifier"):
            return self.aspace_client.create(transformed, "component").get("uri")

    def post_save_actions(self, package, full_data, transformed, transfer_uri):
        try:
            package.data["data"]["archivesspace_identifier"] = transfer_uri
            for sibling in Package.objects.filter(bag_identifier=package.bag_identifier, data__isnull=False):
                sibling.data["data"]["archivesspace_identifier"] = transfer_uri
                sibling.save()
        except Exception as e:
            raise Exception("post_save_actions Exception: {}".format(e))


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
        """Adds additional data to the archival object to which the digital object is attached.

        If no rights statements are already assigned to the archival object, transforms
        and adds rights statements. Adds the newly created digital objects to the
        archival object's instances array.
        """
        transfer_component = self.aspace_client.retrieve(package.data["data"]["archivesspace_identifier"])
        if not len(transfer_component.get("rights_statements")) and package.origin in ["digitization", "legacy_digital"]:
            rights_data = self.ursa_major_client.find_bag_by_id(package.bag_identifier)["data"].get("rights_statements")
            transformed_rights = self.get_transformed_object(
                rights_data, SourceRightsStatement, SourceRightsStatementToArchivesSpaceRightsStatement)
            transfer_component["rights_statements"] = transformed_rights
        transfer_component["instances"].append(
            {"instance_type": "digital_object",
             "jsonmodel_type": "instance",
             "digital_object": {"ref": do_uri}})
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
        for obj in Package.objects.filter(process_status=self.start_status, origin="aurora"):
            try:
                data = self.update_data(obj)
                identifier = data["url"].rstrip("/").split("/")[-1]
                prefix = data["url"].rstrip("/").split("/")[-2]
                url = "/".join([prefix, "{}/".format(identifier.lstrip("/"))])
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
        data = obj.data["data"]
        data["process_status"] = 90
        return data


class AccessionUpdateRequester(AuroraUpdater):
    """Updates accession data in Aurora."""
    start_status = Package.ACCESSION_CREATED
    end_status = Package.ACCESSION_UPDATE_SENT

    def update_data(self, obj):
        data = obj.accession_data["data"]
        data["process_status"] = 30
        return data
