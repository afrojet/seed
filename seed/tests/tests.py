"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
from unittest import skip

from landing.models import SEEDUser as User
from django.test import TestCase

from ..models import Project, Compliance, BuildingSnapshot, CanonicalBuilding
from ..utils import (
    create_organization, get_buildings_for_user, get_buildings_for_user_count
)
from data_importer.models import ImportRecord

class ProjectTestCase(TestCase):
    def test_basic_project_creation(self):
        user = User.objects.create(username='test', first_name='t', last_name='est')
        org, user_role, _user_created = create_organization(
            user, 'Test Organization'
        )
        p = Project.objects.create(
            name='Test Project',
            owner=user,
            super_organization=org,
            description='A really great test organization.',
        )
        p.save()
        self.assertEqual(p.name, 'Test Project')
        self.assertTrue('Test Project' in str(p))
        self.assertEqual(p.owner, user)
        self.assertEqual(p.super_organization, org)
        self.assertEqual(p.status, Project.ACTIVE_STATUS)
        self.assertEqual(p.description, 'A really great test organization.')
        self.assertEqual(p.slug, 'test-project')
        user.delete()
        org.delete()


class ComplianceTestCase(TestCase):
    def test_basic_compliance_creation(self):
        p = Project(name='test project')
        p.save()
        c = Compliance(project=p)
        c.save()

        self.assertEqual(c.compliance_type, 'Benchmarking')
        #  test relation from compliance to project and vice versa
        self.assertEqual(c.project, p)
        self.assertTrue(p.compliance_set.exists())
        self.assertTrue(p.compliance_set.all()[0], c)
        # test repr or str
        self.assertEqual('Compliance Benchmarking for project Project test project', str(c))
        p.delete()
        c.delete()


class UtilsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            username='test',
            first_name='t',
            last_name='est'
        )
        self.user_2 = User.objects.create(
            username='test2',
            first_name='t',
            last_name='est'
        )
        self.org, user_role, _user_created = create_organization(
            self.user, 'Test Organization',
        )
        for i in range(10):
            bs = BuildingSnapshot.objects.create()
            bs.super_organization = self.org
            bs.save()

    @skip('Model changes 02/12/2014')
    def test_get_buildings_for_user(self):
        # user should have access to the buildings in his org
        buildings = get_buildings_for_user(self.user)
        self.assertEqual(len(buildings), 10)

        # a new user shouldn't have access if not in user's org
        buildings_2 = get_buildings_for_user(self.user_2)
        self.assertEqual(len(buildings_2), 0)

        # add user_2 to org and user_2 should have access to buildings
        self.org.add_user(self.user_2)
        buildings_2 = get_buildings_for_user(self.user_2)
        self.assertEqual(buildings, buildings_2)

    def test_get_buildings_count_for_user(self):
        # make 5 canonical buildings
        for b in BuildingSnapshot.objects.all()[:5]:
            c = CanonicalBuilding.objects.create()
            b.canonical_building = c
            c.canonical_snapshot = b
            b.save()
            c.save()
        # make a couple extra buidlings
        BuildingSnapshot.objects.create()
        BuildingSnapshot.objects.create()
        self.assertEqual(get_buildings_for_user_count(self.user), 5)
