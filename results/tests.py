from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework.exceptions import ValidationError as APIValidationError

from accounts.models import User
from assessments.models import Assessment, AssessmentQuestion
from attempts.models import Answer, AnswerSelection, Attempt, AttemptQuestion, AttemptQuestionOption
from candidates.models import Candidate
from institutions.models import Institution
from questions.models import Question, QuestionOption
from subjects.models import Subject
from tenants.models import InstitutionMembership
from .grading import grade_for_percentage
from .models import Result, ResultQuestion
from .services import mark_attempt, publish_result


class ResultFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.school = Institution.objects.create(name="Marking School")
        cls.other_school = Institution.objects.create(name="Other Marking School")
        cls.subject = Subject.objects.create(institution=cls.school, name="Maths", code="MAT")
        cls.other_subject = Subject.objects.create(institution=cls.other_school, name="Maths", code="MAT")
        cls.admin = User.objects.create_user("admin-mark@example.test", "Safe-pass-8392")
        cls.examiner = User.objects.create_user("examiner-mark@example.test", "Safe-pass-8392")
        cls.teacher = User.objects.create_user("teacher-mark@example.test", "Safe-pass-8392")
        cls.student = User.objects.create_user("student-mark@example.test", "Safe-pass-8392")
        cls.foreign = User.objects.create_user("foreign-mark@example.test", "Safe-pass-8392")
        for user, institution, role in (
            (cls.admin, cls.school, "institution_admin"), (cls.examiner, cls.school, "examiner"),
            (cls.teacher, cls.school, "teacher"), (cls.student, cls.school, "student"),
            (cls.foreign, cls.other_school, "institution_admin"),
        ):
            InstitutionMembership.objects.create(user=user, institution=institution, role=role)
        cls.candidate = Candidate.objects.create(institution=cls.school, user=cls.student, candidate_id="M-001", first_name="Ada", last_name="Learner")
        cls.foreign_candidate = Candidate.objects.create(institution=cls.other_school, user=cls.foreign, candidate_id="M-001", first_name="Other", last_name="Learner")
        cls.assessment = Assessment.objects.create(
            institution=cls.school, title="Marking test", assessment_type=Assessment.Type.TEST,
            subject=cls.subject, duration_minutes=30, pass_mark=Decimal("2.00"),
            result_visibility=Assessment.ResultVisibility.AFTER_SUBMISSION,
            result_release_mode=Assessment.ResultReleaseMode.APPROVAL_REQUIRED,
            created_by=cls.admin,
        )
        cls.foreign_assessment = Assessment.objects.create(
            institution=cls.other_school, title="Foreign test", assessment_type=Assessment.Type.TEST,
            subject=cls.other_subject, duration_minutes=30, pass_mark=Decimal("1.00"), created_by=cls.foreign,
            result_visibility=Assessment.ResultVisibility.AFTER_SUBMISSION,
        )
        cls.mcq = cls.make_question(cls, cls.school, cls.subject, Question.Type.MULTIPLE_CHOICE, "MCQ", 1)
        cls.multi = cls.make_question(cls, cls.school, cls.subject, Question.Type.MULTIPLE_SELECT, "Multi", (1, 3))
        cls.tf = cls.make_question(cls, cls.school, cls.subject, Question.Type.TRUE_FALSE, "TF", 1, option_count=2)
        cls.foreign_mcq = cls.make_question(cls, cls.other_school, cls.other_subject, Question.Type.MULTIPLE_CHOICE, "Foreign MCQ", 1)
        for order, option_rows in enumerate((cls.mcq, cls.multi, cls.tf), 1):
            AssessmentQuestion.objects.create(assessment=cls.assessment, question=option_rows[0].question, order=order, marks=Decimal("1.00"))
        AssessmentQuestion.objects.create(assessment=cls.foreign_assessment, question=cls.foreign_mcq[0].question, order=1, marks=Decimal("1.00"))

    @staticmethod
    def make_question(cls, institution, subject, qtype, text, correct, option_count=3):
        question = Question.objects.create(institution=institution, subject=subject, question_type=qtype,
                                           text=text, created_by=cls.admin if institution == cls.school else cls.foreign,
                                           status=Question.Status.APPROVED)
        correct_orders = set(correct) if isinstance(correct, tuple) else {correct}
        return [QuestionOption.objects.create(question=question, text=f"{text}-{i}", order=i, is_correct=i in correct_orders)
                for i in range(1, option_count + 1)]

    def make_attempt(self, status=Attempt.Status.SUBMITTED, *, assessment=None, candidate=None, pass_mark=Decimal("2.00")):
        assessment = assessment or self.assessment
        candidate = candidate or (self.candidate if assessment == self.assessment else self.foreign_candidate)
        return Attempt.objects.create(
            institution=assessment.institution, assessment=assessment, candidate=candidate, attempt_number=1,
            status=status, started_at=timezone.now() - timedelta(minutes=30), expires_at=timezone.now() - timedelta(minutes=1),
            last_activity_at=timezone.now(), pass_mark_snapshot=pass_mark,
        )

    def add_question(self, attempt, question, options, *, marks="1.00", selection=None):
        row = AttemptQuestion.objects.create(attempt=attempt, question=question, order=attempt.attempt_questions.count() + 1,
                                             marks_available=Decimal(marks))
        AttemptQuestionOption.objects.bulk_create([AttemptQuestionOption(attempt_question=row, option=option, order=i)
                                                   for i, option in enumerate(options, 1)])
        if selection is not None:
            answer = Answer.objects.create(attempt=attempt, question=question, answered_at=timezone.now())
            AnswerSelection.objects.bulk_create([AnswerSelection(answer=answer, option=option) for option in selection])
        return row


class MarkingServiceTests(ResultFixtureMixin, APITestCase):
    def test_submitted_attempt_marked(self):
        attempt = self.make_attempt()
        row = self.add_question(attempt, self.mcq[0].question, self.mcq, selection=[self.mcq[0]])
        result = mark_attempt(attempt.pk)
        self.assertEqual(result.attempt_id, attempt.pk)
        self.assertEqual(result.questions.get().attempt_question_id, row.pk)

    def test_expired_attempt_marked(self):
        attempt = self.make_attempt(Attempt.Status.EXPIRED)
        self.add_question(attempt, self.mcq[0].question, self.mcq)
        self.assertEqual(mark_attempt(attempt.pk).marks_obtained, Decimal("0.00"))

    def test_in_progress_attempt_rejected(self):
        attempt = self.make_attempt(Attempt.Status.IN_PROGRESS)
        with self.assertRaises(Exception):
            mark_attempt(attempt.pk)

    def test_cancelled_attempt_rejected(self):
        attempt = self.make_attempt(Attempt.Status.CANCELLED)
        with self.assertRaises(Exception):
            mark_attempt(attempt.pk)

    def test_correct_mcq_full_marks(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq, marks="2.50", selection=[self.mcq[0]])
        self.assertEqual(mark_attempt(attempt.pk).marks_obtained, Decimal("2.50"))

    def test_incorrect_mcq_zero_marks(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq, selection=[self.mcq[1]])
        self.assertEqual(mark_attempt(attempt.pk).marks_obtained, Decimal("0.00"))

    def test_unanswered_mcq_zero_marks(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq)
        self.assertEqual(mark_attempt(attempt.pk).questions.get().status, ResultQuestion.Status.UNANSWERED)

    def test_multiple_mcq_selection_is_invalid(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq, selection=[self.mcq[0], self.mcq[1]])
        detail = mark_attempt(attempt.pk).questions.get()
        self.assertEqual(detail.status, ResultQuestion.Status.INVALID)
        self.assertEqual(detail.marks_obtained, Decimal("0.00"))

    def test_true_false_correct(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.tf[0].question, self.tf, selection=[self.tf[0]])
        self.assertEqual(mark_attempt(attempt.pk).marks_obtained, Decimal("1.00"))

    def test_true_false_incorrect(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.tf[0].question, self.tf, selection=[self.tf[1]])
        self.assertEqual(mark_attempt(attempt.pk).marks_obtained, Decimal("0.00"))

    def test_true_false_unanswered(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.tf[0].question, self.tf)
        self.assertEqual(mark_attempt(attempt.pk).questions.get().status, ResultQuestion.Status.UNANSWERED)

    def test_exact_multi_select_set_correct(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.multi[0].question, self.multi, selection=[self.multi[0], self.multi[2]])
        self.assertEqual(mark_attempt(attempt.pk).marks_obtained, Decimal("1.00"))

    def test_incomplete_multi_select_set_zero(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.multi[0].question, self.multi, selection=[self.multi[0]])
        self.assertEqual(mark_attempt(attempt.pk).marks_obtained, Decimal("0.00"))

    def test_multi_select_extra_wrong_option_zero(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.multi[0].question, self.multi, selection=[self.multi[0], self.multi[1], self.multi[2]])
        self.assertEqual(mark_attempt(attempt.pk).marks_obtained, Decimal("0.00"))

    def test_multi_select_unanswered(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.multi[0].question, self.multi)
        self.assertEqual(mark_attempt(attempt.pk).questions.get().status, ResultQuestion.Status.UNANSWERED)

    def test_total_marks_uses_attempt_snapshots(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq, marks="2.25")
        self.add_question(attempt, self.tf[0].question, self.tf, marks="3.75")
        self.assertEqual(mark_attempt(attempt.pk).total_marks, Decimal("6.00"))

    def test_percentage_is_decimal_and_rounded(self):
        attempt = self.make_attempt(pass_mark=Decimal("1"))
        self.add_question(attempt, self.mcq[0].question, self.mcq, marks="3.00", selection=[self.mcq[0]])
        self.add_question(attempt, self.tf[0].question, self.tf, marks="7.00")
        result = mark_attempt(attempt.pk)
        self.assertIsInstance(result.percentage, Decimal)
        self.assertEqual(result.percentage, Decimal("30.00"))

    def test_zero_total_is_safe(self):
        attempt = self.make_attempt()
        result = mark_attempt(attempt.pk)
        self.assertEqual(result.percentage, Decimal("0.00"))
        self.assertFalse(result.passed)

    def test_exact_pass_threshold_passes(self):
        attempt = self.make_attempt(pass_mark=Decimal("1.00"))
        self.add_question(attempt, self.mcq[0].question, self.mcq, selection=[self.mcq[0]])
        self.assertTrue(mark_attempt(attempt.pk).passed)

    def test_below_pass_threshold_fails(self):
        attempt = self.make_attempt(pass_mark=Decimal("2.00"))
        self.add_question(attempt, self.mcq[0].question, self.mcq, selection=[self.mcq[1]])
        self.assertFalse(mark_attempt(attempt.pk).passed)

    def test_grading_boundaries(self):
        for percentage, grade in (("70", "A"), ("60", "B"), ("50", "C"), ("45", "D"), ("40", "E"), ("39.99", "F")):
            with self.subTest(percentage=percentage):
                self.assertEqual(grade_for_percentage(Decimal(percentage)), grade)

    def test_repeated_marking_is_idempotent(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq, selection=[self.mcq[0]])
        first = mark_attempt(attempt.pk)
        second = mark_attempt(attempt.pk)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Result.objects.filter(attempt=attempt).count(), 1)
        self.assertEqual(ResultQuestion.objects.filter(result=first).count(), 1)

    def test_marking_does_not_change_answers(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq, selection=[self.mcq[0]])
        before = list(AnswerSelection.objects.values_list("answer_id", "option_id"))
        mark_attempt(attempt.pk)
        self.assertEqual(list(AnswerSelection.objects.values_list("answer_id", "option_id")), before)

    def test_approval_required_stays_provisional(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq)
        self.assertEqual(mark_attempt(attempt.pk).status, Result.Status.PROVISIONAL)

    def test_immediate_after_submission_publishes(self):
        self.assessment.result_release_mode = Assessment.ResultReleaseMode.IMMEDIATE
        self.assessment.save(update_fields=("result_release_mode",))
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq)
        result = mark_attempt(attempt.pk)
        self.assertEqual(result.status, Result.Status.PUBLISHED)
        self.assertIsNotNone(result.published_at)

    def test_hidden_results_stay_provisional(self):
        self.assessment.result_visibility = Assessment.ResultVisibility.HIDDEN
        self.assessment.result_release_mode = Assessment.ResultReleaseMode.IMMEDIATE
        self.assessment.save(update_fields=("result_visibility", "result_release_mode"))
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq)
        self.assertEqual(mark_attempt(attempt.pk).status, Result.Status.PROVISIONAL)

    def test_full_score_has_one_hundred_percent(self):
        attempt = self.make_attempt(pass_mark=Decimal("1.00"))
        self.add_question(attempt, self.mcq[0].question, self.mcq, selection=[self.mcq[0]])
        self.assertEqual(mark_attempt(attempt.pk).percentage, Decimal("100.00"))

    def test_grade_is_stored_from_percentage(self):
        attempt = self.make_attempt(pass_mark=Decimal("7.00"))
        for question_options in (self.mcq, self.multi, self.tf):
            self.add_question(attempt, question_options[0].question, question_options,
                              marks="10.00", selection=[o for o in question_options if o.is_correct])
        self.assertEqual(mark_attempt(attempt.pk).grade, "A")

    def test_assessment_passmark_edits_do_not_change_attempt_threshold(self):
        attempt = self.make_attempt(pass_mark=Decimal("1.00"))
        self.add_question(attempt, self.mcq[0].question, self.mcq, selection=[self.mcq[0]])
        Assessment.objects.filter(pk=self.assessment.pk).update(pass_mark=Decimal("3.00"))
        result = mark_attempt(attempt.pk)
        self.assertEqual(result.pass_mark, Decimal("1.00"))
        self.assertTrue(result.passed)

    def test_assessment_question_mark_edits_do_not_change_attempt_total(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq, marks="2.00")
        AssessmentQuestion.objects.filter(assessment=self.assessment, question=self.mcq[0].question).update(marks=Decimal("9.00"))
        self.assertEqual(mark_attempt(attempt.pk).total_marks, Decimal("2.00"))

    def test_result_attempt_is_database_unique(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq)
        result = mark_attempt(attempt.pk)
        self.assertEqual(Result.objects.filter(attempt_id=result.attempt_id).count(), 1)

    def test_selected_option_not_offered_is_invalid(self):
        attempt = self.make_attempt()
        row = self.add_question(attempt, self.mcq[0].question, self.mcq[1:], selection=None)
        answer = Answer.objects.create(attempt=attempt, question=self.mcq[0].question, answered_at=timezone.now())
        AnswerSelection.objects.create(answer=answer, option=self.mcq[0])
        detail = mark_attempt(attempt.pk).questions.get(attempt_question=row)
        self.assertEqual(detail.status, ResultQuestion.Status.INVALID)
        self.assertEqual(detail.marks_obtained, Decimal("0.00"))

    def test_correct_option_missing_from_attempt_snapshot_is_invalid(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq[1:], selection=[self.mcq[1]])
        detail = mark_attempt(attempt.pk).questions.get()
        self.assertEqual(detail.status, ResultQuestion.Status.INVALID)

    def test_cross_tenant_attempt_question_is_invalid(self):
        attempt = self.make_attempt()
        row = self.add_question(attempt, self.foreign_mcq[0].question, self.foreign_mcq)
        detail = mark_attempt(attempt.pk).questions.get(attempt_question=row)
        self.assertEqual(detail.status, ResultQuestion.Status.INVALID)

    def test_answer_from_other_attempt_is_not_used(self):
        current = self.make_attempt()
        other = self.make_attempt(candidate=Candidate.objects.create(
            institution=self.school, user=None, candidate_id="M-OTHER", first_name="Other", last_name="Candidate"))
        self.add_question(current, self.mcq[0].question, self.mcq)
        self.add_question(other, self.mcq[0].question, self.mcq, selection=[self.mcq[0]])
        self.assertEqual(mark_attempt(current.pk).questions.get().status, ResultQuestion.Status.UNANSWERED)

    def test_invalid_answer_records_staff_audit_note(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq[1:], selection=None)
        answer = Answer.objects.create(attempt=attempt, question=self.mcq[0].question, answered_at=timezone.now())
        AnswerSelection.objects.create(answer=answer, option=self.mcq[0])
        detail = mark_attempt(attempt.pk).questions.get()
        self.assertTrue(detail.validation_note)

    def test_manual_release_stays_provisional_until_controlled_release(self):
        self.assessment.result_release_mode = Assessment.ResultReleaseMode.MANUAL_RELEASE
        self.assessment.save(update_fields=("result_release_mode",))
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq)
        self.assertEqual(mark_attempt(attempt.pk).status, Result.Status.PROVISIONAL)

    def test_immediate_scheduled_release_waits_until_end_time(self):
        self.assessment.result_visibility = Assessment.ResultVisibility.SCHEDULED_RELEASE
        self.assessment.result_release_mode = Assessment.ResultReleaseMode.IMMEDIATE
        self.assessment.end_at = timezone.now() + timedelta(hours=1)
        self.assessment.save(update_fields=("result_visibility", "result_release_mode", "end_at"))
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq)
        self.assertEqual(mark_attempt(attempt.pk).status, Result.Status.PROVISIONAL)

    def test_scheduled_release_cannot_publish_early(self):
        self.assessment.result_visibility = Assessment.ResultVisibility.SCHEDULED_RELEASE
        self.assessment.end_at = timezone.now() + timedelta(hours=1)
        self.assessment.save(update_fields=("result_visibility", "end_at"))
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq)
        result = mark_attempt(attempt.pk)
        with self.assertRaises(APIValidationError):
            publish_result(result.pk)

    def test_re_mark_preserves_withheld_state(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq)
        result = mark_attempt(attempt.pk)
        result.status = Result.Status.WITHHELD
        result.save(update_fields=("status",))
        self.assertEqual(mark_attempt(attempt.pk).status, Result.Status.WITHHELD)


class ResultAPITests(ResultFixtureMixin, APITestCase):
    def setUp(self):
        self.client.force_authenticate(self.examiner)
        self.api = "/api/v1/results/"

    def completed_result(self, assessment=None, candidate=None):
        attempt = self.make_attempt(assessment=assessment, candidate=candidate)
        question_options = self.mcq if assessment is None else self.foreign_mcq
        self.add_question(attempt, question_options[0].question, question_options)
        return mark_attempt(attempt.pk)

    def test_examiner_can_mark(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq)
        response = self.client.post(f"{self.api}attempts/{attempt.pk}/mark/", {}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_teacher_cannot_mark(self):
        self.client.force_authenticate(self.teacher)
        attempt = self.make_attempt()
        self.assertEqual(self.client.post(f"{self.api}attempts/{attempt.pk}/mark/", {}, format="json").status_code, 403)

    def test_student_cannot_mark(self):
        self.client.force_authenticate(self.student)
        attempt = self.make_attempt()
        self.assertEqual(self.client.post(f"{self.api}attempts/{attempt.pk}/mark/", {}, format="json").status_code, 403)

    def test_foreign_tenant_cannot_mark(self):
        attempt = self.make_attempt(assessment=self.foreign_assessment)
        self.assertEqual(self.client.post(f"{self.api}attempts/{attempt.pk}/mark/", {}, format="json").status_code, 404)

    def test_admin_can_publish_marked_result(self):
        result = self.completed_result()
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"{self.api}{result.pk}/publish/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], Result.Status.PUBLISHED)

    def test_examiner_cannot_publish(self):
        result = self.completed_result()
        self.assertEqual(self.client.post(f"{self.api}{result.pk}/publish/", {}, format="json").status_code, 403)

    def test_foreign_tenant_cannot_publish(self):
        result = self.completed_result(self.foreign_assessment, self.foreign_candidate)
        self.client.force_authenticate(self.foreign)
        response = self.client.post(f"{self.api}{result.pk}/publish/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f"{self.api}{result.pk}/publish/", {}, format="json").status_code, 404)

    def test_teacher_lists_own_tenant_only(self):
        self.completed_result()
        self.completed_result(self.foreign_assessment, self.foreign_candidate)
        self.client.force_authenticate(self.teacher)
        response = self.client.get(self.api)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_candidate_only_sees_own_published_result_summary(self):
        result = self.completed_result()
        publish_result(result.pk)
        self.client.force_authenticate(self.student)
        response = self.client.get(f"{self.api}my/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertNotIn("questions", response.data[0])
        self.assertNotIn("validation_note", response.data[0])

    def test_candidate_cannot_see_provisional_result(self):
        result = self.completed_result()
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(f"{self.api}{result.pk}/").status_code, 404)

    def test_candidate_cannot_retrieve_another_candidate_result(self):
        result = self.completed_result()
        publish_result(result.pk)
        self.client.force_authenticate(self.foreign)
        self.assertEqual(self.client.get(f"{self.api}{result.pk}/").status_code, 404)

    def test_candidate_cannot_see_hidden_result(self):
        self.assessment.result_visibility = Assessment.ResultVisibility.HIDDEN
        self.assessment.save(update_fields=("result_visibility",))
        result = self.completed_result()
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(f"{self.api}my/").data, [])

    def test_unauthenticated_staff_endpoint_rejected(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(self.api).status_code, (401, 403))

    def test_candidate_can_retrieve_own_published_detail(self):
        result = self.completed_result()
        publish_result(result.pk)
        self.client.force_authenticate(self.student)
        response = self.client.get(f"{self.api}{result.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("questions", response.data)

    def test_institution_admin_cannot_retrieve_foreign_result(self):
        result = self.completed_result(self.foreign_assessment, self.foreign_candidate)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"{self.api}{result.pk}/").status_code, 404)

    def test_student_cannot_mark_expired_attempt(self):
        self.client.force_authenticate(self.student)
        attempt = self.make_attempt(Attempt.Status.EXPIRED)
        self.assertEqual(self.client.post(f"{self.api}attempts/{attempt.pk}/mark/", {}, format="json").status_code, 403)

    def test_candidate_cannot_publish(self):
        result = self.completed_result()
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.post(f"{self.api}{result.pk}/publish/", {}, format="json").status_code, 403)

    def test_published_at_comes_from_server(self):
        result = self.completed_result()
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"{self.api}{result.pk}/publish/", {"published_at": "2000-01-01T00:00:00Z"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["published_at"], "2000-01-01T00:00:00Z")

    def test_admin_can_withhold_published_result(self):
        result = self.completed_result()
        result = publish_result(result.pk)
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"{self.api}{result.pk}/withhold/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Result.Status.WITHHELD)

    def test_examiner_cannot_withhold(self):
        result = self.completed_result()
        self.assertEqual(self.client.post(f"{self.api}{result.pk}/withhold/", {}, format="json").status_code, 403)

    def test_cross_tenant_staff_does_not_list_foreign_results(self):
        self.completed_result()
        self.client.force_authenticate(self.foreign)
        response = self.client.get(self.api)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_candidate_detail_hides_withheld_result(self):
        result = self.completed_result()
        result.status = Result.Status.WITHHELD
        result.save(update_fields=("status",))
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(f"{self.api}{result.pk}/").status_code, 404)

    def test_hidden_result_cannot_be_published(self):
        self.assessment.result_visibility = Assessment.ResultVisibility.HIDDEN
        self.assessment.save(update_fields=("result_visibility",))
        result = self.completed_result()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f"{self.api}{result.pk}/publish/", {}, format="json").status_code, 400)
