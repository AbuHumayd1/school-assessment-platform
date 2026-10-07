import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.test import APIClient

from accounts.models import User
from attempts.models import Attempt
from audit.models import AuditEvent
from candidates.models import Candidate
from candidates.test_management import CandidateManagementTests
from results.models import Result
from subjects.models import Subject
from tenants.models import InstitutionMembership
from .models import Assessment, AssessmentCandidate, QuickExamConfiguration, QuickExamCredential, QuickExamSession
from .quick_services import PIN_ALPHABET, generate_credential, session_is_current, verify_credential


class QuickExamAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CandidateManagementTests.setUpTestData.__func__(cls)
        cls.subject = Subject.objects.create(institution=cls.a, name="Quick subject", code="QUICK")
        cls.exam = Assessment.objects.create(institution=cls.a, subject=cls.subject, title="Quick exam", assessment_type="quiz", duration_minutes=5, created_by=cls.admin, candidate_access="access_code")
        cls.other_exam = Assessment.objects.create(institution=cls.a, subject=cls.subject, title="Other exam", assessment_type="quiz", duration_minutes=5, created_by=cls.admin, candidate_access="access_code")
        cls.portal_exam = Assessment.objects.create(institution=cls.a, subject=cls.subject, title="Portal exam", assessment_type="quiz", duration_minutes=5, created_by=cls.admin)
        cls.config = QuickExamConfiguration.objects.create(assessment=cls.exam, exam_code="QUICK-2026", enabled=True)
        cls.no_account = Candidate.objects.create(institution=cls.a, candidate_id="NO-ACCOUNT", first_name="Quick", last_name="Participant")
        for candidate in (cls.no_account, cls.linked):
            AssessmentCandidate.objects.create(assessment=cls.exam, candidate=candidate, assigned_by=cls.admin)

    setUp = CandidateManagementTests.setUp

    def base(self, exam=None):
        return f"/api/v1/assessments/{(exam or self.exam).pk}/quick-access/"

    def issue(self, candidate=None, **extra):
        return self.client.post(self.base() + "credentials/", {"candidate": (candidate or self.no_account).pk, **extra}, format="json")

    def operation(self, operation, candidate=None, data=None):
        return self.client.post(self.base() + f"credentials/{(candidate or self.no_account).pk}/{operation}/", data or {}, format="json")

    def session(self, credential, **extra):
        return QuickExamSession.objects.create(credential=credential, token_digest=hashlib.sha256(b"test-only-token").hexdigest(), credential_version=credential.version, configuration_version=credential.configuration.session_version, expires_at=timezone.now() + timedelta(hours=1), **extra)

    def history(self):
        now = timezone.now()
        attempt = Attempt.objects.create(institution=self.a, candidate=self.no_account, assessment=self.exam, attempt_number=1, started_at=now, expires_at=now + timedelta(minutes=5), last_activity_at=now)
        result = Result.objects.create(institution=self.a, candidate=self.no_account, assessment=self.exam, attempt=attempt, total_marks=10, marks_obtained=8, pass_mark=5, marked_at=now)
        return attempt, result

    def test_admin_creates_normalized_configuration_for_access_code_assessment(self):
        response = self.client.put(self.base(self.other_exam), {"exam_code": "  bef2026  ", "enabled": True}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["exam_code"], "BEF2026")
        self.assertEqual(response.data["assessment"], self.other_exam.pk)
        self.assertEqual(response.data["session_version"], 1)
        self.assertEqual(self.client.get(self.base(self.other_exam)).data["exam_code"], "BEF2026")

    def test_malformed_or_non_ascii_codes_are_rejected(self):
        for code in ("", "ABC DEF", "A_B", "A/B", "---", "A--B", "A-", "A" * 33, "اختبار", "ß", "ＡＢＣ"):
            response = self.client.put(self.base(self.other_exam), {"exam_code": code}, format="json")
            self.assertEqual(response.status_code, 400, code)
        self.assertFalse(QuickExamConfiguration.objects.filter(assessment=self.other_exam).exists())

    def test_exam_code_is_globally_unique_and_case_normalized(self):
        response = self.client.put(self.base(self.other_exam), {"exam_code": "quick-2026"}, format="json")
        self.assertEqual(response.status_code, 400)
        with self.assertRaises(DjangoValidationError):
            QuickExamConfiguration.objects.create(assessment=self.other_exam, exam_code="Quick-2026")
        with self.assertRaises(IntegrityError), transaction.atomic():
            QuickExamConfiguration.objects.bulk_create([QuickExamConfiguration(assessment=self.other_exam, exam_code="QUICK-2026")])

    def test_configuration_rejects_wrong_delivery_mode_and_assessment_cannot_switch_it(self):
        self.assertEqual(self.client.put(self.base(self.portal_exam), {"exam_code": "PORTAL"}, format="json").status_code, 400)
        self.exam.candidate_access = "assigned_group"
        with self.assertRaises(DjangoValidationError):
            self.exam.save()
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.candidate_access, "access_code")

    def test_configuration_and_credential_cannot_be_reassigned(self):
        self.config.assessment = self.other_exam
        with self.assertRaises(DjangoValidationError):
            self.config.save()
        self.config.refresh_from_db()
        self.issue()
        credential = QuickExamCredential.objects.get(candidate=self.no_account)
        credential.candidate = self.own
        with self.assertRaises(DjangoValidationError):
            credential.save()

    def test_unknown_and_security_sensitive_input_fields_are_rejected(self):
        self.assertEqual(self.client.patch(self.base(), {"session_version": 0, "assessment": self.other_exam.pk}, format="json").status_code, 400)
        self.assertEqual(self.issue(pin_hash="plaintext", active=True).status_code, 400)
        self.assertEqual(self.operation("reset", data={"initial_pin": "unsafe"}).status_code, 400)
        self.assertEqual(self.operation("revoke", data={"candidate": self.foreign.pk}).status_code, 400)

    def test_cross_workspace_configuration_and_all_credential_operations_are_blocked(self):
        InstitutionMembership.objects.create(user=self.admin, institution=self.b, role="institution_admin")
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.b.pk))
        for method in ("get", "put", "patch"):
            response = getattr(self.client, method)(self.base(), {"exam_code": "HIJACK"}, format="json")
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.issue().status_code, 404)
        self.assertEqual(self.client.get(self.base() + "credentials/").status_code, 404)
        self.assertEqual(self.operation("reset").status_code, 404)
        self.assertEqual(self.operation("revoke").status_code, 404)

    def test_multiple_manageable_workspaces_require_selection(self):
        InstitutionMembership.objects.create(user=self.admin, institution=self.b, role="institution_admin")
        self.client.credentials()
        self.assertEqual(self.client.get(self.base()).status_code, 400)

    def test_teachers_examiners_candidates_and_anonymous_are_blocked(self):
        for user in (self.teacher, self.examiner, self.learner, None):
            self.client.force_authenticate(user)
            for response in (self.client.get(self.base()), self.issue(), self.operation("reset"), self.operation("revoke")):
                self.assertIn(response.status_code, (401, 403))

    def test_admin_in_a_teacher_in_b_cannot_manage_b(self):
        InstitutionMembership.objects.create(user=self.admin, institution=self.b, role="teacher")
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(self.client.patch(self.base(), {"enabled": False}, format="json").status_code, 404)

    def test_platform_admin_authority_remains_supported(self):
        self.admin.is_superuser = True
        self.admin.save()
        self.assertEqual(self.issue().status_code, 201)

    def test_no_email_or_user_needed_and_no_accounts_or_memberships_created(self):
        users = User.objects.count()
        memberships = InstitutionMembership.objects.count()
        response = self.issue()
        self.assertEqual(response.status_code, 201, response.data)
        self.no_account.refresh_from_db()
        self.assertIsNone(self.no_account.user_id)
        self.assertEqual(self.no_account.email, "")
        self.assertEqual(User.objects.count(), users)
        self.assertEqual(InstitutionMembership.objects.count(), memberships)

    def test_pin_entropy_hash_verification_and_no_store_response(self):
        response = self.issue()
        pin = response.data["initial_pin"]
        credential = QuickExamCredential.objects.get(candidate=self.no_account)
        self.assertEqual(len(pin), 10)
        self.assertTrue(set(pin).issubset(set(PIN_ALPHABET)))
        self.assertFalse(set(PIN_ALPHABET) & set("01ILO"))
        self.assertGreaterEqual(len(PIN_ALPHABET), 30)
        self.assertNotEqual(credential.pin_hash, pin)
        self.assertTrue(check_password(pin, credential.pin_hash))
        self.assertTrue(verify_credential(credential, pin))
        self.assertFalse(verify_credential(credential, "wrong"))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotIn("pin_hash", str(response.data))

    def test_later_list_responses_contain_no_plaintext_hash_or_session_data(self):
        pin = self.issue().data["initial_pin"]
        credential = QuickExamCredential.objects.get(candidate=self.no_account)
        self.session(credential)
        response = self.client.get(self.base() + "credentials/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["candidate_identifier"], "NO-ACCOUNT")
        for secret in (pin, credential.pin_hash, "pin_hash", "token_digest", "initial_pin"):
            self.assertNotIn(secret, str(response.data))

    def test_repeat_generation_never_rotates_or_reveals_existing_credential(self):
        first = self.issue()
        credential = QuickExamCredential.objects.get(candidate=self.no_account)
        old_hash = credential.pin_hash
        response = self.issue()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(str(response.data["code"]), "credential_exists")
        self.assertNotIn("initial_pin", response.data)
        credential.refresh_from_db()
        self.assertEqual(credential.pin_hash, old_hash)
        self.assertEqual(credential.version, 1)
        self.assertTrue(check_password(first.data["initial_pin"], old_hash))
        self.assertEqual(QuickExamCredential.objects.count(), 1)

    def test_cross_institution_candidate_rejected_by_api_service_and_model(self):
        self.assertEqual(self.issue(self.foreign).status_code, 404)
        with self.assertRaises(NotFound):
            generate_credential(self.config, self.foreign, self.admin)
        with self.assertRaises(DjangoValidationError):
            QuickExamCredential.objects.create(configuration=self.config, candidate=self.foreign, pin_hash=make_password("test-only-pin"))
        self.assertFalse(QuickExamCredential.objects.exists())

    def test_service_authorization_is_authoritative(self):
        for actor in (self.teacher, self.examiner, self.learner, None):
            with self.assertRaises(PermissionDenied):
                generate_credential(self.config, self.no_account, actor)
        self.assertFalse(QuickExamCredential.objects.exists())

    def test_unique_configuration_candidate_is_database_enforced(self):
        self.issue()
        with self.assertRaises(IntegrityError), transaction.atomic():
            QuickExamCredential.objects.bulk_create([QuickExamCredential(configuration=self.config, candidate=self.no_account, pin_hash=make_password("test-only-pin"))])

    def test_plaintext_hash_field_is_rejected_at_model_boundary(self):
        with self.assertRaises(DjangoValidationError):
            QuickExamCredential.objects.create(configuration=self.config, candidate=self.no_account, pin_hash="plaintext")

    def test_reset_rotates_hash_increments_version_and_invalidates_old_session(self):
        with patch("assessments.quick_services.secrets.choice", return_value="A"):
            old_pin = self.issue().data["initial_pin"]
        credential = QuickExamCredential.objects.get(candidate=self.no_account)
        session = self.session(credential)
        self.assertTrue(session_is_current(session))
        with patch("assessments.quick_services.secrets.choice", return_value="B"):
            response = self.operation("reset")
        credential.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(credential.version, 2)
        self.assertFalse(check_password(old_pin, credential.pin_hash))
        self.assertTrue(verify_credential(credential, response.data["initial_pin"]))
        self.assertFalse(session_is_current(session))
        session.refresh_from_db()
        self.assertIsNotNone(session.revoked_at)
        self.assertEqual(session.credential_version, 1)

    def test_revoke_is_idempotent_and_reset_explicitly_reissues(self):
        pin = self.issue().data["initial_pin"]
        credential = QuickExamCredential.objects.get(candidate=self.no_account)
        session = self.session(credential)
        response = self.operation("revoke")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["active"])
        self.assertEqual(response.data["version"], 2)
        self.assertNotIn("initial_pin", response.data)
        self.assertFalse(verify_credential(credential, pin))
        self.assertFalse(session_is_current(session))
        self.assertEqual(self.operation("revoke").data["version"], 2)
        response = self.operation("reset")
        self.assertTrue(response.data["credential"]["active"])
        self.assertEqual(response.data["credential"]["version"], 3)
        self.assertFalse(session_is_current(session))

    def test_disable_and_reenable_do_not_resurrect_old_sessions(self):
        self.issue()
        credential = QuickExamCredential.objects.get(candidate=self.no_account)
        session = self.session(credential)
        self.assertTrue(session_is_current(session))
        response = self.client.patch(self.base(), {"enabled": False}, format="json")
        self.assertEqual(response.data["session_version"], 2)
        self.assertFalse(session_is_current(session))
        self.assertEqual(self.client.patch(self.base(), {"enabled": False}, format="json").data["session_version"], 2)
        response = self.client.patch(self.base(), {"enabled": True}, format="json")
        self.assertEqual(response.data["session_version"], 2)
        self.assertFalse(session_is_current(session))
        session.refresh_from_db()
        session.revoked_at = None
        session.save()
        self.assertFalse(session_is_current(session))

    def test_exam_code_change_is_locked_after_credential_issuance(self):
        self.issue()
        response = self.client.patch(self.base(), {"exam_code": "RENAMED"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.config.refresh_from_db()
        self.assertEqual(self.config.exam_code, "QUICK-2026")

    def test_future_expiry_and_expired_credential_behavior(self):
        future = timezone.now() + timedelta(minutes=10)
        response = self.issue(expires_at=future.isoformat())
        credential = QuickExamCredential.objects.get(candidate=self.no_account)
        self.assertTrue(verify_credential(credential, response.data["initial_pin"]))
        self.assertFalse(verify_credential(credential, response.data["initial_pin"], now=future + timedelta(seconds=1)))
        self.assertEqual(self.operation("reset", data={"expires_at": (timezone.now() - timedelta(days=1)).isoformat()}).status_code, 400)
        credential.refresh_from_db()
        self.assertEqual(credential.version, 1)

    def test_invalid_expiry_inactive_candidate_and_archived_assessment_rejected(self):
        self.assertEqual(self.issue(expires_at="not-a-date").status_code, 400)
        self.assertEqual(self.issue(expires_at=(timezone.now() - timedelta(days=1)).isoformat()).status_code, 400)
        self.no_account.status = "inactive"
        self.no_account.save()
        self.assertEqual(self.issue().status_code, 400)
        self.no_account.status = "active"
        self.no_account.save()
        self.exam.status = "archived"
        self.exam.save()
        self.assertEqual(self.issue().status_code, 400)

    def test_revoke_does_not_change_candidate_attempt_or_result(self):
        self.issue()
        attempt, result = self.history()
        old_candidate = Candidate.objects.values().get(pk=self.no_account.pk)
        old_attempt = Attempt.objects.values().get(pk=attempt.pk)
        old_result = Result.objects.values().get(pk=result.pk)
        self.assertEqual(self.operation("revoke").status_code, 200)
        self.assertEqual(Candidate.objects.values().get(pk=self.no_account.pk), old_candidate)
        self.assertEqual(Attempt.objects.values().get(pk=attempt.pk), old_attempt)
        self.assertEqual(Result.objects.values().get(pk=result.pk), old_result)

    def test_audit_lifecycle_contains_only_safe_identifiers_and_actions(self):
        initial = self.issue().data["initial_pin"]
        reset = self.operation("reset").data["initial_pin"]
        self.operation("revoke")
        self.client.patch(self.base(), {"enabled": False}, format="json")
        events = list(AuditEvent.objects.all())
        self.assertEqual({event.metadata["action"] for event in events}, {"quick_credential_generated", "quick_credential_reset", "quick_credential_revoked", "quick_configuration_disabled"})
        for event in events:
            self.assertEqual(event.actor_id, self.admin.pk)
            self.assertEqual(event.institution_id, self.a.pk)
            self.assertEqual(event.metadata["assessment_id"], self.exam.pk)
            for secret in (initial, reset, "pin_hash", "token_digest", "pbkdf2"):
                self.assertNotIn(secret, str(event.metadata))

    def test_audit_failure_rolls_back_credential_generation_and_reset(self):
        with patch("assessments.quick_services.record_event", side_effect=RuntimeError("Audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.issue()
        self.assertFalse(QuickExamCredential.objects.exists())
        self.issue()
        credential = QuickExamCredential.objects.get(candidate=self.no_account)
        old_hash = credential.pin_hash
        session = self.session(credential)
        with patch("assessments.quick_services.record_event", side_effect=RuntimeError("Audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.operation("reset")
        credential.refresh_from_db()
        self.assertEqual(credential.pin_hash, old_hash)
        self.assertEqual(credential.version, 1)
        self.assertTrue(session_is_current(session))

    def test_session_digest_unique_and_no_raw_token_field(self):
        self.issue()
        credential = QuickExamCredential.objects.get(candidate=self.no_account)
        session = self.session(credential)
        stored = QuickExamSession.objects.values().get(pk=session.pk)
        self.assertNotIn("test-only-token", str(stored))
        self.assertNotIn("token", stored)
        self.assertEqual(stored["credential_version"], 1)
        self.assertEqual(stored["configuration_version"], 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            QuickExamSession.objects.bulk_create([QuickExamSession(credential=credential, token_digest=session.token_digest, credential_version=1, configuration_version=1, expires_at=session.expires_at)])
        with self.assertRaises(DjangoValidationError):
            QuickExamSession.objects.create(credential=credential, token_digest="raw-token", credential_version=1, configuration_version=1, expires_at=session.expires_at)

    def test_session_expiry_revocation_and_live_candidate_state_are_checked(self):
        self.issue()
        credential = QuickExamCredential.objects.get(candidate=self.no_account)
        session = self.session(credential)
        self.assertFalse(session_is_current(session, now=session.expires_at + timedelta(seconds=1)))
        session.revoked_at = timezone.now()
        session.save()
        self.assertFalse(session_is_current(session))
        session.revoked_at = None
        session.save()
        self.no_account.status = "inactive"
        self.no_account.save()
        self.assertFalse(session_is_current(session))

    def test_candidate_deletion_cascades_quick_rows_but_leaves_user_and_config(self):
        self.issue(self.linked)
        credential = QuickExamCredential.objects.get(candidate=self.linked)
        self.session(credential)
        self.exam.candidate_assignments.get(candidate=self.linked).delete()
        response = self.client.delete(f"/api/v1/candidates/{self.linked.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(QuickExamCredential.objects.exists())
        self.assertFalse(QuickExamSession.objects.exists())
        self.assertTrue(User.objects.filter(pk=self.learner.pk).exists())
        self.assertTrue(QuickExamConfiguration.objects.filter(pk=self.config.pk).exists())

    def test_assessment_deletion_cascades_only_quick_rows(self):
        self.issue()
        self.session(QuickExamCredential.objects.get(candidate=self.no_account))
        self.assertEqual(self.client.delete(f"/api/v1/assessments/{self.exam.pk}/").status_code, 204)
        self.assertFalse(QuickExamConfiguration.objects.filter(pk=self.config.pk).exists())
        self.assertFalse(QuickExamCredential.objects.exists())
        self.assertFalse(QuickExamSession.objects.exists())
        self.assertTrue(Candidate.objects.filter(pk=self.no_account.pk).exists())

    def test_history_protection_survives_quick_credentials(self):
        self.issue()
        attempt, result = self.history()
        self.assertEqual(self.client.delete(f"/api/v1/candidates/{self.no_account.pk}/").status_code, 409)
        self.assertTrue(Attempt.objects.filter(pk=attempt.pk).exists())
        self.assertTrue(Result.objects.filter(pk=result.pk).exists())
        QuickExamCredential.objects.get(candidate=self.no_account).delete()
        self.assertTrue(Attempt.objects.filter(pk=attempt.pk).exists())
        self.assertTrue(Result.objects.filter(pk=result.pk).exists())

    def test_portal_account_can_coexist_with_quick_credentials(self):
        response = self.issue(self.linked)
        self.assertEqual(response.status_code, 201)
        self.client.force_authenticate(self.learner)
        self.assertEqual(self.client.get("/api/v1/candidate/me/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/candidate/me/exams/").status_code, 200)
        self.assertEqual(self.client.get(self.base()).status_code, 403)

    def test_session_csrf_and_staff_mutation_throttle_remain_enforced(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.base() + "credentials/", {"candidate": self.no_account.pk}, format="json", HTTP_X_INSTITUTION_ID=str(self.a.pk)).status_code, 403)
        for _ in range(60):
            self.assertEqual(self.operation("reset").status_code, 404)
        self.assertEqual(self.operation("reset").status_code, 429)

    def test_public_quick_routes_require_credentials_or_quick_session(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/v1/quick-exam/verify/", {}, format="json").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/quick-exam/session/").status_code, 401)
