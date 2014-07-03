"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
#
## Utilities for testing SEED modules.
###

from seed.models import(
    ASSESSED_RAW,
    BuildingSnapshot,
    COMPOSITE_BS,
    CanonicalBuilding,
    ColumnMapping,
    set_initial_sources,
)


def make_fake_mappings(mappings, org, source_type=ASSESSED_RAW):
    """Takes a dict and saves a ColumnMapping object for each key"""
    for mapped, raw in mappings.items():
        ColumnMapping.objects.create(
            super_organization=org,
            source_type=source_type,
            column_raw=raw,
            column_mapped=mapped
    )


def make_fake_snapshot(import_file, init_data, bs_type, is_canon=False):
    """For making fake mapped BuildingSnapshots to test matching against."""
    snapshot = BuildingSnapshot.objects.create(**init_data)
    snapshot.import_file = import_file
    if import_file is None:
        snapshot.import_record = None
    else:
        snapshot.import_record = import_file.import_record
    snapshot.source_type = bs_type
    set_initial_sources(snapshot)
    snapshot.save()
    if is_canon:
        canonical_building = CanonicalBuilding.objects.create(
            canonical_snapshot=snapshot
        )
        snapshot.canonical_building = canonical_building
        snapshot.save()

    return snapshot


class FakeRequest(object):
    """A simple request stub."""
    __name__ = 'FakeRequest'
    method = 'POST'
    META = {'REMOTE_ADDR': '127.0.0.1'}
    path = 'fake_login_path'
    body = None

    def __init__(self, headers=None, user=None):
        if headers:
            self.META.update(headers)
        if user:
            self.user = user


class FakeClient(object):
    """An extremely light-weight test client."""

    def _gen_req(self, view_func, data, headers, method='POST', **kwargs):
        request = FakeRequest(headers)
        if 'user' in kwargs:
            request.user = kwargs.get('user')
        if callable(view_func):
            setattr(request, method, data)
            request.body = json.dumps(data)
            return view_func(request)

        return request

    def get(self, view_func, data, headers=None, **kwargs):
        return self._gen_req(view_func, data, headers, method='GET', **kwargs)

    def post(self, view_func, data, headers=None, **kwargs):
        return self._gen_req(view_func, data, headers, **kwargs)


