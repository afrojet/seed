"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
from datetime import datetime

from django.test import TestCase

from superperms.orgs.models import Organization, OrganizationUser

from data_importer.models import ImportFile, ImportRecord
from landing.models import SEEDUser as User
from seed import models as seed_models
from seed.mappings import mapper
from seed.tests import util


class TestBuildingSnapshot(TestCase):
    """Test the clean methods on BuildingSnapshotModel."""

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

    def setUp(self):
        self.fake_user = User.objects.create(username='models_test')
        self.fake_org = Organization.objects.create()
        OrganizationUser.objects.create(
            user=self.fake_user, organization=self.fake_org
        )
        self.import_record = ImportRecord.objects.create(owner=self.fake_user)
        self.import_file1 = ImportFile.objects.create(
            import_record=self.import_record
        )
        self.import_file2 = ImportFile.objects.create(
            import_record=self.import_record
        )
        self.bs1 = util.make_fake_snapshot(
            self.import_file1,
            self.bs1_data,
            bs_type=seed_models.ASSESSED_BS,
            is_canon=True
        )
        self.bs2 = util.make_fake_snapshot(
            self.import_file2, self.bs2_data, bs_type=seed_models.PORTFOLIO_BS
        )

    def _add_additional_fake_buildings(self):
        """DRY up some test code below where many BSes are needed."""
        self.bs3 = util.make_fake_snapshot(
            self.import_file1, self.bs1_data, bs_type=seed_models.COMPOSITE_BS,
        )
        self.bs4 = util.make_fake_snapshot(
            self.import_file1, self.bs2_data, bs_type=seed_models.COMPOSITE_BS,
        )
        self.bs5 = util.make_fake_snapshot(
            self.import_file1, self.bs2_data, bs_type=seed_models.COMPOSITE_BS,
        )

    def _test_year_month_day_equal(self, test_dt, expected_dt):
        for attr in ['year', 'month', 'day']:
            self.assertEqual(getattr(test_dt, attr), getattr(expected_dt, attr))

    def test_clean(self):
        """Make sure we convert datestrings properly."""
        bs_model = seed_models.BuildingSnapshot()
        date_str = u'12/31/2013'

        bs_model.year_ending = date_str
        bs_model.release_date = date_str
        bs_model.generation_date = date_str

        expected_value = datetime(
            year=2013, month=12, day=31
        )

        bs_model.clean()

        self._test_year_month_day_equal(bs_model.year_ending, expected_value)
        self._test_year_month_day_equal(bs_model.release_date, expected_value)
        self._test_year_month_day_equal(bs_model.generation_date, expected_value)


    def test_source_attributions(self):
        """Test that we can point back to an attribute's source.

        This is explicitly just testing the low-level data model, none of
        the convenience functions.

        """
        bs1 = seed_models.BuildingSnapshot()
        bs1.year_ending = datetime.utcnow()
        bs1.year_ending_source = bs1
        bs1.property_name = 'Test 1234'
        bs1.property_name_source = bs1
        bs1.save()

        bs2 = seed_models.BuildingSnapshot()
        bs2.property_name = 'Not Test 1234'
        bs2.property_name_source = bs2
        bs2.year_ending = bs1.year_ending
        bs2.year_ending_source = bs1
        bs2.save()

        self.assertEqual(bs2.year_ending_source, bs1)
        self.assertEqual(bs2.property_name_source, bs2) # We don't inherit.


    def test_create_child(self):
        """Test that we can create a child BS, it has a reference to its parent."""

        bs1 = seed_models.BuildingSnapshot.objects.create()
        bs2 = seed_models.BuildingSnapshot.objects.create()

        bs1.children.add(bs2)

        self.assertEqual(bs1.children.all()[0], bs2)
        self.assertEqual(bs2.parents.all()[0], bs1)
        self.assertEqual(list(bs1.parents.all()), [])
        self.assertEqual(list(bs2.children.all()), [])

    def test_remove_child(self):
        """Test behavior for removing a child."""
        bs1 = seed_models.BuildingSnapshot.objects.create()
        bs2 = seed_models.BuildingSnapshot.objects.create()

        bs1.children.add(bs2)

        self.assertEqual(bs1.children.all()[0], bs2)

        bs1.children.remove(bs2)

        self.assertEqual(list(bs1.children.all()), [])
        self.assertEqual(list(bs2.parents.all()), [])

    def test_get_column_mapping(self):
        """Honor organizational bounds, get mapping data."""
        raw_column = u'Some Weird City ID'
        mapped_column = u'custom_id_1'
        org1 = Organization.objects.create()
        org2 = Organization.objects.create()

        column_mapping1 = seed_models.ColumnMapping.objects.create(
            super_organization=org2,
            source_type=seed_models.ASSESSED_RAW,
            column_raw=raw_column,
            column_mapped=mapped_column
        )

        # Test that it Doesn't give us a mapping from another org.
        self.assertEqual(
            seed_models.get_column_mapping(raw_column, org1),
            None
        )

        # Correct org, but incorrect destination column.
        self.assertEqual(
            seed_models.get_column_mapping('random', org2),
            None
        )

        # Fully correct example
        self.assertEqual(
            seed_models.get_column_mapping(raw_column, org2),
            (u'custom_id_1', 1.0)
        )

    def test_get_column_mappings(self):
        """We produce appropriate data structure for mapping"""
        expected = dict(sorted([
            (u'example_9', u'mapped_9'),
            (u'example_8', u'mapped_8'),
            (u'example_7', u'mapped_7'),
            (u'example_6', u'mapped_6'),
            (u'example_5', u'mapped_5'),
            (u'example_4', u'mapped_4'),
            (u'example_3', u'mapped_3'),
            (u'example_2', u'mapped_2'),
            (u'example_1', u'mapped_1'),
            (u'example_0', u'mapped_0')
        ]))
        org = Organization.objects.create()
        for x in range(10):
            seed_models.ColumnMapping.objects.create(
                super_organization=org,
                source_type=seed_models.ASSESSED_RAW,
                column_raw='example_{0}'.format(x),
                column_mapped='mapped_{0}'.format(x)
            )
        test_mapping = seed_models.get_column_mappings(org)

        self.assertDictEqual(test_mapping, expected)

    def test_save_snapshot_match(self):
        """Test good case for saving a snapshot match."""
        self.assertEqual(seed_models.BuildingSnapshot.objects.all().count(), 2)
        bs2_canon = seed_models.CanonicalBuilding.objects.create(
            canonical_snapshot=self.bs2
        )

        self.bs2.canonical_building = bs2_canon
        self.bs2.save()

        seed_models.save_snapshot_match(
            self.bs1.pk, self.bs2.pk, confidence=0.9, user=self.fake_user
        )
        # We made an entirely new snapshot!
        self.assertEqual(seed_models.BuildingSnapshot.objects.all().count(), 3)
        result = seed_models.BuildingSnapshot.objects.all()[0]
        # Affirm that we give preference to the first BS passed
        # into our method.
        self.assertEqual(result.property_name, self.bs1.property_name)
        self.assertEqual(result.property_name_source, self.bs1)

        # Test that all the parent/child relationships are sorted.
        self.assertEqual(result.confidence, 0.9)
        self.assertEqual(
            sorted([r.pk for r in result.parents.all()]),
            sorted([self.bs1.pk, self.bs2.pk])
        )

        # Test that "duplicate" CanonicalBuilding is now marked inactive.
        refreshed_bs2 = seed_models.BuildingSnapshot.objects.get(
            pk=self.bs2.pk
        )
        refreshed_bs2_canon = refreshed_bs2.canonical_building
        self.assertFalse(refreshed_bs2_canon.active)

    def test_merge_extra_data_no_data(self):
        """Test edgecase where there is no extra_data to merge."""
        test_extra, test_sources = mapper.merge_extra_data(self.bs1, self.bs2)

        self.assertDictEqual(test_extra, {})
        self.assertDictEqual(test_sources, {})

    def test_merge_extra_data(self):
        """extra_data dicts get merged proper-like."""
        self.bs1.extra_data = {'test': 'dataface', 'test2': 'nuup'}
        self.bs1.save()

        self.bs2.extra_data = {'test': 'getting overridden', 'thing': 'hi'}
        self.bs2.save()

        expected_extra = {'test': 'dataface', 'test2': 'nuup', 'thing': 'hi'}
        expected_sources = {
            'test': self.bs1.pk, 'test2': self.bs1.pk, 'thing': self.bs2.pk
        }

        test_extra, test_sources = mapper.merge_extra_data(self.bs1, self.bs2)

        self.assertDictEqual(test_extra, expected_extra)
        self.assertDictEqual(test_sources, expected_sources)


    def test_update_building(self):
        """Good case for updating a building."""
        fake_building_extra = {
            u'Assessor Data 1': u'2342342',
            u'Assessor Data 2': u'245646',
        }
        fake_building_kwargs = {
            u'property_name': u'Place pl.',
            u'address_line_1': u'332 Place pl.',
            u'owner': u'Duke of Earl',
            u'postal_code': u'68674',
        }

        fake_building = util.make_fake_snapshot(
            self.import_file2,
            fake_building_kwargs,
            seed_models.COMPOSITE_BS,
            is_canon=True
        )

        fake_building.super_org = self.fake_org
        fake_building.extra_data = fake_building_extra
        fake_building.save()

        fake_building_kwargs[u'property_name_source'] = fake_building.pk
        fake_building_kwargs[u'address_line_1_source'] = fake_building.pk
        fake_building_kwargs[u'owner_source'] = fake_building.pk
        seed_models.set_initial_sources(fake_building)

        # Hydrated JS version will have this, we'll query off it.
        fake_building_kwargs[u'pk'] = fake_building.pk
        # "update" one of the field values.
        fake_building_kwargs[u'import_file'] = self.import_file1
        fake_building_kwargs[u'postal_code'] = u'99999'
        fake_building_extra[u'Assessor Data 1'] = u'NUP.'
        # Need to simulate JS hydrated payload here.
        fake_building_kwargs[u'extra_data'] = fake_building_extra

        new_snap = seed_models.update_building(
            fake_building, fake_building_kwargs, self.fake_user
        )

        # Make sure our value was updated.
        self.assertEqual(
            new_snap.postal_code, fake_building_kwargs[u'postal_code']
        )

        self.assertNotEqual(new_snap.pk, fake_building.pk)

        # Make sure that the extra data were saved, with orig sources.
        self.assertDictEqual(
            new_snap.extra_data, fake_building_extra
        )

        # Make sure we have the same orgs.
        self.assertEqual(
            new_snap.super_organization, fake_building.super_organization
        )

        self.assertEqual(new_snap.match_type, fake_building.match_type)
        # Make sure we're set as the source for updated info!!!
        self.assertEqual(new_snap, new_snap.postal_code_source)
        # Make sure our sources from parent get set properly.
        for attr in ['property_name', 'address_line_1', 'owner']:
            self.assertEqual(
                getattr(new_snap, '{0}_source'.format(attr)).pk,
                fake_building.pk
            )
        # Make sure our parent is set.
        self.assertEqual(new_snap.parents.all()[0].pk, fake_building.pk)

    def test_recurse_tree(self):
        """Make sure we get an accurate child tree."""
        self._add_additional_fake_buildings()
        can = self.bs1.canonical_building
        # Make our child relationships.
        self.bs1.children.add(self.bs3)
        self.bs3.children.add(self.bs4)
        self.bs4.children.add(self.bs5)

        can.canonical_snapshot = self.bs5
        can.save()

        child_expected = [self.bs3, self.bs4, self.bs5]
        # Here we're actually testing ``child_tree`` property
        self.assertEqual(self.bs1.child_tree, child_expected)

        # Leaf node condition.
        self.assertEqual(self.bs5.child_tree, [])

        # And here ``parent_tree`` property
        parent_expected = [self.bs1, self.bs3, self.bs4]
        self.assertEqual(self.bs5.parent_tree, parent_expected)

        # Root parent case
        self.assertEqual(self.bs1.parent_tree, [])

    def test_unmatch_snapshot_tree_single_ancestor(self):
        """Test experimental unmatch_snapshot_tree functionality."""
        self._add_additional_fake_buildings()
        can = self.bs1.canonical_building
        # Make our child relationships.
        self.bs1.children.add(self.bs3)
        self.bs3.children.add(self.bs5)
        # Bs4 will be our outlier
        self.bs4.children.add(self.bs5)
        self.bs5.canonical_building = can
        self.bs5.save()

        can.canonical_snapshot = self.bs5
        can.save()

        seed_models.unmatch_snapshot_tree(self.bs1.pk)

        refreshed_can = seed_models.CanonicalBuilding.objects.get(pk=can.pk)

        # Tests that if there's only one remainting ancestor, it just becomes
        # the canonical snapshot.
        self.assertEqual(refreshed_can.canonical_snapshot, self.bs4)

    def test_unmatch_snapshot_tree_several_ancestors(self):
        """Test the effects of unmatching several ancestors."""
        self._add_additional_fake_buildings()
        can = self.bs1.canonical_building

        self.bs1.children.add(self.bs2)
        self.bs2.children.add(self.bs5)
        # These two should remain  when self.bs1 is unmerged.
        # Note that these two are not direct parents for bs5.
        self.bs3.children.add(self.bs2)
        self.bs4.children.add(self.bs5)

        self.bs5.canonical_building = can
        self.bs5.save()

        can.canonical_snapshot = self.bs5
        can.save()

        seed_models.unmatch_snapshot_tree(self.bs1.pk)
        refreshed_can = seed_models.CanonicalBuilding.objects.get(pk=can.pk)

        expected_snapshot_parents = [self.bs3, self.bs4]
        # Make certain that the parents of the now canonical snapshot are
        # the "remaining ancestors" from our winnowing of ancesors.
        for parent in refreshed_can.canonical_snapshot.parents.all():
            self.assertTrue(parent in expected_snapshot_parents)

        refreshed_bs1 = seed_models.BuildingSnapshot.objects.get(
            pk=self.bs1.pk
        )
        refreshed_bs1_can = refreshed_bs1.canonical_building
        self.assertNotEqual(refreshed_bs1_can, refreshed_can)
        self.assertNotEqual(refreshed_bs1_can, None)
        self.assertEqual(refreshed_bs1_can.canonical_snapshot, refreshed_bs1)

        # Ensure that bs2 and bs5 were deleted.
        self.assertEqual(
            list(seed_models.BuildingSnapshot.objects.filter(
                pk__in=(self.bs2.pk, self.bs5.pk)
            )),
            []
        )

    def test_unmatch_snapshot_tree_inactive_canonical_building(self):
        """Make sure that old CanonicalBuildings get activated where needed."""
        self._add_additional_fake_buildings()
        can = self.bs1.canonical_building
        can.active = False
        can.save()

        new_can = seed_models.CanonicalBuilding.objects.create(
            canonical_snapshot = self.bs2
        )
        self.bs2.canonical_building = new_can
        self.bs2.save()

        self.bs1.children.add(self.bs2)
        self.bs3.children.add(self.bs2)

        seed_models.unmatch_snapshot_tree(self.bs1.pk)

        refreshed_can = seed_models.CanonicalBuilding.objects.get(pk=can.pk)
        refreshed_bs1 = seed_models.BuildingSnapshot.objects.get(pk=self.bs1.pk)

        # Our unmerged snapshot reactivates its canonical building
        self.assertEqual(refreshed_can.canonical_snapshot, self.bs1)
        self.assertEqual(refreshed_bs1.canonical_building, refreshed_can)

        # Newly remerged snapshot gets the original CanonicalBuilding
        refreshed_bs3 = seed_models.BuildingSnapshot.objects.get(pk=self.bs3.pk)
        self.assertEqual(refreshed_bs3.canonical_building, new_can)

    def test_unmatch_snapshot_tree_common_case(self):
        """Make sure it works for the general purpose."""
        self._add_additional_fake_buildings()
        # Setup the typical situation in which our CanonicalSnapshot has
        # two parents. And we've decided that we don't like the match.
        can = self.bs1.canonical_building
        self.bs1.children.add(self.bs3)
        self.bs2.children.add(self.bs3)

        can.canonical_snapshot = self.bs3
        can.save()
        self.bs3.canonical_building = can
        self.bs3.save()

        # We try to unmerge the child, since that's what we're looking at.
        seed_models.unmatch_snapshot_tree(self.bs3.pk)

        # Our child has been deleted, even though it's a leaf node.
        self.assertEqual(
            list(seed_models.BuildingSnapshot.objects.filter(pk=self.bs3.pk)),
            []
        )

        # Both parents are not leaf nodes themselves.
        self.assertEqual(self.bs1.children.count(), 0)
        self.assertEqual(self.bs2.children.count(), 0)

        refreshed_bs1 = seed_models.BuildingSnapshot.objects.get(pk=self.bs1.pk)
        refreshed_bs2 = seed_models.BuildingSnapshot.objects.get(pk=self.bs2.pk)
        # Both of our parents have canonical_buildings.
        self.assertNotEqual(refreshed_bs1.canonical_building, None)
        self.assertNotEqual(refreshed_bs2.canonical_building, None)
        # That are not the same...
        self.assertNotEqual(
            refreshed_bs1.canonical_building,
            refreshed_bs2.canonical_building
        )

        # Make sure that our canonical snapshot references are updated.
        self.assertEqual(
            refreshed_bs1.canonical_building.canonical_snapshot, refreshed_bs1
        )
        self.assertEqual(
            refreshed_bs2.canonical_building.canonical_snapshot, refreshed_bs2
        )


class TestCanonicalBuilding(TestCase):
    """Test the clean methods on CanonicalBuildingModel."""

    def test_repr(self):
        c = seed_models.CanonicalBuilding()
        c.save()
        self.assertTrue('pk: %s' % c.pk in str(c))
        self.assertTrue('snapshot: None' in str(c))
        self.assertTrue('- active: True' in str(c))

        c.active = False
        c.save()
        self.assertTrue('- active: False' in str(c))

        b = seed_models.BuildingSnapshot()
        c.canonical_snapshot = b
        c.save()
        self.assertTrue('snapshot: %s' % b.pk in str(c))
        self.assertEqual(
            'pk: %s - snapshot: %s - active: False' % (c.pk, b.pk),
            str(c)
        )
