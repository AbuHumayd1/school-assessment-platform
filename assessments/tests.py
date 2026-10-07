from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.core.exceptions import ValidationError
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from groups.models import Group
from institutions.models import Institution
from questions.models import Question, QuestionOption
from subjects.models import Subject
from tenants.models import InstitutionMembership
from .models import Assessment, AssessmentQuestion
from .serializers import AssessmentSerializer, AssessmentQuestionSerializer


class AssessmentAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school_a = Institution.objects.create(name="North Academy")
        cls.school_b = Institution.objects.create(name="South Academy")
        cls.subject_a = Subject.objects.create(institution=cls.school_a, name="Mathematics", code="MATH")
        cls.subject_b = Subject.objects.create(institution=cls.school_b, name="Mathematics", code="MATH")
        cls.subject_a_other = Subject.objects.create(institution=cls.school_a, name="Science", code="SCI")
        cls.group_a = Group.objects.create(institution=cls.school_a, name="Cohort A", code="A")
        cls.group_b = Group.objects.create(institution=cls.school_b, name="Cohort B", code="A")
        cls.group_inactive = Group.objects.create(institution=cls.school_a, name="Inactive", code="I", is_active=False)
        cls.teacher = User.objects.create_user("teacher@example.test", "Safe-pass-8392")
        cls.examiner = User.objects.create_user("examiner@example.test", "Safe-pass-8392")
        cls.admin = User.objects.create_user("admin@example.test", "Safe-pass-8392")
        cls.student = User.objects.create_user("student@example.test", "Safe-pass-8392")
        cls.foreign_author = User.objects.create_user("foreign-author@example.test")
        for user, role, school in (
            (cls.teacher, "teacher", cls.school_a), (cls.examiner, "examiner", cls.school_a),
            (cls.admin, "institution_admin", cls.school_a), (cls.student, "student", cls.school_a),
            (cls.foreign_author, "teacher", cls.school_b),
        ):
            InstitutionMembership.objects.create(user=user, institution=school, role=role)
        cls.question = cls.make_question(cls, cls.school_a, cls.subject_a, "approved", "Question one")
        cls.question_two = cls.make_question(cls, cls.school_a, cls.subject_a, "approved", "Question two")
        cls.question_other_subject = cls.make_question(cls, cls.school_a, cls.subject_a_other, "approved", "Science question")
        cls.question_b = cls.make_question(cls, cls.school_b, cls.subject_b, "approved", "Other tenant question")
        cls.question_draft = cls.make_question(cls, cls.school_a, cls.subject_a, "draft", "Draft question")
        cls.question_review = cls.make_question(cls, cls.school_a, cls.subject_a, "review", "Review question")
        cls.question_archived = cls.make_question(cls, cls.school_a, cls.subject_a, "archived", "Archived question")

    @staticmethod
    def make_question(cls, school, subject, qstatus, text):
        question = Question.objects.create(
            institution=school, subject=subject, question_type=Question.Type.MULTIPLE_CHOICE,
            text=text, created_by=cls.teacher if school.name == "North Academy" else cls.foreign_author,
            status='draft',
        )
        QuestionOption.objects.bulk_create([QuestionOption(question=question, text=str(order),
            order=order, is_correct=order == 1) for order in (1, 2)])
        if qstatus != 'draft':
            question.status = 'approved' if qstatus == 'archived' else qstatus
            question.save(update_fields=['status'])
            if qstatus == 'archived':
                question.status = 'archived'
                question.save(update_fields=['status'])
        return question

    def setUp(self):
        self.client.force_authenticate(self.teacher)
        self.url = "/api/v1/assessments/"

    def payload(self, **overrides):
        data = {
            "title": "First term assessment", "assessment_type": "class_test", "subject": self.subject_a.pk,
            "group": self.group_a.pk, "duration_minutes": 45, "pass_mark": "5.00", "attempt_limit": 1,
            "questions": [{"question": self.question.pk, "order": 1, "marks": "10.00"}],
        }
        data.update(overrides)
        return data

    def create_assessment(self, **overrides):
        return self.client.post(self.url, self.payload(**overrides), format="json")

    def test_create_assessment_with_valid_question(self):
        response = self.create_assessment()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["status"], "draft")
        self.assertEqual(Decimal(response.data["total_marks"]), Decimal("10.00"))

    def test_server_sets_institution_and_creator(self):
        response = self.create_assessment()
        self.assertEqual(response.data["institution"], self.school_a.pk)
        self.assertEqual(response.data["created_by"], self.teacher.pk)

    def test_client_cannot_set_tenant(self):
        response = self.create_assessment(institution=self.school_b.pk)
        self.assertEqual(response.status_code, 400)

    def test_client_cannot_set_status(self):
        self.assertEqual(self.create_assessment(status="approved").status_code, 400)

    def test_client_cannot_set_total_marks(self):
        response = self.create_assessment(total_marks="999.00")
        self.assertEqual(response.status_code, 400)

    def test_required_title(self):
        response = self.create_assessment(title="")
        self.assertEqual(response.status_code, 400)

    def test_invalid_assessment_type(self):
        self.assertEqual(self.create_assessment(assessment_type="book_reading").status_code, 400)

    def test_duration_must_be_positive(self):
        self.assertEqual(self.create_assessment(duration_minutes=0).status_code, 400)

    def test_negative_duration_rejected(self):
        self.assertEqual(self.create_assessment(duration_minutes=-3).status_code, 400)

    def test_attempt_limit_must_be_positive(self):
        self.assertEqual(self.create_assessment(attempt_limit=0).status_code, 400)

    def test_negative_attempt_limit_rejected(self):
        self.assertEqual(self.create_assessment(attempt_limit=-1).status_code, 400)

    def test_subject_from_other_tenant_rejected(self):
        self.assertEqual(self.create_assessment(subject=self.subject_b.pk).status_code, 400)

    def test_group_from_other_tenant_rejected(self):
        self.assertEqual(self.create_assessment(group=self.group_b.pk).status_code, 400)

    def test_inactive_group_rejected(self):
        self.assertEqual(self.create_assessment(group=self.group_inactive.pk).status_code, 400)

    def test_group_is_optional(self):
        response = self.create_assessment(group=None)
        self.assertEqual(response.status_code, 201, response.data)

    def test_approved_same_subject_question_accepted(self):
        self.assertEqual(self.create_assessment().status_code, 201)

    def test_draft_question_rejected(self):
        self.assertEqual(self.create_assessment(questions=[{"question": self.question_draft.pk, "order": 1, "marks": 2}]).status_code, 400)

    def test_review_question_rejected(self):
        self.assertEqual(self.create_assessment(questions=[{"question": self.question_review.pk, "order": 1, "marks": 2}]).status_code, 400)

    def test_archived_question_rejected(self):
        self.assertEqual(self.create_assessment(questions=[{"question": self.question_archived.pk, "order": 1, "marks": 2}]).status_code, 400)

    def test_cross_tenant_question_rejected(self):
        self.assertEqual(self.create_assessment(questions=[{"question": self.question_b.pk, "order": 1, "marks": 2}]).status_code, 400)

    def test_question_from_another_subject_rejected(self):
        self.assertEqual(self.create_assessment(questions=[{"question": self.question_other_subject.pk, "order": 1, "marks": 2}]).status_code, 400)

    def test_duplicate_question_rejected(self):
        rows = [{"question": self.question.pk, "order": 1, "marks": 2}, {"question": self.question.pk, "order": 2, "marks": 3}]
        self.assertEqual(self.create_assessment(questions=rows).status_code, 400)

    def test_duplicate_order_rejected(self):
        rows = [{"question": self.question.pk, "order": 1, "marks": 2}, {"question": self.question_two.pk, "order": 1, "marks": 3}]
        self.assertEqual(self.create_assessment(questions=rows).status_code, 400)

    def test_zero_marks_rejected(self):
        self.assertEqual(self.create_assessment(questions=[{"question": self.question.pk, "order": 1, "marks": 0}]).status_code, 400)
        created = self.create_assessment(questions=[])
        exam = Assessment.objects.get(pk=created.data['id'])
        for value in (Decimal('1.25'), 1, 1.25, '1.25'):
            with self.subTest(valid_marks=value):
                row = AssessmentQuestion.objects.create(assessment=exam, question=self.question,
                    order=1, marks=value)
                self.assertIsInstance(row.marks, Decimal)
                row.refresh_from_db()
                self.assertEqual(row.marks, Decimal(str(value)))
                row.delete()
        for value in (0, '0.00', -1, '-1.25', 'invalid', None, 'NaN', 'Infinity', '0.001', '100000.00'):
            with self.subTest(invalid_marks=value), self.assertRaises(ValidationError):
                AssessmentQuestion.objects.create(assessment=exam, question=self.question,
                    order=1, marks=value)
        self.assertFalse(exam.assessment_questions.exists())

    def test_negative_marks_rejected(self):
        self.assertEqual(self.create_assessment(questions=[{"question": self.question.pk, "order": 1, "marks": -2}]).status_code, 400)

    def test_total_marks_sum_selected_question_marks(self):
        response = self.create_assessment(questions=[
            {"question": self.question.pk, "order": 1, "marks": "2.25"},
            {"question": self.question_two.pk, "order": 2, "marks": "3.75"},
        ])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["total_marks"]), Decimal("6.00"))

    def test_pass_mark_over_total_rejected(self):
        self.assertEqual(self.create_assessment(pass_mark="10.01").status_code, 400)

    def test_zero_pass_mark_allowed(self):
        self.assertEqual(self.create_assessment(pass_mark="0").status_code, 201)

    def test_invalid_date_range_rejected(self):
        start = (timezone.now() + timedelta(days=2)).isoformat()
        end = (timezone.now() + timedelta(days=1)).isoformat()
        self.assertEqual(self.create_assessment(start_at=start, end_at=end).status_code, 400)

    def test_timezone_naive_date_rejected(self):
        self.assertEqual(self.create_assessment(start_at="2030-01-01T10:00:00").status_code, 400)

    def test_timezone_aware_availability_accepted(self):
        start = (timezone.now() + timedelta(days=1)).isoformat()
        end = (timezone.now() + timedelta(days=2)).isoformat()
        self.assertEqual(self.create_assessment(start_at=start, end_at=end).status_code, 201)

    def test_randomization_configuration_persists(self):
        response = self.create_assessment(randomize_questions=True, randomize_options=True)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["randomize_questions"])
        self.assertTrue(response.data["randomize_options"])

    def test_draft_can_be_submitted_for_review(self):
        created = self.create_assessment()
        result = self.client.post(f"{self.url}{created.data['id']}/submit-review/", {}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["status"], "review")

    def test_empty_draft_cannot_be_submitted(self):
        data = self.payload(questions=[])
        created = self.client.post(self.url, data, format="json")
        result = self.client.post(f"{self.url}{created.data['id']}/submit-review/", {}, format="json")
        self.assertEqual(result.status_code, 400)

    def test_examiner_can_request_changes(self):
        created = self.create_assessment()
        self.client.post(f"{self.url}{created.data['id']}/submit-review/", {}, format="json")
        self.client.force_authenticate(self.examiner)
        result = self.client.post(f"{self.url}{created.data['id']}/request-changes/", {}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["status"], "draft")

    def test_admin_can_approve_reviewed_assessment(self):
        created = self.create_assessment()
        self.client.post(f"{self.url}{created.data['id']}/submit-review/", {}, format="json")
        self.client.force_authenticate(self.admin)
        result = self.client.post(f"{self.url}{created.data['id']}/approve/", {}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["status"], "approved")
        self.assertEqual(result.data["approved_by"], self.admin.pk)

    def test_teacher_cannot_approve(self):
        created = self.create_assessment()
        self.client.post(f"{self.url}{created.data['id']}/submit-review/", {}, format="json")
        result = self.client.post(f"{self.url}{created.data['id']}/approve/", {}, format="json")
        self.assertIn(result.status_code, (403, 404))

    def test_invalid_transition_rejected(self):
        created = self.create_assessment()
        self.client.force_authenticate(self.admin)
        result = self.client.post(f"{self.url}{created.data['id']}/approve/", {}, format="json")
        self.assertEqual(result.status_code, 400)

    def test_schedule_requires_complete_window(self):
        created = self.create_assessment(group=None)
        self.client.post(f"{self.url}{created.data['id']}/submit-review/", {}, format="json")
        self.client.force_authenticate(self.admin)
        self.client.post(f"{self.url}{created.data['id']}/approve/", {}, format="json")
        result = self.client.post(f"{self.url}{created.data['id']}/schedule/", {}, format="json")
        self.assertEqual(result.status_code, 400)

    def test_assigned_group_schedule_requires_group(self):
        created = self.create_assessment(group=None, start_at=(timezone.now()+timedelta(days=1)).isoformat(), end_at=(timezone.now()+timedelta(days=2)).isoformat())
        self.client.post(f"{self.url}{created.data['id']}/submit-review/", {}, format="json")
        self.client.force_authenticate(self.admin)
        self.client.post(f"{self.url}{created.data['id']}/approve/", {}, format="json")
        self.assertEqual(self.client.post(f"{self.url}{created.data['id']}/schedule/", {}, format="json").status_code, 400)

    def test_schedule_and_archive_transitions(self):
        start, end = timezone.now()+timedelta(days=1), timezone.now()+timedelta(days=2)
        created = self.create_assessment(start_at=start.isoformat(), end_at=end.isoformat())
        self.client.post(f"{self.url}{created.data['id']}/submit-review/", {}, format="json")
        self.client.force_authenticate(self.admin)
        self.client.post(f"{self.url}{created.data['id']}/approve/", {}, format="json")
        scheduled = self.client.post(f"{self.url}{created.data['id']}/schedule/", {}, format="json")
        self.assertEqual(scheduled.status_code, 200, scheduled.data)
        archived = self.client.post(f"{self.url}{created.data['id']}/archive/", {}, format="json")
        self.assertEqual(archived.data["status"], "archived")

    def test_approved_can_reopen_to_draft(self):
        created = self.create_assessment()
        self.client.post(f"{self.url}{created.data['id']}/submit-review/", {}, format="json")
        self.client.force_authenticate(self.admin)
        self.client.post(f"{self.url}{created.data['id']}/approve/", {}, format="json")
        result = self.client.post(f"{self.url}{created.data['id']}/reopen/", {}, format="json")
        self.assertEqual(result.data["status"], "draft")

    def test_student_cannot_create_assessment(self):
        self.client.force_authenticate(self.student)
        self.assertIn(self.create_assessment().status_code, (403, 400))

    def test_teacher_can_edit_own_draft(self):
        created = self.create_assessment()
        result = self.client.patch(f"{self.url}{created.data['id']}/", {"title": "Updated"}, format="json")
        self.assertEqual(result.status_code, 200)

    def test_teacher_can_delete_own_draft(self):
        created = self.create_assessment()
        self.assertEqual(self.client.delete(f"{self.url}{created.data['id']}/").status_code, 204)

    def test_non_draft_cannot_be_edited(self):
        created = self.create_assessment()
        self.client.post(f"{self.url}{created.data['id']}/submit-review/", {}, format="json")
        result = self.client.patch(f"{self.url}{created.data['id']}/", {"title": "tamper"}, format="json")
        self.assertIn(result.status_code, (403, 404))

    def test_list_is_tenant_scoped(self):
        Assessment.objects.create(institution=self.school_b, title="B", assessment_type="quiz", subject=self.subject_b, duration_minutes=30, created_by=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertTrue(all(item["institution"] == self.school_a.pk for item in rows))

    def test_cross_tenant_retrieve_returns_404(self):
        other = Assessment.objects.create(institution=self.school_b, title="B", assessment_type="quiz", subject=self.subject_b, duration_minutes=30, created_by=self.admin)
        self.assertEqual(self.client.get(f"{self.url}{other.pk}/").status_code, 404)

    def test_cross_tenant_update_returns_404(self):
        other = Assessment.objects.create(institution=self.school_b, title="B", assessment_type="quiz", subject=self.subject_b, duration_minutes=30, created_by=self.admin)
        self.assertEqual(self.client.patch(f"{self.url}{other.pk}/", {"title": "tamper"}, format="json").status_code, 404)

    def test_cross_tenant_delete_returns_404(self):
        other = Assessment.objects.create(institution=self.school_b, title="B", assessment_type="quiz", subject=self.subject_b, duration_minutes=30, created_by=self.admin)
        self.assertEqual(self.client.delete(f"{self.url}{other.pk}/").status_code, 404)

    def test_filter_by_subject(self):
        created = self.create_assessment()
        exam = Assessment.objects.get(pk=created.data['id'])
        self.question.status = 'archived'
        self.question.save(update_fields=['status'])
        response = self.client.get(self.url, {"subject": self.subject_a.pk})
        self.assertEqual(response.status_code, 200)
        for instances in ([exam], Assessment.objects.filter(pk=exam.pk)):
            with self.subTest(collection=type(instances).__name__):
                serializer = AssessmentSerializer(instances, many=True,
                    context={'institution': self.school_a})
                self.assertEqual(serializer.data[0]['questions'][0]['question'], self.question.pk)
                with CaptureQueriesContext(connection) as queries:
                    pinned = list(serializer.child.fields['questions'].child.fields['question'].queryset)
                self.assertLessEqual(len(queries), 1)
                self.assertIn(self.question.pk, [question.pk for question in pinned])

    def test_nested_question_list_add_edit_remove(self):
        created = self.create_assessment(questions=[])
        base = f"{self.url}{created.data['id']}/questions/"
        added = self.client.post(base, {"question": self.question.pk, "order": 1, "marks": "6.00"}, format="json")
        self.assertEqual(added.status_code, 201, added.data)
        self.question.status = 'archived'
        self.question.save(update_fields=['status'])
        self.assertEqual(self.client.get(base).status_code, 200)
        row = AssessmentQuestion.objects.get(pk=added.data['id'])
        for instances in (row, [row], AssessmentQuestion.objects.filter(pk=row.pk)):
            many = not isinstance(instances, AssessmentQuestion)
            serializer = AssessmentQuestionSerializer(instances, many=many,
                context={'assessment': row.assessment})
            payload = serializer.data[0] if many else serializer.data
            self.assertEqual(payload['question'], self.question.pk)
            child = serializer.child if many else serializer
            self.assertTrue(child.fields['question'].queryset.filter(pk=self.question.pk).exists())
        detail = f"{base}{added.data['id']}/"
        changed = self.client.patch(detail, {"marks": "7.00"}, format="json")
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(Decimal(Assessment.objects.get(pk=created.data["id"]).total_marks), Decimal("7.00"))
        self.assertEqual(self.client.delete(detail).status_code, 204)

    def test_nested_endpoint_rejects_nonapproved_question(self):
        created = self.create_assessment(questions=[])
        response = self.client.post(f"{self.url}{created.data['id']}/questions/", {"question": self.question_draft.pk, "order": 1, "marks": 2}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_nested_endpoint_cross_tenant_assessment_is_hidden(self):
        other = Assessment.objects.create(institution=self.school_b, title="B", assessment_type="quiz", subject=self.subject_b, duration_minutes=30, created_by=self.admin)
        self.assertEqual(self.client.get(f"{self.url}{other.pk}/questions/").status_code, 404)

    def test_multiple_membership_requires_explicit_tenant_selection(self):
        second_teacher = User.objects.create_user("multi@example.test", "Safe-pass-8392")
        InstitutionMembership.objects.create(user=second_teacher, institution=self.school_a, role="teacher")
        InstitutionMembership.objects.create(user=second_teacher, institution=self.school_b, role="teacher")
        self.client.force_authenticate(second_teacher)
        self.assertEqual(self.client.post(self.url, self.payload(), format="json").status_code, 400)
        response = self.client.post(self.url, self.payload(), format="json", HTTP_X_INSTITUTION_ID=str(self.school_b.pk))
        self.assertEqual(response.status_code, 400)  # subject/group/question belong to A

    def test_multiple_membership_valid_selection_and_relationships(self):
        multi = User.objects.create_user("multi2@example.test", "Safe-pass-8392")
        InstitutionMembership.objects.create(user=multi, institution=self.school_a, role="teacher")
        InstitutionMembership.objects.create(user=multi, institution=self.school_b, role="teacher")
        self.client.force_authenticate(multi)
        response = self.client.post(self.url, self.payload(), format="json", HTTP_X_INSTITUTION_ID=str(self.school_a.pk))
        self.assertEqual(response.status_code, 201, response.data)

    def test_filter_cannot_escape_tenant_scope(self):
        other = Assessment.objects.create(institution=self.school_b, title="B", assessment_type="quiz", subject=self.subject_b, duration_minutes=30, created_by=self.admin)
        response = self.client.get(self.url, {"subject": other.subject_id})
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        ids = [row["id"] for row in rows]
        self.assertNotIn(other.pk, ids)
