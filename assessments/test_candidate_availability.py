from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from attempts.models import Attempt
from attempts.services import _validate_assessment_for_candidate, start_attempt
from attempts.tenancy import assessment_window_state
from .models import Assessment, AssessmentCandidate
from .serializers import AwareDateTimeField
from .test_quick_sessions import QuickSessionTests


LAGOS = ZoneInfo("Africa/Lagos")
START = datetime(2026, 10, 7, 11, 0, tzinfo=LAGOS)
END = datetime(2026, 10, 7, 12, 0, tzinfo=LAGOS)
INSIDE = datetime(2026, 10, 7, 11, 45, tzinfo=LAGOS)


@override_settings(USE_TZ=True, TIME_ZONE="UTC")
class CandidateAvailabilityTests(TestCase):
    PIN = QuickSessionTests.PIN
    make_question = staticmethod(QuickSessionTests.make_question)
    make_assessment = staticmethod(QuickSessionTests.make_assessment)

    @classmethod
    def setUpTestData(cls):
        with patch("django.utils.timezone.now", return_value=INSIDE):
            QuickSessionTests.setUpTestData.__func__(cls)
            for exam in (cls.assessment, cls.quick_assessment):
                Assessment.objects.filter(pk=exam.pk).update(status='draft')
                Assessment.objects.filter(pk=exam.pk).update(start_at=START, end_at=END, duration_minutes=5)
                exam.refresh_from_db()
            # Account and Quick delivery both use direct assignment in these fixtures.
            Assessment.objects.filter(pk=cls.assessment.pk).update(candidate_access="specific_candidates", group=None)
            cls.assessment.refresh_from_db()
            for exam, candidate in ((cls.assessment, cls.candidate), (cls.quick_assessment, cls.quick_candidate)):
                AssessmentCandidate.objects.create(assessment=exam, candidate=candidate, assigned_by=cls.admin)
                Assessment.objects.filter(pk=exam.pk).update(status='approved')
                exam.refresh_from_db()

    def setUp(self):
        cache.clear()
        self.clock = patch("django.utils.timezone.now", return_value=INSIDE)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.quick = APIClient(enforce_csrf_checks=True)
        self.quick.defaults["HTTP_X_CSRFTOKEN"] = self.quick.get("/api/v1/auth/csrf/").data["csrfToken"]
        response = self.quick.post("/api/v1/quick-exam/verify/", {
            "exam_code": self.configuration.exam_code, "candidate_id": self.quick_candidate.candidate_id,
            "pin": QuickSessionTests.PIN,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def summary(self):
        response = self.quick.get("/api/v1/quick-exam/session/")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["availability"]

    def test_aware_lagos_window_boundaries_shared_by_quick_and_account(self):
        cases = [(START - timedelta(microseconds=1), "upcoming"), (START, "open"),
                 (INSIDE, "open"), (END, "open"), (END + timedelta(microseconds=1), "ended")]
        for instant, expected in cases:
            for exam, candidate, mode in [(self.quick_assessment, self.quick_candidate, "quick"),
                                           (self.assessment, self.candidate, "portal")]:
                with self.subTest(instant=instant, mode=mode):
                    now = instant.astimezone(datetime_timezone.utc)
                    self.assertEqual(assessment_window_state(exam, now), expected)
                    if expected == "open":
                        self.assertTrue(_validate_assessment_for_candidate(exam, candidate, now, access_mode=mode))
                    else:
                        with self.assertRaises(PermissionDenied) as error:
                            _validate_assessment_for_candidate(exam, candidate, now, access_mode=mode)
                        self.assertEqual(error.exception.get_codes(), expected)

    def test_session_reason_agrees_with_window_at_each_boundary(self):
        cases = [(START - timedelta(seconds=1), "upcoming", False), (START, "available", True),
                 (INSIDE, "available", True), (END, "available", True), (END + timedelta(seconds=1), "ended", False)]
        for instant, state, can_start in cases:
            with self.subTest(instant=instant), patch("django.utils.timezone.now", return_value=instant):
                availability = self.summary()
                self.assertEqual(availability["state"], state)
                self.assertEqual(availability["can_start"], can_start)
                self.assertEqual(availability["reason"], None if can_start else state)
        self.assertFalse(Attempt.objects.exists())

    def assert_quick_start_at(self, instant):
        with patch("django.utils.timezone.now", return_value=instant):
            self.assertTrue(self.summary()["can_start"])
            response = self.quick.post("/api/v1/quick-exam/start/", {}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            attempt = Attempt.objects.get(pk=response.data["id"])
            self.assertEqual(attempt.candidate_id, self.quick_candidate.pk)
            self.assertEqual(attempt.started_at, instant)
            self.assertEqual(attempt.expires_at, instant + timedelta(minutes=5))

    def test_quick_assigned_candidate_starts_exactly_at_start(self):
        self.assert_quick_start_at(START)

    def test_quick_assigned_candidate_starts_inside_lagos_window(self):
        self.assert_quick_start_at(INSIDE)

    def test_quick_assigned_candidate_starts_exactly_at_inclusive_end(self):
        self.assert_quick_start_at(END)

    def test_quick_start_before_or_after_window_is_rejected_with_safe_reason(self):
        for instant, reason in ((START - timedelta(seconds=1), "upcoming"), (END + timedelta(seconds=1), "ended")):
            with patch("django.utils.timezone.now", return_value=instant):
                response = self.quick.post("/api/v1/quick-exam/start/", {}, format="json")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data["reason"], reason)
        self.assertFalse(Attempt.objects.exists())

    def test_account_assigned_candidate_starts_inside_same_lagos_window(self):
        portal = APIClient()
        portal.force_authenticate(self.user)
        response = portal.post("/api/v1/attempts/start/", {"assessment": self.assessment.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        attempt = Attempt.objects.get(pk=response.data["id"])
        self.assertEqual(attempt.started_at, INSIDE)
        self.assertEqual(attempt.expires_at, INSIDE + timedelta(minutes=5))

    def test_account_start_outside_same_window_is_rejected(self):
        for instant in (START - timedelta(seconds=1), END + timedelta(seconds=1)):
            with self.assertRaises(PermissionDenied):
                start_attempt(self.user, self.assessment.pk, now=instant)
        self.assertFalse(Attempt.objects.exists())

    def test_workflow_reason_overrides_open_window_without_weakening_lifecycle(self):
        for workflow in ("draft", "review", "archived"):
            Assessment.objects.filter(pk=self.quick_assessment.pk).update(status=workflow)
            availability = self.summary()
            self.assertEqual(availability["state"], "unavailable")
            self.assertEqual(availability["reason"], "not_open")
            self.assertEqual(availability["message"], "Exam is not open for candidates.")
            self.assertFalse(availability["can_start"])
            response = self.quick.post("/api/v1/quick-exam/start/", {}, format="json")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.data, {"detail": "Exam is not open for candidates.", "reason": "not_open"})
        for workflow in ("approved", "scheduled"):
            Assessment.objects.filter(pk=self.quick_assessment.pk).update(status=workflow)
            self.assertTrue(self.summary()["can_start"])
        self.assertFalse(Attempt.objects.exists())

    def test_exhausted_limit_remains_unavailable(self):
        Attempt.objects.create(institution=self.school, assessment=self.quick_assessment, candidate=self.quick_candidate,
            attempt_number=1, started_at=START, expires_at=START + timedelta(minutes=5), last_activity_at=START,
            status="submitted", submitted_at=START + timedelta(minutes=4))
        availability = self.summary()
        self.assertEqual(availability["reason"], "attempt_limit_reached")
        self.assertFalse(availability["can_start"])
        response = self.quick.post("/api/v1/quick-exam/start/", {}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["reason"], "attempt_limit_reached")
        self.assertEqual(Attempt.objects.count(), 1)

    def test_display_api_instants_match_stored_lagos_configuration_under_use_tz(self):
        response = self.quick.get("/api/v1/quick-exam/session/")
        data = response.json()
        self.assertEqual(data["assessment"]["timezone"], "Africa/Lagos")
        for key, expected in (("start_at", START), ("end_at", END)):
            value = datetime.fromisoformat(data["assessment"][key].replace("Z", "+00:00"))
            self.assertTrue(timezone.is_aware(value))
            self.assertEqual(value.astimezone(LAGOS), expected)
        self.quick_assessment.refresh_from_db()
        self.assertTrue(timezone.is_aware(self.quick_assessment.start_at))
        self.assertEqual(self.quick_assessment.start_at.astimezone(datetime_timezone.utc).hour, 10)
        self.assertTrue(data["availability"]["can_start"])

    def test_api_date_input_requires_offset_and_preserves_lagos_instant(self):
        field = AwareDateTimeField()
        with self.assertRaises(ValidationError):
            field.run_validation("2026-10-07T11:00:00")
        self.assertEqual(field.run_validation("2026-10-07T11:00:00+01:00"), START)

    def test_account_ineligible_candidate_gets_safe_reason(self):
        AssessmentCandidate.objects.filter(assessment=self.assessment).delete()
        with self.assertRaises(PermissionDenied) as error:
            start_attempt(self.user, self.assessment.pk, now=INSIDE)
        self.assertEqual(str(error.exception.detail), "Candidate is not eligible.")

    def test_invalid_question_configuration_is_safe_without_internal_details(self):
        self.quick_assessment.assessment_questions.all().delete()
        availability = self.summary()
        self.assertEqual(availability["reason"], "not_ready")
        self.assertEqual(availability["message"], "Exam is not ready for candidates.")
        response = self.quick.post("/api/v1/quick-exam/start/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": "Exam is not ready for candidates.", "reason": "not_ready"})
