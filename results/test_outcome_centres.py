"""Institution centres and exam publication orchestration, using real services."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.contrib.auth.hashers import make_password
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from assessments.models import Assessment, QuickExamConfiguration, QuickExamCredential
from attempts.models import Attempt
from audit.models import AuditEvent
from candidates.models import Candidate
from groups.models import Group, GroupMembership
from questions.models import Question, QuestionOption
from tenants.models import InstitutionMembership
from .models import Result
from .services import mark_attempt, publish_result
from .tests import ResultFixtureMixin


class OutcomeCentreTests(ResultFixtureMixin, APITestCase):
    def setUp(self):
        self.group = Group.objects.create(institution=self.school, name="Cohort", code="C")
        self.assessment.group = self.group
        self.assessment.start_at = timezone.now() - timedelta(hours=1)
        self.assessment.end_at = timezone.now() + timedelta(hours=1)
        self.assessment.save()
        self.idle = Candidate.objects.create(institution=self.school, candidate_id="IDLE", first_name="Never", last_name="Started")
        for candidate in (self.candidate, self.idle):
            GroupMembership.objects.create(group=self.group, candidate=candidate)
        self.client.force_authenticate(self.admin)

    def index(self, kind="results", query="", institution=None):
        return self.client.get(f'/api/v1/assessments/outcomes/{kind}/?institution={institution or self.school.pk}{query}')

    def bulk(self, assessment=None, institution=None):
        return self.client.post(f'/api/v1/assessments/{(assessment or self.assessment).pk}/results/release/?institution={institution or self.school.pk}', {}, format="json")

    def marked(self, candidate=None, correct=True, assessment=None):
        attempt = self.make_attempt(candidate=candidate, assessment=assessment)
        options = self.foreign_mcq if assessment == self.foreign_assessment else self.mcq
        self.add_question(attempt, options[0].question, options, marks="3.00", selection=[options[0 if correct else 1]])
        attempt.submitted_at = timezone.now()
        attempt.save()
        return mark_attempt(attempt.pk)

    def row(self, response=None):
        response = response or self.index()
        self.assertEqual(response.status_code, 200)
        return next(row for row in response.data["results"] if row["id"] == self.assessment.pk)

    def test_all_centres_only_selected_authorized_assessments(self):
        for kind in ("results", "reports", "submissions"):
            response = self.index(kind)
            self.assertEqual([row["id"] for row in response.data["results"]], [self.assessment.pk])
            self.assertEqual(response.data["count"], 1)
            self.assertEqual(self.row(response)["institution"], self.school.pk)

    def test_all_centres_foreign_context_denied(self):
        for kind in ("results", "reports", "submissions"):
            self.assertEqual(self.index(kind, institution=self.other_school.pk).status_code, 404)

    def test_student_denied_all_centres(self):
        self.client.force_authenticate(self.student)
        for kind in ("results", "reports", "submissions"):
            self.assertEqual(self.index(kind).status_code, 404)

    def test_inactive_membership_denied(self):
        InstitutionMembership.objects.filter(user=self.admin).update(is_active=False)
        self.assertEqual(self.index().status_code, 404)

    def test_multiple_workspaces_require_explicit_context(self):
        InstitutionMembership.objects.create(user=self.admin, institution=self.other_school, role="institution_admin")
        self.assertEqual(self.client.get('/api/v1/assessments/outcomes/results/').status_code, 400)
        self.assertEqual(self.index(institution=self.other_school.pk).data["results"][0]["id"], self.foreign_assessment.pk)

    def test_read_roles_preserved(self):
        for user in (self.teacher, self.examiner):
            self.client.force_authenticate(user)
            for kind in ("results", "reports", "submissions"):
                self.assertEqual(self.index(kind).status_code, 200)

    def test_no_results_has_truthful_null_performance(self):
        row = self.row()
        self.assertEqual(row["summary"]["total_candidates"], 2)
        self.assertEqual(row["summary"]["not_started_count"], 2)
        self.assertEqual(row["summary"]["results_count"], 0)
        for field in ("average_percentage", "pass_rate", "highest_percentage", "lowest_percentage"):
            self.assertIsNone(row["summary"][field])
        self.assertEqual(row["summary"]["release_state"], "no_results")
        self.assertFalse(row["report_available"])

    def test_no_candidates_state(self):
        GroupMembership.objects.all().delete()
        self.assertEqual(self.row()["summary"]["total_candidates"], 0)

    def test_metrics_use_results_not_eligible_population(self):
        self.marked()
        summary = self.row()["summary"]
        self.assertEqual(summary["total_candidates"], 2)
        self.assertEqual(summary["results_count"], 1)
        self.assertEqual(summary["passed_count"], 1)
        self.assertEqual(summary["failed_count"], 0)
        self.assertEqual(summary["average_percentage"], Decimal("100.00"))
        self.assertEqual(summary["pass_rate"], Decimal("100.00"))

    def test_partial_performance_population(self):
        self.marked()
        self.marked(self.idle, correct=False)
        summary = self.row()["summary"]
        self.assertEqual(summary["average_percentage"], Decimal("50.00"))
        self.assertEqual(summary["pass_rate"], Decimal("50.00"))
        self.assertEqual((summary["passed_count"], summary["failed_count"]), (1, 1))

    def test_not_released_state(self):
        self.marked()
        summary = self.row()["summary"]
        self.assertEqual(summary["release_state"], "not_released")
        self.assertEqual((summary["released_count"], summary["unreleased_count"]), (0, 1))

    def test_partially_released_state(self):
        result = self.marked()
        self.marked(self.idle)
        publish_result(result.pk, actor=self.admin)
        summary = self.row()["summary"]
        self.assertEqual(summary["release_state"], "partially_released")
        self.assertEqual((summary["released_count"], summary["unreleased_count"]), (1, 1))

    def test_released_state(self):
        result = self.marked()
        publish_result(result.pk, actor=self.admin)
        self.assertEqual(self.row()["summary"]["release_state"], "released")

    def test_visibility_policy_not_a_duplicate_assessment_flag(self):
        result = self.marked()
        publish_result(result.pk, actor=self.admin)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            Assessment.objects.filter(pk=self.assessment.pk).update(result_visibility="hidden")
        self.assertEqual(self.row()["summary"]["release_state"], "released")

    def test_search_all_centres(self):
        for kind in ("results", "reports", "submissions"):
            self.assertEqual(self.index(kind, "&search=MARKING").data["count"], 1)
            self.assertEqual(self.index(kind, "&search=Foreign").data["count"], 0)

    def test_assessment_pagination(self):
        for index in range(26):
            Assessment.objects.create(institution=self.school, subject=self.subject, created_by=self.admin, title=f"Exam {index}", duration_minutes=10)
        first = self.index()
        second = self.index(query="&page=2")
        self.assertEqual(first.data["count"], 27)
        self.assertEqual(len(first.data["results"]), 25)
        self.assertEqual(len(second.data["results"]), 2)
        self.assertFalse({r["id"] for r in first.data["results"]} & {r["id"] for r in second.data["results"]})

    def test_index_queries_no_answers_and_read_only(self):
        self.marked()
        audits = AuditEvent.objects.count()
        with CaptureQueriesContext(connection) as queries:
            self.index()
        self.assertLessEqual(len(queries), 12)
        self.assertFalse(any('FROM `attempts_answer' in query["sql"] or 'FROM `results_resultquestion' in query["sql"] for query in queries))
        self.assertEqual(AuditEvent.objects.count(), audits)

    def test_reports_summary_reuses_existing_export_dataset(self):
        self.marked()
        self.assertEqual(self.row(self.index("reports"))["summary"], self.row()["summary"])
        self.assertTrue(self.row(self.index("reports"))["report_available"])
        for fmt in ("csv", "pdf", "docx"):
            self.assertEqual(self.client.get(f'/api/v1/assessments/{self.assessment.pk}/reports/{fmt}/?institution={self.school.pk}').status_code, 200)

    def test_submissions_active_finalized_never_started(self):
        self.make_attempt(Attempt.Status.IN_PROGRESS)
        summary = self.row(self.index("submissions"))["summary"]
        self.assertEqual((summary["in_progress_count"], summary["not_started_count"]), (1, 1))
        self.marked(self.idle)
        self.assertEqual(self.row(self.index("submissions"))["summary"]["submitted_count"], 1)

    def test_submissions_without_results_do_not_offer_report(self):
        self.make_attempt()
        row = self.row(self.index("reports"))
        self.assertEqual(row["summary"]["submitted_count"], 1)
        self.assertFalse(row["report_available"])

    def test_unknown_centre_rejected(self):
        self.assertEqual(self.index("secrets").status_code, 400)

    def test_bulk_admin_releases_all_using_existing_service(self):
        first = self.marked()
        second = self.marked(self.idle)
        with patch('results.owner_views.publish_result', wraps=publish_result) as service:
            response = self.bulk()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(service.call_count, 2)
        self.assertEqual(response.data["released_count"], 2)
        self.assertEqual(response.data["results_available"], 2)
        self.assertEqual(response.data["already_released_count"], 0)
        self.assertEqual(response.data["release_state"], "released")
        for result in (first, second):
            result.refresh_from_db()
            self.assertEqual(result.status, Result.Status.PUBLISHED)

    def test_bulk_non_admin_denied(self):
        self.marked()
        for user in (self.teacher, self.examiner, self.student):
            self.client.force_authenticate(user)
            self.assertEqual(self.bulk().status_code, 404 if user == self.student else 403)

    def test_bulk_cross_tenant_denied(self):
        self.assertEqual(self.bulk(self.foreign_assessment).status_code, 404)
        self.assertEqual(self.bulk(self.foreign_assessment, self.other_school.pk).status_code, 404)

    def test_bulk_already_published_preserved_and_repeat_idempotent(self):
        first = self.marked()
        self.marked(self.idle)
        publish_result(first.pk, actor=self.admin)
        first.refresh_from_db()
        original = (first.published_at, first.updated_at)
        response = self.bulk()
        self.assertEqual((response.data["released_count"], response.data["already_released_count"]), (1, 1))
        first.refresh_from_db()
        self.assertEqual((first.published_at, first.updated_at), original)
        audit_count = AuditEvent.objects.count()
        response = self.bulk()
        self.assertEqual((response.data["released_count"], response.data["already_released_count"]), (0, 2))
        self.assertEqual(AuditEvent.objects.count(), audit_count)

    def test_bulk_other_assessment_untouched(self):
        self.marked()
        foreign = self.marked(assessment=self.foreign_assessment)
        before = Result.objects.filter(pk=foreign.pk).values().get()
        self.bulk()
        self.assertEqual(Result.objects.filter(pk=foreign.pk).values().get(), before)

    def test_bulk_audits_one_per_new_publication(self):
        results = (self.marked(), self.marked(self.idle))
        self.bulk()
        events = AuditEvent.objects.filter(event_type=AuditEvent.Type.RESULT_PUBLISHED)
        self.assertEqual(events.count(), 2)
        self.assertEqual(set(events.values_list("resource_id", flat=True)), {str(r.pk) for r in results})
        for event in events:
            self.assertEqual(event.actor_id, self.admin.pk)
            self.assertEqual(event.institution_id, self.school.pk)
            self.assertNotIn("answer", str(event.metadata).lower())

    def test_bulk_zero_safe_no_result_creation_or_finalization(self):
        attempt = self.make_attempt(Attempt.Status.IN_PROGRESS)
        before = Attempt.objects.filter(pk=attempt.pk).values().get()
        count = AuditEvent.objects.count()
        response = self.bulk()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["released_count"], 0)
        self.assertEqual(response.data["results_available"], 0)
        self.assertEqual(response.data["release_state"], "no_results")
        self.assertEqual(Result.objects.count(), 0)
        self.assertEqual(Attempt.objects.filter(pk=attempt.pk).values().get(), before)
        self.assertEqual(AuditEvent.objects.count(), count)

    def test_bulk_does_not_change_scores_attempts_questions_or_provenance(self):
        self.marked()
        attempts = list(Attempt.objects.values())
        questions = list(Question.objects.values())
        options = list(QuestionOption.objects.values())
        scores = list(Result.objects.values('id', 'marks_obtained', 'total_marks', 'pass_mark', 'percentage', 'grade', 'passed', 'marked_at'))
        self.bulk()
        self.assertEqual(list(Attempt.objects.values()), attempts)
        self.assertEqual(list(Question.objects.values()), questions)
        self.assertEqual(list(QuestionOption.objects.values()), options)
        self.assertEqual(list(Result.objects.values('id', 'marks_obtained', 'total_marks', 'pass_mark', 'percentage', 'grade', 'passed', 'marked_at')), scores)

    def test_bulk_hidden_policy_rejected_without_partial_writes(self):
        self.assessment.result_visibility = "hidden"
        self.assessment.save()
        self.marked()
        self.marked(self.idle)
        response = self.bulk()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Result.objects.filter(status=Result.Status.PUBLISHED).count(), 0)
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.Type.RESULT_PUBLISHED).exists())

    def test_bulk_scheduled_policy_respected(self):
        self.assessment.result_visibility = "scheduled_release"
        self.assessment.save()
        self.marked()
        self.assertEqual(self.bulk().status_code, 400)
        # Advance the frozen server clock instead of editing a participated exam.
        with patch('django.utils.timezone.now', return_value=self.assessment.end_at + timedelta(seconds=1)):
            self.assertEqual(self.bulk().data["release_state"], "released")

    def test_bulk_withheld_uses_existing_publication_policy(self):
        result = self.marked()
        Result.objects.filter(pk=result.pk).update(status=Result.Status.WITHHELD)
        self.assertEqual(self.bulk().data["released_count"], 1)

    def test_bulk_malformed_ownership_excluded(self):
        result = self.marked()
        Result.objects.filter(pk=result.pk).update(candidate=self.foreign_candidate)
        self.assertEqual(self.bulk().data["results_available"], 0)
        result.refresh_from_db()
        self.assertEqual(result.status, Result.Status.PROVISIONAL)

    def test_bulk_invalid_unfinalized_result_not_published(self):
        result = self.marked()
        Attempt.objects.filter(pk=result.attempt_id).update(status=Attempt.Status.IN_PROGRESS)
        self.assertEqual(self.bulk().data["released_count"], 0)

    def test_candidate_before_after_bulk_own_only_safe_whitelist(self):
        result = self.marked()
        other = self.marked(self.idle)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get('/api/v1/results/my/').data, [])
        self.client.force_authenticate(self.admin)
        self.bulk()
        self.client.force_authenticate(self.student)
        rows = self.client.get('/api/v1/results/my/').data
        self.assertEqual([row["id"] for row in rows], [result.pk])
        self.assertNotIn(other.pk, [row["id"] for row in rows])
        self.assertEqual(set(rows[0]), {'id', 'assessment_title', 'assessment_type', 'marks_obtained', 'total_marks', 'percentage', 'grade', 'passed', 'published_at', 'submitted_at'})

    def test_individual_release_kept_partial_then_released(self):
        first = self.marked()
        second = self.marked(self.idle)
        for result, state in ((first, 'partially_released'), (second, 'released')):
            response = self.client.post(f'/api/v1/assessments/{self.assessment.pk}/results/{result.pk}/release/?institution={self.school.pk}', {})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.row()["summary"]["release_state"], state)

    def test_details_and_exports_remain_available_before_release(self):
        result = self.marked()
        response = self.client.get(f'/api/v1/assessments/{self.assessment.pk}/submissions/{result.attempt_id}/?institution={self.school.pk}')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["questions"][0]["options"][0]["is_correct"])
        self.assertEqual(response.data["candidate"]["publication"], "not_released")

    def test_quick_candidate_without_portal_account_preserved(self):
        from assessments.models import AssessmentQuestion
        self.assessment = Assessment.objects.create(institution=self.school, subject=self.subject,
            created_by=self.admin, title='Synthetic Quick outcomes', assessment_type='test',
            duration_minutes=30, candidate_access='access_code')
        AssessmentQuestion.objects.create(assessment=self.assessment, question=self.mcq[0].question, order=1, marks=3)
        configuration = QuickExamConfiguration.objects.create(assessment=self.assessment, exam_code="QUICK")
        QuickExamCredential.objects.create(configuration=configuration, candidate=self.idle, pin_hash=make_password("123456"), issued_by=self.admin)
        self.marked(self.idle)
        self.assertEqual(self.bulk().data["released_count"], 1)
        response = self.index()
        self.assertNotIn("pin_hash", str(response.data))
        self.assertIsNone(self.idle.user_id)

    def test_pending_count_includes_all_available_attempt_results(self):
        first = self.marked()
        Attempt.objects.filter(pk=first.attempt_id).update(attempt_number=2)
        second_attempt = self.make_attempt()
        second_attempt.attempt_number = 3
        second_attempt.save()
        self.add_question(second_attempt, self.mcq[0].question, self.mcq)
        mark_attempt(second_attempt.pk)
        response = self.client.get(f'/api/v1/assessments/{self.assessment.pk}/results/?institution={self.school.pk}')
        self.assertEqual(response.data["summary"]["results_count"], 1)
        self.assertEqual(response.data["summary"]["release_pending_count"], 2)
        self.assertEqual(self.bulk().data["released_count"], 2)
