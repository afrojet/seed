"""
:copyright: (c) 2014 Building Energy Inc
:license: see LICENSE for more details.
"""
from dateutil import parser
from os import path

from mock import patch

from django.test import TestCase
from django.core.files import File

from data_importer.models import ImportFile, ImportRecord
from landing.models import SEEDUser as User
from superperms.orgs.models import Organization, OrganizationUser
from seed.models import (
    ASSESSED_RAW,
    PORTFOLIO_RAW,
    ASSESSED_BS,
    PORTFOLIO_BS,
    POSSIBLE_MATCH,
    SYSTEM_MATCH,
    BuildingSnapshot,
    CanonicalBuilding,
    ColumnMapping,
    get_ancestors,
)
from seed import tasks
from seed.tests import util


class TestTasks(TestCase):
    """Tests for dealing with SEED related tasks."""

    def setUp(self):
        self.fake_user = User.objects.create(username='test')
        self.import_record = ImportRecord.objects.create(
            owner=self.fake_user,
        )
        self.import_file = ImportFile.objects.create(
            import_record=self.import_record
        )
        self.import_file.is_espm = True
        self.import_file.source_type = 'PORTFOLIO_RAW'
        self.import_file.file = File(
            open(
                 path.join(
                     path.dirname(__file__),
                     'data',
                     'portfolio-manager-sample.csv'
                 )
            )
        )
        self.import_file.save()

        # Mimic the representation in the PM file. #ThanksAaron
        self.fake_extra_data = {
                u'City': u'EnergyTown',
                u'ENERGY STAR Score': u'',
                u'State/Province': u'Ilinois',
                u'Site EUI (kBtu/ft2)': u'',
                u'Year Ending': u'',
                u'Weather Normalized Source EUI (kBtu/ft2)': u'',
                u'Parking - Gross Floor Area (ft2)': u'',
                u'Address 1': u'000015581 SW Sycamore Court',
                u'Property Id': u'101125',
                u'Address 2': u'Not Available',
                u'Source EUI (kBtu/ft2)': u'',
                u'Release Date': u'',
                u'National Median Source EUI (kBtu/ft2)': u'',
                u'Weather Normalized Site EUI (kBtu/ft2)': u'',
                u'National Median Site EUI (kBtu/ft2)': u'',
                u'Year Built': u'',
                u'Postal Code': u'10108-9812',
                u'Organization': u'Occidental Management',
                u'Property Name': u'Not Available',
                u'Property Floor Area (Buildings and Parking) (ft2)': u'',
                u'Total GHG Emissions (MtCO2e)': u'', u'Generation Date': u'',
                u'Generation Date': u''
        }
        self.fake_row = {
            u'Name': u'The Whitehouse',
            u'Address Line 1': u'1600 Pennsylvania Ave.',
            u'Year Built': u'1803',
        }

        self.fake_org = Organization.objects.create()
        OrganizationUser.objects.create(
            user=self.fake_user, organization=self.fake_org
        )

        self.import_record.super_organization = self.fake_org
        self.import_record.save()

        self.fake_mappings = {
            'property_name': u'Name',
            'address_line_1': u'Address Line 1',
            'year_built': u'Year Built'
        }

    def test_save_raw_data(self):
        """Save information in extra_data, set other attrs."""
        with patch.object(
            ImportFile, 'cache_first_rows', return_value=None
        ) as mock_method:
            tasks._save_raw_data(
                self.import_file.pk,
                'fake_cache_key',
                1
            )

        raw_saved = BuildingSnapshot.objects.filter(
            import_file=self.import_file,
            source_type=PORTFOLIO_RAW
        )

        raw_bldg = raw_saved[0]

        self.assertDictEqual(raw_bldg.extra_data, self.fake_extra_data)
        self.assertEqual(raw_bldg.source_type, PORTFOLIO_RAW)
        self.assertEqual(raw_bldg.super_organization, self.fake_org)

        expected_pk = raw_bldg.pk

        for k in self.fake_extra_data:
            self.assertEqual(
                raw_bldg.extra_data_sources.get(k),
                expected_pk,
                "%s didn't match the expected source pk.  %s vs %s" %
                    (k, expected_pk, raw_bldg.extra_data_sources.get(k))
            )

    def test_map_data(self):
        """Save mappings for assessor data based on user specifications."""
        fake_import_file = ImportFile.objects.create(
            import_record=self.import_record,
            raw_save_done=True
        )
        fake_raw_bs = BuildingSnapshot.objects.create(
            import_file=fake_import_file,
            source_type=ASSESSED_RAW,
            extra_data=self.fake_row
        )

        util.make_fake_mappings(self.fake_mappings, self.fake_org)

        tasks.map_data(fake_import_file.pk)

        mapped_bs = list(BuildingSnapshot.objects.filter(
            import_file=fake_import_file,
            source_type=ASSESSED_BS,
        ))

        self.assertEqual(len(mapped_bs), 1)

        test_bs = mapped_bs[0]

        self.assertNotEqual(test_bs.pk, fake_raw_bs.pk)
        self.assertEqual(test_bs.property_name, self.fake_row['Name'])
        self.assertEqual(
            test_bs.address_line_1, self.fake_row['Address Line 1']
        )
        self.assertEqual(
            test_bs.year_built,
            parser.parse(self.fake_row['Year Built']).year
        )


    def test_mapping_w_concat(self):
        """When we have a json encoded list as a column mapping, we concat."""
        fake_import_file = ImportFile.objects.create(
            import_record=self.import_record,
            raw_save_done=True
        )
        self.fake_row['City'] = 'Someplace Nice'
        fake_raw_bs = BuildingSnapshot.objects.create(
            import_file=fake_import_file,
            source_type=ASSESSED_RAW,
            extra_data=self.fake_row
        )

        self.fake_mappings['address_line_1'] = '["Address Line 1", "City"]'
        util.make_fake_mappings(self.fake_mappings, self.fake_org)

        tasks.map_data(fake_import_file.pk)

        mapped_bs = list(BuildingSnapshot.objects.filter(
            import_file=fake_import_file,
            source_type=ASSESSED_BS,
        ))[0]

        self.assertEqual(
            mapped_bs.address_line_1, u'1600 Pennsylvania Ave. Someplace Nice'
        )

    def test_match_buildings(self):
        """Good case for testing our matching system."""
        bs_data = {
           'pm_property_id': 1243,
           'tax_lot_id': '435/422',
           'property_name': 'Greenfield Complex',
           'custom_id_1': 1243,
           'address_line_1': '555 Database LN.',
           'address_line_2': '',
           'city': 'Gotham City',
           'postal_code': 8999,
        }

        # Setup mapped AS snapshot.
        snapshot = util.make_fake_snapshot(
            self.import_file, bs_data, ASSESSED_BS, is_canon=True
        )
        # Different file, but same ImportRecord.
        # Setup mapped PM snapshot.
        # Should be an identical match.
        new_import_file = ImportFile.objects.create(
            import_record=self.import_record,
            mapping_done=True
        )

        new_snapshot = util.make_fake_snapshot(
            new_import_file, bs_data, PORTFOLIO_BS
        )

        tasks.match_buildings(new_import_file.pk)

        result = BuildingSnapshot.objects.all()[0]

        self.assertEqual(result.property_name, snapshot.property_name)
        self.assertEqual(result.property_name, new_snapshot.property_name)
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(
            sorted([r.pk for r in result.parents.all()]),
            sorted([new_snapshot.pk, snapshot.pk])
        )

    def test_match_no_matches(self):
        """When a canonical exists, but doesn't match, we create a new one."""
        bs1_data = {
           'pm_property_id': 1243,
           'tax_lot_id': '435/422',
           'property_name': 'Greenfield Complex',
           'custom_id_1': 1243,
           'address_line_1': '555 Database LN.',
           'address_line_2': '',
           'city': 'Gotham City',
           'postal_code': 8999,
        }

        bs2_data = {
           'pm_property_id': 9999,
           'tax_lot_id': '1231',
           'property_name': 'A Place',
           'custom_id_1': 0000111000,
           'address_line_1': '44444 Hmmm Ave.',
           'address_line_2': 'Apt 4',
           'city': 'Gotham City',
           'postal_code': 8999,
        }

        snapshot = util.make_fake_snapshot(
            self.import_file, bs1_data, ASSESSED_BS, is_canon=True
        )
        new_import_file = ImportFile.objects.create(
            import_record=self.import_record,
            mapping_done=True
        )
        new_snapshot = util.make_fake_snapshot(
            new_import_file, bs2_data, PORTFOLIO_BS
        )

        self.assertEqual(BuildingSnapshot.objects.all().count(), 2)

        tasks.match_buildings(new_import_file.pk)

        # E.g. we didn't create a match
        self.assertEqual(BuildingSnapshot.objects.all().count(), 2)
        latest_snapshot = BuildingSnapshot.objects.get(pk=new_snapshot.pk)

        # But we did create another canonical building for the unmatched bs.
        self.assertNotEqual(latest_snapshot.canonical_building, None)
        self.assertNotEqual(
            latest_snapshot.canonical_building.pk,
            snapshot.canonical_building.pk
        )

        self.assertEqual(latest_snapshot.confidence, None)

    def test_match_no_canonical_buildings(self):
        """If no canonicals exist, create, but no new BSes."""
        bs1_data = {
           'pm_property_id': 1243,
           'tax_lot_id': '435/422',
           'property_name': 'Greenfield Complex',
           'custom_id_1': 1243,
           'address_line_1': '555 Database LN.',
           'address_line_2': '',
           'city': 'Gotham City',
           'postal_code': 8999,
        }

        # Note: no Canonical Building is created for this snapshot.
        snapshot = util.make_fake_snapshot(
            self.import_file, bs1_data, ASSESSED_BS, is_canon=False
        )

        self.import_file.mapping_done = True
        self.import_file.save()

        self.assertEqual(snapshot.canonical_building, None)
        self.assertEqual(BuildingSnapshot.objects.all().count(), 1)

        tasks.match_buildings(self.import_file.pk)

        refreshed_snapshot = BuildingSnapshot.objects.get(pk=snapshot.pk)
        self.assertNotEqual(refreshed_snapshot.canonical_building, None)
        self.assertEqual(BuildingSnapshot.objects.all().count(), 1)

    def test_no_unmatched_buildings(self):
        """Make sure we shortcut out if there isn't unmatched data."""
        bs1_data = {
           'pm_property_id': 1243,
           'tax_lot_id': '435/422',
           'property_name': 'Greenfield Complex',
           'custom_id_1': 1243,
           'address_line_1': '555 Database LN.',
           'address_line_2': '',
           'city': 'Gotham City',
           'postal_code': 8999,
        }

        self.import_file.mapping_done = True
        self.import_file.save()
        util.make_fake_snapshot(
            self.import_file, bs1_data, ASSESSED_BS, is_canon=True
        )

        self.assertEqual(BuildingSnapshot.objects.all().count(), 1)

        tasks.match_buildings(self.import_file.pk)

        self.assertEqual(BuildingSnapshot.objects.all().count(), 1)

    def test_separates_system_and_possible_match_types(self):
        """We save possible matches separately."""
        bs1_data = {
           'pm_property_id': 123,
           'tax_lot_id': '435/422',
           'property_name': 'Greenfield Complex',
           'custom_id_1': 1243,
           'address_line_1': '555 NorthWest Databaseer Lane.',
           'address_line_2': '',
           'city': 'Gotham City',
           'postal_code': 8999,
        }
        # This building will have a lot less data to identify it.
        bs2_data = {
           'pm_property_id': 1243,
           'custom_id_1': 1243,
           'address_line_1': '555 Database LN.',
           'city': 'Gotham City',
           'postal_code': 8999,
        }
        new_import_file = ImportFile.objects.create(
            import_record=self.import_record,
            mapping_done=True
        )

        util.make_fake_snapshot(
            self.import_file, bs1_data, ASSESSED_BS, is_canon=True
        )

        util.make_fake_snapshot(new_import_file, bs2_data, PORTFOLIO_BS)

        tasks.match_buildings(new_import_file.pk)

        self.assertEqual(
            BuildingSnapshot.objects.filter(match_type=POSSIBLE_MATCH).count(),
            1
        )
        self.assertEqual(
            BuildingSnapshot.objects.filter(match_type=SYSTEM_MATCH).count(),
            0
        )

    def test_get_ancestors(self):
        """Tests get_ancestors(building), returns all non-composite, non-raw
            BuildingSnapshot instances.
        """
        bs_data = {
           'pm_property_id': 1243,
           'tax_lot_id': '435/422',
           'property_name': 'Greenfield Complex',
           'custom_id_1': 1243,
           'address_line_1': '555 Database LN.',
           'address_line_2': '',
           'city': 'Gotham City',
           'postal_code': 8999,
        }

        # Setup mapped AS snapshot.
        snapshot = util.make_fake_snapshot(
            self.import_file, bs_data, ASSESSED_BS, is_canon=True
        )
        # Different file, but same ImportRecord.
        # Setup mapped PM snapshot.
        # Should be an identical match.
        new_import_file = ImportFile.objects.create(
            import_record=self.import_record,
            raw_save_done=True,
            mapping_done=True
        )

        new_snapshot = util.make_fake_snapshot(
            new_import_file, bs_data, PORTFOLIO_BS
        )

        tasks.match_buildings(new_import_file.pk)

        result = BuildingSnapshot.objects.filter(source_type=4)[0]
        ancestor_pks = set([b.pk for b in get_ancestors(result)])
        buildings = BuildingSnapshot.objects.filter(
            source_type__in=[2, 3]
        ).exclude(
            pk=result.pk
        )
        building_pks = set([b.pk for b in buildings])

        self.assertEqual(ancestor_pks, building_pks)

    def test_save_raw_data_batch_iterator(self):
        """Ensure split_csv completes"""
        tasks.save_raw_data(self.import_file.pk)

        self.assertEqual(BuildingSnapshot.objects.filter(
            import_file=self.import_file
        ).count(), 512)

    def test_delete_organization_buildings(self):
        """tests the delete builings for an org"""
        # start with the normal use case
        bs1_data = {
            'pm_property_id': 123,
            'tax_lot_id': '435/422',
            'property_name': 'Greenfield Complex',
            'custom_id_1': 1243,
            'address_line_1': '555 NorthWest Databaseer Lane.',
            'address_line_2': '',
            'city': 'Gotham City',
            'postal_code': 8999,
        }
        # This building will have a lot less data to identify it.
        bs2_data = {
            'pm_property_id': 1243,
            'custom_id_1': 1243,
            'address_line_1': '555 Database LN.',
            'city': 'Gotham City',
            'postal_code': 8999,
        }
        new_import_file = ImportFile.objects.create(
            import_record=self.import_record,
            mapping_done=True
        )

        snapshot = util.make_fake_snapshot(
            self.import_file, bs1_data, ASSESSED_BS, is_canon=True
        )

        snapshot.super_organization = self.fake_org
        snapshot.save()

        snapshot = util.make_fake_snapshot(
            new_import_file,
            bs2_data, PORTFOLIO_BS
        )
        snapshot.super_organization = self.fake_org
        snapshot.save()

        tasks.match_buildings(new_import_file.pk)

        # make one more building snapshot in a different org
        fake_org_2 = Organization.objects.create()
        snapshot = util.make_fake_snapshot(
            self.import_file, bs1_data, ASSESSED_BS, is_canon=True
        )
        snapshot.super_organization = fake_org_2
        snapshot.save()

        self.assertGreater(BuildingSnapshot.objects.filter(
            super_organization=self.fake_org
        ).count(), 0)

        tasks.delete_organization_buildings(self.fake_org.pk)

        self.assertEqual(BuildingSnapshot.objects.filter(
            super_organization=self.fake_org
        ).count(), 0)

        self.assertGreater(BuildingSnapshot.objects.filter(
            super_organization=fake_org_2
        ).count(), 0)

        # test that the CanonicalBuildings are deleted
        self.assertEqual(CanonicalBuilding.objects.filter(
            canonical_snapshot__super_organization=self.fake_org
        ).count(), 0)
        # test that other orgs CanonicalBuildings are not deleted
        self.assertGreater(CanonicalBuilding.objects.filter(
            canonical_snapshot__super_organization=fake_org_2
        ).count(), 0)
