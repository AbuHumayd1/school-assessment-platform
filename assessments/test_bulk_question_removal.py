from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from attempts.models import Attempt
from audit.models import AuditEvent
from candidates.models import Candidate
from questions.models import Question, QuestionOption
from results.models import Result
from .models import Assessment, AssessmentQuestion, QuickExamConfiguration, QuickExamCredential
from .test_bulk_questions import BulkSubjectQuestionTests


class BulkQuestionRemovalTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Only generated fixtures in Django's isolated test database.
        BulkSubjectQuestionTests.setUpTestData.__func__(cls)
        AssessmentQuestion.objects.bulk_create([
            AssessmentQuestion(assessment=cls.exam, question=q, order=i + 1, marks=q.marks)
            for i, q in enumerate(cls.questions)
        ])
        cls.second = Assessment.objects.create(institution=cls.school, subject=cls.subject,
            created_by=cls.platform, title="Separate fixture exam", assessment_type="test", duration_minutes=30)
        cls.second_row = AssessmentQuestion.objects.create(assessment=cls.second, question=cls.questions[0], order=8, marks=2)
        cls.foreign_exam = Assessment.objects.create(institution=cls.other, subject=cls.foreign_subject,
            created_by=cls.platform, title="Foreign fixture exam", assessment_type="test", duration_minutes=30)
        cls.foreign_row = AssessmentQuestion.objects.create(assessment=cls.foreign_exam, question=cls.extras[0], order=1, marks=1)

    def setUp(self):
        self.client.force_authenticate(self.platform)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))
        self.url = f"/api/v1/assessments/{self.exam.pk}/questions/remove/"
        self.rows = list(self.exam.assessment_questions.order_by("order"))
        self.bank = list(Question.objects.order_by("pk").values())
        self.options = list(QuestionOption.objects.order_by("pk").values())

    def remove(self, **selection):
        return self.client.post(self.url, selection, format="json")

    def unchanged_bank(self):
        self.assertEqual(list(Question.objects.order_by("pk").values()), self.bank)
        self.assertEqual(list(QuestionOption.objects.order_by("pk").values()), self.options)
        self.assertTrue(AssessmentQuestion.objects.filter(pk=self.second_row.pk).exists())
        self.assertTrue(AssessmentQuestion.objects.filter(pk=self.foreign_row.pk).exists())

    def test_remove_one_attachment_only(self):
        response = self.remove(attachments=[self.rows[0].pk])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["removed_count"], 1)
        self.assertEqual(response.data["question_count"], 150)
        self.unchanged_bank()

    def test_remove_multiple_deduplicates_selection_and_keeps_remaining_orders_marks(self):
        selected = [self.rows[1].pk, self.rows[4].pk]
        before = list(self.exam.assessment_questions.exclude(pk__in=selected).values())
        response = self.remove(attachments=selected + selected)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["removed_count"], 2)
        self.assertEqual(list(self.exam.assessment_questions.values()), before)
        self.unchanged_bank()

    def test_select_all_151_across_pages_and_add_again_in_document_order(self):
        for page in (1, 2, 7):
            response = self.client.get(self.url, {"page": page})
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["count"], 151)
            self.assertLessEqual(len(response.data["results"]), 25)
        response = self.remove(select_all=True, expected_count=151)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["removed_count"], 151)
        self.assertEqual(response.data["question_count"], 0)
        self.assertEqual(response.data["total_marks"], "0.00")
        self.assertFalse(self.exam.assessment_questions.exists())
        self.assertEqual(AuditEvent.objects.filter(event_type="assessment_question_removed").count(), 151)
        self.unchanged_bank()
        added = self.client.post(f"/api/v1/assessments/{self.exam.pk}/questions/add/",
            {"select_all": True, "expected_count": 151}, format="json")
        self.assertEqual(added.status_code, 200, added.data)
        self.assertEqual(added.data["added_count"], 151)
        self.assertEqual(list(self.exam.assessment_questions.values_list("question_id", flat=True)), [q.pk for q in reversed(self.questions)])
        self.unchanged_bank()

    def test_search_limits_select_all_on_server_across_pages(self):
        search = "Pilot 1"
        expected = [row.pk for row in self.rows if search in row.question.text]
        self.assertGreater(len(expected), 25)
        for page in (1, 2):
            listing = self.client.get(self.url, {"search": search, "page": page})
            self.assertEqual(listing.data["count"], len(expected))
            self.assertTrue(all(search in r["question"]["text"] for r in listing.data["results"]))
        response = self.remove(select_all=True, search=search, expected_count=len(expected))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["removed_count"], len(expected))
        self.assertFalse(self.exam.assessment_questions.filter(pk__in=expected).exists())
        self.assertEqual(self.exam.assessment_questions.count(), 151 - len(expected))
        self.unchanged_bank()

    def test_stale_count_rejects_entire_selection(self):
        before = list(self.exam.assessment_questions.values())
        for count in (150, 152):
            response = self.remove(select_all=True, expected_count=count)
            self.assertEqual(response.status_code, 400)
            self.assertIn("changed", str(response.data))
            self.assertEqual(list(self.exam.assessment_questions.values()), before)
        self.assertFalse(AuditEvent.objects.filter(event_type="assessment_question_removed").exists())

    def test_invalid_foreign_other_exam_or_unattached_selection_is_atomic(self):
        for pk in (self.foreign_row.pk, self.second_row.pk, max(r.pk for r in self.rows) + 10000):
            self.assertEqual(self.remove(attachments=[self.rows[0].pk, pk]).status_code, 400)
            self.assertEqual(self.exam.assessment_questions.count(), 151)
        self.unchanged_bank()

    def test_workspace_and_managed_admin_preparation_denied_for_list_and_removal(self):
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.other.pk))
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.remove(select_all=True, expected_count=151).status_code, 404)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.remove(select_all=True, expected_count=151).status_code, 403)
        self.client.force_authenticate(User.objects.create_user("removal-outsider@example.test"))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.remove(attachments=[self.rows[0].pk]).status_code, 403)
        self.assertEqual(self.exam.assessment_questions.count(), 151)

    def test_non_draft_and_attempt_result_history_block_removal_without_mutation(self):
        Assessment.objects.filter(pk=self.exam.pk).update(status="review")
        self.assertEqual(self.remove(select_all=True, expected_count=151).status_code, 403)
        Assessment.objects.filter(pk=self.exam.pk).update(status="draft")
        candidate = Candidate.objects.create(institution=self.school, candidate_id="REMOVE-FIXTURE", first_name="Test", last_name="Only")
        now = timezone.now()
        attempt = Attempt.objects.create(institution=self.school, assessment=self.exam, candidate=candidate,
            attempt_number=1, started_at=now, expires_at=now + timedelta(minutes=30), last_activity_at=now)
        result = Result.objects.create(institution=self.school, assessment=self.exam, candidate=candidate, attempt=attempt,
            total_marks=1, marks_obtained=0, pass_mark=0, marked_at=now)
        history = (list(Attempt.objects.values()), list(Result.objects.values()))
        self.assertEqual(self.remove(select_all=True, expected_count=151).status_code, 400)
        self.assertEqual(self.exam.assessment_questions.count(), 151)
        self.assertEqual((list(Attempt.objects.values()), list(Result.objects.values())), history)
        self.assertTrue(Result.objects.filter(pk=result.pk).exists())
        self.unchanged_bank()

    def test_mid_removal_failure_rolls_back_all_detachments_and_audits(self):
        original = AssessmentQuestion.delete
        calls = []
        def fail_second(row, *args, **kwargs):
            calls.append(row.pk)
            if len(calls) == 2:
                raise IntegrityError("Synthetic removal failure")
            return original(row, *args, **kwargs)
        with patch.object(AssessmentQuestion, "delete", fail_second):
            with self.assertRaises(IntegrityError):
                self.remove(select_all=True, expected_count=151)
        self.assertEqual(self.exam.assessment_questions.count(), 151)
        self.assertFalse(AuditEvent.objects.filter(event_type="assessment_question_removed").exists())
        self.unchanged_bank()

    def test_selection_fields_are_strict_and_select_all_requires_count(self):
        for body in ({}, {"attachments": []}, {"select_all": True},
                     {"select_all": True, "expected_count": 151, "attachments": [self.rows[0].pk]},
                     {"select_all": True, "expected_count": 151, "institution": self.other.pk},
                     {"attachments": [self.rows[0].pk], "search": "Pilot"}):
            self.assertEqual(self.remove(**body).status_code, 400)
        self.assertEqual(self.exam.assessment_questions.count(), 151)

    def test_removal_does_not_change_candidates_or_quick_credentials(self):
        from django.contrib.auth.hashers import make_password
        candidate = Candidate.objects.create(institution=self.school, candidate_id="KEEP-FIXTURE", first_name="Test", last_name="Only")
        quick = Assessment.objects.create(institution=self.school, subject=self.subject, created_by=self.platform,
            title="Unrelated Quick fixture", assessment_type="test", duration_minutes=30, candidate_access="access_code")
        configuration = QuickExamConfiguration.objects.create(assessment=quick, exam_code="REMOVAL-FIXTURE")
        QuickExamCredential.objects.create(configuration=configuration, candidate=candidate, pin_hash=make_password("fixture-only-pin"))
        before = (list(Candidate.objects.values()), list(QuickExamCredential.objects.values()), list(QuickExamConfiguration.objects.values()))
        self.assertEqual(self.remove(select_all=True, expected_count=151).status_code, 200)
        self.assertEqual((list(Candidate.objects.values()), list(QuickExamCredential.objects.values()), list(QuickExamConfiguration.objects.values())), before)
        self.unchanged_bank()
