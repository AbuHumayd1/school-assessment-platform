from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase
from django.contrib import admin as django_admin
from django.test import RequestFactory
from django.test import override_settings
from types import SimpleNamespace

from accounts.models import User
from audit.models import AuditEvent
from results.models import Result
from results.services import mark_attempt, publish_result
from results.tests import ResultFixtureMixin
from tenants.models import InstitutionMembership
from .models import Institution
from .platform_views import ClientSerializer, ClientViewSet
from .serializers import InstitutionSerializer
from .views import InstitutionViewSet


class PlatformFoundationTests(ResultFixtureMixin, APITestCase):
    def setUp(self):
        self.platform = User.objects.create_superuser("platform@example.test", "Strong-random-4829")
        self.school.workspace_mode = "managed_exam"
        self.school.can_release_candidate_results = False
        self.school.save()
        self.client.force_authenticate(self.platform)

    def client_url(self, suffix=""):
        return f"/api/v1/platform/clients/{self.school.pk}/{suffix}"

    def exam_url(self, suffix="", institution=None):
        return f"/api/v1/assessments/{self.assessment.pk}/{suffix}?institution={institution or self.school.pk}"

    def result(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq, selection=[self.mcq[0]])
        return mark_attempt(attempt.pk)

    def test_defaults_are_full_workspace_and_release_off(self):
        institution = Institution.objects.create(name="Default institution")
        self.assertEqual(institution.workspace_mode, "full_workspace")
        self.assertFalse(institution.can_release_candidate_results)

    def test_platform_overview_and_clients(self):
        response = self.client.get("/api/v1/platform/overview/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["clients"], 2)
        response = self.client.get("/api/v1/platform/clients/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

    def test_non_platform_users_and_staff_flag_cannot_access_platform(self):
        self.admin.is_staff = True
        self.admin.save()
        for user in (self.admin, self.student, self.teacher):
            self.client.force_authenticate(user)
            for path in ("overview/", "clients/", "exams/", f"clients/{self.school.pk}/"):
                self.assertEqual(self.client.get(f"/api/v1/platform/{path}", HTTP_X_INSTITUTION_ID=str(self.school.pk)).status_code, 403)

    def test_active_platform_membership_grants_authority(self):
        InstitutionMembership.objects.create(user=self.teacher, institution=self.other_school, role="platform_admin")
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get("/api/v1/platform/clients/").status_code, 200)
        InstitutionMembership.objects.filter(user=self.teacher, role="platform_admin").update(is_active=False)
        self.assertEqual(self.client.get("/api/v1/platform/clients/").status_code, 403)

    def test_client_search(self):
        response = self.client.get("/api/v1/platform/clients/?search=Other")
        self.assertEqual([row["id"] for row in response.data["results"]], [self.other_school.pk])

    def test_create_client_does_not_create_actor_membership(self):
        before = InstitutionMembership.objects.count()
        response = self.client.post("/api/v1/platform/clients/", {
            "name": "New Client", "slug": "new-client", "institution_type": "training_provider",
            "timezone": "Africa/Lagos", "workspace_mode": "managed_exam",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(InstitutionMembership.objects.count(), before)
        self.assertFalse(response.data["can_release_candidate_results"])
        event = AuditEvent.objects.get(resource_id=str(response.data["id"]), metadata__action="client_created")
        self.assertEqual(event.actor, self.platform)
        self.assertEqual(event.institution_id, response.data["id"])
        self.assertEqual(event.metadata["management_context"], "platform")

    def test_create_validation_and_duplicate_slug(self):
        for changes in ({"timezone": "Invalid/Zone"}, {"workspace_mode": "billing"}, {"slug": self.school.slug}):
            data = {"name": "Client", "slug": "unique-client", "timezone": "Africa/Lagos", **changes}
            self.assertEqual(self.client.post("/api/v1/platform/clients/", data, format="json").status_code, 400)

    def test_provision_new_administrator_hashes_password(self):
        response = self.client.post(self.client_url("administrators/"), {
            "name": "Client Operator", "email": "operator@example.test", "initial_password": "Stronger-unique-7319",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="operator@example.test")
        self.assertTrue(user.check_password("Stronger-unique-7319"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.institution_memberships.get().role, "institution_admin")
        self.assertNotIn("password", str(response.data).lower())
        event = AuditEvent.objects.get(metadata__action="administrator_provisioned")
        self.assertEqual(event.actor, self.platform)
        self.assertEqual(event.institution, self.school)
        self.assertNotIn("password", str(event.metadata).lower())

    def test_existing_user_keeps_global_password_and_identity(self):
        user = User.objects.create_user("existing@example.test", "Original-safe-1948", first_name="Original")
        original = user.password
        response = self.client.post(self.client_url("administrators/"), {
            "name": "Replacement", "email": "EXISTING@example.test", "initial_password": "Replacement-safe-3281",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user.refresh_from_db()
        self.assertEqual(user.password, original)
        self.assertEqual(user.first_name, "Original")

    def test_duplicate_membership_is_rejected_without_mutation(self):
        original = self.admin.password
        response = self.client.post(self.client_url("administrators/"), {"name": "Admin", "email": self.admin.email}, format="json")
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.password, original)
        self.assertEqual(self.admin.institution_memberships.get().role, "institution_admin")

    def test_provision_password_validation_and_required_password(self):
        for password in (None, "12345678"):
            data = {"name": "New", "email": "invalid@example.test"}
            if password is not None:
                data["initial_password"] = password
            self.assertEqual(self.client.post(self.client_url("administrators/"), data, format="json").status_code, 400)
        self.assertFalse(User.objects.filter(email="invalid@example.test").exists())

    def test_inactive_or_platform_user_not_provisioned_as_client_admin(self):
        user = User.objects.create_user("inactive@example.test", is_active=False)
        for account in (user, self.platform):
            self.assertEqual(self.client.post(self.client_url("administrators/"), {"name": "Name", "email": account.email}, format="json").status_code, 400)
        self.assertFalse(InstitutionMembership.objects.filter(user=self.platform).exists())

    def test_ordinary_admin_cannot_provision_or_toggle(self):
        self.client.force_authenticate(self.admin)
        for suffix, data in (("administrators/", {"name": "New", "email": "new@example.test"}), ("release-permission/", {"enabled": True})):
            self.assertEqual(self.client.post(self.client_url(suffix), data, format="json").status_code, 403)

    def test_workspace_context_keeps_platform_identity_without_membership(self):
        response = self.client.get("/api/v1/auth/context/")
        self.assertTrue(response.data["is_platform_admin"])
        self.assertEqual(response.data["user"]["id"], self.platform.pk)
        self.assertEqual(len(response.data["workspaces"]), 2)
        self.assertTrue(all(row["role"] == "platform_admin" for row in response.data["workspaces"]))
        self.assertFalse(self.platform.institution_memberships.exists())
        self.assertEqual(self.client.get(self.exam_url()).status_code, 200)

    def test_client_context_contains_only_own_client(self):
        self.client.force_authenticate(self.admin)
        data = self.client.get("/api/v1/auth/context/").data
        self.assertFalse(data["is_platform_admin"])
        self.assertEqual([row["institution"]["id"] for row in data["workspaces"]], [self.school.pk])
        self.assertEqual(data["workspaces"][0]["institution"]["workspace_mode"], "managed_exam")

    def test_managed_client_hidden_modules_server_denied(self):
        self.client.force_authenticate(self.admin)
        for path in ("subjects/", "groups/", "memberships/", "questions/", "topics/", "institutions/", "assessments/form-options/", "assessments/question-options/"):
            response = self.client.get(f"/api/v1/{path}?institution={self.school.pk}")
            self.assertEqual(response.status_code, 403, (path, response.data))
        for suffix in ("preview/", "question-inspection/", "candidate-assignments/"):
            self.assertEqual(self.client.get(self.exam_url(suffix)).status_code, 403)

    def test_managed_client_cannot_modify_exam(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(self.exam_url(), {"title": "Unauthorized"}, format="json").status_code, 403)
        self.assertEqual(self.client.post(self.exam_url("submit-review/"), {}).status_code, 403)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.title, "Marking test")

    def test_platform_can_prepare_managed_client(self):
        self.assertEqual(self.client.get(f"/api/v1/questions/?institution={self.school.pk}").status_code, 200)
        self.assertEqual(self.client.patch(self.exam_url(), {"title": "Prepared"}, format="json").status_code, 200)
        self.assertFalse(self.platform.institution_memberships.exists())

    def test_full_workspace_preserves_modules(self):
        self.school.workspace_mode = "full_workspace"
        self.school.save()
        self.client.force_authenticate(self.admin)
        for path in ("subjects/", "groups/", "memberships/", "questions/", "institutions/"):
            self.assertEqual(self.client.get(f"/api/v1/{path}?institution={self.school.pk}").status_code, 200, path)

    def test_header_and_object_ids_do_not_grant_other_client_access(self):
        self.client.force_authenticate(self.admin)
        for suffix in ("", "outcomes/", "results/", "reports/csv/"):
            self.assertEqual(self.client.get(self.exam_url(suffix, self.other_school.pk)).status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/candidates/{self.foreign_candidate.pk}/?institution={self.school.pk}").status_code, 404)

    def test_client_reads_outcomes_and_reports_when_unpublished(self):
        result = self.result()
        self.client.force_authenticate(self.admin)
        for suffix in ("outcomes/", "results/", "submissions/"):
            response = self.client.get(self.exam_url(suffix))
            self.assertEqual(response.status_code, 200, response.data)
        for kind in ("results", "reports", "submissions"):
            self.assertEqual(self.client.get(f"/api/v1/assessments/outcomes/{kind}/?institution={self.school.pk}").status_code, 200)
        for format in ("csv", "pdf", "docx"):
            response = self.client.get(self.exam_url(f"reports/{format}/"))
            self.assertEqual(response.status_code, 200, response.content[:100])
        result.refresh_from_db()
        self.assertIsNone(result.published_at)

    def test_release_off_denies_all_endpoints_and_service(self):
        result = self.result()
        self.client.force_authenticate(self.admin)
        for path in (self.exam_url("results/release/"), self.exam_url(f"results/{result.pk}/release/"), f"/api/v1/results/{result.pk}/publish/"):
            response = self.client.post(path, {})
            self.assertEqual(response.status_code, 403, (path, response.data))
        with self.assertRaises(PermissionDenied):
            publish_result(result.pk, actor=self.admin)
        with self.assertRaises(PermissionDenied):
            publish_result(result.pk)
        result.refresh_from_db()
        self.assertIsNone(result.published_at)

    def test_bulk_release_off_denied_even_with_no_results(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(self.exam_url("results/release/"), {}).status_code, 403)

    def test_platform_release_off_allowed_and_audited(self):
        result = self.result()
        self.assertEqual(self.client.post(self.exam_url(f"results/{result.pk}/release/"), {}).status_code, 200)
        event = AuditEvent.objects.filter(event_type="result_published").latest("pk")
        self.assertEqual(event.actor, self.platform)
        self.assertEqual(event.institution, self.school)
        self.assertEqual(event.metadata["management_context"], "platform")

    def test_toggle_on_then_off_immediate_service_authority(self):
        result = self.result()
        before = list(Result.objects.values())
        response = self.client.post(self.client_url("release-permission/"), {"enabled": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(Result.objects.values()), before)
        self.assertEqual(publish_result(result.pk, actor=self.admin).status, "published")
        published = list(Result.objects.values())
        self.assertEqual(self.client.post(self.client_url("release-permission/"), {"enabled": False}, format="json").status_code, 200)
        self.assertEqual(list(Result.objects.values()), published)
        with self.assertRaises(PermissionDenied):
            publish_result(result.pk, actor=self.admin)
        self.assertEqual(publish_result(result.pk, actor=self.platform).status, "published")

    def test_toggle_validation_does_not_change_permission(self):
        self.assertEqual(self.client.post(self.client_url("release-permission/"), {}, format="json").status_code, 400)
        self.assertEqual(self.client.post(self.client_url("release-permission/"), {"enabled": "invalid"}, format="json").status_code, 400)
        self.school.refresh_from_db()
        self.assertFalse(self.school.can_release_candidate_results)

    def test_candidate_only_own_result_after_release(self):
        result = self.result()
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get("/api/v1/results/my/").data, [])
        self.assertEqual(self.client.get(f"/api/v1/results/{result.pk}/").status_code, 404)
        publish_result(result.pk, actor=self.platform)
        self.assertEqual([row["id"] for row in self.client.get("/api/v1/results/my/").data], [result.pk])
        self.client.force_authenticate(self.foreign)
        self.assertEqual(self.client.get(f"/api/v1/results/{result.pk}/").status_code, 404)

    def test_managed_submission_detail_omits_answer_key(self):
        result = self.result()
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.exam_url(f"submissions/{result.attempt_id}/"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("is_correct", str(response.data))
        self.assertNotIn("explanation", str(response.data))

    def test_platform_exams_listing_contains_no_sensitive_data(self):
        response = self.client.get("/api/v1/platform/exams/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(set(response.data["results"][0]), {"id", "institution", "client", "title", "status"})

    def test_release_on_all_api_paths_then_off(self):
        result = self.result()
        self.client.post(self.client_url("release-permission/"), {"enabled": True}, format="json")
        self.client.force_authenticate(self.admin)
        paths = (self.exam_url("results/release/"), self.exam_url(f"results/{result.pk}/release/"), f"/api/v1/results/{result.pk}/publish/")
        for path in paths:
            self.assertEqual(self.client.post(path, {}).status_code, 200, path)
        self.client.force_authenticate(self.platform)
        self.client.post(self.client_url("release-permission/"), {"enabled": False}, format="json")
        self.client.force_authenticate(self.admin)
        for path in paths:
            self.assertEqual(self.client.post(path, {}).status_code, 403, path)

    def test_server_summary_updates_release_control_for_actual_actor(self):
        self.result()
        self.client.force_authenticate(self.admin)
        self.assertFalse(self.client.get(self.exam_url("results/")).data["summary"]["can_release_results"])
        self.client.force_authenticate(self.platform)
        self.assertTrue(self.client.get(self.exam_url("results/")).data["summary"]["can_release_results"])
        self.client.post(self.client_url("release-permission/"), {"enabled": True}, format="json")
        self.client.force_authenticate(self.admin)
        self.assertTrue(self.client.get(self.exam_url("results/")).data["summary"]["can_release_results"])

    def test_permission_cannot_be_written_through_client_profile_patch(self):
        self.assertEqual(self.client.patch(self.client_url(), {"can_release_candidate_results": True}, format="json").status_code, 200)
        self.school.refresh_from_db()
        self.assertFalse(self.school.can_release_candidate_results)

    def test_mixed_workspace_user_cannot_bypass_mode_with_full_workspace_header(self):
        InstitutionMembership.objects.create(user=self.admin, institution=self.other_school, role="institution_admin")
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/v1/subjects/").status_code, 400)
        headers = {"HTTP_X_INSTITUTION_ID": str(self.other_school.pk)}
        response = self.client.get("/api/v1/subjects/", **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [self.other_subject.pk])
        self.assertEqual(self.client.get(f"/api/v1/institutions/{self.school.pk}/", **headers).status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/subjects/{self.subject.pk}/", **headers).status_code, 404)
        self.assertEqual(self.client.post("/api/v1/subjects/", {"institution": self.school.pk, "name": "Bypass", "code": "BAD"}, format="json", **headers).status_code, 400)

    def test_managed_user_cannot_use_forged_header_to_access_profile(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/api/v1/institutions/{self.school.pk}/", HTTP_X_INSTITUTION_ID=str(self.other_school.pk)).status_code, 404)

    def test_managed_users_directory_is_server_denied(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/api/v1/users/?institution={self.school.pk}").status_code, 403)

    @override_settings(MADAAR_PUBLIC_WORKSPACE_CREATION_ENABLED=True)
    def test_managed_admin_can_deliberately_create_separate_workspace(self):
        InstitutionMembership.objects.create(user=self.admin, institution=self.other_school, role="institution_admin")
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/v1/institutions/create-workspace/", {"name": "Own workspace", "timezone": "Africa/Lagos"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        institution = Institution.objects.get(pk=response.data["id"])
        self.assertEqual(institution.workspace_mode, "full_workspace")
        self.assertFalse(institution.can_release_candidate_results)

    def test_release_requires_active_membership_and_active_institution(self):
        result = self.result()
        self.school.can_release_candidate_results = True
        self.school.save()
        self.admin.institution_memberships.update(is_active=False)
        with self.assertRaises(PermissionDenied):
            publish_result(result.pk, actor=self.admin)
        self.school.is_active = False
        self.school.save()
        with self.assertRaises(PermissionDenied):
            publish_result(result.pk, actor=self.platform)

    def test_platform_direct_result_api_respects_selected_client(self):
        result = self.result()
        for path in (f"/api/v1/results/{result.pk}/", f"/api/v1/results/{result.pk}/publish/"):
            action = self.client.post if path.endswith("publish/") else self.client.get
            self.assertEqual(action(path, HTTP_X_INSTITUTION_ID=str(self.other_school.pk)).status_code, 404)

    def test_managed_client_cannot_access_quick_credentials(self):
        self.client.force_authenticate(self.admin)
        for suffix in ("quick-access/", "quick-access/credentials/"):
            self.assertEqual(self.client.get(self.exam_url(suffix)).status_code, 403)

    def test_profile_saves_cannot_clobber_a_new_permission_toggle(self):
        for serializer_class, view_class in ((ClientSerializer, ClientViewSet), (InstitutionSerializer, InstitutionViewSet)):
            stale = Institution.objects.get(pk=self.school.pk)
            request = SimpleNamespace(user=self.platform)
            serializer = serializer_class(stale, data={"name": "Updated client"}, partial=True, context={"request": request})
            serializer.is_valid(raise_exception=True)
            Institution.objects.filter(pk=self.school.pk).update(can_release_candidate_results=not stale.can_release_candidate_results)
            expected = not stale.can_release_candidate_results
            view = view_class()
            view.request = request
            view.perform_update(serializer)
            self.school.refresh_from_db()
            self.assertEqual(self.school.can_release_candidate_results, expected)

    def test_django_admin_cannot_bypass_audited_setting_control(self):
        model_admin = django_admin.site._registry[Institution]
        request = RequestFactory().get("/admin/institutions/institution/")
        request.user = self.platform
        form_class = model_admin.get_form(request, self.school)
        self.assertNotIn("workspace_mode", form_class.base_fields)
        self.assertNotIn("can_release_candidate_results", form_class.base_fields)
        stale = Institution.objects.get(pk=self.school.pk)
        Institution.objects.filter(pk=self.school.pk).update(can_release_candidate_results=True)
        stale.workspace_mode = "full_workspace"
        model_admin.save_model(request, stale, SimpleNamespace(), True)
        self.school.refresh_from_db()
        self.assertTrue(self.school.can_release_candidate_results)
        self.assertEqual(self.school.workspace_mode, "managed_exam")

    def test_alternate_numeric_selectors_cannot_bypass_managed_mode(self):
        self.client.force_authenticate(self.admin)
        for selector in (str(self.school.pk), f"+{self.school.pk}", f" {self.school.pk} "):
            self.assertEqual(self.client.get("/api/v1/questions/", HTTP_X_INSTITUTION_ID=selector).status_code, 403)
            self.assertEqual(self.client.get("/api/v1/questions/", {"institution": selector}).status_code, 403)
