from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from assessments.models import Assessment
from attempts.models import Attempt
from candidates.models import Candidate
from institutions.models import Institution
from questions.models import Question
from results.models import Result
from subjects.models import Subject
from tenants.models import InstitutionMembership


class WorkspaceDashboardTests(APITestCase):
    url = "/api/v1/institution/dashboard/"

    def setUp(self):
        self.a = Institution.objects.create(name="Organizer A")
        self.b = Institution.objects.create(name="Organizer B")
        self.user = User.objects.create_user("dashboard@example.test", "safe-password-932")
        self.membership = InstitutionMembership.objects.create(
            institution=self.a, user=self.user, role="institution_admin",
        )
        self.client.force_authenticate(self.user)
        self.now = timezone.now()
        self.subject = Subject.objects.create(institution=self.a, code="A", name="Subject A")

    def assessment(self, title="Assessment A", **kwargs):
        return Assessment.objects.create(
            institution=self.a, subject=self.subject, title=title, created_by=self.user,
            assessment_type="quiz", duration_minutes=30, **kwargs,
        )

    def get(self, section=None, institution=None):
        return self.client.get(self.url, {"section": section} if section else {},
                               HTTP_X_INSTITUTION_ID=str((institution or self.a).pk))

    def test_empty_workspace_has_real_zeros_and_empty_lists(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        for key in ("active_candidates", "questions", "assessments", "results"):
            self.assertEqual(response.data["counts"][key], 0)
        self.assertEqual(response.data["assessment_status_counts"], dict.fromkeys(Assessment.Status.values, 0))
        self.assertEqual(self.get("assessments").data["upcoming_assessments"], [])
        self.assertEqual(self.get("results").data["recent_results"], [])

    def test_real_counts_and_full_status_overview_are_not_limited_to_five(self):
        for i in range(7):
            self.assessment(title=str(i))
        Question.objects.create(institution=self.a, subject=self.subject, created_by=self.user,
                                question_type="true_false", text="Actual question")
        response = self.get().data
        self.assertEqual(response["counts"]["questions"], 1)
        self.assertEqual(response["counts"]["assessments"], 7)
        self.assertEqual(response["assessment_status_counts"]["draft"], 7)
        self.assertEqual(len(self.get("assessments").data["recent_assessments"]), 5)

    def test_scheduled_list_excludes_ended_and_draft_records(self):
        future = self.assessment("Future", status="scheduled", start_at=self.now + timedelta(hours=1))
        active = self.assessment("Active", status="scheduled", start_at=self.now - timedelta(hours=1),
                                 end_at=self.now + timedelta(hours=1))
        self.assessment("Ended", status="scheduled", start_at=self.now - timedelta(hours=2),
                        end_at=self.now - timedelta(hours=1))
        self.assessment()
        response = self.get("assessments")
        self.assertEqual(response.status_code, 200)
        rows = response.data["upcoming_assessments"]
        self.assertEqual([row["id"] for row in rows], [active.pk, future.pk])
        self.assertEqual(rows[0]["subject"], "Subject A")
        self.assertIsNone(rows[0]["group"])
        self.assertEqual(rows[0]["duration_minutes"], 30)
        self.assertNotIn("assessment_questions", rows[0])

    def test_result_summaries_are_bounded_ordered_and_do_not_include_answers(self):
        assessment = self.assessment()
        candidate = Candidate.objects.create(institution=self.a, candidate_id="CA-1",
                                             first_name="Candidate", last_name="A")
        for i in range(7):
            attempt = Attempt.objects.create(institution=self.a, assessment=assessment, candidate=candidate,
                                             attempt_number=i + 1, status="submitted", started_at=self.now,
                                             expires_at=self.now + timedelta(hours=1), last_activity_at=self.now)
            Result.objects.create(institution=self.a, candidate=candidate, assessment=assessment, attempt=attempt,
                                  total_marks=10, marks_obtained=8, pass_mark=5,
                                  marked_at=self.now + timedelta(minutes=i))
        for role in ("institution_admin", "teacher", "examiner"):
            self.membership.role = role
            self.membership.save()
            response = self.get("results")
            self.assertEqual(response.status_code, 200)
            rows = response.data["recent_results"]
            self.assertEqual(len(rows), 5)
            self.assertGreater(rows[0]["id"], rows[1]["id"])
            self.assertEqual(rows[0]["candidate_id"], "CA-1")
            self.assertEqual(rows[0]["marks_obtained"], "8.00")
            self.assertEqual(set(rows[0]), {"id", "candidate_id", "assessment_title", "status",
                                            "marks_obtained", "total_marks", "marked_at"})
            self.assertEqual(self.get().data["counts"]["results"], 7)

    def test_each_section_rejects_foreign_student_inactive_and_anonymous_context(self):
        for section in (None, "assessments", "results"):
            self.assertEqual(self.get(section, self.b).status_code, 404)
        for role, active in (("student", True), ("teacher", False), ("examiner", False)):
            self.membership.role, self.membership.is_active = role, active
            self.membership.save()
            for section in (None, "assessments", "results"):
                self.assertEqual(self.get(section).status_code, 404)
        self.client.force_authenticate(None)
        for section in (None, "assessments", "results"):
            self.assertIn(self.get(section).status_code, (401, 403))

    def test_selected_workspace_is_scoped_for_each_role_and_section(self):
        InstitutionMembership.objects.create(institution=self.b, user=self.user, role="teacher")
        subject_b = Subject.objects.create(institution=self.b, code="B", name="Private B")
        Assessment.objects.create(institution=self.b, subject=subject_b, created_by=self.user,
                                  title="Private assessment B", assessment_type="quiz", duration_minutes=20)
        candidate = Candidate.objects.create(institution=self.b, candidate_id="PRIVATE-B",
                                             first_name="B", last_name="Candidate")
        assessment = Assessment.objects.get(institution=self.b)
        attempt = Attempt.objects.create(institution=self.b, assessment=assessment, candidate=candidate,
                                         attempt_number=1, started_at=self.now, expires_at=self.now + timedelta(hours=1),
                                         last_activity_at=self.now)
        Result.objects.create(institution=self.b, candidate=candidate, assessment=assessment, attempt=attempt,
                              total_marks=10, marks_obtained=5, pass_mark=5, marked_at=self.now)
        for role in ("institution_admin", "teacher", "examiner"):
            self.membership.role = role
            self.membership.save()
            self.assertEqual(self.client.get(self.url).status_code, 400)
            self.assertEqual(self.get().data["counts"]["assessments"], 0)
            self.assertEqual(self.get().data["counts"]["results"], 0)
            self.assertEqual(self.get("assessments").data["recent_assessments"], [])
            self.assertEqual(self.get("results").data["recent_results"], [])
            self.assertEqual(self.get(None, self.b).data["counts"]["results"], 1)
            self.assertEqual(self.get("results", self.b).data["recent_results"][0]["candidate_id"], "PRIVATE-B")
            self.assertNotIn("active_members", self.get(None, self.b).data["counts"])

    def test_each_section_rejects_inactive_institution(self):
        self.a.is_active = False
        self.a.save()
        for section in (None, "assessments", "results"):
            self.assertEqual(self.get(section).status_code, 404)

    def test_unsupported_section_is_rejected(self):
        self.assertEqual(self.get("audit").status_code, 400)
