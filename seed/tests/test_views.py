"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
import json

from django.core.cache import cache
from django.core.urlresolvers import reverse_lazy
from django.test import TestCase

from superperms.orgs.models import Organization, OrganizationUser

from data_importer.models import ROW_DELIMITER, ImportFile, ImportRecord
from landing.models import SEEDUser as User
from seed import decorators
from seed.factory import SEEDFactory
from seed.models import (
    ColumnMapping,
    CanonicalBuilding,
    BuildingSnapshot,
    ASSESSED_RAW,
    ASSESSED_BS,
    COMPOSITE_BS,
    PORTFOLIO_BS,
    save_snapshot_match,
)
from seed.views.main import DEFAULT_CUSTOM_COLUMNS
from seed.utils import ASSESSOR_FIELDS
from seed.tests import util as test_util


# Gavin 02/18/2014
# Why are we testing DataImporterViews in the seed module?
class DataImporterViewTests(TestCase):
    """
    Tests of the data_importer views (and the objects they create).
    """

    def setUp(self):
        user_details = {
            'username': 'test_user',
            'password': 'test_pass',
        }
        self.user = User.objects.create_superuser(
            email='test_user@demo.com', **user_details)
        self.client.login(**user_details)

    def test_get_raw_column_names(self):
        """Make sure we get column names back in a format we expect."""
        import_record = ImportRecord.objects.create()
        expected_raw_columns = ['tax id', 'name', 'etc.']
        expected_saved_format = ROW_DELIMITER.join(expected_raw_columns)
        import_file = ImportFile.objects.create(
            import_record=import_record,
            cached_first_row=expected_saved_format
        )

        # Just make sure we were saved correctly
        self.assertEqual(import_file.cached_first_row, expected_saved_format)

        url = reverse_lazy("seed:get_raw_column_names")
        resp = self.client.post(
            url, data=json.dumps(
                {'import_file_id': import_file.pk}
            ), content_type='application/json'
        )

        body = json.loads(resp.content)

        self.assertEqual(body.get('raw_columns', []), expected_raw_columns)

    def test_get_first_five_rows(self):
        """Make sure we get our first five rows back correctly."""
        import_record = ImportRecord.objects.create()
        expected_raw_columns = ['tax id', 'name', 'etc.']
        expected_raw_rows = [
            ['02023', '12 Jefferson St.', 'etc.'],
            ['12433', '23 Washington St.', 'etc.'],
            ['04422', '4 Adams St.', 'etc.'],
        ]

        expected = [
            dict(zip(expected_raw_columns, row)) for row in expected_raw_rows
        ]
        expected_saved_format = '\n'.join([
            ROW_DELIMITER.join(row) for row in expected_raw_rows
        ])
        import_file = ImportFile.objects.create(
            import_record=import_record,
            cached_first_row=ROW_DELIMITER.join(expected_raw_columns),
            cached_second_to_fifth_row=expected_saved_format
        )

        # Just make sure we were saved correctly
        self.assertEqual(
            import_file.cached_second_to_fifth_row, expected_saved_format
        )

        url = reverse_lazy("seed:get_first_five_rows")
        resp = self.client.post(
            url, data=json.dumps(
                {'import_file_id': import_file.pk}
            ), content_type='application/json'
        )

        body = json.loads(resp.content)

        self.assertEqual(body.get('first_five_rows', []), expected)


class DefaultColumnsViewTests(TestCase):
    """
    Tests of the SEED default custom saved columns
    """

    def setUp(self):
        user_details = {
            'username': 'test_user',
            'password': 'test_pass',
            'email': 'test_user@demo.com'
        }
        self.user = User.objects.create_superuser(**user_details)
        self.client.login(**user_details)

    def test_get_default_columns_with_set_columns(self):
        columns = ["source_facility_id", "test_column_0"]
        self.user.default_custom_columns = columns
        self.user.save()
        columns = ["source_facility_id", "test_column_0"]
        url = reverse_lazy("seed:get_default_columns")
        response = self.client.get(url)
        json_string = response.content
        data = json.loads(json_string)

        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['columns'], columns)
        self.assertEqual(data['initial_columns'], False)

    def test_get_default_columns_initial_state(self):
        url = reverse_lazy("seed:get_default_columns")
        response = self.client.get(url)
        json_string = response.content
        data = json.loads(json_string)

        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['columns'], DEFAULT_CUSTOM_COLUMNS)
        self.assertEqual(data['initial_columns'], True)

    def test_set_default_columns(self):
        url = reverse_lazy("seed:set_default_columns")
        columns = ['s', 'c1', 'c2']
        post_data = {
            'columns': columns,
            'show_shared_buildings': True
        }
        # set the columns
        response = self.client.post(
            url,
            content_type='application/json',
            data=json.dumps(post_data)
        )
        json_string = response.content
        data = json.loads(json_string)
        self.assertEqual(data['status'], 'success')

        # get the columns
        url = reverse_lazy("seed:get_default_columns")
        response = self.client.get(url)
        json_string = response.content
        data = json.loads(json_string)
        self.assertEqual(data['columns'], DEFAULT_CUSTOM_COLUMNS + columns)

        # get show_shared_buildings
        url = reverse_lazy("accounts:get_shared_buildings")
        response = self.client.get(url)
        json_string = response.content
        data = json.loads(json_string)
        self.assertEqual(data['show_shared_buildings'], True)

        # set show_shared_buildings to False
        post_data['show_shared_buildings'] = False
        url = reverse_lazy("seed:set_default_columns")
        response = self.client.post(
            url,
            content_type='application/json',
            data=json.dumps(post_data)
        )
        json_string = response.content
        data = json.loads(json_string)
        self.assertEqual(data['status'], 'success')

        # get show_shared_buildings
        url = reverse_lazy("accounts:get_shared_buildings")
        response = self.client.get(url)
        json_string = response.content
        data = json.loads(json_string)
        self.assertEqual(data['show_shared_buildings'], False)

    def test_get_columns(self):
        url = reverse_lazy("seed:get_columns")
        response = self.client.get(url)
        json_string = response.content
        data = json.loads(json_string)
        self.assertEqual(data['fields'], ASSESSOR_FIELDS)

    def tearDown(self):
        self.user.delete()


class SearchViewTests(TestCase):
    """
    Tests of the SEED search_buildings
    """

    def setUp(self):
        user_details = {
            'username': 'test_user',
            'password': 'test_pass',
            'email': 'test_user@demo.com'
        }
        self.user = User.objects.create_superuser(**user_details)
        self.org = Organization.objects.create()
        OrganizationUser.objects.create(user=self.user, organization=self.org)
        self.client.login(**user_details)

    def test_seach_active_canonicalbuildings(self):
        """ tests the search_buidlings method used throughout the app for only
            returning active CanonicalBuilding BuildingSnapshot insts.
        """
        # arrange
        NUMBER_ACTIVE = 50
        NUMBER_INACTIVE = 25
        NUMBER_WITHOUT_CANONICAL = 5
        NUMBER_PER_PAGE = 10
        for i in range(NUMBER_ACTIVE):
            cb = CanonicalBuilding(active=True)
            cb.save()
            b = SEEDFactory.building_snapshot(canonical_building=cb)
            cb.canonical_snapshot = b
            cb.save()
            b.super_organization = self.org
            b.save()
        for i in range(NUMBER_INACTIVE):
            cb = CanonicalBuilding(active=False)
            cb.save()
            b = SEEDFactory.building_snapshot(canonical_building=cb)
            cb.canonical_snapshot = b
            cb.save()
            b.super_organization = self.org
            b.save()
        for i in range(NUMBER_WITHOUT_CANONICAL):
            b = SEEDFactory.building_snapshot()
            b.super_organization = self.org
            b.save()
        url = reverse_lazy("seed:search_buildings")
        post_data = {
            'filter_params': {},
            'number_per_page': NUMBER_PER_PAGE,
            'order_by': '',
            'page': 1,
            'q': '',
            'sort_reverse': False,
            'project_id': None,
        }

        # act
        response = self.client.post(
            url,
            content_type='application/json',
            data=json.dumps(post_data)
        )
        json_string = response.content
        data = json.loads(json_string)

        # assert
        self.assertEqual(
            BuildingSnapshot.objects.all().count(),
            NUMBER_ACTIVE + NUMBER_INACTIVE + NUMBER_WITHOUT_CANONICAL
        )
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['number_matching_search'], NUMBER_ACTIVE)
        self.assertEqual(data['number_returned'], NUMBER_PER_PAGE)
        self.assertEqual(len(data['buildings']), NUMBER_PER_PAGE)


class BuildingDetailViewTests(TestCase):
    """
    Tests of the SEED Building Detail page
    """

    def setUp(self):
        user_details = {
            'username': 'test_user',
            'password': 'test_pass',
            'email': 'test_user@demo.com'
        }
        self.user = User.objects.create_superuser(**user_details)
        self.org = Organization.objects.create()
        OrganizationUser.objects.create(user=self.user, organization=self.org)
        self.client.login(**user_details)

        import_record = ImportRecord.objects.create()
        import_file_1 = ImportFile.objects.create(
            import_record=import_record,
        )
        import_file_1.save()
        import_file_2 = ImportFile.objects.create(
            import_record=import_record,
        )
        import_file_2.save()
        cb = CanonicalBuilding(active=True)
        cb.save()
        parent_1 = SEEDFactory.building_snapshot(
            canonical_building=cb,
            gross_floor_area=None
        )
        cb.canonical_snapshot = parent_1
        cb.save()
        parent_1.super_organization = self.org
        parent_1.import_file = import_file_1
        parent_1.source_type = 2
        parent_1.save()

        cb = CanonicalBuilding(active=True)
        cb.save()
        parent_2 = SEEDFactory.building_snapshot(canonical_building=cb)
        cb.canonical_snapshot = parent_2
        cb.save()
        parent_2.super_organization = self.org
        parent_2.import_file = import_file_2
        parent_2.source_type = 3
        parent_2.save()

        self.import_record = import_record
        self.import_file_1 = import_file_1
        self.import_file_2 = import_file_2
        self.parent_1 = parent_1
        self.parent_2 = parent_2

    def test_get_building(self):
        """ tests the get_building view which retuns building detail and source
            information from parent buildings.
        """
        # arrange
        child = save_snapshot_match(self.parent_1.pk, self.parent_2.pk)

        url = reverse_lazy("seed:get_building")
        get_data = {
            'building_id': child.pk,
            'organization_id': self.org.pk,
        }

        # act
        response = self.client.get(
            url,
            get_data,
            content_type='application/json',
        )
        json_string = response.content
        data = json.loads(json_string)

        # assert
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['imported_buildings']), 2)
        # both parents have the same child
        self.assertEqual(
            data['imported_buildings'][0]['children'][0],
            child.pk
        )
        self.assertEqual(
            data['imported_buildings'][1]['children'][0],
            child.pk
        )
        # both parents link to their import file
        self.assertEqual(
            data['imported_buildings'][0]['import_file'],
            self.import_file_1.pk
        )
        self.assertEqual(
            data['imported_buildings'][1]['import_file'],
            self.import_file_2.pk
        )
        # child should get the first address
        self.assertEqual(
            data['building']['address_line_1'],
            self.parent_1.address_line_1
        )
        self.assertEqual(
            data['building']['address_line_1_source'],
            self.parent_1.pk
        )
        # child should get second gross floor area since first is set to None
        self.assertEqual(
            data['building']['gross_floor_area_source'],
            self.parent_2.pk
        )

    def test_get_building_with_deleted_dataset(self):
        """ tests the get_building view where the dataset has been deleted and
            the building should load without showing the sources from deleted
            import files.
        """
        # arrange
        child = save_snapshot_match(self.parent_1.pk, self.parent_2.pk)

        url = reverse_lazy("seed:get_building")
        get_data = {
            'building_id': child.pk,
            'organization_id': self.org.pk,
        }

        # act
        self.import_record.delete()
        response = self.client.get(
            url,
            get_data,
            content_type='application/json',
        )
        json_string = response.content
        data = json.loads(json_string)

        # assert
        self.assertEqual(data['status'], 'success')
        # empty list of parents
        self.assertEqual(len(data['imported_buildings']), 0)
        # building should still have all its info
        self.assertEqual(
            data['building']['address_line_1'],
            self.parent_1.address_line_1
        )
        self.assertEqual(
            data['building']['address_line_1_source'],
            self.parent_1.pk
        )
        self.assertEqual(
            data['building']['gross_floor_area_source'],
            self.parent_2.pk
        )
        self.assertAlmostEqual(
            data['building']['gross_floor_area'],
            self.parent_2.gross_floor_area,
            places=1,
        )


class TestMCMViews(TestCase):
    suggested_expected = {
        u'status': 'success',
        u'suggested_column_mappings': {
            u'address': [u'owner_address', 70],
            u'building id': [u'building_count', 64],
            u'name': [u'property_name', 47],
            u'year built': [u'year_built', 50]
        },
        u'building_column_types': {
            u'address_line_1': u'',
            u'address_line_2': u'',
            u'block_number': u'',
            u'building_certification': u'',
            u'building_count': u'float',
            u'city': u'',
            u'conditioned_floor_area': u'float',
            u'custom_id_1': u'',
            u'district': u'',
            u'energy_alerts': u'',
            u'energy_score': u'float',
            u'generation_date': u'date',
            u'gross_floor_area': u'float',
            u'lot_number': u'',
            u'occupied_floor_area': u'float',
            u'owner': u'',
            u'owner_address': u'',
            u'owner_city_state': u'',
            u'owner_email': u'',
            u'owner_postal_code': u'',
            u'owner_telephone': u'',
            u'pm_property_id': u'',
            u'postal_code': u'',
            u'property_name': u'',
            u'property_notes': u'',
            u'recent_sale_date': u'date',
            u'release_date': u'date',
            u'site_eui': u'float',
            u'site_eui_weather_normalized': u'float',
            u'source_eui': u'float',
            u'source_eui_weather_normalized': u'float',
            u'space_alerts': u'',
            u'state_province': u'',
            u'tax_lot_id': u'',
            u'use_description': u'',
            u'year_built': u'float',
            u'year_ending': u'date'},
        u'building_columns': [
            u'lot_number',
            u'owner_address',
            u'owner_postal_code',
            u'block_number',
            u'source_eui_weather_normalized',
            u'owner_email',
            u'year_ending',
            u'building_count',
            u'postal_code',
            u'owner',
            u'property_name',
            u'source_eui',
            u'custom_id_1',
            u'city',
            u'property_notes',
            u'district',
            u'conditioned_floor_area',
            u'occupied_floor_area',
            u'generation_date',
            u'energy_alerts',
            u'space_alerts',
            u'pm_property_id',
            u'use_description',
            u'site_eui',
            u'site_eui_weather_normalized',
            u'building_certification',
            u'energy_score',
            u'state_province',
            u'year_built',
            u'release_date',
            u'gross_floor_area',
            u'owner_city_state',
            u'owner_telephone',
            u'recent_sale_date',
            u'tax_lot_id',
            u'address_line_2',
            u'address_line_1'
        ],
    }

    raw_columns_expected = {
        u'status': u'success',
        u'raw_columns': [u'name', u'address', u'year built', u'building id']
    }

    def setUp(self):
        self.maxDiff = None
        self.org = Organization.objects.create()
        user_details = {
            'username': 'test_user',
            'password': 'test_pass',
            'email': 'test_user@demo.com',
        }
        self.user = User.objects.create_superuser(**user_details)
        OrganizationUser.objects.create(user=self.user, organization=self.org)
        self.client.login(**user_details)
        self.import_record = ImportRecord.objects.create(
            owner=self.user
        )
        self.import_record.super_organization = self.org
        self.import_record.save()
        self.import_file = ImportFile.objects.create(
            import_record=self.import_record,
            cached_first_row=ROW_DELIMITER.join(
                [u'name', u'address', u'year built', u'building id']
            )
        )

    def test_get_column_mapping_suggestions(self):
        """Good case for ``get_column_mapping_suggestions``."""
        resp = self.client.post(
            reverse_lazy("seed:get_column_mapping_suggestions"),
            data=json.dumps({
                'import_file_id': self.import_file.id,
            }),
            content_type='application/json'
        )
        body = json.loads(resp.content)

        self.assertDictEqual(body, self.suggested_expected)

    def test_get_raw_column_names(self):
        """Good case for ``get_raw_column_names``."""
        resp = self.client.post(
            reverse_lazy("seed:get_raw_column_names"),
            data=json.dumps({
                'import_file_id': self.import_file.id,
            }),
            content_type='application/json'
        )

        body = json.loads(resp.content)

        self.assertDictEqual(body, self.raw_columns_expected)

    def test_save_column_mappings(self):
        """Same endpoint."""
        self.assertEqual(
            ColumnMapping.objects.filter(super_organization=self.org).count(),
            0
        )
        resp = self.client.post(
            reverse_lazy("seed:save_column_mappings"),
            data=json.dumps({
                'import_file_id': self.import_file.id,
                'mappings': [
                    ["name", "name"],
                ]
            }),
            content_type='application/json',
        )

        self.assertDictEqual(json.loads(resp.content), {'status': 'success'})

        test_mappings = ColumnMapping.objects.filter(
            super_organization=self.org
        )
        self.assertEquals(test_mappings[0].source_type, 0)

    def test_save_column_mappings_w_concat(self):
        """Concat payloads come back as lists."""
        resp = self.client.post(
            reverse_lazy("seed:save_column_mappings"),
            data=json.dumps({
                'import_file_id': self.import_file.id,
                'mappings': [
                    ["name", ["name", "other_name"]],
                ]
            }),
            content_type='application/json',
        )

        self.assertDictEqual(json.loads(resp.content), {'status': 'success'})

        test_mappings = ColumnMapping.objects.filter(
            super_organization=self.org
        )
        self.assertTrue(test_mappings.exists())
        self.assertEquals(
            json.loads(test_mappings[0].column_raw),
            ['name', 'other_name']
        )

    def test_save_column_mappings_idempotent(self):
        """We need to make successive calls to save_column_mappings."""
        # Save the first mapping, just like before
        self.assertEqual(
            ColumnMapping.objects.filter(super_organization=self.org).count(),
            0
        )
        resp = self.client.post(
            reverse_lazy("seed:save_column_mappings"),
            data=json.dumps({
                'import_file_id': self.import_file.id,
                'mappings': [
                    ["name", "name"],
                ]
            }),
            content_type='application/json',
        )
        self.assertDictEqual(json.loads(resp.content), {'status': 'success'})
        self.assertEqual(
            ColumnMapping.objects.filter(super_organization=self.org).count(),
            1
        )

        # the second user in the org makes the same save, which shouldn't be
        # unique
        user_2_details = {
            'username': 'test_2_user',
            'password': 'test_pass',
            'email': 'test_2_user@demo.com',
        }
        user_2 = User.objects.create_superuser(**user_2_details)
        OrganizationUser.objects.create(
            user=user_2, organization=self.org
        )
        self.client.login(**user_2_details)

        self.client.post(
            reverse_lazy("seed:save_column_mappings"),
            data=json.dumps({
                'import_file_id': self.import_file.id,
                'mappings': [
                    ["name", "name"],
                ]
            }),
            content_type='application/json',
        )

        # Sure enough, we haven't created a new ColumnMapping
        self.assertDictEqual(json.loads(resp.content), {'status': 'success'})
        self.assertEqual(
            ColumnMapping.objects.filter(super_organization=self.org).count(),
            1
        )

    def test_progress(self):
        """Make sure we retrieve data from cache properly."""
        progress_key = decorators.get_prog_key('fun_func', 23)
        expected = 50.0
        cache.set(progress_key, expected)
        resp = self.client.post(
            reverse_lazy("seed:progress"),
            data=json.dumps({
                'progress_key': progress_key,
            }),
            content_type='application/json'
        )

        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertEqual(body.get('progress', 0), expected)
        self.assertEqual(body.get('progress_key', ''), progress_key)

    def test_remap_buildings(self):
        """Test good case for resetting mapping."""
        # Make raw BSes, these should stick around.
        for x in range(10):
            test_util.make_fake_snapshot(self.import_file, {}, ASSESSED_RAW)

        # Make "mapped" BSes, these should get removed.
        for x in range(10):
            test_util.make_fake_snapshot(self.import_file, {}, ASSESSED_BS)

        # Set import file like we're done mapping
        self.import_file.mapping_done = True
        self.import_file.mapping_progress = 100
        self.import_file.save()

        # Set cache like we're done mapping.
        cache_key = decorators.get_prog_key('map_data', self.import_file.pk)
        cache.set(cache_key, 100)

        resp = self.client.post(
            reverse_lazy("seed:remap_buildings"),
            data=json.dumps({
                'file_id': self.import_file.pk,
            }),
            content_type='application/json'
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            BuildingSnapshot.objects.filter(
                import_file=self.import_file,
                source_type__in=(ASSESSED_BS, PORTFOLIO_BS)
            ).count(),
            0
        )

        self.assertEqual(
            BuildingSnapshot.objects.filter(
                import_file=self.import_file,
            ).count(),
            10
        )

        self.assertEqual(cache.get(cache_key), 0)

    def test_reset_mapped_w_previous_matches(self):
        """Ensure we ignore mapped buildings with children BSes."""
        # Make the raw BSes for us to make new mappings from
        for x in range(10):
            test_util.make_fake_snapshot(self.import_file, {}, ASSESSED_RAW)
        # Simulate existing mapped BSes, which should be deleted.
        for x in range(10):
            test_util.make_fake_snapshot(self.import_file, {}, ASSESSED_BS)

        # Setup our exceptional case: here the first BS has a child, COMPOSITE.
        child = test_util.make_fake_snapshot(None, {}, COMPOSITE_BS)
        first = BuildingSnapshot.objects.filter(
            import_file=self.import_file
        )[:1].get()

        # We add a child to our first BuildingSnapshot, which should exclude it
        # from deletion and thus it should remain after a remapping is issued.
        first.children.add(child)

        # Here we mark all of the mapped building snapshots. These should all
        # get deleted when we remap from the raw snapshots after the call to
        # to this function.
        for item in BuildingSnapshot.objects.filter(source_type=ASSESSED_BS):
            item.property_name = 'Touched'
            item.save()

        # Ensure we have all 10 mapped BuildingSnapshots saved.
        self.assertEqual(
            BuildingSnapshot.objects.filter(property_name='Touched').count(),
            10
        )

        self.client.post(
            reverse_lazy("seed:remap_buildings"),
            data=json.dumps({
                'file_id': self.import_file.pk,
            }),
            content_type='application/json'
        )

        # Assert that only one remains that was touched, and that it has the
        # child.
        self.assertEqual(
            BuildingSnapshot.objects.filter(property_name='Touched').count(),
            1
        )
        self.assertEqual(
            BuildingSnapshot.objects.get(
                property_name='Touched'
            ).children.all()[0],
            child
        )

    def test_reset_mapped_w_matching_done(self):
        """Make sure we don't delete buildings that have been merged."""
        self.import_file.matching_done = True
        self.import_file.matching_progress = 100
        self.import_file.save()

        for x in range(10):
            test_util.make_fake_snapshot(self.import_file, {}, ASSESSED_BS)

        expected = {
            'status': 'warning',
            'message': 'Mapped buildings already merged'
        }

        resp = self.client.post(
            reverse_lazy("seed:remap_buildings"),
            data=json.dumps({
                'file_id': self.import_file.pk,
            }),
            content_type='application/json'
        )

        self.assertDictEqual(json.loads(resp.content), expected)

        # Verify that we haven't deleted those mapped buildings.
        self.assertEqual(
            BuildingSnapshot.objects.filter(
                import_file=self.import_file
            ).count(),
            10
        )

    def test_create_dataset(self):
        """tests the create_dataset view, allows duplicate dataset names"""
        DATASET_NAME_1 = 'test_name 1'
        DATASET_NAME_2 = 'city compliance dataset 2014'
        resp = self.client.post(
            reverse_lazy("seed:create_dataset"),
            data=json.dumps({
                'organization_id': self.org.pk,
                'name': DATASET_NAME_1,
            }),
            content_type='application/json',
        )
        data = json.loads(resp.content)
        self.assertEqual(data['name'], DATASET_NAME_1)

        resp = self.client.post(
            reverse_lazy("seed:create_dataset"),
            data=json.dumps({
                'organization_id': self.org.pk,
                'name': DATASET_NAME_2,
            }),
            content_type='application/json',
        )
        data = json.loads(resp.content)

        self.assertEqual(data['name'], DATASET_NAME_2)
        the_id = data['id']

        # ensure future API changes to create_dataset are tested
        self.assertDictEqual(data, {
            'id': the_id,
            'name': DATASET_NAME_2,
            'status': 'success',
        })

        # test duplicate name
        resp = self.client.post(
            reverse_lazy("seed:create_dataset"),
            data=json.dumps({
                'organization_id': self.org.pk,
                'name': DATASET_NAME_1,
            }),
            content_type='application/json',
        )
        data_3 = json.loads(resp.content)
        import_record = ImportRecord.objects.get(pk=data_3['id'])

        # test data set was created properly
        self.assertEqual(data_3['status'], 'success')
        self.assertEqual(data_3['name'], DATASET_NAME_1)
        self.assertNotEqual(data_3['id'], data['id'])
        self.assertEqual(import_record.owner, self.user)
        self.assertEqual(import_record.last_modified_by, self.user)
        self.assertEqual(import_record.app, 'seed')
        self.assertEqual(import_record.name, DATASET_NAME_1)
        self.assertEqual(self.org, import_record.super_organization)
