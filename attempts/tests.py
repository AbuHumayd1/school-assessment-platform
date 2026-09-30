from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from assessments.models import Assessment, AssessmentQuestion
from candidates.models import Candidate
from groups.models import Group, GroupMembership
from institutions.models import Institution
from questions.models import Question, QuestionOption
from subjects.models import Subject
from tenants.models import InstitutionMembership
from .models import Answer, AnswerSelection, Attempt, AttemptQuestion, AttemptQuestionOption
from .services import start_attempt


class CandidateAttemptAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.school = Institution.objects.create(name="Attempt Academy", timezone="Africa/Lagos")
        cls.other_school = Institution.objects.create(name="Other Attempt Academy")
        cls.subject = Subject.objects.create(institution=cls.school, name="Mathematics", code="MATH")
        cls.other_subject = Subject.objects.create(institution=cls.other_school, name="Mathematics", code="MATH")
        cls.group = Group.objects.create(institution=cls.school, name="Cohort", code="C1")
        cls.other_group = Group.objects.create(institution=cls.other_school, name="Other cohort", code="C1")
        cls.user = User.objects.create_user("candidate@example.test", "Safe-pass-8392")
        cls.other_user = User.objects.create_user("othercandidate@example.test", "Safe-pass-8392")
        cls.foreign_user = User.objects.create_user("foreigncandidate@example.test", "Safe-pass-8392")
        cls.staff = User.objects.create_user("examiner@example.test", "Safe-pass-8392")
        InstitutionMembership.objects.create(user=cls.user, institution=cls.school, role="student")
        InstitutionMembership.objects.create(user=cls.foreign_user, institution=cls.other_school, role="student")
        InstitutionMembership.objects.create(user=cls.staff, institution=cls.school, role="examiner")
        cls.candidate = Candidate.objects.create(
            institution=cls.school, user=cls.user, candidate_id="C-001", first_name="Ada", last_name="Learner",
        )
        cls.other_candidate = Candidate.objects.create(
            institution=cls.school, user=cls.other_user, candidate_id="C-002", first_name="Ben", last_name="Learner",
        )
        cls.foreign_candidate = Candidate.objects.create(
            institution=cls.other_school, user=cls.foreign_user, candidate_id="C-003", first_name="Cam", last_name="Learner",
        )
        GroupMembership.objects.create(candidate=cls.candidate, group=cls.group, is_active=True)
        GroupMembership.objects.create(candidate=cls.other_candidate, group=cls.group, is_active=True)
        GroupMembership.objects.create(candidate=cls.foreign_candidate, group=cls.other_group, is_active=True)
        cls.mcq = cls.make_question(cls, cls.school, cls.subject, Question.Type.MULTIPLE_CHOICE, "What is 2 + 2?", 1)
        cls.mcq_two = cls.make_question(cls, cls.school, cls.subject, Question.Type.MULTIPLE_CHOICE, "What is 3 + 3?", 1)
        cls.multi = cls.make_question(cls, cls.school, cls.subject, Question.Type.MULTIPLE_SELECT, "Select prime numbers", 1)
        cls.truefalse = cls.make_question(cls, cls.school, cls.subject, Question.Type.TRUE_FALSE, "The sky is blue", 1)
        cls.foreign_q = cls.make_question(cls, cls.other_school, cls.other_subject, Question.Type.MULTIPLE_CHOICE, "Foreign question", 1)
        cls.assessment = cls.make_assessment(cls, institution=cls.school, subject=cls.subject, group=cls.group, created_by=cls.staff)
        for position, question in enumerate((cls.mcq, cls.mcq_two, cls.multi, cls.truefalse), 1):
            AssessmentQuestion.objects.create(assessment=cls.assessment, question=question, order=position, marks=Decimal("1.00"))
        cls.foreign_assessment = cls.make_assessment(cls, institution=cls.other_school, subject=cls.other_subject, group=cls.other_group, created_by=cls.staff)
        AssessmentQuestion.objects.create(assessment=cls.foreign_assessment, question=cls.foreign_q, order=1, marks=Decimal("1.00"))

    @staticmethod
    def make_question(cls, institution, subject, question_type, text, correct_order):
        q = Question.objects.create(
            institution=institution, subject=subject, question_type=question_type, text=text,
            created_by=cls.staff, status=Question.Status.APPROVED,
        )
        count = 2 if question_type == Question.Type.TRUE_FALSE else 3
        for index in range(1, count + 1):
            QuestionOption.objects.create(
                question=q, text=f"{text} option {index}", order=index,
                is_correct=index == correct_order or (question_type == Question.Type.MULTIPLE_SELECT and index == 3),
            )
        return q

    @staticmethod
    def make_assessment(cls, institution, subject, group, created_by, **kwargs):
        values = dict(
            institution=institution, title="Term assessment", assessment_type=Assessment.Type.TERM_EXAM,
            subject=subject, group=group, duration_minutes=30, attempt_limit=1,
            candidate_access=Assessment.CandidateAccess.ASSIGNED_GROUP,
            status=Assessment.Status.SCHEDULED, created_by=created_by,
            start_at=timezone.now() - timedelta(hours=1), end_at=timezone.now() + timedelta(hours=2),
        )
        values.update(kwargs)
        return Assessment.objects.create(**values)

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.base = "/api/v1/attempts/"

    def start(self, assessment=None, **extra):
        data = {"assessment": (assessment or self.assessment).pk, **extra}
        return self.client.post(f"{self.base}start/", data, format="json")

    def begin(self, assessment=None):
        response = self.start(assessment)
        self.assertIn(response.status_code, (200, 201), response.data)
        return Attempt.objects.get(pk=response.data["id"])

    def question_url(self, attempt, question=None, suffix=""):
        return f"{self.base}{attempt.pk}/questions/{(question or self.mcq).pk}/{suffix}"

    def answer(self, attempt, question, option_ids):
        return self.client.put(self.question_url(attempt, question, "answer/"), {"selected_options": option_ids}, format="json")

    def test_eligible_candidate_starts(self):
        response = self.start()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "in_progress")

    def test_attempt_is_owned_by_linked_candidate(self):
        attempt = self.begin()
        self.assertEqual(attempt.candidate_id, self.candidate.pk)

    def test_inactive_candidate_cannot_start(self):
        self.candidate.status = Candidate.Status.INACTIVE
        self.candidate.save(update_fields=("status",))
        self.assertEqual(self.start().status_code, 403)

    def test_account_without_candidate_profile_cannot_start(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.start().status_code, 403)

    def test_candidate_must_be_active_group_member(self):
        GroupMembership.objects.filter(candidate=self.candidate).update(is_active=False)
        self.assertEqual(self.start().status_code, 403)

    def test_future_dated_group_membership_is_ineligible(self):
        GroupMembership.objects.filter(candidate=self.candidate).update(start_date=timezone.localdate() + timedelta(days=1))
        self.assertEqual(self.start().status_code, 403)

    def test_expired_group_membership_is_ineligible(self):
        GroupMembership.objects.filter(candidate=self.candidate).update(end_date=timezone.localdate() - timedelta(days=1))
        self.assertEqual(self.start().status_code, 403)

    def test_wrong_tenant_assessment_is_hidden(self):
        self.assertEqual(self.start(self.foreign_assessment).status_code, 404)

    def test_draft_assessment_cannot_start(self):
        a = self.make_assessment(self, self.school, self.subject, self.group, self.staff, status=Assessment.Status.DRAFT)
        AssessmentQuestion.objects.create(assessment=a, question=self.mcq, order=1, marks=1)
        self.assertEqual(self.start(a).status_code, 403)

    def test_review_assessment_cannot_start(self):
        a = self.make_assessment(self, self.school, self.subject, self.group, self.staff, status=Assessment.Status.REVIEW)
        AssessmentQuestion.objects.create(assessment=a, question=self.mcq, order=1, marks=1)
        self.assertEqual(self.start(a).status_code, 403)

    def test_archived_assessment_cannot_start(self):
        a = self.make_assessment(self, self.school, self.subject, self.group, self.staff, status=Assessment.Status.ARCHIVED)
        AssessmentQuestion.objects.create(assessment=a, question=self.mcq, order=1, marks=1)
        self.assertEqual(self.start(a).status_code, 403)

    def test_approved_assessment_can_start(self):
        a = self.make_assessment(self, self.school, self.subject, self.group, self.staff, status=Assessment.Status.APPROVED)
        AssessmentQuestion.objects.create(assessment=a, question=self.mcq, order=1, marks=1)
        self.assertEqual(self.start(a).status_code, 201)

    def test_start_before_start_at_rejected(self):
        self.assessment.start_at = timezone.now() + timedelta(hours=1)
        self.assessment.save(update_fields=("start_at",))
        self.assertEqual(self.start().status_code, 403)

    def test_start_after_end_at_rejected(self):
        self.assessment.end_at = timezone.now() - timedelta(seconds=1)
        self.assessment.save(update_fields=("end_at",))
        self.assertEqual(self.start().status_code, 403)

    def test_assessment_without_questions_cannot_start(self):
        a = self.make_assessment(self, self.school, self.subject, self.group, self.staff)
        self.assertEqual(self.start(a).status_code, 400)

    def test_invalid_duration_assessment_cannot_start(self):
        a = self.make_assessment(self, self.school, self.subject, self.group, self.staff, duration_minutes=0)
        AssessmentQuestion.objects.create(assessment=a, question=self.mcq, order=1, marks=1)
        self.assertEqual(self.start(a).status_code, 400)

    def test_specific_candidate_access_is_not_enabled(self):
        self.assessment.candidate_access = Assessment.CandidateAccess.SPECIFIC_CANDIDATES
        self.assessment.save(update_fields=("candidate_access",))
        self.assertEqual(self.start().status_code, 403)

    def test_access_code_mode_is_not_enabled(self):
        self.assessment.candidate_access = Assessment.CandidateAccess.ACCESS_CODE
        self.assessment.save(update_fields=("candidate_access",))
        self.assertEqual(self.start().status_code, 403)

    def test_attempt_number_starts_at_one(self):
        self.assertEqual(self.begin().attempt_number, 1)

    def test_attempt_number_increments_for_same_candidate_and_assessment(self):
        first = self.begin()
        first.status = Attempt.Status.SUBMITTED
        first.submitted_at = timezone.now()
        first.save(update_fields=("status", "submitted_at"))
        self.assessment.attempt_limit = 2
        self.assessment.save(update_fields=("attempt_limit",))
        second = self.begin()
        self.assertEqual(second.attempt_number, 2)

    def test_different_candidate_starts_at_attempt_one(self):
        self.client.force_authenticate(self.other_user)
        response = self.start()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["id"], Attempt.objects.get(candidate=self.other_candidate).pk)
        self.assertEqual(Attempt.objects.get(candidate=self.other_candidate).attempt_number, 1)

    def test_attempt_limit_one_blocks_second_started_attempt(self):
        first = self.begin()
        first.status = Attempt.Status.SUBMITTED
        first.save(update_fields=("status",))
        self.assertEqual(self.start().status_code, 403)

    def test_attempt_limit_two_allows_second_attempt(self):
        first = self.begin()
        first.status = Attempt.Status.SUBMITTED
        first.save(update_fields=("status",))
        self.assessment.attempt_limit = 2
        self.assessment.save(update_fields=("attempt_limit",))
        self.assertEqual(self.start().status_code, 201)

    def test_duplicate_start_returns_existing_attempt(self):
        first = self.start()
        second = self.start()
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Attempt.objects.filter(candidate=self.candidate, assessment=self.assessment).count(), 1)

    def test_active_attempt_is_resumed_when_resume_allowed(self):
        attempt = self.begin()
        response = self.start()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], attempt.pk)

    def test_active_attempt_not_resumed_when_resume_disabled(self):
        self.begin()
        self.assessment.resume_allowed = False
        self.assessment.save(update_fields=("resume_allowed",))
        self.assertEqual(self.start().status_code, 409)

    def test_client_cannot_choose_candidate_or_attempt_number(self):
        response = self.start(candidate=self.candidate.pk, attempt_number=77)
        self.assertEqual(response.status_code, 400)

    def test_client_cannot_supply_expiry_or_started_time(self):
        response = self.start(expires_at="2099-01-01T00:00:00Z", started_at="2099-01-01T00:00:00Z")
        self.assertEqual(response.status_code, 400)

    def test_expiry_uses_server_start_plus_duration(self):
        now = timezone.now()
        attempt, _ = start_attempt(self.user, self.assessment.pk, now=now)
        self.assertEqual(attempt.started_at, now)
        self.assertEqual(attempt.expires_at, now + timedelta(minutes=self.assessment.duration_minutes))

    def test_start_response_contains_required_safe_fields(self):
        data = self.start().data
        self.assertTrue({"id", "assessment_title", "assessment_type", "duration_minutes", "started_at", "expires_at", "status", "total_questions"}.issubset(data))

    def test_attempt_questions_are_created_from_assessment_set(self):
        attempt = self.begin()
        self.assertEqual(set(attempt.attempt_questions.values_list("question_id", flat=True)), {self.mcq.pk, self.mcq_two.pk, self.multi.pk, self.truefalse.pk})

    def test_attempt_question_order_matches_configured_order_without_randomization(self):
        attempt = self.begin()
        self.assertEqual(list(attempt.attempt_questions.values_list("question_id", flat=True)), [self.mcq.pk, self.mcq_two.pk, self.multi.pk, self.truefalse.pk])

    def test_random_question_order_is_stored(self):
        self.assessment.randomize_questions = True
        self.assessment.save(update_fields=("randomize_questions",))
        attempt = self.begin()
        self.assertEqual(attempt.attempt_questions.count(), 4)
        self.assertEqual(list(attempt.attempt_questions.values_list("order", flat=True)), [1, 2, 3, 4])

    def test_random_question_order_is_stable_after_refresh(self):
        self.assessment.randomize_questions = True
        self.assessment.save(update_fields=("randomize_questions",))
        attempt = self.begin()
        first = list(attempt.attempt_questions.values_list("question_id", flat=True))
        self.client.get(f"{self.base}{attempt.pk}/questions/")
        self.assertEqual(first, list(attempt.attempt_questions.values_list("question_id", flat=True)))

    def test_random_option_order_is_stored(self):
        self.assessment.randomize_options = True
        self.assessment.save(update_fields=("randomize_options",))
        attempt = self.begin()
        row = attempt.attempt_questions.get(question=self.mcq)
        self.assertEqual(list(row.ordered_options.values_list("order", flat=True)), [1, 2, 3])

    def test_random_option_order_is_stable_after_refresh(self):
        self.assessment.randomize_options = True
        self.assessment.save(update_fields=("randomize_options",))
        attempt = self.begin()
        path = self.question_url(attempt)
        first = self.client.get(path).data["options"]
        second = self.client.get(path).data["options"]
        self.assertEqual(first, second)

    def test_only_assessment_selected_questions_are_delivered(self):
        attempt = self.begin()
        delivered = self.client.get(f"{self.base}{attempt.pk}/questions/").data
        self.assertEqual(len(delivered), 4)
        self.assertNotIn(self.foreign_q.pk, [row["id"] for row in delivered])

    def test_candidate_cannot_access_other_candidate_attempt(self):
        attempt = self.begin()
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get(f"{self.base}{attempt.pk}/").status_code, 404)

    def test_candidate_cannot_modify_other_candidate_answer(self):
        attempt = self.begin()
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.answer(attempt, self.mcq, [self.mcq.options.first().pk]).status_code, 404)

    def test_candidate_cannot_submit_other_candidate_attempt(self):
        attempt = self.begin()
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.post(f"{self.base}{attempt.pk}/submit/", {}, format="json").status_code, 404)

    def test_candidate_cannot_access_other_institution_attempt(self):
        self.client.force_authenticate(self.foreign_user)
        response = self.start(self.foreign_assessment)
        self.assertEqual(response.status_code, 201)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(f"{self.base}{response.data['id']}/").status_code, 404)

    def test_candidate_cannot_access_foreign_institution_question_data(self):
        attempt = self.begin()
        self.assertEqual(self.client.get(self.question_url(attempt, self.foreign_q)).status_code, 404)

    def test_mcq_accepts_one_option(self):
        attempt = self.begin()
        response = self.answer(attempt, self.mcq, [self.mcq.options.first().pk])
        self.assertEqual(response.status_code, 200, response.data)

    def test_mcq_rejects_multiple_options(self):
        attempt = self.begin()
        ids = list(self.mcq.options.values_list("pk", flat=True)[:2])
        self.assertEqual(self.answer(attempt, self.mcq, ids).status_code, 400)

    def test_true_false_accepts_one_option(self):
        attempt = self.begin()
        option_id = self.truefalse.options.first().pk
        self.assertEqual(self.answer(attempt, self.truefalse, [option_id]).status_code, 200)

    def test_multiple_select_accepts_multiple_options(self):
        attempt = self.begin()
        ids = list(self.multi.options.values_list("pk", flat=True)[:2])
        self.assertEqual(self.answer(attempt, self.multi, ids).status_code, 200)

    def test_multiple_select_can_be_cleared_to_unanswered(self):
        attempt = self.begin()
        ids = list(self.multi.options.values_list("pk", flat=True)[:2])
        self.answer(attempt, self.multi, ids)
        response = self.answer(attempt, self.multi, [])
        self.assertEqual(response.data["answered"], False)
        self.assertFalse(Answer.objects.filter(attempt=attempt, question=self.multi).exists())

    def test_invalid_option_id_rejected(self):
        attempt = self.begin()
        self.assertEqual(self.answer(attempt, self.mcq, [99999999]).status_code, 400)

    def test_option_from_another_question_rejected(self):
        attempt = self.begin()
        other_option = self.mcq_two.options.first().pk
        self.assertEqual(self.answer(attempt, self.mcq, [other_option]).status_code, 400)

    def test_answer_is_updated_idempotently(self):
        attempt = self.begin()
        first, second = list(self.mcq.options.values_list("pk", flat=True)[:2])
        self.answer(attempt, self.mcq, [first])
        self.answer(attempt, self.mcq, [second])
        self.assertEqual(Answer.objects.filter(attempt=attempt, question=self.mcq).count(), 1)
        self.assertEqual(list(AnswerSelection.objects.filter(answer__attempt=attempt).values_list("option_id", flat=True)), [second])

    def test_answer_save_updates_last_activity(self):
        attempt = self.begin()
        old = attempt.last_activity_at
        self.answer(attempt, self.mcq, [self.mcq.options.first().pk])
        attempt.refresh_from_db()
        self.assertGreaterEqual(attempt.last_activity_at, old)

    def test_client_cannot_set_answer_timestamp(self):
        attempt = self.begin()
        response = self.client.put(self.question_url(attempt, self.mcq, "answer/"), {"selected_options": [self.mcq.options.first().pk], "answered_at": "2099-01-01T00:00:00Z"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_navigation_reports_answered_and_unanswered(self):
        attempt = self.begin()
        self.answer(attempt, self.mcq, [self.mcq.options.first().pk])
        rows = self.client.get(f"{self.base}{attempt.pk}/questions/").data
        states = {row["id"]: row["answered"] for row in rows}
        self.assertTrue(states[self.mcq.pk])
        self.assertFalse(states[self.mcq_two.pk])

    def test_mark_for_review_and_unmark(self):
        attempt = self.begin()
        url = self.question_url(attempt, self.mcq, "review/")
        self.assertTrue(self.client.patch(url, {"marked_for_review": True}, format="json").data["marked_for_review"])
        self.assertFalse(self.client.patch(url, {"marked_for_review": False}, format="json").data["marked_for_review"])

    def test_review_flag_updates_navigator_state(self):
        attempt = self.begin()
        self.client.patch(self.question_url(attempt, self.mcq, "review/"), {"marked_for_review": True}, format="json")
        rows = self.client.get(f"{self.base}{attempt.pk}/questions/").data
        row = next(value for value in rows if value["id"] == self.mcq.pk)
        self.assertTrue(row["marked_for_review"])

    def test_attempt_summary_has_counts_and_remaining_time(self):
        attempt = self.begin()
        self.answer(attempt, self.mcq, [self.mcq.options.first().pk])
        data = self.client.get(f"{self.base}{attempt.pk}/").data
        self.assertEqual(data["total_questions"], 4)
        self.assertEqual(data["answered_count"], 1)
        self.assertEqual(data["unanswered_count"], 3)
        self.assertGreater(data["remaining_seconds"], 0)

    def test_expired_attempt_becomes_expired_on_access(self):
        attempt = self.begin()
        Attempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.get(f"{self.base}{attempt.pk}/")
        self.assertEqual(response.data["status"], "expired")
        self.assertIsNone(Attempt.objects.get(pk=attempt.pk).submitted_at)

    def test_expired_attempt_rejects_answer_save(self):
        attempt = self.begin()
        Attempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.answer(attempt, self.mcq, [self.mcq.options.first().pk]).status_code, 409)

    def test_expired_attempt_cannot_be_submitted_as_normal(self):
        attempt = self.begin()
        Attempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.post(f"{self.base}{attempt.pk}/submit/", {}, format="json").status_code, 409)

    def test_expired_attempt_consumes_attempt_limit(self):
        attempt = self.begin()
        Attempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.client.get(f"{self.base}{attempt.pk}/")
        self.assertEqual(self.start().status_code, 403)

    def test_expired_attempt_not_resumed(self):
        attempt = self.begin()
        Attempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.start().status_code, 403)

    def test_submit_sets_server_timestamp_and_status(self):
        attempt = self.begin()
        response = self.client.post(f"{self.base}{attempt.pk}/submit/", {}, format="json")
        self.assertEqual(response.data["status"], "submitted")
        self.assertIsNotNone(response.data["submitted_at"])

    def test_submitted_attempt_cannot_be_submitted_twice(self):
        attempt = self.begin()
        self.client.post(f"{self.base}{attempt.pk}/submit/", {}, format="json")
        self.assertEqual(self.client.post(f"{self.base}{attempt.pk}/submit/", {}, format="json").status_code, 409)

    def test_submission_locks_answer_changes(self):
        attempt = self.begin()
        self.client.post(f"{self.base}{attempt.pk}/submit/", {}, format="json")
        self.assertEqual(self.answer(attempt, self.mcq, [self.mcq.options.first().pk]).status_code, 409)

    def test_submission_locks_review_flags(self):
        attempt = self.begin()
        self.client.post(f"{self.base}{attempt.pk}/submit/", {}, format="json")
        self.assertEqual(self.client.patch(self.question_url(attempt, self.mcq, "review/"), {"marked_for_review": True}, format="json").status_code, 409)

    def test_submission_does_not_return_score_or_result(self):
        attempt = self.begin()
        response = self.client.post(f"{self.base}{attempt.pk}/submit/", {}, format="json")
        self.assertFalse({"score", "grade", "percentage", "result", "passed"}.intersection(response.data))

    def test_staff_can_list_attempts_for_their_tenant(self):
        attempt = self.begin()
        self.client.force_authenticate(self.staff)
        response = self.client.get(self.base)
        self.assertEqual(response.status_code, 200)
        self.assertIn(attempt.pk, [row["id"] for row in response.data])

    def test_staff_cannot_list_attempts_for_other_tenant(self):
        self.client.force_authenticate(self.foreign_user)
        self.start(self.foreign_assessment)
        self.client.force_authenticate(self.staff)
        response = self.client.get(self.base)
        self.assertNotIn(self.foreign_assessment.pk, [row.get("assessment_id") for row in response.data])

    def test_staff_attempt_serializer_does_not_include_answer_selections(self):
        attempt = self.begin()
        self.client.force_authenticate(self.staff)
        row = next(item for item in self.client.get(self.base).data if item["id"] == attempt.pk)
        self.assertNotIn("answers", row)
        self.assertNotIn("selected_options", row)

    def test_candidate_list_contains_only_own_attempts(self):
        first = self.begin()
        self.client.force_authenticate(self.other_user)
        other = self.start().data
        self.client.force_authenticate(self.user)
        ids = [item["id"] for item in self.client.get(self.base).data]
        self.assertEqual(ids, [first.pk])
        self.assertNotIn(other["id"], ids)

    def test_candidate_response_contains_no_correctness_or_question_metadata(self):
        attempt = self.begin()
        response = self.client.get(self.question_url(attempt))
        self.assertEqual(response.status_code, 200)
        forbidden = {"is_correct", "explanation", "status", "difficulty", "created_by", "reviewed_by", "source", "learning_objective", "institution", "score", "grade", "percentage", "answer_key"}
        self.assertFalse(forbidden.intersection(response.data))
        self.assertFalse(forbidden.intersection(response.data["question"]))
        self.assertTrue(all(not forbidden.intersection(option) for option in response.data["options"]))

    def test_candidate_navigation_and_summary_contain_no_result_fields(self):
        attempt = self.begin()
        forbidden = {"score", "grade", "percentage", "result", "is_correct", "answer_key"}
        for payload in (self.client.get(f"{self.base}{attempt.pk}/").data, *self.client.get(f"{self.base}{attempt.pk}/questions/").data):
            self.assertFalse(forbidden.intersection(payload))

    def test_answer_response_contains_only_candidate_selection_state(self):
        attempt = self.begin()
        response = self.answer(attempt, self.mcq, [self.mcq.options.first().pk])
        forbidden = {"is_correct", "explanation", "score", "grade", "result", "answer_key"}
        self.assertFalse(forbidden.intersection(response.data))

    def test_question_content_cannot_be_edited_after_attempt_exists(self):
        self.begin()
        self.mcq.text = "Changed question"
        with self.assertRaises(DjangoValidationError):
            self.mcq.save()

    def test_question_option_cannot_be_changed_after_attempt_exists(self):
        self.begin()
        option = self.mcq.options.first()
        option.text = "Changed choice"
        with self.assertRaises(DjangoValidationError):
            option.save()

    def test_question_option_cannot_be_added_after_attempt_exists(self):
        self.begin()
        option = QuestionOption(question=self.mcq, text="New choice", order=99)
        with self.assertRaises(DjangoValidationError):
            option.save()

    def test_attempt_question_is_referenced_from_assessment_selection(self):
        attempt = self.begin()
        row = attempt.attempt_questions.first()
        self.assertTrue(self.assessment.assessment_questions.filter(question=row.question).exists())

    def test_assessment_question_set_cannot_be_changed_after_scheduling(self):
        attempt = self.begin()
        self.client.force_authenticate(self.staff)
        response = self.client.post(f"/api/v1/assessments/{self.assessment.pk}/questions/", {"question": self.mcq.pk, "order": 9, "marks": "1.00"}, format="json")
        self.assertIn(response.status_code, (403, 404))
        self.assertEqual(attempt.attempt_questions.count(), 4)

    def test_unauthenticated_attempt_endpoint_is_protected(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(self.base).status_code, (401, 403))

    def test_institution_header_must_match_linked_candidate(self):
        response = self.client.post(f"{self.base}start/", {"assessment": self.assessment.pk}, format="json", HTTP_X_INSTITUTION_ID=str(self.other_school.pk))
        self.assertEqual(response.status_code, 403)
