from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditEvent
from candidates.models import Candidate
from tenants.models import InstitutionMembership
from .models import Institution


@override_settings(MADAAR_PUBLIC_WORKSPACE_CREATION_ENABLED=True)
class WorkspaceOnboardingTests(TestCase):
    url = "/api/v1/institutions/create-workspace/"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("organizer@example.com", "onboarding-password-934!")
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.token = self.client.get("/api/v1/auth/csrf/").data["csrfToken"]
        self.fields = dict(name="Learning Workspace", institution_type="training", timezone="Africa/Lagos")

    def create(self, **changes):
        return self.client.post(self.url, {**self.fields, **changes}, format="json", HTTP_X_CSRFTOKEN=self.token)

    @override_settings(MADAAR_PUBLIC_WORKSPACE_CREATION_ENABLED=False)
    def test_disabled_creation_has_no_side_effects_and_operator_path_remains(self):
        response = self.create()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "public_workspace_creation_disabled")
        self.assertFalse(Institution.objects.exists())
        self.assertFalse(InstitutionMembership.objects.exists())
        self.assertFalse(AuditEvent.objects.exists())
        operator = User.objects.create_superuser("operator@example.com", "Operator-password-729!")
        self.client.force_authenticate(operator)
        response = self.client.post("/api/v1/institutions/", {"name": "Operator provisioned", "slug": "operator-provisioned", "institution_type": "school"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Institution.objects.count(), 1)

    def test_requires_authentication_and_session_csrf(self):
        self.assertEqual(APIClient().post(self.url, self.fields, format="json").status_code, 403)
        self.assertEqual(self.client.post(self.url, self.fields, format="json").status_code, 403)
        self.assertFalse(Institution.objects.exists())

    def test_creates_active_admin_membership_audit_and_authoritative_context(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        institution = Institution.objects.get(pk=response.data["id"])
        self.assertTrue(institution.is_active)
        self.assertEqual(institution.timezone, "Africa/Lagos")
        membership = InstitutionMembership.objects.get(institution=institution, user=self.user)
        self.assertEqual(membership.role, InstitutionMembership.Role.INSTITUTION_ADMIN)
        self.assertTrue(membership.is_active)
        event = AuditEvent.objects.get(institution=institution)
        self.assertEqual(event.event_type, AuditEvent.Type.MEMBERSHIP_CHANGED)
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.metadata, {"action": "created", "role": "institution_admin"})
        context = self.client.get("/api/v1/auth/context/")
        self.assertEqual(context.data["workspaces"][0]["institution"]["id"], institution.pk)
        self.assertEqual(context.data["workspaces"][0]["role"], "institution_admin")
        self.assertFalse(User.objects.get(pk=self.user.pk).is_staff)

    def test_membership_failure_rolls_back_institution(self):
        with patch("institutions.onboarding.InstitutionMembership.objects.create", side_effect=RuntimeError("membership failed")):
            with self.assertRaises(RuntimeError):
                self.create()
        self.assertFalse(Institution.objects.exists())
        self.assertFalse(InstitutionMembership.objects.exists())
        self.assertFalse(AuditEvent.objects.exists())

    def test_audit_failure_rolls_back_institution_and_membership(self):
        with patch("institutions.onboarding.record_event", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                self.create()
        self.assertFalse(Institution.objects.exists())
        self.assertFalse(InstitutionMembership.objects.exists())

    def test_client_cannot_assign_privileges_ownership_slug_or_activation(self):
        for field, value in (("role", "platform_admin"), ("user", self.user.pk), ("institution", 1),
                             ("slug", "chosen"), ("is_active", False), ("interface_language", "arabic")):
            with self.subTest(field=field):
                self.assertEqual(self.create(**{field: value}).status_code, 400)
        self.assertFalse(Institution.objects.exists())

    def test_same_name_and_non_latin_names_have_unique_server_slugs(self):
        ids = []
        for name in ("Same Name", "Same Name", "معهد العلم", "معهد العلم"):
            response = self.create(name=name)
            self.assertEqual(response.status_code, 201, response.data)
            ids.append(response.data["id"])
        slugs = list(Institution.objects.filter(pk__in=ids).values_list("slug", flat=True))
        self.assertEqual(len(set(slugs)), 4)
        self.assertTrue(all(slugs))

    def test_candidate_can_create_additional_workspaces_without_losing_relationship(self):
        original = Institution.objects.create(name="Candidate Institution")
        candidate = Candidate.objects.create(institution=original, user=self.user, candidate_id="C-1", first_name="Robin", last_name="Learner")
        original_membership = InstitutionMembership.objects.create(institution=original, user=self.user, role="student", is_active=True)
        for name in ("First Workspace", "Second Workspace"):
            self.assertEqual(self.create(name=name).status_code, 201)
        candidate.refresh_from_db()
        original_membership.refresh_from_db()
        self.assertEqual(candidate.user_id, self.user.pk)
        self.assertEqual(candidate.institution_id, original.pk)
        self.assertEqual(original_membership.role, "student")
        self.assertEqual(self.client.get("/api/v1/auth/me/").data["is_candidate"], True)
        self.assertEqual(self.client.get("/api/v1/candidate/me/").status_code, 200)
        self.assertEqual(len(self.client.get("/api/v1/auth/context/").data["workspaces"]), 2)

    def test_new_admin_can_access_only_own_dashboard_and_institution(self):
        other = Institution.objects.create(name="Unrelated Institution")
        own = self.create().data["id"]
        self.assertEqual(self.client.get("/api/v1/institution/dashboard/", HTTP_X_INSTITUTION_ID=str(own)).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/institution/dashboard/", HTTP_X_INSTITUTION_ID=str(other.pk)).status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/institutions/{other.pk}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/v1/institutions/{other.pk}/", {"name": "Hijacked"}, format="json", HTTP_X_CSRFTOKEN=self.token).status_code, 404)
        self.assertEqual([item["id"] for item in self.client.get("/api/v1/institutions/").data], [own])

    def test_validates_minimal_fields_and_timezone_and_supports_broad_types(self):
        for changes in ({"name": ""}, {"timezone": "invalid-zone"}, {"institution_type": "x" * 41}):
            self.assertEqual(self.create(**changes).status_code, 400)
        for category in ("school", "training", "professional_exam", "madrasah", "cbt", "competition", "other"):
            self.assertEqual(self.create(institution_type=category).status_code, 201)

    def test_workspace_creation_is_throttled(self):
        for _ in range(10):
            self.assertEqual(self.create(name="").status_code, 400)
        self.assertEqual(self.create(name="").status_code, 429)
