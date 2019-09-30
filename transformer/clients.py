from asnake.client import ASnakeClient
from electronbonder.client import ElectronBond
from datetime import date
import json


class ArchivesSpaceClientError(Exception): pass
class ArchivesSpaceClientAccessionNumberError(Exception): pass
class UrsaMajorClientError(Exception): pass
class AuroraClientError(Exception): pass


class ArchivesSpaceClient(object):
    """Client to get and receive data from ArchivesSpace."""

    def __init__(self, baseurl, username, password, repo_id):
        self.client = ASnakeClient(baseurl=baseurl, username=username, password=password)
        self.repo_id = repo_id
        if not self.client.authorize():
            raise ArchivesSpaceClientError("Couldn't authenticate user credentials for ArchivesSpace")
        self.TYPE_LIST = {
            'family': ['agent_family', 'agents/families'],
            'organization': ['agent_corporate_entity', 'agents/corporate_entities'],
            'person': ['agent_person', 'agents/people'],
            'component': ['archival_object', 'repositories/{repo_id}/archival_objects'.format(repo_id=self.repo_id)],
            'accession': ['accession', 'repositories/{repo_id}/accessions'.format(repo_id=self.repo_id)],
            'digital object': ['digital_objects', 'repositories/{repo_id}/digital_objects'.format(repo_id=self.repo_id)]
        }

    def send_request(self, method, url, data=None, *args, **kwargs):
        """Base method for sending requests to ArchivesSpace."""
        r = getattr(self.client, method)(url, data=json.dumps(data), *args, **kwargs)
        if r.status_code == 200:
            return r.json()
        else:
            if r.json()['error'].get('id_0'):
                raise ArchivesSpaceClientAccessionNumberError(r.json()['error'])
            raise ArchivesSpaceClientError('Error sending {} request to {}: {}'.format(method, url, r.json()['error']))

    def retrieve(self, url, *args, **kwargs):
        return self.send_request('get', url, *args, **kwargs)

    def create(self, data, type, *args, **kwargs):
        return self.send_request('post', self.TYPE_LIST[type][1], data, *args, **kwargs)

    def update(self, uri, data, *args, **kwargs):
        return self.send_request('post', uri, data, *args, *kwargs)

    def get_or_create(self, type, field, value, last_updated, consumer_data):
        """
        Attempts to find and return an object in ArchivesSpace.
        If the object is not found, creates and returns a new object.
        """
        model_type = self.TYPE_LIST[type][0]
        endpoint = self.TYPE_LIST[type][1]
        query = json.dumps({"query": {"field": field, "value": value, "jsonmodel_type": "field_query"}})
        try:
            r = self.client.get('search', params={"page": 1, "type[]": model_type, "aq": query}).json()
            if len(r['results']) == 0:
                r = self.client.get(endpoint, params={"all_ids": True, "modified_since": last_updated-120}).json()
                for ref in r:
                    r = self.client.get('{}/{}'.format(endpoint, ref)).json()
                    if r[field] == str(value):
                        return r['uri']
                return self.create(consumer_data, type)
            return r['results'][0]['uri']
        except Exception as e:
            raise ArchivesSpaceClientError('Error finding or creating object in ArchivesSpace: {}'.format(e))

    def next_accession_number(self):
        """
        Finds the next available accession number by searching for accession
        numbers with the current year, and then incrementing.

        Assumes that accession numbers are in the format YYYY NNN, where YYYY
        is the current year and NNN is a zero-padded integer.
        """
        current_year = str(date.today().year)
        try:
            query = json.dumps({"query": {"field": "four_part_id", "value": current_year, "jsonmodel_type": "field_query"}})
            r = self.client.get('search', params={"page": 1, "type[]": "accession", "sort": "identifier desc", "aq": query}).json()
            number = '001'
            if r.get('total_hits') >= 1:
                if r['results'][0]['identifier'].split("-")[0] == current_year:
                    id_1 = int(r['results'][0]['identifier'].split("-")[1])
                    id_1 += 1
                    updated = str(id_1).zfill(3)
                    number = updated
            return [current_year, number]
        except Exception as e:
            raise ArchivesSpaceClientError('Error retrieving next accession number from ArchivesSpace: {}'.format(e))


class UrsaMajorClient(object):
    """Client to get and receive data from Ursa Major."""

    def __init__(self, baseurl):
        self.client = ElectronBond(baseurl=baseurl)

    def send_request(self, method, url, data=None, *args, **kwargs):
        """Base class for sending requests to Ursa Major"""
        try:
            return getattr(self.client, method)(url, data=json.dumps(data), *args, **kwargs).json()
        except Exception as e:
            raise UrsaMajorClientError("Error sending {} request to {}: {}".format(method, url, e))

    def retrieve(self, url, *args, **kwargs):
        return self.send_request('get', url, *args, **kwargs)

    def update(self, url, data, *args, **kwargs):
        return self.send_request('put', url, data, headers={"Content-Type":"application/json"}, *args, **kwargs)

    def retrieve_paged(self, url, *args, **kwargs):
        try:
            resp = self.client.get_paged(url, *args, **kwargs)
            return resp
        except Exception as e:
            raise UrsaMajorClientError("Error retrieving list from Ursa Major: {}".format(e))

    def find_bag_by_id(self, identifier, *args, **kwargs):
        """Finds a bag by its id."""
        try:
            bag_resp = self.client.get("bags/", params={"id": identifier}).json()
            count = bag_resp.get('count')
            if count != 1:
                raise UrsaMajorClientError("Found {} bags matching id {}, expected 1".format(count, identifier))
            bag_url = bag_resp.get('results')[0]['url']
            return self.send_request('get', bag_url)
        except Exception as e:
            raise UrsaMajorClientError("Error finding bag by id: {}".format(e))


class AuroraClient:

    def __init__(self, baseurl, username, password):
        self.client = ElectronBond(baseurl=baseurl, username=username, password=password)
        if not self.client.authorize():
            raise AuroraClientError("Could not authorize {} in Aurora".format(username))

    def update(self, url, data, *args, **kwargs):
        resp = self.client.put(url, data=json.dumps(data), headers={"Content-Type":"application/json"}, *args, **kwargs)
        if resp.status_code == 200:
            return resp.json()
        else:
            raise AuroraClientError("Error sending request {} to Aurora: {}".format(url, resp.json()))
