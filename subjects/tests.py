from django.db import IntegrityError, transaction
from django.test import TestCase
from institutions.models import Institution
from .models import Subject

class SubjectTests(TestCase):
    def test_code_unique_per_institution(self):
        school = Institution.objects.create(name="School")
        other = Institution.objects.create(name="Other School")
        Subject.objects.create(institution=school, name="Math", code="MATH")
        Subject.objects.create(institution=other, name="Math", code="MATH")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subject.objects.create(institution=school, name="Duplicate", code="MATH")
