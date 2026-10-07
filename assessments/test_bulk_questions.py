from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError
from rest_framework.test import APITestCase

from accounts.models import User
from audit.models import AuditEvent
from institutions.models import Institution
from questions.models import Question, QuestionOption
from subjects.models import Subject
from tenants.models import InstitutionMembership
from .models import Assessment, AssessmentQuestion


class BulkSubjectQuestionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = Institution.objects.create(name="Bulk managed client", workspace_mode="managed_exam")
        cls.other = Institution.objects.create(name="Other bulk client")
        cls.platform = User.objects.create_superuser("bulk-platform@example.test", None)
        cls.admin = User.objects.create_user("bulk-admin@example.test")
        InstitutionMembership.objects.create(user=cls.admin, institution=cls.school, role="institution_admin")
        cls.subject = Subject.objects.create(institution=cls.school, name="Pilot", code="PILOT")
        cls.other_subject = Subject.objects.create(institution=cls.school, name="Other subject", code="OTHER")
        cls.foreign_subject = Subject.objects.create(institution=cls.other, name="Foreign", code="PILOT")
        cls.questions = Question.objects.bulk_create([Question(institution=cls.school, subject=cls.subject,
            created_by=cls.platform, text=f"Pilot {index}", question_type="multiple_choice", status="draft",
            marks=Decimal("1.25"), source_metadata={"section_order": 1, "document_order": 151-index})
            for index in range(151)])
        extras = [Question(institution=institution, subject=subject, created_by=cls.platform,
            text="Pilot excluded", question_type="multiple_choice", status="draft")
            for institution, subject, status in [(cls.other, cls.foreign_subject, "approved"),
                (cls.school, cls.other_subject, "approved"), (cls.school, cls.subject, "draft"),
                (cls.school, cls.subject, "review"), (cls.school, cls.subject, "archived")]]
        cls.extras = Question.objects.bulk_create(extras)
        # MySQL bulk inserts need not populate the in-memory auto-increment IDs.
        cls.questions = list(Question.objects.filter(institution=cls.school, subject=cls.subject,
            text__startswith='Pilot ').exclude(text='Pilot excluded').order_by('pk'))
        cls.extras = list(Question.objects.exclude(pk__in=[q.pk for q in cls.questions]).order_by("pk"))
        QuestionOption.objects.bulk_create([QuestionOption(question=q, text=f"Option {order}", order=order,
            is_correct=order == 1) for q in cls.questions + cls.extras for order in (1, 2)])
        for question, target_status in zip(cls.questions + cls.extras,
                ['approved'] * 151 + ['approved', 'approved', 'draft', 'review', 'archived']):
            if target_status == 'draft':
                continue
            question.status = 'approved' if target_status == 'archived' else target_status
            question.save(update_fields=['status'])
            if target_status == 'archived':
                question.status = 'archived'
                question.save(update_fields=['status'])
        cls.exam = Assessment.objects.create(institution=cls.school, subject=cls.subject, created_by=cls.platform,
            title="Bulk pilot draft", assessment_type="test", duration_minutes=30, status="draft")

    def setUp(self):
        self.client.force_authenticate(self.platform)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))
        self.url = f"/api/v1/assessments/{self.exam.pk}/questions/add/"

    def add_all(self, **extra):
        return self.client.post(self.url, {"select_all": True, **extra}, format="json")

    def test_platform_attaches_all_151_in_one_atomic_operation_in_document_order(self):
        before = list(Question.objects.order_by("pk").values())
        options = list(QuestionOption.objects.order_by("pk").values())
        response = self.add_all(expected_count=151)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["added_count"], 151)
        rows = list(self.exam.assessment_questions.order_by("order"))
        self.assertEqual([r.question_id for r in rows], [q.pk for q in reversed(self.questions)])
        self.assertEqual([r.order for r in rows], list(range(1, 152)))
        self.assertEqual(len({r.question_id for r in rows}), 151)
        self.assertTrue(all(r.marks == Decimal("1.25") for r in rows))
        self.assertEqual(list(Question.objects.order_by("pk").values()), before)
        self.assertEqual(list(QuestionOption.objects.order_by("pk").values()), options)
        self.assertEqual(self.add_all().data["added_count"], 0)
        self.assertEqual(self.exam.assessment_questions.count(), 151)

    def test_existing_attachments_kept_and_new_questions_append_after_maximum(self):
        AssessmentQuestion.objects.create(assessment=self.exam, question=self.questions[0], order=7, marks="2.00")
        response = self.add_all(expected_count=150)
        self.assertEqual(response.status_code, 200, response.data)
        rows = list(self.exam.assessment_questions.order_by("order"))
        self.assertEqual(rows[0].order, 7)
        self.assertEqual(rows[0].marks, Decimal("2.00"))
        self.assertEqual([r.order for r in rows[1:]], list(range(8, 158)))
        self.assertEqual([r.question_id for r in rows[1:]], [q.pk for q in reversed(self.questions[1:])])

    def test_full_matching_count_excludes_attached_and_is_independent_of_page(self):
        AssessmentQuestion.objects.create(assessment=self.exam, question=self.questions[0], order=1, marks="1.25")
        url = f"/api/v1/assessments/question-options/?subject={self.subject.pk}&assessment={self.exam.pk}"
        for page in (1, 2):
            response = self.client.get(url + f"&page={page}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["count"], 151)
            self.assertEqual(response.data["available_count"], 150)
            self.assertLess(len(response.data["results"]), 150)

    def test_search_selects_all_matching_only_and_filters_all_ineligible_records(self):
        response = self.add_all(search="Pilot 1")
        self.assertEqual(response.status_code, 200, response.data)
        expected = {q.pk for q in self.questions if "Pilot 1" in q.text}
        self.assertEqual(set(self.exam.assessment_questions.values_list("question_id", flat=True)), expected)
        self.assertFalse(self.exam.assessment_questions.filter(question__in=self.extras).exists())

    def test_explicit_foreign_subject_tenant_and_unapproved_ids_rejected_atomically(self):
        for question in self.extras:
            with self.subTest(question=question.pk):
                response = self.client.post(self.url, {"questions": [self.questions[0].pk, question.pk]}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertFalse(self.exam.assessment_questions.exists())

    def test_managed_admin_cannot_bulk_attach(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.add_all().status_code, 403)
        self.assertFalse(self.exam.assessment_questions.exists())

    def test_wrong_workspace_and_noneditable_assessment_rejected(self):
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.other.pk))
        self.assertEqual(self.add_all().status_code, 404)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))
        Assessment.objects.filter(pk=self.exam.pk).update(status="review")
        self.assertEqual(self.add_all().status_code, 403)
        self.assertFalse(self.exam.assessment_questions.exists())

    def test_attempt_history_lock_respected(self):
        from attempts.models import Attempt
        from candidates.models import Candidate
        from django.utils import timezone
        from datetime import timedelta
        candidate = Candidate.objects.create(institution=self.school, candidate_id="BULK001",
            first_name="Test", last_name="Candidate")
        now = timezone.now()
        Attempt.objects.create(institution=self.school, assessment=self.exam, candidate=candidate,
            attempt_number=1, started_at=now, expires_at=now + timedelta(minutes=30), last_activity_at=now)
        response = self.add_all()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.exam.assessment_questions.exists())

    def test_stale_count_and_ambiguous_payload_abort_without_writes(self):
        for payload in ({"select_all": True, "expected_count": 150},
                        {"select_all": True, "questions": [self.questions[0].pk]},
                        {"select_all": True, "subject": self.other_subject.pk}):
            self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        self.assertFalse(self.exam.assessment_questions.exists())

    def test_mid_batch_database_failure_rolls_back_attachments_and_audits(self):
        original = AssessmentQuestion.save
        calls = []
        def save(instance, *args, **kwargs):
            calls.append(instance)
            if len(calls) == 2:
                raise IntegrityError("Concurrent failure")
            return original(instance, *args, **kwargs)
        with patch.object(AssessmentQuestion, "save", save):
            with self.assertRaises(IntegrityError):
                self.add_all()
        self.assertFalse(self.exam.assessment_questions.exists())
        self.assertFalse(AuditEvent.objects.filter(event_type="assessment_question_attached").exists())

    def test_existing_single_attachment_endpoint_still_works(self):
        response = self.client.post(f"/api/v1/assessments/{self.exam.pk}/questions/",
            {"question": self.questions[0].pk, "order": 1, "marks": "1.25"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.exam.assessment_questions.count(), 1)
