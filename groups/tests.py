from django.db import IntegrityError, transaction
from django.test import TestCase
from institutions.models import Institution
from candidates.models import Candidate
from .models import Group, GroupMembership

class GroupTests(TestCase):
    def setUp(self):
        self.a = Institution.objects.create(name="School A")
        self.b = Institution.objects.create(name="School B")
    def test_code_unique_per_institution_and_membership(self):
        group = Group.objects.create(institution=self.a, name="Year 1", code="Y1")
        Group.objects.create(institution=self.b, name="Year 1", code="Y1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Group.objects.create(institution=self.a, name="Duplicate", code="Y1")
        candidate = Candidate.objects.create(institution=self.a, candidate_id="C1", first_name="Test", last_name="Candidate")
        self.assertEqual(GroupMembership.objects.create(candidate=candidate, group=group).group, group)
        with self.assertRaises(IntegrityError), transaction.atomic():
            GroupMembership.objects.create(candidate=candidate, group=group)
