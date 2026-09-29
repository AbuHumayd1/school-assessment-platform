from django.db import IntegrityError, transaction
from django.test import TestCase
from institutions.models import Institution
from .models import Candidate

class CandidateTests(TestCase):
    def setUp(self):
        self.a = Institution.objects.create(name="School A")
        self.b = Institution.objects.create(name="School B")
    def test_candidate_id_unique_per_institution(self):
        Candidate.objects.create(institution=self.a, candidate_id="001", first_name="A", last_name="One")
        Candidate.objects.create(institution=self.b, candidate_id="001", first_name="B", last_name="Two")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Candidate.objects.create(institution=self.a, candidate_id="001", first_name="C", last_name="Three")
