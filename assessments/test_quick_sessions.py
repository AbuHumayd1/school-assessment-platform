import hashlib
import json
from datetime import timedelta
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.hashers import make_password
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.db import connections
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from attempts.models import Answer, Attempt, AttemptQuestionOption
from attempts.tests import CandidateAttemptAPITests, finish_fixture_exam, save_prepared_fixture
from audit.models import AuditEvent
from candidates.models import Candidate
from results.models import Result
from tenants.models import InstitutionMembership
from .models import Assessment, AssessmentCandidate, AssessmentQuestion, QuickExamConfiguration, QuickExamCredential, QuickExamSession
from .quick_services import configure_quick_access, reset_credential, revoke_credential
from .quick_sessions import COOKIE_NAME, COOKIE_PATH, INVALID_DETAILS, session_expiry


class QuickSessionTests(TestCase):
    PIN = "ABCDEFGHJK"
    base = "/api/v1/quick-exam/"
    make_question = staticmethod(CandidateAttemptAPITests.make_question)
    make_assessment = staticmethod(CandidateAttemptAPITests.make_assessment)

    @classmethod
    def setUpTestData(cls):
        CandidateAttemptAPITests.setUpTestData.__func__(cls)
        cls.admin = User.objects.create_user("quick-admin@example.test", "Safe-pass-8392")
        InstitutionMembership.objects.create(user=cls.admin, institution=cls.school, role="institution_admin")
        cls.quick_candidate = Candidate.objects.create(institution=cls.school, candidate_id="QUICK-001", first_name="Quick", last_name="Learner")
        cls.quick_assessment = cls.make_assessment(cls, institution=cls.school, subject=cls.subject, group=None,
            created_by=cls.staff, candidate_access="access_code", title="Quick assessment", randomize_questions=True, randomize_options=True)
        for position, question in enumerate((cls.mcq, cls.multi, cls.truefalse), 1):
            AssessmentQuestion.objects.create(assessment=cls.quick_assessment, question=question, order=position, marks=1)
        AssessmentCandidate.objects.create(assessment=cls.quick_assessment, candidate=cls.quick_candidate, assigned_by=cls.admin)
        finish_fixture_exam(cls.quick_assessment)
        cls.configuration = QuickExamConfiguration.objects.create(assessment=cls.quick_assessment, exam_code="PUBLIC-2026", enabled=True)
        cls.credential = QuickExamCredential.objects.create(configuration=cls.configuration, candidate=cls.quick_candidate, pin_hash=make_password(cls.PIN))

    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.csrf = self.client.get("/api/v1/auth/csrf/").data["csrfToken"]
        self.client.defaults["HTTP_X_CSRFTOKEN"] = self.csrf

    def verify(self, **extra):
        return self.client.post(self.base + "verify/", {"exam_code": self.configuration.exam_code, "candidate_id": self.quick_candidate.candidate_id, "pin": self.PIN, **extra}, format="json")

    def login_quick(self):
        response = self.verify()
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return QuickExamSession.objects.latest("pk")

    def begin(self):
        self.login_quick()
        response = self.client.post(self.base + "start/", {}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return Attempt.objects.get(pk=response.data["id"])

    def route(self, attempt, suffix=""):
        return self.base + f"attempt/{attempt.pk}/" + suffix

    def question_route(self, attempt, question, suffix=""):
        return self.route(attempt, f"questions/{question.pk}/" + suffix)

    def assert_generic(self, response):
        self.assertEqual(response.status_code, 401, response.data)
        self.assertEqual(response.data, {"detail": INVALID_DETAILS})
        self.assertNotIn(COOKIE_NAME, response.cookies)
        self.assertFalse(QuickExamSession.objects.exists())

    def test_valid_credentials_create_only_limited_session(self):
        users, memberships = User.objects.count(), InstitutionMembership.objects.count()
        self.login_quick()
        self.assertFalse(Attempt.objects.exists())
        self.assertFalse(Answer.objects.exists())
        self.assertEqual(User.objects.count(), users)
        self.assertEqual(InstitutionMembership.objects.count(), memberships)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.quick_candidate.refresh_from_db()
        self.assertIsNone(self.quick_candidate.user_id)
        self.assertEqual(self.quick_candidate.email, "")

    def test_exam_code_normalization_and_candidate_whitespace(self):
        response = self.verify(exam_code=" public-2026 ", candidate_id=" QUICK-001 ")
        self.assertEqual(response.status_code, 200)

    def test_assigned_candidate_with_valid_credential_can_start(self):
        attempt = self.begin()
        self.assertEqual(attempt.candidate_id, self.quick_candidate.pk)
        self.assertEqual(attempt.assessment_id, self.quick_assessment.pk)
        self.assertEqual(Attempt.objects.count(), 1)

    def test_unassigned_candidate_with_valid_credential_cannot_start(self):
        candidate = Candidate.objects.create(institution=self.school, candidate_id="QUICK-UNASSIGNED", first_name="Unassigned", last_name="Learner")
        QuickExamCredential.objects.create(configuration=self.configuration, candidate=candidate, pin_hash=make_password(self.PIN))
        self.assertEqual(self.verify(candidate_id=candidate.candidate_id).status_code, 200)
        response = self.client.post(self.base + "start/", {}, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data["reason"], "not_eligible")
        self.assertFalse(AssessmentCandidate.objects.filter(assessment=self.quick_assessment, candidate=candidate).exists())
        self.assertFalse(Attempt.objects.exists())
        self.assertFalse(Answer.objects.exists())
        self.assertFalse(Result.objects.exists())

    def test_wrong_code_candidate_and_pin_are_indistinguishable(self):
        for extra in ({"exam_code": "UNKNOWN"}, {"candidate_id": "OTHER"}, {"pin": "WRONG"}, {"exam_code": "INVALID/"}, {"exam_code": ""}):
            with self.subTest(extra=extra):
                cache.clear()
                self.assert_generic(self.verify(**extra))

    def test_revoked_credential_generic_failure(self):
        revoke_credential(self.configuration, self.quick_candidate, self.admin)
        self.assert_generic(self.verify())

    def test_expired_credential_generic_failure(self):
        QuickExamCredential.objects.filter(pk=self.credential.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assert_generic(self.verify())

    def test_inactive_candidate_generic_failure(self):
        Candidate.objects.filter(pk=self.quick_candidate.pk).update(status="inactive")
        self.assert_generic(self.verify())

    def test_disabled_configuration_generic_failure(self):
        QuickExamConfiguration.objects.filter(pk=self.configuration.pk).update(enabled=False)
        self.assert_generic(self.verify())

    def test_inactive_institution_generic_failure(self):
        type(self.school).objects.filter(pk=self.school.pk).update(is_active=False)
        self.assert_generic(self.verify())

    def test_wrong_access_mode_generic_failure(self):
        with self.assertRaises(ValidationError):
            Assessment.objects.filter(pk=self.quick_assessment.pk).update(candidate_access="assigned_group")
        self.assertEqual(self.verify().status_code, 200)

    def test_missing_credential_generic_failure(self):
        self.credential.delete()
        self.assert_generic(self.verify())

    def test_cross_tenant_credential_cannot_authenticate_even_if_corrupt(self):
        QuickExamCredential.objects.filter(pk=self.credential.pk).update(candidate=self.foreign_candidate)
        self.assert_generic(self.verify(candidate_id=self.foreign_candidate.candidate_id))

    def test_nonexistent_credentials_use_dummy_password_check(self):
        with patch("assessments.quick_sessions.check_password", return_value=False) as check, patch("assessments.quick_sessions.dummy_password_hash", return_value="dummy-hash"):
            self.assert_generic(self.verify(exam_code="UNKNOWN"))
        check.assert_called_once_with(self.PIN, "dummy-hash")

    def test_inactive_credentials_still_pay_hash_verification_cost(self):
        QuickExamConfiguration.objects.filter(pk=self.configuration.pk).update(enabled=False)
        with patch("assessments.quick_sessions.check_password", return_value=True) as check:
            self.assert_generic(self.verify())
        check.assert_called_once_with(self.PIN, self.credential.pin_hash)

    def test_public_input_rejects_internal_identity_fields(self):
        for field in ("institution", "candidate", "assessment", "user", "token"):
            self.assert_generic(self.verify(**{field: 1}))

    def test_malformed_json_shape_does_not_crash(self):
        for data in ([], [1], "text"):
            cache.clear()
            response = self.client.post(self.base + "verify/", data, format="json")
            self.assert_generic(response)

    def test_token_only_in_scoped_httponly_cookie_and_digest_storage(self):
        response = self.verify()
        self.assertEqual(response.data, {"verified": True})
        cookie = response.cookies[COOKIE_NAME]
        token = cookie.value
        self.assertEqual(len(token), 43)
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], COOKIE_PATH)
        session = QuickExamSession.objects.get()
        self.assertEqual(session.token_digest, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, str(QuickExamSession.objects.values().get()))
        self.assertNotIn(token, response.content.decode())
        self.assertIn("no-store", response["Cache-Control"])

    @override_settings(QUICK_EXAM_COOKIE_SECURE=True)
    def test_production_cookie_is_secure(self):
        self.assertTrue(self.verify().cookies[COOKIE_NAME]["secure"])

    def test_verification_audit_has_no_authentication_secrets(self):
        self.login_quick()
        token = self.client.cookies[COOKIE_NAME].value
        session = QuickExamSession.objects.get()
        events = AuditEvent.objects.filter(metadata__action="quick_session_created")
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.institution_id, self.school.pk)
        self.assertEqual(event.metadata["candidate_id"], self.quick_candidate.pk)
        serialized = json.dumps(list(AuditEvent.objects.values("metadata")))
        for secret in (self.PIN, self.credential.pin_hash, token, session.token_digest):
            self.assertNotIn(secret, serialized)

    def test_unknown_verification_failure_does_not_fabricate_audit(self):
        self.assert_generic(self.verify(exam_code="UNKNOWN"))
        self.assertFalse(AuditEvent.objects.exists())

    def test_reverification_replaces_session_without_rotating_pin_or_starting_attempt(self):
        first = self.login_quick()
        first_token = self.client.cookies[COOKIE_NAME].value
        second = self.login_quick()
        first.refresh_from_db()
        self.assertIsNotNone(first.revoked_at)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(QuickExamSession.objects.filter(revoked_at__isnull=True).count(), 1)
        self.credential.refresh_from_db()
        self.assertEqual(self.credential.pin_hash, type(self).credential.pin_hash)
        self.assertEqual(self.credential.version, 1)
        self.assertFalse(Attempt.objects.exists())
        self.client.cookies[COOKIE_NAME] = first_token
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_session_creation_audit_failure_rolls_back_replacement(self):
        first = self.login_quick()
        with patch("assessments.quick_sessions.record_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.verify()
        first.refresh_from_db()
        self.assertIsNone(first.revoked_at)
        self.assertEqual(QuickExamSession.objects.count(), 1)

    def test_verification_throttle_is_identifier_aware_without_global_lockout(self):
        for _ in range(5):
            self.assertEqual(self.verify(pin="WRONG").status_code, 401)
        self.assertEqual(self.verify().status_code, 429)
        self.credential.refresh_from_db()
        self.assertTrue(self.credential.active)
        # A different IP is not locked out by an attacker targeting this identity.
        self.client.defaults["REMOTE_ADDR"] = "192.0.2.20"
        self.assertEqual(self.verify().status_code, 200)

    def test_verification_ip_limit_covers_identifier_rotation(self):
        for number in range(10):
            self.assertEqual(self.verify(candidate_id=f"GUESS-{number}").status_code, 401)
        self.assertEqual(self.verify(candidate_id="ANOTHER").status_code, 429)

    def test_throttle_cache_keys_do_not_contain_pin_or_candidate_identity(self):
        self.verify(pin="WRONG")
        keys = " ".join(cache._cache.keys())
        self.assertNotIn(self.quick_candidate.candidate_id, keys)
        self.assertNotIn(self.configuration.exam_code, keys)
        self.assertNotIn("WRONG", keys)

    def test_cookie_recovers_context_after_refresh_with_safe_allowlist(self):
        self.login_quick()
        for _ in range(2):
            response = self.client.get(self.base + "session/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.data), {"candidate", "assessment", "availability"})
            self.assertEqual(set(response.data["candidate"]), {"candidate_id", "first_name", "last_name"})
            self.assertEqual(response.data["assessment"]["id"], self.quick_assessment.pk)
            self.assertTrue(response.data["availability"]["can_start"])
            self.assertIn("no-store", response["Cache-Control"])
            for field in ("pin_hash", "pin", "token", "token_digest", "correct_answer", "explanation", "email", "user"):
                self.assertNotIn('"' + field + '"', response.content.decode())
        self.assertFalse(Attempt.objects.exists())

    def test_missing_or_random_cookie_rejected(self):
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)
        for token in ("a" * 43, "x", "a" * 1000, "\u00e9" * 43):
            self.client.cookies[COOKIE_NAME] = token
            self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_expired_session_rejected(self):
        session = self.login_quick()
        QuickExamSession.objects.filter(pk=session.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_revoked_session_rejected(self):
        session = self.login_quick()
        QuickExamSession.objects.filter(pk=session.pk).update(revoked_at=timezone.now())
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_credential_version_mismatch_rejected(self):
        self.login_quick()
        QuickExamCredential.objects.filter(pk=self.credential.pk).update(version=2)
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_configuration_version_mismatch_rejected(self):
        self.login_quick()
        QuickExamConfiguration.objects.filter(pk=self.configuration.pk).update(session_version=2)
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_credential_revocation_invalidates_cookie(self):
        self.login_quick()
        revoke_credential(self.configuration, self.quick_candidate, self.admin)
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_credential_expiration_invalidates_cookie(self):
        self.login_quick()
        QuickExamCredential.objects.filter(pk=self.credential.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_reset_invalidates_cookie(self):
        self.login_quick()
        reset_credential(self.configuration, self.quick_candidate, self.admin)
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_configuration_disable_reenable_does_not_resurrect_cookie(self):
        self.login_quick()
        configure_quick_access(self.quick_assessment, self.admin, enabled=False)
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)
        configure_quick_access(self.quick_assessment, self.admin, enabled=True)
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_candidate_deactivation_invalidates_cookie(self):
        self.login_quick()
        Candidate.objects.filter(pk=self.quick_candidate.pk).update(status="inactive")
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_institution_deactivation_invalidates_cookie(self):
        self.login_quick()
        type(self.school).objects.filter(pk=self.school.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_corrupt_tenant_ownership_invalidates_cookie(self):
        self.login_quick()
        Candidate.objects.filter(pk=self.quick_candidate.pk).update(institution=self.other_school)
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)

    def test_quick_cookie_never_authenticates_portal_or_staff_endpoints(self):
        self.login_quick()
        for route in ("candidate/me/", "candidate/me/exams/", "attempts/", "memberships/", "candidates/", "auth/context/", "results/"):
            with self.subTest(route=route):
                self.assertIn(self.client.get("/api/v1/" + route).status_code, (401, 403))
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_invalid_quick_cookie_does_not_fall_back_to_normal_user(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)
        self.client.cookies[COOKIE_NAME] = "a" * 43
        self.assertEqual(self.client.get(self.base + "session/").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)

    def test_logout_revokes_current_session_and_is_idempotent(self):
        session = self.login_quick()
        response = self.client.post(self.base + "logout/", {}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.cookies[COOKIE_NAME]["max-age"], 0)
        self.assertEqual(response.cookies[COOKIE_NAME]["path"], COOKIE_PATH)
        session.refresh_from_db()
        self.assertIsNotNone(session.revoked_at)
        self.assertEqual(self.client.post(self.base + "logout/", {}, format="json").status_code, 204)
        self.assertEqual(AuditEvent.objects.filter(metadata__action="quick_session_revoked").count(), 1)

    def test_logout_preserves_normal_user_and_examination_state(self):
        attempt = self.begin()
        self.client.force_login(self.user)
        before = Attempt.objects.values().get(pk=attempt.pk)
        self.assertEqual(self.client.post(self.base + "logout/", {}, format="json").status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(Attempt.objects.values().get(pk=attempt.pk), before)
        self.assertFalse(Result.objects.exists())
        self.credential.refresh_from_db()
        self.assertTrue(self.credential.active)
        self.assertEqual(self.credential.version, 1)

    def test_csrf_required_even_for_anonymous_verification(self):
        self.client.defaults.pop("HTTP_X_CSRFTOKEN")
        self.assertEqual(self.verify().status_code, 403)
        self.assertFalse(QuickExamSession.objects.exists())

    def test_fresh_client_requires_bootstrap_cookie_and_matching_header(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(self.verify().status_code, 403)
        bootstrap = self.client.get('/api/v1/auth/csrf/')
        self.assertEqual(bootstrap.status_code, 200)
        self.assertIn('csrftoken', bootstrap.cookies)
        self.assertIn('no-store', bootstrap['Cache-Control'])
        self.client.defaults['HTTP_X_CSRFTOKEN'] = 'x' * 64
        self.assertEqual(self.verify().status_code, 403)
        self.assertFalse(QuickExamSession.objects.exists())
        self.client.defaults['HTTP_X_CSRFTOKEN'] = bootstrap.data['csrfToken']
        self.assertEqual(self.verify().status_code, 200)
        self.assertEqual(QuickExamSession.objects.count(), 1)
        self.assertFalse(Attempt.objects.exists())

    def test_matching_bootstrap_header_without_cookie_is_rejected(self):
        self.client.cookies.clear()
        self.assertEqual(self.verify().status_code, 403)
        self.assertFalse(QuickExamSession.objects.exists())

    def test_csrf_required_for_every_quick_mutation(self):
        attempt = self.begin()
        self.client.defaults.pop("HTTP_X_CSRFTOKEN")
        for method, route, data in (
            ("post", self.base + "start/", {}), ("post", self.base + "logout/", {}),
            ("put", self.question_route(attempt, self.mcq, "answer/"), {"selected_options": []}),
            ("patch", self.question_route(attempt, self.mcq, "answer/"), {"selected_options": []}),
            ("patch", self.question_route(attempt, self.mcq, "review/"), {"marked_for_review": True}),
            ("post", self.route(attempt, "integrity/"), {"signal": "page_hidden"}),
            ("post", self.route(attempt, "submit/"), {}),
        ):
            with self.subTest(route=route):
                self.assertEqual(getattr(self.client, method)(route, data, format="json").status_code, 403)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "in_progress")
        self.assertFalse(Answer.objects.exists())

    def test_cross_origin_verification_rejected(self):
        response = self.client.post(self.base + "verify/", {"exam_code": "PUBLIC-2026", "candidate_id": "QUICK-001", "pin": self.PIN}, format="json", HTTP_ORIGIN="https://evil.example")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(QuickExamSession.objects.exists())

    @override_settings(QUICK_EXAM_SESSION_BASE_SECONDS=28800, QUICK_EXAM_RECOVERY_BUFFER_SECONDS=7200)
    def test_session_lifetime_formula_and_long_exams(self):
        now = timezone.now()
        assessment = self.credential.configuration.assessment
        assessment.end_at = None
        self.assertEqual(session_expiry(self.credential, now), now + timedelta(hours=8))
        assessment.duration_minutes = 12 * 60
        self.assertEqual(session_expiry(self.credential, now), now + timedelta(hours=14))
        assessment.duration_minutes = 30
        assessment.end_at = now + timedelta(minutes=5)
        self.assertEqual(session_expiry(self.credential, now), assessment.end_at + timedelta(minutes=150))
        self.credential.expires_at = now + timedelta(minutes=10)
        self.assertEqual(session_expiry(self.credential, now), self.credential.expires_at)

    def test_session_lifetime_does_not_slide_on_reads(self):
        session = self.login_quick()
        original_expiry = session.expires_at
        self.client.get(self.base + "session/")
        session.refresh_from_db()
        self.assertEqual(session.expires_at, original_expiry)
        self.assertNotIn(COOKIE_NAME, self.client.get(self.base + "session/").cookies)

    def test_authenticated_availability_upcoming_ended_draft_and_limit(self):
        self.login_quick()
        for fields, state in (({"start_at": timezone.now() + timedelta(hours=1)}, "upcoming"),
                              ({"start_at": timezone.now() - timedelta(hours=2), "end_at": timezone.now() - timedelta(hours=1)}, "ended"),
                              ({"status": "draft"}, "unavailable")):
            Assessment.objects.filter(pk=self.quick_assessment.pk).update(status='draft')
            Assessment.objects.filter(pk=self.quick_assessment.pk).update(**fields)
            if fields.get('status') != 'draft':
                Assessment.objects.filter(pk=self.quick_assessment.pk).update(status='approved')
            response = self.client.get(self.base + "session/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["availability"]["state"], state)
            self.assertFalse(response.data["availability"]["can_start"])
            self.assertEqual(self.client.post(self.base + "start/", {}, format="json").status_code, 403)

    def test_start_uses_server_identity_without_assigned_group(self):
        attempt = self.begin()
        self.assertEqual(attempt.candidate_id, self.quick_candidate.pk)
        self.assertEqual(attempt.assessment_id, self.quick_assessment.pk)
        self.assertEqual(attempt.institution_id, self.school.pk)
        self.assertEqual(attempt.expires_at - attempt.started_at, timedelta(minutes=30))
        self.assertEqual(attempt.attempt_questions.count(), 3)

    def test_start_rejects_client_identity_or_timer_override(self):
        self.login_quick()
        for field in ("candidate", "candidate_id", "assessment", "assessment_id", "attempt_id", "started_at", "expires_at", "institution"):
            self.assertEqual(self.client.post(self.base + "start/", {field: 1}, format="json").status_code, 400)
        self.assertFalse(Attempt.objects.exists())

    def test_active_attempt_resumes_with_stable_timer_and_randomization(self):
        attempt = self.begin()
        questions = list(attempt.attempt_questions.values_list("question_id", "order"))
        options = list(AttemptQuestionOption.objects.filter(attempt_question__attempt=attempt).values_list("option_id", "order"))
        response = self.client.post(self.base + "start/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], attempt.pk)
        current = Attempt.objects.get(pk=attempt.pk)
        self.assertEqual(current.started_at, attempt.started_at)
        self.assertEqual(current.expires_at, attempt.expires_at)
        self.assertEqual(list(current.attempt_questions.values_list("question_id", "order")), questions)
        self.assertEqual(list(AttemptQuestionOption.objects.filter(attempt_question__attempt=attempt).values_list("option_id", "order")), options)

    def test_resume_precedes_new_start_window_eligibility(self):
        instant = timezone.now()
        self.quick_assessment.end_at = instant + timedelta(minutes=5)
        save_prepared_fixture(self.quick_assessment, update_fields=['end_at'])
        attempt = self.begin()
        with patch('django.utils.timezone.now', return_value=instant + timedelta(minutes=6)):
            self.assertTrue(self.client.get(self.base + "session/").data["availability"]["can_resume"])
            response = self.client.post(self.base + "start/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], attempt.pk)

    def test_resume_disabled_preserves_existing_engine_conflict(self):
        self.quick_assessment.resume_allowed = False
        save_prepared_fixture(self.quick_assessment, update_fields=['resume_allowed'])
        self.begin()
        self.assertEqual(self.client.post(self.base + "start/", {}, format="json").status_code, 409)

    def test_attempt_limit_counts_existing_candidate_assessment_history(self):
        self.quick_candidate.user = self.user
        self.quick_candidate.save()
        now = timezone.now()
        Attempt.objects.create(institution=self.school, assessment=self.quick_assessment, candidate=self.quick_candidate,
            attempt_number=1, started_at=now - timedelta(hours=1), expires_at=now - timedelta(minutes=30),
            last_activity_at=now, status="submitted", submitted_at=now)
        self.login_quick()
        self.assertEqual(self.client.post(self.base + "start/", {}, format="json").status_code, 403)
        self.assertEqual(Attempt.objects.count(), 1)
        self.assertEqual(self.client.get(self.base + "session/").data["availability"]["state"], "attempt_limit_reached")

    def test_portal_cannot_start_quick_assessment_merely_due_to_credential(self):
        portal_user = User.objects.create_user("quick-linked@example.test", "Safe-pass-8392")
        self.quick_candidate.user = portal_user
        self.quick_candidate.save()
        portal = APIClient()
        portal.force_authenticate(portal_user)
        self.assertEqual(portal.post("/api/v1/attempts/start/", {"assessment": self.quick_assessment.pk}, format="json").status_code, 403)
        self.begin()
        self.assertEqual(portal.post("/api/v1/attempts/start/", {"assessment": self.quick_assessment.pk}, format="json").status_code, 403)

    def test_normal_portal_session_cannot_bypass_quick_runner_authorization(self):
        portal_user = User.objects.create_user("quick-runner-linked@example.test", "Safe-pass-8392")
        self.quick_candidate.user = portal_user
        self.quick_candidate.save()
        attempt = self.begin()
        portal = APIClient()
        portal.force_authenticate(portal_user)
        self.assertEqual(portal.get("/api/v1/attempts/").data, [])
        for method, suffix, data in (
            ("get", "", None), ("get", "questions/", None),
            ("get", f"questions/{self.mcq.pk}/", None),
            ("put", f"questions/{self.mcq.pk}/answer/", {"selected_options": []}),
            ("patch", f"questions/{self.mcq.pk}/review/", {"marked_for_review": True}),
            ("post", "integrity/", {"signal": "page_hidden"}), ("post", "submit/", {}),
        ):
            route = f"/api/v1/attempts/{attempt.pk}/" + suffix
            response = getattr(portal, method)(route) if method == "get" else getattr(portal, method)(route, data, format="json")
            self.assertEqual(response.status_code, 404)
        revoke_credential(self.configuration, self.quick_candidate, self.admin)
        self.assertEqual(portal.post(f"/api/v1/attempts/{attempt.pk}/submit/", {}, format="json").status_code, 404)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "in_progress")
        self.assertFalse(Result.objects.exists())

    def test_safe_questions_navigation_and_current_attempt(self):
        attempt = self.begin()
        self.assertEqual(self.client.get(self.base + "attempt/").data["id"], attempt.pk)
        navigation = self.client.get(self.route(attempt, "questions/"))
        self.assertEqual(navigation.status_code, 200)
        self.assertEqual(len(navigation.data), 3)
        detail = self.client.get(self.question_route(attempt, self.mcq))
        self.assertEqual(detail.status_code, 200)
        for field in ("is_correct", "correct_answer", "explanation", "marks_available", "marks_obtained", "percentage"):
            self.assertNotIn('"' + field + '"', detail.content.decode())

    def test_current_attempt_missing_is_404(self):
        self.login_quick()
        self.assertEqual(self.client.get(self.base + "attempt/").status_code, 404)

    def test_answer_save_all_objective_types_and_clear(self):
        attempt = self.begin()
        for question in (self.mcq, self.multi, self.truefalse):
            ids = list(question.options.filter(is_correct=True).values_list("pk", flat=True))
            response = self.client.put(self.question_route(attempt, question, "answer/"), {"selected_options": ids}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(self.client.get(self.question_route(attempt, question)).data["selected_options"], sorted(ids))
        self.assertEqual(Answer.objects.filter(attempt=attempt).count(), 3)
        response = self.client.patch(self.question_route(attempt, self.multi, "answer/"), {"selected_options": []}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Answer.objects.filter(attempt=attempt, question=self.multi).exists())

    def test_answer_validation_reuses_existing_rules(self):
        attempt = self.begin()
        for ids in ([999999], list(self.multi.options.values_list("pk", flat=True)), list(self.mcq.options.values_list("pk", flat=True))):
            self.assertEqual(self.client.put(self.question_route(attempt, self.mcq, "answer/"), {"selected_options": ids}, format="json").status_code, 400)
        self.assertEqual(self.client.put(self.question_route(attempt, self.mcq, "answer/"), {"selected_options": [], "candidate": self.candidate.pk}, format="json").status_code, 400)

    def test_review_mark_and_unmark(self):
        attempt = self.begin()
        for marked in (True, False):
            response = self.client.patch(self.question_route(attempt, self.mcq, "review/"), {"marked_for_review": marked}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.get(self.question_route(attempt, self.mcq)).data["marked_for_review"], marked)

    def test_integrity_uses_existing_dedupe_and_page_hide_semantics(self):
        attempt = self.begin()
        route = self.route(attempt, "integrity/")
        def signal(value):
            return self.client.post(route, {"signal": value}, format="json")
        self.assertEqual(signal("page_hidden").data["interruption_count"], 1)
        self.assertTrue(signal("navigation_attempt").data["deduplicated"])
        self.assertEqual(signal("page_hide").data["interruption_count"], 1)
        signal("page_visible")
        self.assertEqual(signal("page_hidden").data["interruption_count"], 2)
        self.assertEqual(self.client.get(route).data["interruption_count"], 2)

    @override_settings(EXAM_INTEGRITY_INTERRUPTION_LIMIT=1)
    def test_integrity_auto_submit_preserves_answers_and_marks(self):
        attempt = self.begin()
        ids = list(self.mcq.options.filter(is_correct=True).values_list("pk", flat=True))
        self.client.put(self.question_route(attempt, self.mcq, "answer/"), {"selected_options": ids}, format="json")
        response = self.client.post(self.route(attempt, "integrity/"), {"signal": "page_hidden"}, format="json")
        self.assertTrue(response.data["automatically_submitted"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")
        self.assertTrue(Answer.objects.filter(attempt=attempt).exists())
        self.assertEqual(Result.objects.get(attempt=attempt).marks_obtained, 1)
        self.assertNotIn("marks_obtained", response.data)

    def test_manual_submit_reuses_marking_and_returns_no_hidden_score(self):
        attempt = self.begin()
        for question in (self.mcq, self.multi, self.truefalse):
            ids = list(question.options.filter(is_correct=True).values_list("pk", flat=True))
            self.client.put(self.question_route(attempt, question, "answer/"), {"selected_options": ids}, format="json")
        response = self.client.post(self.route(attempt, "submit/"), {}, format="json")
        self.assertEqual(response.status_code, 200)
        result = Result.objects.get(attempt=attempt)
        self.assertEqual(result.marks_obtained, 3)
        self.assertEqual(result.status, "provisional")
        for field in ("score", "result", "marks_obtained", "percentage", "grade", "passed"):
            self.assertNotIn(field, response.data)
        self.assertEqual(self.client.post(self.route(attempt, "submit/"), {}, format="json").status_code, 200)
        self.assertEqual(Result.objects.count(), 1)
        self.assertEqual(self.client.put(self.question_route(attempt, self.mcq, "answer/"), {"selected_options": []}, format="json").status_code, 409)
        self.assertEqual(self.client.patch(self.question_route(attempt, self.mcq, "review/"), {"marked_for_review": True}, format="json").status_code, 409)

    def test_existing_result_publication_modes_remain_authoritative(self):
        for visibility, release, expected in (("after_submission", "immediate", "published"), ("hidden", "immediate", "provisional"),
                                              ("after_submission", "approval_required", "provisional"), ("after_submission", "manual_release", "provisional"),
                                              ("scheduled_release", "immediate", "provisional")):
            with self.subTest(visibility=visibility, release=release):
                cache.clear()
                self.quick_assessment = self.make_assessment(self, institution=self.school, subject=self.subject,
                    group=None, created_by=self.staff, candidate_access='access_code',
                    result_visibility=visibility, result_release_mode=release)
                for position, question in enumerate((self.mcq, self.multi, self.truefalse), 1):
                    AssessmentQuestion.objects.create(assessment=self.quick_assessment, question=question, order=position, marks=1)
                AssessmentCandidate.objects.create(assessment=self.quick_assessment, candidate=self.quick_candidate, assigned_by=self.admin)
                finish_fixture_exam(self.quick_assessment)
                self.configuration = QuickExamConfiguration.objects.create(assessment=self.quick_assessment,
                    exam_code=f'POLICY-{self.quick_assessment.pk}', enabled=True)
                self.credential = QuickExamCredential.objects.create(configuration=self.configuration,
                    candidate=self.quick_candidate, pin_hash=make_password(self.PIN))
                self.login_quick()
                response = self.client.post(self.base + "start/", {}, format="json")
                self.assertEqual(response.status_code, 201)
                attempt = Attempt.objects.get(pk=response.data["id"])
                response = self.client.post(self.route(attempt, "submit/"), {}, format="json")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(Result.objects.get(attempt=attempt).status, expected)
                self.assertNotIn("result", response.data)

    def test_attempt_scope_blocks_other_candidate_assessment_and_tenant_on_all_routes(self):
        self.login_quick()
        now = timezone.now()
        for candidate, assessment in ((self.candidate, self.quick_assessment), (self.quick_candidate, self.assessment), (self.foreign_candidate, self.foreign_assessment)):
            other = Attempt.objects.create(institution=assessment.institution, assessment=assessment, candidate=candidate,
                attempt_number=1, started_at=now, expires_at=now + timedelta(minutes=30), last_activity_at=now)
            for method, route, data in (
                ("get", self.route(other), None), ("get", self.route(other, "questions/"), None),
                ("get", self.question_route(other, self.mcq), None),
                ("put", self.question_route(other, self.mcq, "answer/"), {"selected_options": []}),
                ("patch", self.question_route(other, self.mcq, "review/"), {"marked_for_review": True}),
                ("get", self.route(other, "integrity/"), None),
                ("post", self.route(other, "integrity/"), {"signal": "page_hidden"}),
                ("post", self.route(other, "submit/"), {}),
            ):
                with self.subTest(route=route):
                    response = getattr(self.client, method)(route) if method == "get" else getattr(self.client, method)(route, data, format="json")
                    self.assertEqual(response.status_code, 404)
            other.refresh_from_db()
            self.assertEqual(other.status, "in_progress")
        self.assertFalse(Result.objects.exists())

    def test_session_expiry_does_not_finalize_and_reverification_resumes(self):
        attempt = self.begin()
        before = Attempt.objects.values().get(pk=attempt.pk)
        QuickExamSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(self.route(attempt)).status_code, 401)
        self.assertEqual(Attempt.objects.values().get(pk=attempt.pk), before)
        self.assertFalse(Result.objects.exists())
        self.login_quick()
        response = self.client.post(self.base + "start/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], attempt.pk)
        self.assertEqual(Attempt.objects.count(), 1)

    def test_credential_revocation_does_not_finalize_active_attempt(self):
        attempt = self.begin()
        before = Attempt.objects.values().get(pk=attempt.pk)
        revoke_credential(self.configuration, self.quick_candidate, self.admin)
        self.assertEqual(self.client.post(self.route(attempt, "submit/"), {}, format="json").status_code, 401)
        self.assertEqual(Attempt.objects.values().get(pk=attempt.pk), before)
        self.assertFalse(Result.objects.exists())

    def test_attempt_deadline_still_expires_and_marks_through_existing_engine(self):
        attempt = self.begin()
        Attempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.put(self.question_route(attempt, self.mcq, "answer/"), {"selected_options": []}, format="json").status_code, 409)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "expired")
        self.assertTrue(Result.objects.filter(attempt=attempt).exists())
        self.assertEqual(self.client.post(self.base + "start/", {}, format="json").status_code, 403)

    def test_reset_after_request_resolution_is_rechecked_at_engine_boundary(self):
        attempt = self.begin()
        from attempts.services import lock_access_attempt
        from .quick_sessions import resolve_session
        context = resolve_session(token=self.client.cookies[COOKIE_NAME].value)
        reset_credential(self.configuration, self.quick_candidate, self.admin)
        from rest_framework.exceptions import AuthenticationFailed
        with self.assertRaises(AuthenticationFailed):
            lock_access_attempt(context, attempt.pk)

    def test_quick_wrappers_reuse_existing_runner_view_methods(self):
        from .quick_public_views import QuickAnswerView, QuickIntegrityView, QuickReviewView, QuickSubmitView
        from attempts.views import AttemptAnswerView, AttemptIntegrityView, AttemptReviewFlagView, AttemptSubmitView
        self.assertIs(QuickAnswerView.put, AttemptAnswerView.put)
        self.assertIs(QuickReviewView.patch, AttemptReviewFlagView.patch)
        self.assertIs(QuickIntegrityView.post, AttemptIntegrityView.post)
        self.assertIs(QuickSubmitView.post, AttemptSubmitView.post)

    def test_replaced_prestart_session_cannot_start_and_new_session_starts_only_once(self):
        first = self.login_quick()
        old = APIClient(enforce_csrf_checks=True)
        old.cookies = self.client.cookies.copy()
        old.defaults["HTTP_X_CSRFTOKEN"] = self.csrf
        self.login_quick()
        first.refresh_from_db()
        self.assertIsNotNone(first.revoked_at)
        self.assertEqual(old.post(self.base + "start/", {}, format="json").status_code, 401)
        first_start = self.client.post(self.base + "start/", {}, format="json")
        second_start = self.client.post(self.base + "start/", {}, format="json")
        self.assertEqual(first_start.status_code, 201)
        self.assertEqual(second_start.status_code, 200)
        self.assertEqual(first_start.data["id"], second_start.data["id"])
        self.assertEqual(Attempt.objects.count(), 1)

    def test_active_takeover_rejects_every_old_operation_and_preserves_answers_deadline_and_attempt(self):
        attempt = self.begin()
        selected = [self.mcq.options.first().pk]
        self.assertEqual(self.client.put(self.question_route(attempt, self.mcq, "answer/"), {"selected_options": selected}, format="json").status_code, 200)
        before = Attempt.objects.values().get(pk=attempt.pk)
        old = APIClient(enforce_csrf_checks=True)
        old.cookies = self.client.cookies.copy()
        old.defaults["HTTP_X_CSRFTOKEN"] = self.csrf
        for _ in range(2):
            self.login_quick()
        operations = [
            ("post", self.base + "start/", {}),
            ("get", self.route(attempt), None),
            ("get", self.route(attempt, "questions/"), None),
            ("get", self.question_route(attempt, self.mcq), None),
            ("put", self.question_route(attempt, self.mcq, "answer/"), {"selected_options": []}),
            ("patch", self.question_route(attempt, self.mcq, "review/"), {"marked_for_review": True}),
            ("post", self.route(attempt, "integrity/"), {"signal": "navigation_attempt"}),
            ("post", self.route(attempt, "submit/"), {}),
        ]
        for method, route, payload in operations:
            with self.subTest(method=method, route=route):
                response = getattr(old, method)(route) if payload is None else getattr(old, method)(route, payload, format="json")
                self.assertEqual(response.status_code, 401)
        self.assertEqual(Attempt.objects.values().get(pk=attempt.pk), before)
        self.assertFalse(Result.objects.exists())
        self.assertFalse(attempt.attempt_questions.get(question=self.mcq).marked_for_review)
        self.assertEqual(list(Answer.objects.get(attempt=attempt, question=self.mcq).selections.values_list("option_id", flat=True)), selected)
        self.assertTrue(self.client.get(self.base + "session/").data["availability"]["can_resume"])
        response = self.client.post(self.base + "start/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], attempt.pk)
        attempt.refresh_from_db()
        for field in ("started_at", "expires_at", "attempt_number"):
            self.assertEqual(getattr(attempt, field), before[field])
        self.assertEqual(Attempt.objects.count(), 1)
        self.assertEqual(QuickExamSession.objects.filter(revoked_at__isnull=True).count(), 1)

    def test_reverification_after_context_resolution_is_rechecked_before_engine_operation(self):
        from .quick_sessions import resolve_session
        from attempts.services import lock_access_attempt, start_access_attempt
        from rest_framework.exceptions import AuthenticationFailed
        attempt = self.begin()
        context = resolve_session(token=self.client.cookies[COOKIE_NAME].value)
        self.login_quick()
        with self.assertRaises(AuthenticationFailed):
            start_access_attempt(context)
        with self.assertRaises(AuthenticationFailed):
            lock_access_attempt(context, attempt.pk)
        self.assertEqual(Attempt.objects.count(), 1)


@skipUnlessDBFeature("has_select_for_update")
class QuickClientRaceTests(TransactionTestCase):
    PIN = QuickSessionTests.PIN
    make_question = staticmethod(CandidateAttemptAPITests.make_question)
    make_assessment = staticmethod(CandidateAttemptAPITests.make_assessment)

    def setUp(self):
        # Committed fixtures are visible to the independent worker connections.
        QuickSessionTests.setUpTestData.__func__(type(self))
        from .quick_sessions import verify_and_create_session
        _, self.token = verify_and_create_session(self.configuration.exam_code, self.quick_candidate.candidate_id, QuickSessionTests.PIN)

    def race(self, operation):
        barrier = Barrier(2)
        def worker():
            try:
                barrier.wait(timeout=15)
                return operation()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker) for _ in range(2)]
            return [future.result(timeout=30) for future in futures]

    def test_simultaneous_starts_use_one_attempt_and_preserve_the_deadline(self):
        from .quick_sessions import resolve_session
        from attempts.services import start_access_attempt
        def start():
            attempt, created = start_access_attempt(resolve_session(token=self.token))
            return attempt.pk, created, attempt.expires_at
        results = self.race(start)
        self.assertEqual(Attempt.objects.count(), 1)
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(results[0][2], results[1][2])
        self.assertEqual(sorted(row[1] for row in results), [False, True])

    def test_simultaneous_finalization_marks_once(self):
        from .quick_sessions import resolve_session
        from attempts.services import start_access_attempt, finalize_attempt, CompletionReason
        attempt, _ = start_access_attempt(resolve_session(token=self.token))
        def finish():
            _, finalized = finalize_attempt(attempt.pk, reason=CompletionReason.MANUAL)
            return finalized
        self.assertEqual(sorted(self.race(finish)), [False, True])
        self.assertEqual(Result.objects.filter(attempt=attempt).count(), 1)
