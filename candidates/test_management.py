from unittest.mock import patch
from datetime import timedelta
from types import SimpleNamespace

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditEvent
from institutions.models import Institution
from tenants.models import InstitutionMembership
from .models import Candidate


class CandidateManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Institution.objects.create(name="Candidate Workspace A")
        cls.b = Institution.objects.create(name="Candidate Workspace B")
        cls.admin = User.objects.create_user("manager@example.com", "management-password-753!")
        cls.teacher = User.objects.create_user("teacher@example.com", "management-password-753!")
        cls.examiner = User.objects.create_user("examiner@example.com", "management-password-753!")
        cls.learner = User.objects.create_user("learner@example.com", "management-password-753!")
        for user, role in ((cls.admin, "institution_admin"), (cls.teacher, "teacher"), (cls.examiner, "examiner")):
            InstitutionMembership.objects.create(user=user, institution=cls.a, role=role)
        cls.own = Candidate.objects.create(institution=cls.a, candidate_id="A-1", first_name="Amina", last_name="Learner", email="amina@example.com")
        cls.foreign = Candidate.objects.create(institution=cls.b, candidate_id="B-1", first_name="Foreign", last_name="Learner")
        cls.linked = Candidate.objects.create(institution=cls.a, user=cls.learner, candidate_id="A-2", first_name="Linked", last_name="Learner")

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.a.pk))

    def provision(self, candidate=None, data=None):
        return self.client.post(f"/api/v1/candidates/{(candidate or self.own).pk}/provision-access/", data or {}, format="json")

    def test_list_is_bounded_and_selected_workspace_scoped(self):
        for i in range(30):
            Candidate.objects.create(institution=self.a, candidate_id=f"NEW-{i}", first_name="New", last_name=str(i))
        response = self.client.get("/api/v1/candidates/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 32)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertNotIn(self.foreign.pk, [row["id"] for row in response.data["results"]])
        self.assertIsNotNone(response.data["next"])

    def test_create_without_email_account_staff_or_groups(self):
        response = self.client.post("/api/v1/candidates/", {"first_name": "New", "last_name": "Participant", "candidate_id": "NEW"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        record = Candidate.objects.get(pk=response.data["id"])
        self.assertEqual(record.institution_id, self.a.pk)
        self.assertEqual(record.email, "")
        self.assertIsNone(record.user_id)
        self.assertFalse(record.group_memberships.exists())

    def test_candidate_id_uniqueness_is_per_workspace(self):
        fields = {"first_name": "New", "last_name": "Learner", "candidate_id": self.own.candidate_id}
        response = self.client.post("/api/v1/candidates/", fields, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("candidate_id", response.data)
        InstitutionMembership.objects.create(user=self.admin, institution=self.b, role="institution_admin")
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(self.client.post("/api/v1/candidates/", fields, format="json").status_code, 201)

    def test_edit_profile_and_status(self):
        response = self.client.patch(f"/api/v1/candidates/{self.own.pk}/", {"first_name": "Updated", "status": "archived", "phone": "123", "date_of_birth": "2000-01-02"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.own.refresh_from_db()
        self.assertEqual(self.own.first_name, "Updated")
        self.assertEqual(self.own.status, "archived")

    def test_cross_tenant_detail_update_and_provisioning_are_blocked(self):
        url = f"/api/v1/candidates/{self.foreign.pk}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {"first_name": "Hijacked"}, format="json").status_code, 404)
        self.assertEqual(self.provision(self.foreign).status_code, 404)
        self.assertEqual(self.client.post("/api/v1/candidates/", {"institution": self.b.pk, "candidate_id": "NEW", "first_name": "New", "last_name": "Name"}, format="json").status_code, 400)

    def test_anonymous_and_candidate_linked_account_cannot_manage_candidates(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get("/api/v1/candidates/").status_code, (401, 403))
        self.client.force_authenticate(self.learner)
        self.assertEqual(self.client.get("/api/v1/candidates/").status_code, 403)
        self.assertEqual(self.provision().status_code, 403)

    def test_staff_in_a_and_student_in_b_does_not_leak_b_records(self):
        InstitutionMembership.objects.create(user=self.teacher, institution=self.b, role="student")
        self.client.force_authenticate(self.teacher)
        response = self.client.get("/api/v1/candidates/")
        self.assertEqual(response.data["count"], 2)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(self.client.get("/api/v1/candidates/").status_code, 404)

    def test_multiple_staff_workspaces_require_explicit_selection(self):
        InstitutionMembership.objects.create(user=self.admin, institution=self.b, role="institution_admin")
        self.client.credentials()
        self.assertEqual(self.client.get("/api/v1/candidates/").status_code, 400)

    def test_search_name_candidate_id_email_and_status_preserves_tenancy(self):
        for search in ("Amina", "Amina Learner", "A-1", "amina@example.com"):
            response = self.client.get("/api/v1/candidates/", {"search": search})
            self.assertEqual([row["id"] for row in response.data["results"]], [self.own.pk])
        self.assertEqual(self.client.get("/api/v1/candidates/", {"search": "Foreign"}).data["count"], 0)
        self.assertEqual(self.client.get("/api/v1/candidates/", {"status": "archived"}).data["count"], 0)
        self.assertEqual(self.client.get("/api/v1/candidates/", {"status": "invalid"}).status_code, 400)

    def test_teachers_and_examiners_keep_crud_but_cannot_provision(self):
        for user in (self.teacher, self.examiner):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/v1/candidates/").status_code, 200)
            self.assertEqual(self.client.patch(f"/api/v1/candidates/{self.own.pk}/", {"phone": "987"}, format="json").status_code, 200)
            self.assertEqual(self.provision().status_code, 403)

    def test_admin_in_a_teacher_in_b_cannot_provision_b(self):
        InstitutionMembership.objects.create(user=self.admin, institution=self.b, role="teacher")
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(self.provision(self.foreign).status_code, 404)

    def test_provision_creates_hashed_account_link_and_secret_free_audit_only(self):
        response = self.provision()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn("no-store", response["Cache-Control"])
        self.own.refresh_from_db()
        user = self.own.user
        password = response.data["initial_password"]
        self.assertGreaterEqual(len(password), 24)
        self.assertTrue(user.check_password(password))
        self.assertNotEqual(user.password, password)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.institution_memberships.exists())
        event = AuditEvent.objects.get(resource_id=str(self.own.pk))
        self.assertNotIn(password, str(event.metadata))
        self.assertEqual(event.metadata["action"], "candidate_portal_access_provisioned")
        detail = self.client.get(f"/api/v1/candidates/{self.own.pk}/").data
        self.assertEqual(detail["portal_account"], {"email": user.email, "is_active": True})
        self.assertNotIn(password, str(detail))
        self.assertNotIn(user.password, str(detail))
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/v1/candidate/me/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/candidate/me/exams/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/context/").data["workspaces"], [])

    def test_repeated_provisioning_never_reissues_or_rotates_credentials(self):
        first = self.provision()
        self.own.refresh_from_db()
        old_hash = self.own.user.password
        count = User.objects.count()
        second = self.provision()
        self.assertEqual(second.status_code, 400)
        self.assertEqual(str(second.data["code"]), "already_linked")
        self.assertNotIn("initial_password", second.data)
        self.assertEqual(User.objects.count(), count)
        self.own.user.refresh_from_db()
        self.assertEqual(self.own.user.password, old_hash)

    def test_existing_email_collision_is_rejected_without_linking(self):
        self.own.email = self.admin.email.upper()
        self.own.save()
        response = self.provision()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["code"]), "email_exists")
        self.own.refresh_from_db()
        self.assertIsNone(self.own.user_id)
        self.assertFalse(AuditEvent.objects.exists())

    def test_missing_email_and_inactive_candidates_are_safe_failures(self):
        candidate = Candidate.objects.create(institution=self.a, candidate_id="NOEMAIL", first_name="No", last_name="Email")
        self.assertEqual(str(self.provision(candidate).data["code"]), "email_required")
        self.own.status = "inactive"
        self.own.save()
        self.assertEqual(str(self.provision().data["code"]), "candidate_inactive")

    def test_audit_failure_rolls_back_account_and_link(self):
        count = User.objects.count()
        with patch("candidates.provisioning.record_event", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                self.provision()
        self.own.refresh_from_db()
        self.assertIsNone(self.own.user_id)
        self.assertEqual(User.objects.count(), count)

    def test_provisioning_rejects_client_account_fields(self):
        self.assertEqual(self.provision(data={"user": self.admin.pk, "password": "unsafe"}).status_code, 400)
        self.own.refresh_from_db()
        self.assertIsNone(self.own.user_id)

    def test_generated_credentials_authenticate_through_existing_session_login(self):
        response = self.provision()
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/v1/auth/csrf/").data["csrfToken"]
        login = client.post("/api/v1/auth/login/", {"email": response.data["account"]["email"], "password": response.data["initial_password"]}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.data["user"]["is_candidate"])
        self.assertEqual(client.get("/api/v1/candidate/me/").status_code, 200)

    def test_session_provisioning_requires_csrf_and_is_throttled(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(f"/api/v1/candidates/{self.own.pk}/provision-access/", {}, format="json", HTTP_X_INSTITUTION_ID=str(self.a.pk)).status_code, 403)
        for _ in range(30):
            self.assertEqual(self.provision(self.linked).status_code, 400)
        self.assertEqual(self.provision(self.linked).status_code, 429)

    def test_identity_locked_candidate_cannot_be_provisioned_or_renumbered(self):
        from assessments.models import Assessment
        from attempts.models import Attempt
        from subjects.models import Subject
        subject = Subject.objects.create(institution=self.a, name="Subject", code="SUB")
        assessment = Assessment.objects.create(institution=self.a, subject=subject, title="Identity test", assessment_type="quiz", duration_minutes=5, created_by=self.admin)
        now = timezone.now()
        Attempt.objects.create(institution=self.a, assessment=assessment, candidate=self.own, attempt_number=1, started_at=now, expires_at=now + timedelta(minutes=5), last_activity_at=now)
        count = User.objects.count()
        self.assertEqual(str(self.provision().data["code"]), "identity_locked")
        response = self.client.patch(f"/api/v1/candidates/{self.own.pk}/", {"candidate_id": "CHANGED"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), count)
        self.assertTrue(self.client.get(f"/api/v1/candidates/{self.own.pk}/").data["identity_locked"])

    def test_profile_edit_validated_before_provisioning_preserves_new_account_link(self):
        from .serializers import CandidateSerializer
        from .views import CandidateViewSet
        serializer = CandidateSerializer(self.own, data={"first_name": "Updated"}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        account_id = self.provision().data["account"]["id"]
        view = CandidateViewSet()
        view.request = SimpleNamespace(data={})
        view.perform_update(serializer)
        self.own.refresh_from_db()
        self.assertEqual(self.own.user_id, account_id)
        self.assertEqual(self.own.first_name, "Updated")

    def test_dashboard_count_reflects_real_candidate_creation(self):
        before = self.client.get("/api/v1/institution/dashboard/").data["counts"]["active_candidates"]
        self.client.post("/api/v1/candidates/", {"first_name": "New", "last_name": "Learner", "candidate_id": "DASH"}, format="json")
        after = self.client.get("/api/v1/institution/dashboard/").data["counts"]["active_candidates"]
        self.assertEqual(after, before + 1)
