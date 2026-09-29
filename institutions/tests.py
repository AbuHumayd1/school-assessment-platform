from django.db import IntegrityError, transaction
from django.test import TestCase
from .models import Institution
from tenants.models import InstitutionMembership
from accounts.models import User

class InstitutionTests(TestCase):
    def test_institution_and_membership(self):
        institution = Institution.objects.create(name="North School")
        user = User.objects.create_user("staff@example.com", "long-test-password")
        membership = InstitutionMembership.objects.create(user=user, institution=institution, role="institution_admin")
        self.assertEqual(institution.slug, "north-school")
        self.assertEqual(membership.institution, institution)
        with self.assertRaises(IntegrityError), transaction.atomic():
            InstitutionMembership.objects.create(user=user, institution=institution, role="teacher")
