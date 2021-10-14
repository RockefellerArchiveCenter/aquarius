import json
import time
from os import listdir
from os.path import join
from unittest.mock import patch

from aquarius import settings
from django.test import TestCase
from django.urls import reverse

from .models import Package
from .routines import (AccessionRoutine, AccessionUpdateRequester,
                       DigitalObjectRoutine, GroupingComponentRoutine,
                       TransferComponentRoutine, TransferUpdateRequester)


class ViewTestCase(TestCase):

    VIEW_MAP = (
        ("transformer.routines.AccessionRoutine.run", "accessions"),
        ("transformer.routines.GroupingComponentRoutine.run", "grouping-components"),
        ("transformer.routines.TransferComponentRoutine.run", "transfer-components"),
        ("transformer.routines.DigitalObjectRoutine.run", "digital-objects"),
        ("transformer.routines.TransferUpdateRequester.run", "send-update"),
        ("transformer.routines.AccessionUpdateRequester.run", "send-accession-update"),
    )

    @patch("transformer.routines.Routine.__init__")
    @patch("transformer.routines.AuroraUpdater.__init__")
    def test_routine_views(self, mock_aurora_init, mock_routine_init):
        mock_aurora_init.return_value = None
        mock_routine_init.return_value = None
        for run_fn, view_str in self.VIEW_MAP:
            with patch(run_fn) as mocked_fn:
                mocked_fn.return_value = "foo", []
                response = self.client.post(reverse(view_str))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"detail": "foo", "objects": [], "count": 0})
                mocked_fn.assert_called_once()

    def test_schema(self):
        schema = self.client.get(reverse("schema"))
        self.assertEqual(schema.status_code, 200, "Wrong HTTP code")

    def test_health_check(self):
        status = self.client.get(reverse("api_health_ping"))
        self.assertEqual(status.status_code, 200, "Wrong HTTP code")

    def test_create_transfers(self):
        for file in sorted(listdir(join(settings.BASE_DIR, "transformer", "fixtures", "package_data"))):
            with open(join(settings.BASE_DIR, "transformer", "fixtures", "package_data", file), "r") as json_file:
                data = json.load(json_file)
                response = self.client.post(reverse("package-list"), data, format="json")
                self.assertEqual(response.status_code, 200, "Request threw exception: {}".format(response.data))
                new_obj = Package.objects.get(fedora_uri=data.get("uri"))
                process_status = Package.SAVED if new_obj.origin == "aurora" else Package.TRANSFER_COMPONENT_CREATED
                self.assertEqual(int(new_obj.process_status), process_status, "Package was created with the incorrect process status.")
                if new_obj.origin in ["digitization", "legacy_digital"]:
                    self.assertEqual(
                        new_obj.archivesspace_transfer, data.get("archivesspace_uri"),
                        "ArchivesSpace Identifier was not created correctly")

    def test_search_objects(self):
        updated_time = int(time.time()) - (24 * 3600)
        response = self.client.get(reverse("package-list"), {"updated_since": updated_time})
        self.assertEqual(response.status_code, 200, "Wrong HTTP code")
        self.assertTrue(len(response.json()) >= 1, "No search results")


class RoutinesTestCase(TestCase):
    fixtures = ["packages.json"]

    def setUp(self):
        """Load fixtures needed for mocking responses"""
        for fixture in [
                "archivesspace_archival_object",
                "ursa_major_accession",
                "ursa_major_bag"]:
            with open(join("transformer", "fixtures", "{}.json".format(fixture))) as df:
                data = json.load(df)
                setattr(self, fixture, data)

    @patch("transformer.clients.UrsaMajorClient.find_bag_by_id")
    @patch("transformer.clients.UrsaMajorClient.retrieve")
    @patch("transformer.clients.ASnakeClient.authorize")
    @patch("transformer.clients.ArchivesSpaceClient.next_accession_number")
    @patch("transformer.clients.ArchivesSpaceClient.create")
    @patch("transformer.clients.ArchivesSpaceClient.get_or_create")
    def test_process_accessions(self, as_get_or_create, as_create, as_accession_number, as_auth, ursa_accession, ursa_bag):
        ursa_major_transfer_url = "/api/transfers/1635/"
        as_accession_uri = "/repositories/2/accessions/123"
        ursa_bag.return_value = self.ursa_major_bag
        ursa_accession.return_value = self.ursa_major_accession
        as_auth.return_value = True
        as_accession_number.return_value = "2020:001"
        as_create.return_value = {"uri": as_accession_uri}
        as_get_or_create.return_value = "/agents/people/1"
        msg, obj_list = AccessionRoutine().run()
        self.assertEqual(msg, "Accession created.")
        self.assertEqual(len(obj_list), 1)
        as_create.assert_called_once()
        for package in Package.objects.filter(process_status=Package.ACCESSION_CREATED):
            self.assertIsNot(None, package.ursa_major_accession)
            self.assertEqual(package.aurora_accession, self.ursa_major_accession["data"]["url"])
            self.assertEqual(package.aurora_transfer, ursa_major_transfer_url)
            self.assertIsNot(package.archivesspace_accession, as_accession_uri)

    @patch("transformer.clients.UrsaMajorClient.retrieve")
    @patch("transformer.clients.ASnakeClient.authorize")
    @patch("transformer.clients.ArchivesSpaceClient.create")
    @patch("transformer.clients.ArchivesSpaceClient.get_or_create")
    def test_process_grouping_components(self, as_get_or_create, as_create, as_auth, ursa_accession):
        as_group_uri = "/repositories/2/archival_objects/123"
        ursa_accession.return_value = self.ursa_major_accession
        as_auth.return_value = True
        as_create.return_value = {"uri": as_group_uri}
        as_get_or_create.return_value = "/agents/people/1"
        msg, obj_list = GroupingComponentRoutine().run()
        self.assertEqual(msg, "Grouping component created.")
        self.assertEqual(len(obj_list), 1)
        as_create.assert_called_once()
        for package in Package.objects.filter(process_status=Package.GROUPING_COMPONENT_CREATED):
            self.assertEqual(package.archivesspace_group, as_group_uri)

    @patch("transformer.clients.UrsaMajorClient.find_bag_by_id")
    @patch("transformer.clients.ASnakeClient.authorize")
    @patch("transformer.clients.ArchivesSpaceClient.create")
    @patch("transformer.clients.ArchivesSpaceClient.get_or_create")
    def test_process_transfer_components(self, as_get_or_create, as_create, as_auth, ursa_bag):
        as_transfer_uri = "/repositories/2/archival_objects/1234"
        ursa_bag.return_value = self.ursa_major_bag
        as_auth.return_value = True
        as_create.return_value = {"uri": as_transfer_uri}
        as_get_or_create.return_value = "/agents/people/1"
        msg, obj_list = TransferComponentRoutine().run()
        self.assertEqual(msg, "Transfer component created.")
        self.assertEqual(len(obj_list), 1)
        as_create.assert_called_once()
        for package in Package.objects.filter(process_status=Package.TRANSFER_COMPONENT_CREATED):
            self.assertEqual(package.archivesspace_transfer, as_transfer_uri)

    @patch("transformer.clients.UrsaMajorClient.find_bag_by_id")
    @patch("transformer.clients.ASnakeClient.authorize")
    @patch("transformer.clients.ArchivesSpaceClient.create")
    @patch("transformer.clients.ArchivesSpaceClient.retrieve")
    @patch("transformer.clients.ArchivesSpaceClient.update")
    def test_process_digital_objects(self, as_update_object, as_object, as_create_object, as_auth, ursa_bag):
        as_auth.return_value = True
        as_create_object.return_value = {"uri": "foobar"}
        as_object.return_value = self.archivesspace_archival_object
        as_update_object.return_value = {"uri": "barbaz"}
        ursa_bag.return_value = self.ursa_major_bag
        msg, obj_list = DigitalObjectRoutine().run()
        self.assertEqual(msg, "Digital object created.")
        self.assertEqual(len(obj_list), 1)
        self.assertEqual(as_create_object.call_count, 1)

    @patch("transformer.clients.ElectronBond.authorize")
    @patch("transformer.clients.ElectronBond.patch")
    def test_transfer_update(self, mock_patch, mock_auth):
        mock_auth.return_value = True
        mock_patch.return_value.status_code = 200
        msg, obj_list = TransferUpdateRequester().run()
        self.assertEqual(msg, "Update requests sent.")
        self.assertEqual(len(obj_list), 4)

    @patch("transformer.clients.ElectronBond.authorize")
    @patch("transformer.clients.ElectronBond.patch")
    def test_accession_update(self, mock_patch, mock_auth):
        mock_auth.return_value = True
        mock_patch.return_value.status_code = 200
        msg, obj_list = AccessionUpdateRequester().run()
        self.assertEqual(msg, "Update requests sent.")
        self.assertEqual(len(obj_list), 4)
