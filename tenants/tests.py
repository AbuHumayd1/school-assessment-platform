from rest_framework.test import APITestCase
from rest_framework import status
from accounts.models import User
from institutions.models import Institution
from tenants.models import InstitutionMembership
from candidates.models import Candidate
from groups.models import Group
from subjects.models import Subject

class TenantIsolationTests(APITestCase):
    def setUp(self):
        self.a = Institution.objects.create(name="Institution A")
        self.b = Institution.objects.create(name="Institution B")
        self.user = User.objects.create_user("teacher@example.com", "long-test-password")
        InstitutionMembership.objects.create(user=self.user, institution=self.a, role="teacher")
        self.candidate_a = Candidate.objects.create(institution=self.a, candidate_id="A1", first_name="A", last_name="Candidate")
        self.candidate_b = Candidate.objects.create(institution=self.b, candidate_id="B1", first_name="B", last_name="Candidate")
        self.group_a = Group.objects.create(institution=self.a, name="Group A", code="GA")
        self.group_b = Group.objects.create(institution=self.b, name="Group B", code="GB")
        self.subject_a = Subject.objects.create(institution=self.a, name="Subject A", code="SA")
        self.subject_b = Subject.objects.create(institution=self.b, name="Subject B", code="SB")
        self.client.force_authenticate(self.user)

    def test_lists_and_detail_ids_are_tenant_scoped(self):
        for url, own, foreign in [
            ("/api/v1/candidates/", self.candidate_a, self.candidate_b),
            ("/api/v1/groups/", self.group_a, self.group_b),
            ("/api/v1/subjects/", self.subject_a, self.subject_b),
        ]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            returned_ids = {item["id"] for item in response.data["results"]} if isinstance(response.data, dict) and "results" in response.data else {item["id"] for item in response.data}
            self.assertIn(own.id, returned_ids)
            self.assertNotIn(foreign.id, returned_ids)
            self.assertEqual(self.client.get(f"{url}{foreign.id}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_foreign_records_cannot_be_changed_or_deleted_by_url_id(self):
        for url, record in [("/api/v1/candidates/", self.candidate_b), ("/api/v1/groups/", self.group_b), ("/api/v1/subjects/", self.subject_b)]:
            detail = f"{url}{record.id}/"
            self.assertEqual(self.client.patch(detail, {"name": "Changed"}, format="json").status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(self.client.delete(detail).status_code, status.HTTP_404_NOT_FOUND)

    def test_client_cannot_assign_foreign_tenant(self):
        response = self.client.post("/api/v1/candidates/", {"institution": self.b.id, "candidate_id": "X", "first_name": "X", "last_name": "Y"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
