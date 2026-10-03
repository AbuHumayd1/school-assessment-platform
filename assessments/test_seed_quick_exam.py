import hashlib
import json
import re
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.hashers import check_password
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from assessments.management.commands.seed_quick_exam import ASSESSMENT_DESCRIPTION, ASSESSMENT_TITLE, EXAM_CODE
from assessments.models import Assessment, QuickExamConfiguration, QuickExamCredential, QuickExamSession
from assessments.quick_services import configure_quick_access, generate_credential, reset_credential, session_is_current, verify_credential
from attempts.models import Attempt, AttemptQuestion
from attempts.services import _validate_assessment_for_candidate
from audit.models import AuditEvent
from candidates.models import Candidate
from institutions.models import Institution
from questions.models import Question, QuestionOption
from results.models import Result
from subjects.models import Subject
from tenants.models import InstitutionMembership


COMMAND_MODULE = "assessments.management.commands.seed_quick_exam"


@override_settings(DEBUG=True)
class SeedQuickExamCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name="Demo Training Institute")
        cls.admin = User.objects.create_user("demo.admin@example.com", "test-only-password")
        cls.membership = InstitutionMembership.objects.create(
            user=cls.admin, institution=cls.institution, role=InstitutionMembership.Role.INSTITUTION_ADMIN,
        )
        cls.candidate = Candidate.objects.create(
            institution=cls.institution, candidate_id="TEST001", first_name="Test", last_name="Student",
        )

    def run_seed(self, **options):
        output = StringIO()
        call_command("seed_quick_exam", stdout=output, **options)
        return output.getvalue()

    def fixture(self):
        assessment = Assessment.objects.get(institution=self.institution, title=ASSESSMENT_TITLE)
        configuration = QuickExamConfiguration.objects.get(assessment=assessment)
        credential = QuickExamCredential.objects.get(configuration=configuration, candidate=self.candidate)
        return assessment, configuration, credential

    def pin(self, output):
        match = re.search(r"^Access PIN: ([A-Z0-9]+)$", output, flags=re.MULTILINE)
        self.assertIsNotNone(match)
        return match.group(1)

    def history(self, assessment):
        now = timezone.now()
        return Attempt.objects.create(
            institution=self.institution, assessment=assessment, candidate=self.candidate,
            attempt_number=1, started_at=now, expires_at=now + timedelta(minutes=30), last_activity_at=now,
        )

    @override_settings(DEBUG=False)
    def test_debug_only_protection_prevents_writes_and_service_calls(self):
        with patch(f"{COMMAND_MODULE}.generate_credential") as generate, patch(f"{COMMAND_MODULE}.configure_quick_access") as configure:
            with self.assertRaisesMessage(CommandError, "DEBUG=True"):
                self.run_seed(reset=True)
        generate.assert_not_called()
        configure.assert_not_called()
        self.assertFalse(Assessment.objects.exists())
        self.assertFalse(Question.objects.exists())

    def test_creates_a_real_immediately_available_assessment_with_all_objective_types(self):
        self.run_seed()
        assessment, _, _ = self.fixture()
        self.assertEqual(assessment.description, ASSESSMENT_DESCRIPTION)
        self.assertEqual(assessment.institution, self.institution)
        self.assertEqual(assessment.status, Assessment.Status.SCHEDULED)
        self.assertEqual(assessment.duration_minutes, 30)
        self.assertTrue(assessment.resume_allowed)
        self.assertLess(assessment.start_at, timezone.now())
        self.assertGreater(assessment.end_at, timezone.now())
        self.assertEqual(set(assessment.assessment_questions.values_list("question__question_type", flat=True)), {
            Question.Type.MULTIPLE_CHOICE, Question.Type.MULTIPLE_SELECT, Question.Type.TRUE_FALSE,
        })
        self.assertEqual(Question.objects.filter(status=Question.Status.APPROVED).count(), 3)
        assessment.full_clean()
        assessment.validate_configuration(require_questions=True, require_schedule=True)

    def test_access_code_delivery_passes_existing_quick_engine_validation(self):
        self.run_seed()
        assessment, _, _ = self.fixture()
        self.assertEqual(assessment.candidate_access, Assessment.CandidateAccess.ACCESS_CODE)
        rows = _validate_assessment_for_candidate(assessment, self.candidate, timezone.now(), access_mode="quick")
        self.assertEqual(len(rows), 3)
        self.assertEqual(assessment.total_marks, 6)

    def test_uses_test001_without_creating_or_requiring_a_login(self):
        output = self.run_seed()
        _, _, credential = self.fixture()
        self.assertEqual(credential.candidate_id, self.candidate.pk)
        self.assertIn("Candidate ID: TEST001", output)
        self.candidate.refresh_from_db()
        self.assertIsNone(self.candidate.user_id)
        self.assertEqual(User.objects.count(), 1)

    def test_configures_access_through_existing_service_with_canonical_unique_code(self):
        with patch(f"{COMMAND_MODULE}.configure_quick_access", wraps=configure_quick_access) as configure:
            self.run_seed()
        configure.assert_called_once()
        self.assertEqual(configure.call_args.args[1], self.admin)
        self.assertEqual(configure.call_args.kwargs, {"exam_code": EXAM_CODE, "enabled": True})
        _, configuration, _ = self.fixture()
        self.assertEqual(configuration.exam_code, "DEMO-QUICK-01")
        self.assertTrue(configuration.enabled)

    def test_generates_credentials_only_through_existing_lifecycle_service(self):
        with patch(f"{COMMAND_MODULE}.generate_credential", wraps=generate_credential) as generate:
            self.run_seed()
        generate.assert_called_once()
        self.assertEqual(generate.call_args.args[1], self.candidate)
        self.assertEqual(generate.call_args.args[2], self.admin)

    def test_first_creation_prints_the_one_time_plaintext_pin_once_and_safe_test_block(self):
        output = self.run_seed()
        pin = self.pin(output)
        _, _, credential = self.fixture()
        self.assertTrue(verify_credential(credential, pin))
        self.assertEqual(output.count(pin), 1)
        self.assertIn("Quick Exam development access ready", output)
        self.assertIn("Exam Code: DEMO-QUICK-01", output)
        self.assertIn("http://localhost:5173/take-exam", output)
        self.assertIn("Use --reset to issue a new one", output)
        self.assertNotIn(credential.pin_hash, output)
        self.assertNotIn("token_digest", output)
        self.assertNotIn("Assessment ID:", output)

    def test_only_hash_persists_and_audit_metadata_contains_no_plaintext_secret(self):
        pin = self.pin(self.run_seed())
        _, _, credential = self.fixture()
        self.assertNotEqual(credential.pin_hash, pin)
        self.assertTrue(check_password(pin, credential.pin_hash))
        self.assertNotIn(pin, json.dumps(list(QuickExamCredential.objects.values()), default=str))
        self.assertNotIn(pin, json.dumps(list(AuditEvent.objects.values_list("metadata", flat=True))))

    def test_rerun_without_reset_does_not_rotate_or_redisplay_credentials(self):
        first_pin = self.pin(self.run_seed())
        _, _, credential = self.fixture()
        before = (credential.pin_hash, credential.version, credential.generated_at)
        with patch(f"{COMMAND_MODULE}.generate_credential") as generate, patch(f"{COMMAND_MODULE}.reset_credential") as reset:
            output = self.run_seed()
        generate.assert_not_called()
        reset.assert_not_called()
        credential.refresh_from_db()
        self.assertEqual((credential.pin_hash, credential.version, credential.generated_at), before)
        self.assertIn("Credential already exists. Its PIN cannot be redisplayed.", output)
        self.assertNotIn("Access PIN:", output)
        self.assertNotIn(first_pin, output)
        self.assertTrue(verify_credential(credential, first_pin))

    def test_explicit_reset_uses_service_and_outputs_a_new_valid_pin_once(self):
        old_pin = self.pin(self.run_seed())
        with patch(f"{COMMAND_MODULE}.reset_credential", wraps=reset_credential) as reset:
            output = self.run_seed(reset=True)
        reset.assert_called_once()
        self.assertEqual(reset.call_args.kwargs, {"expires_at": None})
        new_pin = self.pin(output)
        _, _, credential = self.fixture()
        self.assertNotEqual(old_pin, new_pin)
        self.assertTrue(verify_credential(credential, new_pin))
        self.assertEqual(credential.version, 2)
        self.assertEqual(output.count(new_pin), 1)
        self.assertNotIn(old_pin, output)

    def test_reset_invalidates_old_pin_and_existing_session_without_creating_a_session(self):
        old_pin = self.pin(self.run_seed())
        _, configuration, credential = self.fixture()
        session = QuickExamSession.objects.create(
            credential=credential, token_digest=hashlib.sha256(b"command-test-session").hexdigest(),
            credential_version=credential.version, configuration_version=configuration.session_version,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(session_is_current(session))
        self.run_seed(reset=True)
        credential.refresh_from_db()
        session.refresh_from_db()
        self.assertFalse(verify_credential(credential, old_pin))
        self.assertFalse(check_password(old_pin, credential.pin_hash))
        self.assertIsNotNone(session.revoked_at)
        self.assertFalse(session_is_current(session))
        self.assertEqual(QuickExamSession.objects.count(), 1)

    def test_never_creates_an_attempt_or_result_or_starts_the_timer(self):
        self.run_seed()
        self.run_seed(reset=True)
        self.assertEqual(Attempt.objects.count(), 0)
        self.assertEqual(AttemptQuestion.objects.count(), 0)
        self.assertEqual(Result.objects.count(), 0)

    def test_never_creates_a_quick_session(self):
        self.run_seed()
        self.run_seed()
        self.run_seed(reset=True)
        self.assertEqual(QuickExamSession.objects.count(), 0)

    def test_reruns_do_not_duplicate_institutions_candidates_or_users(self):
        self.run_seed()
        self.run_seed(reset=True)
        self.assertEqual(Institution.objects.count(), 1)
        self.assertEqual(Candidate.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    def test_assessment_questions_options_and_relationships_are_idempotent(self):
        self.run_seed()
        assessment, _, credential = self.fixture()
        rows = list(assessment.assessment_questions.values_list("pk", "question_id", "order", "marks"))
        question_ids = list(Question.objects.values_list("pk", flat=True))
        option_ids = list(QuestionOption.objects.values_list("pk", flat=True))
        self.run_seed()
        self.assertEqual(Assessment.objects.count(), 1)
        self.assertEqual(QuickExamConfiguration.objects.count(), 1)
        self.assertEqual(QuickExamCredential.objects.count(), 1)
        self.assertEqual(list(assessment.assessment_questions.values_list("pk", "question_id", "order", "marks")), rows)
        self.assertEqual(list(Question.objects.values_list("pk", flat=True)), question_ids)
        self.assertEqual(list(QuestionOption.objects.values_list("pk", flat=True)), option_ids)
        self.assertEqual(self.fixture()[2].pk, credential.pk)

    def test_reuses_existing_demo_seed_data_without_touching_portal_question_history(self):
        user = User.objects.create_user("teststudent@example.com", "test-only-password")
        self.candidate.user = user
        self.candidate.save()
        call_command("seed_demo_assessment", stdout=StringIO())
        portal_exam = Assessment.objects.get(title="Backend Fundamentals Practice Assessment")
        attempt = self.history(portal_exam)
        question = portal_exam.assessment_questions.first().question
        AttemptQuestion.objects.create(attempt=attempt, question=question, order=1, marks_available=2)
        before = list(Question.objects.order_by("pk").values_list("pk", "updated_at"))
        self.run_seed()
        self.assertEqual(Question.objects.count(), 9)
        self.assertEqual(list(Question.objects.order_by("pk").values_list("pk", "updated_at")), before)
        self.assertEqual(Assessment.objects.count(), 3)
        self.assertEqual(Attempt.objects.count(), 1)

    def test_reset_after_browser_attempt_preserves_frozen_assessment_and_question_configuration(self):
        self.run_seed()
        assessment, _, _ = self.fixture()
        attempt = self.history(assessment)
        AttemptQuestion.objects.create(attempt=attempt, question=assessment.assessment_questions.first().question, order=1, marks_available=2)
        before = (assessment.start_at, assessment.end_at, assessment.duration_minutes, assessment.updated_at)
        questions = list(Question.objects.values_list("pk", "updated_at"))
        self.run_seed(reset=True)
        assessment.refresh_from_db()
        self.assertEqual((assessment.start_at, assessment.end_at, assessment.duration_minutes, assessment.updated_at), before)
        self.assertEqual(list(Question.objects.values_list("pk", "updated_at")), questions)
        self.assertEqual(Attempt.objects.count(), 1)

    def test_missing_or_inactive_candidate_is_not_created_or_reactivated(self):
        self.candidate.status = Candidate.Status.INACTIVE
        self.candidate.save()
        with self.assertRaisesMessage(CommandError, "inactive"):
            self.run_seed()
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.Status.INACTIVE)
        self.candidate.delete()
        with self.assertRaisesMessage(CommandError, "was not found"):
            self.run_seed()
        self.assertEqual(Candidate.objects.count(), 0)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Assessment.objects.count(), 0)

    def test_inactive_institution_and_missing_admin_are_not_reactivated_or_granted_access(self):
        self.institution.is_active = False
        self.institution.save()
        with self.assertRaisesMessage(CommandError, "inactive"):
            self.run_seed()
        self.institution.is_active = True
        self.institution.save()
        self.membership.is_active = False
        self.membership.save()
        with self.assertRaisesMessage(CommandError, "active demo.admin@example.com"):
            self.run_seed()
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.is_active)
        self.assertEqual(Assessment.objects.count(), 0)

    def test_global_exam_code_collision_rolls_back_seed_without_reassigning_other_assessment(self):
        subject = Subject.objects.create(institution=self.institution, name="Existing subject", code="OTHER")
        assessment = Assessment.objects.create(
            institution=self.institution, subject=subject, title="Unrelated examination",
            assessment_type=Assessment.Type.QUIZ, duration_minutes=10,
            candidate_access=Assessment.CandidateAccess.ACCESS_CODE, created_by=self.admin,
        )
        configuration, _ = configure_quick_access(assessment, self.admin, exam_code=EXAM_CODE, enabled=True)
        with self.assertRaises(CommandError):
            self.run_seed()
        configuration.refresh_from_db()
        self.assertEqual(configuration.assessment, assessment)
        self.assertEqual(Assessment.objects.count(), 1)
        self.assertEqual(Question.objects.count(), 0)
        self.assertEqual(QuickExamCredential.objects.count(), 0)

    def test_title_collision_refuses_to_overwrite_unrelated_assessment(self):
        subject = Subject.objects.create(institution=self.institution, name="Existing subject", code="OTHER")
        assessment = Assessment.objects.create(
            institution=self.institution, subject=subject, title=ASSESSMENT_TITLE,
            description="Not seed-owned", assessment_type=Assessment.Type.QUIZ,
            duration_minutes=10, created_by=self.admin,
        )
        with self.assertRaisesMessage(CommandError, "different data"):
            self.run_seed()
        assessment.refresh_from_db()
        self.assertEqual(assessment.description, "Not seed-owned")
        self.assertEqual(Question.objects.count(), 0)
        self.assertEqual(QuickExamConfiguration.objects.count(), 0)
