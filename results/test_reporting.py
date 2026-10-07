import csv
import io
import zipfile
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone
from rest_framework.test import APITestCase

from assessments.models import Assessment, AssessmentQuestion, QuickExamConfiguration, QuickExamCredential
from attempts.models import Attempt
from audit.models import AuditEvent
from candidates.models import Candidate
from groups.models import Group, GroupMembership
from tenants.models import InstitutionMembership
from .reporting import build_assessment_report
from .report_exports import csv_report, pdf_report, docx_report, safe_csv_text
from .services import mark_attempt, publish_result
from .tests import ResultFixtureMixin


class ReportingTests(ResultFixtureMixin, APITestCase):
    def setUp(self):
        self.group = Group.objects.create(institution=self.school, name="Class", code="CLASS")
        self.assessment.group = self.group
        self.assessment.start_at = timezone.now() - timedelta(hours=1)
        self.assessment.end_at = timezone.now() + timedelta(hours=1)
        self.assessment.save()
        GroupMembership.objects.create(group=self.group, candidate=self.candidate)
        self.idle = Candidate.objects.create(institution=self.school, first_name="Never", last_name="Started", candidate_id="IDLE")
        GroupMembership.objects.create(group=self.group, candidate=self.idle)
        self.client.force_authenticate(self.admin)

    def url(self, suffix="outcomes/", institution=None, assessment=None):
        return f'/api/v1/assessments/{assessment or self.assessment.pk}/{suffix}?institution={institution or self.school.pk}'

    def report(self, **kwargs):
        return build_assessment_report(self.assessment, self.school, **kwargs)

    def marked(self, *, status=Attempt.Status.SUBMITTED, correct=True):
        attempt = self.make_attempt(status)
        attempt.submitted_at = timezone.now(); attempt.save()
        self.add_question(attempt, self.mcq[0].question, self.mcq, marks="3.00", selection=[self.mcq[0] if correct else self.mcq[1]])
        result = mark_attempt(attempt.pk)
        return attempt, result

    def test_never_started_population_blank_score(self):
        response = self.client.get(self.url("submissions/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        for row in response.data["results"]:
            self.assertEqual(row["submission_status"], "not_started")
            for field in ("score", "total_marks", "percentage", "passed", "result"):
                self.assertIsNone(row[field])

    def test_in_progress_no_read_side_effect(self):
        attempt = self.make_attempt(Attempt.Status.IN_PROGRESS)
        self.assertEqual(self.report()["rows"][0]["submission_status"], "in_progress")
        self.client.get(self.url("submissions/"))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "in_progress")
        self.assertFalse(hasattr(attempt, "result"))

    def test_normal_submitted(self):
        self.marked()
        self.assertEqual(self.report()["rows"][0]["submission_status"], "submitted")

    def test_expired_is_auto_submitted(self):
        self.marked(status=Attempt.Status.EXPIRED)
        self.assertEqual(self.report()["rows"][0]["submission_status"], "auto_submitted")
        self.assertEqual(self.report()["summary"]["auto_submitted_count"], 1)

    def test_integrity_auto_submission_uses_recorded_event(self):
        attempt, _ = self.marked()
        AuditEvent.objects.create(institution=self.school, event_type="integrity_auto_submitted", resource_type="attempts.attempt", resource_id=str(attempt.pk))
        self.assertEqual(self.report()["rows"][0]["submission_status"], "auto_submitted")

    def test_closed_window_never_started_and_unfinished(self):
        attempt = self.make_attempt(Attempt.Status.IN_PROGRESS)
        report = self.report(now=self.assessment.end_at + timedelta(seconds=1))
        self.assertEqual(report["summary"]["not_submitted_count"], 2)
        self.assertEqual(report["summary"]["started_count"], 1)
        self.assertEqual(report["summary"]["in_progress_count"], 0)
        attempt.refresh_from_db(); self.assertEqual(attempt.status, "in_progress")

    def test_completed_after_window_not_absent(self):
        self.marked()
        report = self.report(now=self.assessment.end_at + timedelta(seconds=1))
        self.assertEqual(report["summary"]["submitted_count"], 1)
        self.assertEqual(report["summary"]["not_submitted_count"], 1)

    def test_cancelled_is_not_fabricated_not_started(self):
        self.make_attempt(Attempt.Status.CANCELLED)
        self.assertEqual(self.report()["rows"][0]["submission_status"], "cancelled")

    def test_historical_participant_retained(self):
        self.marked()
        GroupMembership.objects.filter(candidate=self.candidate).update(is_active=False)
        self.assertEqual(self.report()["summary"]["total_candidates"], 2)

    def test_inactive_unstarted_not_eligible(self):
        Candidate.objects.filter(pk=self.idle.pk).update(status="inactive")
        self.assertEqual(self.report()["summary"]["total_candidates"], 1)

    def test_group_effective_dates(self):
        GroupMembership.objects.filter(candidate=self.idle).update(start_date=timezone.localdate() + timedelta(days=1))
        self.assertEqual(self.report()["summary"]["total_candidates"], 1)

    def test_quick_population_no_account_or_email(self):
        self.assessment = Assessment.objects.create(institution=self.school, subject=self.subject,
            created_by=self.admin, title='Synthetic Quick report', assessment_type='test',
            duration_minutes=30, candidate_access='access_code')
        config = QuickExamConfiguration.objects.create(assessment=self.assessment, exam_code="REPORT-QUICK")
        from django.contrib.auth.hashers import make_password
        QuickExamCredential.objects.create(configuration=config, candidate=self.idle, pin_hash=make_password("secret-report-pin"))
        report = self.report()
        self.assertEqual(report["summary"]["total_candidates"], 1)
        self.assertIsNone(self.idle.user_id); self.assertEqual(self.idle.email, "")
        for output in (csv_report(report), pdf_report(report), docx_report(report)):
            self.assertNotIn(b"secret-report-pin", output)

    def test_latest_attempt_only_no_duplicate_candidate(self):
        attempt, _ = self.marked()
        Attempt.objects.create(institution=self.school, candidate=self.candidate, assessment=self.assessment,
                               attempt_number=2, started_at=timezone.now(), expires_at=timezone.now()+timedelta(minutes=30),
                               last_activity_at=timezone.now(), pass_mark_snapshot=2)
        report = self.report()
        self.assertEqual(len(report["rows"]), 2)
        self.assertEqual(report["rows"][0]["submission_status"], "in_progress")
        self.assertIsNone(report["rows"][0]["score"])
        self.assertEqual(report["summary"]["results_count"], 0)

    def test_search_name_and_candidate_id(self):
        for query in ("ada", "M-001", "LEARNER"):
            response = self.client.get(self.url("submissions/") + "&search=" + query)
            self.assertEqual(response.data["count"], 1)
            self.assertEqual(response.data["results"][0]["candidate_id"], "M-001")

    def test_status_pass_fail_publication_filters(self):
        _, result = self.marked()
        for status, count in (("passed", 1), ("failed", 0), ("submitted", 1), ("not_started", 1), ("not_released", 1), ("released", 0)):
            self.assertEqual(self.client.get(self.url("results/") + "&status=" + status).data["count"], count)
        publish_result(result.pk, actor=self.admin)
        self.assertEqual(self.client.get(self.url("results/") + "&status=released").data["count"], 1)

    def test_invalid_filters_rejected(self):
        for query in ("&status=secret", "&sort=pin_hash"):
            self.assertEqual(self.client.get(self.url("results/") + query).status_code, 400)

    def test_pagination_population(self):
        for number in range(26):
            candidate = Candidate.objects.create(institution=self.school, first_name="Zed", candidate_id=f"Z-{number}")
            GroupMembership.objects.create(group=self.group, candidate=candidate)
        response = self.client.get(self.url("submissions/"))
        self.assertEqual(response.data["count"], 28); self.assertEqual(len(response.data["results"]), 25)
        self.assertEqual(len(self.client.get(self.url("submissions/") + "&page=2").data["results"]), 3)

    def test_sort_score_percentage_submission_nulls_last(self):
        self.marked()
        for sort in ("score", "-score", "percentage", "-percentage", "submitted_at", "-submitted_at"):
            response = self.client.get(self.url("results/") + "&sort=" + sort)
            self.assertEqual(response.data["results"][0]["candidate_id"], "M-001")

    def test_authoritative_stored_results_and_metrics(self):
        _, result = self.marked()
        report = self.report(); row = report["rows"][0]; summary = report["summary"]
        for field, expected in (("score", result.marks_obtained), ("total_marks", result.total_marks), ("percentage", result.percentage), ("grade", result.grade), ("passed", result.passed)):
            self.assertEqual(row[field], expected)
        self.assertEqual(summary, dict(total_candidates=2, started_count=1, not_started_count=1, in_progress_count=0,
            submitted_count=1, auto_submitted_count=0, not_submitted_count=0, results_count=1, passed_count=1, failed_count=0,
            average_percentage=Decimal("100.00"), highest_percentage=Decimal("100.00"), lowest_percentage=Decimal("100.00"), pass_rate=Decimal("100.00"),
            released_count=0, unreleased_count=1, release_state="not_released"))

    def test_average_and_pass_rate_exclude_missing(self):
        self.marked()
        other = self.make_attempt(candidate=self.idle)
        self.add_question(other, self.mcq[0].question, self.mcq, marks="3.00", selection=[self.mcq[1]])
        mark_attempt(other.pk)
        summary = self.report()["summary"]
        self.assertEqual(summary["average_percentage"], 50)
        self.assertEqual(summary["highest_percentage"], 100); self.assertEqual(summary["lowest_percentage"], 0)
        self.assertEqual(summary["passed_count"], 1); self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["pass_rate"], 50)

    def test_zero_results_safe_and_no_candidates(self):
        summary = self.report()["summary"]
        for field in ("average_percentage", "highest_percentage", "lowest_percentage", "pass_rate"):
            self.assertIsNone(summary[field])
        GroupMembership.objects.all().delete()
        self.assertEqual(self.report()["summary"]["total_candidates"], 0)

    def test_all_owner_endpoints_tenant_denial(self):
        attempt, _ = self.marked()
        self.client.force_authenticate(self.foreign)
        for suffix in ("outcomes/", "submissions/", "results/", f"submissions/{attempt.pk}/", "reports/csv/", "reports/pdf/", "reports/docx/"):
            self.assertEqual(self.client.get(self.url(suffix)).status_code, 404)

    def test_candidate_cannot_access_staff_endpoints(self):
        attempt, _ = self.marked(); self.client.force_authenticate(self.student)
        for suffix in ("outcomes/", "results/", f"submissions/{attempt.pk}/", "reports/csv/", "reports/pdf/", "reports/docx/"):
            self.assertEqual(self.client.get(self.url(suffix)).status_code, 404)

    def test_inactive_membership_denied(self):
        InstitutionMembership.objects.filter(user=self.admin).update(is_active=False)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_selected_workspace_cannot_cross_assessment(self):
        self.assertEqual(self.client.get(self.url(assessment=self.foreign_assessment.pk)).status_code, 404)

    def test_teacher_read_but_not_release(self):
        attempt, result = self.marked(); self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get(self.url(f"submissions/{attempt.pk}/")).status_code, 200)
        self.assertEqual(self.client.post(self.url(f"results/{result.pk}/release/")).status_code, 403)

    def test_detail_responses_correct_incorrect_unanswered_and_order(self):
        attempt, _ = self.marked()
        self.add_question(attempt, self.multi[0].question, self.multi, selection=[self.multi[1]])
        self.add_question(attempt, self.tf[0].question, self.tf)
        mark_attempt(attempt.pk)
        response = self.client.get(self.url(f"submissions/{attempt.pk}/"))
        self.assertEqual(response.status_code, 200)
        rows = response.data["questions"]
        self.assertEqual([row["order"] for row in rows], [1, 2, 3])
        self.assertEqual([row["status"] for row in rows], ["correct", "incorrect", "unanswered"])
        self.assertEqual(rows[0]["marks_obtained"], 3)
        self.assertTrue(rows[0]["options"][0]["selected"])
        self.assertTrue(rows[0]["options"][0]["is_correct"])
        self.assertFalse(any(option["selected"] for option in rows[2]["options"]))

    def test_unfinished_detail_not_exposed(self):
        attempt = self.make_attempt(Attempt.Status.IN_PROGRESS)
        self.assertEqual(self.client.get(self.url(f"submissions/{attempt.pk}/")).status_code, 404)

    def test_release_audit_and_candidate_no_answer_leak(self):
        _, result = self.marked()
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get("/api/v1/results/my/").data, [])
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(self.url(f"results/{result.pk}/release/")).status_code, 200)
        self.assertEqual(AuditEvent.objects.filter(event_type="result_published", resource_id=str(result.pk)).count(), 1)
        self.client.force_authenticate(self.student)
        rows = self.client.get("/api/v1/results/my/").data
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["percentage"], "100.00")
        self.assertIn("submitted_at", rows[0])
        self.assertFalse({"questions", "answers", "validation_note", "candidate", "is_correct"} & rows[0].keys())
        self.assertEqual(self.client.get(f"/api/v1/results/{result.pk}/").status_code, 200)

    def test_other_candidate_result_hidden(self):
        _, result = self.marked(); publish_result(result.pk, actor=self.admin)
        self.client.force_authenticate(self.foreign)
        self.assertEqual(self.client.get(f"/api/v1/results/{result.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/results/my/").data, [])

    def test_hidden_and_scheduled_release_policy_preserved(self):
        for visibility in ("hidden", "scheduled_release"):
            self.assessment = Assessment.objects.create(institution=self.school, subject=self.subject,
                group=self.group, created_by=self.admin, title='Synthetic publication policy',
                assessment_type='test', duration_minutes=30, result_visibility=visibility,
                end_at=timezone.now() + timedelta(hours=1))
            AssessmentQuestion.objects.create(assessment=self.assessment, question=self.mcq[0].question, order=1, marks=3)
            _, result = self.marked()
            response = self.client.post(self.url(f"results/{result.pk}/release/"))
            self.assertEqual(response.status_code, 400)

    def test_csv_values_non_submitter_and_secrets_absent(self):
        self.marked()
        output = self.client.get(self.url("reports/csv/"))
        self.assertEqual(output.status_code, 200)
        self.assertEqual(output["Cache-Control"], "private, no-store")
        rows = list(csv.DictReader(io.StringIO(output.content.decode("utf-8-sig"))))
        self.assertEqual(rows[0]["Score"], "3.00"); self.assertEqual(rows[1]["Score"], "")
        self.assertEqual(rows[1]["Submission"], "Not started")
        for token in ("is_correct", "pin_hash", "MCQ-1", "validation_note"):
            self.assertNotIn(token, output.content.decode("utf-8-sig"))

    def test_formula_injection_all_dangerous_prefixes(self):
        for text in ("=SUM(A1)", "+CMD", "-CMD", "@CMD", " \t=CMD", "\r+CMD"):
            self.assertTrue(safe_csv_text(text).startswith("'"))
        self.assertEqual(safe_csv_text("Normal"), "Normal")
        Candidate.objects.filter(pk=self.idle.pk).update(first_name="=HYPERLINK(x)", candidate_id="@CMD")
        rows = list(csv.DictReader(io.StringIO(csv_report(self.report()).decode("utf-8-sig"))))
        row = next(row for row in rows if "HYPERLINK" in row["Candidate"])
        self.assertTrue(row["Candidate"].startswith("'")); self.assertTrue(row["Candidate ID"].startswith("'"))

    def test_pdf_generated_metadata_and_no_secret_dataset(self):
        self.marked()
        response = self.client.get(self.url("reports/pdf/"))
        self.assertEqual(response.status_code, 200); self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertNotIn(b"MCQ-1", response.content)

    def test_pdf_receives_summary_and_every_candidate_value(self):
        self.marked()
        from reportlab.platypus import Paragraph
        with patch("reportlab.platypus.Paragraph", wraps=Paragraph) as paragraphs:
            pdf_report(self.report())
        text = "\n".join(call.args[0] for call in paragraphs.call_args_list)
        for value in ("Marking School", "Marking test", "Ada Learner", "Never Started", "3.00", "100.00", "Results available: 1", "Pass rate %: 100.00"):
            self.assertIn(value, text)
        for value in ("MCQ-1", "pin_hash", "validation_note", "is_correct"):
            self.assertNotIn(value, text)

    def test_docx_editable_content_and_no_keys(self):
        self.marked()
        response = self.client.get(self.url("reports/docx/"))
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            xml = archive.read("word/document.xml").decode()
        for text in ("Marking School", "Marking test", "Ada Learner", "Never Started", "100.00", "Pass rate %", "tblHeader"):
            self.assertIn(text, xml)
        for text in ("MCQ-1", "pin_hash", "is_correct", "validation_note"):
            self.assertNotIn(text, xml)

    def test_all_renderers_use_one_normalized_service(self):
        report = self.report()
        for format in ("csv", "pdf", "docx"):
            with patch("results.owner_views.build_assessment_report", return_value=report) as build, patch("results.report_exports.render_report", return_value=b"report") as render:
                self.assertEqual(self.client.get(self.url(f"reports/{format}/")).status_code, 200)
                build.assert_called_once(); render.assert_called_once_with(report, format)

    def test_report_query_count_bounded_and_no_answers(self):
        self.marked()
        with CaptureQueriesContext(connection) as queries:
            self.report()
        self.assertLessEqual(len(queries), 5)
        self.assertFalse(any('FROM `attempts_answer' in query["sql"] or 'FROM `results_resultquestion' in query["sql"] for query in queries))

    def test_no_read_audit_mutations(self):
        before = AuditEvent.objects.count()
        for suffix in ("outcomes/", "submissions/", "results/", "reports/csv/"):
            self.client.get(self.url(suffix))
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_wrong_report_institution_rejected(self):
        with self.assertRaises(ValueError):
            build_assessment_report(self.assessment, self.other_school)

    def test_platform_authority_requires_selected_workspace(self):
        InstitutionMembership.objects.create(user=self.admin, institution=self.other_school, role="platform_admin")
        self.assertEqual(self.client.get(self.url(institution=self.other_school.pk, assessment=self.foreign_assessment.pk)).status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/assessments/{self.assessment.pk}/outcomes/").status_code, 400)

    def test_superuser_can_read_without_fake_membership(self):
        self.foreign.is_superuser = True; self.foreign.save()
        self.client.force_authenticate(self.foreign)
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        self.assertFalse(InstitutionMembership.objects.filter(user=self.foreign, institution=self.school).exists())

    def test_django_staff_flag_alone_not_authority(self):
        self.student.is_staff = True; self.student.save()
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(self.url("reports/csv/")).status_code, 404)

    def test_inactive_institution_denies_reads_and_reports(self):
        self.school.is_active = False; self.school.save()
        for suffix in ("outcomes/", "results/", "reports/csv/", "reports/pdf/", "reports/docx/"):
            self.assertEqual(self.client.get(self.url(suffix)).status_code, 404)

    def test_release_cannot_cross_assessment_or_workspace(self):
        _, result = self.marked()
        self.assertEqual(self.client.post(self.url(f"results/{result.pk}/release/", institution=self.other_school.pk, assessment=self.foreign_assessment.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url(f"results/{result.pk}/release/")).status_code, 405)

    def test_multiselect_correct_response_uses_stored_marking(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.multi[0].question, self.multi, selection=[self.multi[0], self.multi[2]])
        mark_attempt(attempt.pk)
        data = self.client.get(self.url(f"submissions/{attempt.pk}/")).data
        self.assertEqual(data["questions"][0]["status"], "correct")
        self.assertEqual(sum(option["selected"] for option in data["questions"][0]["options"]), 2)

    def test_true_false_correct_response_uses_stored_marking(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.tf[0].question, self.tf, selection=[self.tf[0]])
        mark_attempt(attempt.pk)
        self.assertEqual(self.client.get(self.url(f"submissions/{attempt.pk}/")).data["questions"][0]["status"], "correct")

    def test_exports_do_not_mutate_stored_attempts_or_results(self):
        self.marked()
        from .models import Result, ResultQuestion
        before = (list(Attempt.objects.values()), list(Result.objects.values()), list(ResultQuestion.objects.values()))
        for format in ("csv", "pdf", "docx"):
            self.assertEqual(self.client.get(self.url(f"reports/{format}/")).status_code, 200)
        self.assertEqual(before, (list(Attempt.objects.values()), list(Result.objects.values()), list(ResultQuestion.objects.values())))

    def test_malformed_foreign_question_or_offered_option_never_leaks(self):
        from attempts.models import AttemptQuestion, AttemptQuestionOption
        attempt, _ = self.marked()
        own_row = attempt.attempt_questions.get()
        AttemptQuestion.objects.create(attempt=attempt, question=self.foreign_mcq[0].question, order=2, marks_available=1)
        AttemptQuestionOption.objects.create(attempt_question=own_row, option=self.foreign_mcq[0], order=4)
        response = self.client.get(self.url(f"submissions/{attempt.pk}/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["questions"]), 1)
        self.assertNotIn("Foreign MCQ", str(response.data))

    def test_malformed_result_ownership_never_leaks_score(self):
        from .models import Result
        _, result = self.marked()
        Result.objects.filter(pk=result.pk).update(institution=self.other_school)
        report = self.report()
        self.assertIsNone(report["rows"][0]["score"])
        self.assertIsNone(report["rows"][0]["result"])
        self.assertEqual(report["summary"]["results_count"], 0)

    def test_malformed_foreign_candidate_link_denied(self):
        attempt, _ = self.marked()
        Attempt.objects.filter(pk=attempt.pk).update(candidate=self.foreign_candidate)
        self.assertEqual(self.client.get(self.url(f"submissions/{attempt.pk}/")).status_code, 404)

    def test_unused_foreign_taxonomy_never_enters_detail_payload(self):
        from questions.models import Question, Topic
        attempt, _ = self.marked()
        topic = Topic.objects.create(institution=self.other_school, subject=self.other_subject, name="Foreign private taxonomy")
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            Question.objects.filter(pk=self.mcq[0].question_id).update(topic=topic)
        response = self.client.get(self.url(f"submissions/{attempt.pk}/"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Foreign private taxonomy", str(response.data))
        self.assertNotIn("topic", response.data["questions"][0]["question"])
