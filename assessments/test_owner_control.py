import json
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APITestCase
from accounts.models import User
from audit.models import AuditEvent
from candidates.models import Candidate
from groups.models import Group, GroupMembership
from institutions.models import Institution
from questions.models import Question, QuestionOption
from subjects.models import Subject
from tenants.models import InstitutionMembership
from attempts.models import Attempt
from results.models import Result
from .models import Assessment, AssessmentCandidate, AssessmentQuestion, QuickExamConfiguration, QuickExamCredential, QuickExamSession


class OwnerControlTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Institution.objects.create(name="Client A")
        cls.b = Institution.objects.create(name="Client B")
        cls.platform = Institution.objects.create(name="Platform")
        cls.operator = User.objects.create_user("operator@owner.test")
        cls.admin = User.objects.create_user("admin@owner.test")
        cls.teacher = User.objects.create_user("teacher@owner.test")
        cls.examiner = User.objects.create_user("examiner@owner.test")
        cls.student = User.objects.create_user("student@owner.test")
        cls.other_admin = User.objects.create_user("other@owner.test")
        for user, institution, role in ((cls.operator, cls.platform, "platform_admin"), (cls.admin, cls.a, "institution_admin"),
                                         (cls.teacher, cls.a, "teacher"), (cls.examiner, cls.a, "examiner"),
                                         (cls.student, cls.a, "student"), (cls.other_admin, cls.b, "institution_admin")):
            InstitutionMembership.objects.create(user=user, institution=institution, role=role)
        cls.subject = Subject.objects.create(institution=cls.a, name="Subject A", code="A")
        cls.subject_b = Subject.objects.create(institution=cls.b, name="Subject B", code="B")
        cls.other_subject = Subject.objects.create(institution=cls.a, name="Other subject", code="O")
        cls.group = Group.objects.create(institution=cls.a, name="Cohort", code="C")
        cls.group_b = Group.objects.create(institution=cls.b, name="Other cohort", code="C")
        cls.question = cls.make_question(cls.subject, cls.operator, "Approved paper")
        cls.question_b = cls.make_question(cls.subject_b, cls.operator, "Other paper")
        cls.question_other_subject = cls.make_question(cls.other_subject, cls.operator, "Other subject paper")
        cls.draft_question = cls.make_question(cls.subject, cls.operator, "Draft paper", approved=False)
        cls.exam = Assessment.objects.create(institution=cls.a, subject=cls.subject, group=cls.group, created_by=cls.operator,
                                            title="Managed exam", assessment_type="test", duration_minutes=30)
        cls.exam_b = Assessment.objects.create(institution=cls.b, subject=cls.subject_b, created_by=cls.operator,
                                              title="Other client exam", assessment_type="test", duration_minutes=30)
        cls.link = AssessmentQuestion.objects.create(assessment=cls.exam, question=cls.question, marks=2, order=1)
        cls.candidate = Candidate.objects.create(institution=cls.a, candidate_id="A-1", first_name="Amina", last_name="Candidate")
        cls.candidate_b = Candidate.objects.create(institution=cls.b, candidate_id="B-1", first_name="Other", last_name="Candidate")
        GroupMembership.objects.create(candidate=cls.candidate, group=cls.group)

    @staticmethod
    def make_question(subject, actor, text, approved=True):
        question = Question.objects.create(institution=subject.institution, subject=subject, created_by=actor,
                                           text=text, question_type="multiple_choice", explanation="Owner-only explanation")
        QuestionOption.objects.create(question=question, text="First option", order=1, is_correct=True)
        QuestionOption.objects.create(question=question, text="Second option", order=2, is_correct=False)
        if approved:
            Question.objects.filter(pk=question.pk).update(status="approved")
            question.refresh_from_db()
        return question

    def setUp(self):
        self.client.force_authenticate(self.operator)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.a.pk))
        self.base = f"/api/v1/assessments/{self.exam.pk}/"

    def create_payload(self):
        return {"title": "Operator creation", "assessment_type": "test", "subject": self.subject.pk, "duration_minutes": 20}

    def test_operator_creation_has_client_ownership_actual_actor_and_no_membership(self):
        before = InstitutionMembership.objects.count()
        response = self.client.post("/api/v1/assessments/", self.create_payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        exam = Assessment.objects.get(pk=response.data["id"])
        self.assertEqual((exam.institution_id, exam.created_by_id), (self.a.pk, self.operator.pk))
        event = AuditEvent.objects.get(event_type="assessment_created", resource_id=str(exam.pk))
        self.assertEqual((event.actor_id, event.institution_id), (self.operator.pk, self.a.pk))
        self.assertEqual(InstitutionMembership.objects.count(), before)
        self.assertFalse(self.operator.institution_memberships.filter(institution=self.a).exists())
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/api/v1/assessments/{exam.pk}/").status_code, 200)
        self.client.force_authenticate(self.other_admin)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(self.client.get(f"/api/v1/assessments/{exam.pk}/").status_code, 404)

    def test_platform_list_is_selected_paginated_and_searchable(self):
        for number in range(27):
            Assessment.objects.create(institution=self.a, subject=self.subject, created_by=self.operator, title=f"Paged {number}", assessment_type="test", duration_minutes=20)
        response = self.client.get("/api/v1/assessments/")
        self.assertEqual(response.data["count"], 28)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertTrue(all(row["institution"] == self.a.pk for row in response.data["results"]))
        self.assertEqual(len(self.client.get("/api/v1/assessments/?page=2").data["results"]), 3)
        self.assertEqual(self.client.get("/api/v1/assessments/?search=Managed").data["count"], 1)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(self.client.get("/api/v1/assessments/").data["count"], 1)

    def test_multiple_workspaces_require_selection_for_owner_operations(self):
        self.client.credentials()
        for path in ("/api/v1/assessments/", self.base, self.base + "preview/", self.base + "questions/", "/api/v1/assessments/form-options/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 400)
        self.assertEqual(self.client.post("/api/v1/assessments/", self.create_payload(), format="json").status_code, 400)

    def test_selected_context_hides_other_assessment_reads(self):
        other = f"/api/v1/assessments/{self.exam_b.pk}/"
        for suffix in ("", "questions/", "preview/", "question-inspection/", "eligibility/"):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.client.get(other + suffix).status_code, 404)

    def test_selected_context_hides_mutations_workflows_and_links(self):
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(self.client.patch(self.base, {"title": "Wrong client"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(self.base).status_code, 404)
        for suffix in ("submit-review/", "approve/", "archive/", "schedule/", "reopen/", "request-changes/"):
            self.assertEqual(self.client.post(self.base + suffix, {}, format="json").status_code, 404)
        self.assertEqual(self.client.post(self.base + "questions/", {"question": self.question_b.pk, "order": 2, "marks": 1}, format="json").status_code, 404)
        self.assertEqual(self.client.patch(self.base + f"questions/{self.link.pk}/", {"marks": 3}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(self.base + f"questions/{self.link.pk}/").status_code, 404)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.title, "Managed exam")

    def test_inactive_or_unauthorized_context_is_rejected(self):
        self.client.force_authenticate(self.admin)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(self.client.get("/api/v1/assessments/").status_code, 404)
        self.client.force_authenticate(self.operator)
        Institution.objects.filter(pk=self.b.pk).update(is_active=False)
        self.assertEqual(self.client.get("/api/v1/assessments/").status_code, 404)

    def test_anonymous_student_and_is_staff_only_cannot_access_owner_endpoints(self):
        django_staff = User.objects.create_user("django-staff@owner.test", is_staff=True)
        for user in (None, self.student, django_staff):
            self.client.force_authenticate(user)
            for path in (self.base, self.base + "preview/", self.base + "question-inspection/", self.base + "eligibility/", self.base + "questions/", "/api/v1/assessments/form-options/", f"/api/v1/assessments/question-options/?subject={self.subject.pk}"):
                with self.subTest(user=user, path=path):
                    self.assertIn(self.client.get(path).status_code, (401, 403))

    def test_staff_read_policy_includes_teacher_and_examiner(self):
        for user in (self.operator, self.admin, self.teacher, self.examiner):
            self.client.force_authenticate(user)
            for suffix in ("", "preview/", "question-inspection/", "eligibility/"):
                self.assertEqual(self.client.get(self.base + suffix).status_code, 200)

    def test_additive_overview_fields(self):
        data = self.client.get(self.base).data
        self.assertEqual(data["subject_name"], "Subject A")
        self.assertEqual(data["group_name"], "Cohort")
        self.assertEqual(data["question_count"], 1)
        self.assertFalse(data["quick_access_configured"])
        self.assertFalse(data["has_attempt_history"])

    def test_staff_inspection_contains_correctness_and_explanation(self):
        rows = self.client.get(self.base + "question-inspection/").data
        self.assertEqual(rows[0]["id"], self.link.pk)
        self.assertEqual(rows[0]["order"], 1)
        self.assertTrue(rows[0]["question"]["options"][0]["is_correct"])
        self.assertEqual(rows[0]["question"]["explanation"], "Owner-only explanation")

    def test_preview_is_allowlisted_and_has_no_mutation_or_delivery_side_effects(self):
        models = (Assessment, AssessmentQuestion, Question, QuestionOption, Candidate, Attempt, Result, QuickExamConfiguration, QuickExamCredential, QuickExamSession, AuditEvent)
        before = [list(model.objects.order_by("pk").values()) for model in models]
        response = self.client.get(self.base + "preview/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"title", "duration_minutes", "randomize_questions", "randomize_options", "questions"})
        question = response.data["questions"][0]
        self.assertEqual(set(question), {"id", "prompt", "type", "options", "media", "order", "marks"})
        self.assertEqual(set(question["options"][0]), {"id", "label", "order"})
        self.assertNotIn("is_correct", json.dumps(response.data))
        self.assertNotIn("explanation", json.dumps(response.data))
        self.assertEqual(before, [list(model.objects.order_by("pk").values()) for model in models])

    def test_form_options_scope_groups_and_subjects(self):
        Group.objects.create(institution=self.a, name="Inactive", code="I", is_active=False)
        data = self.client.get("/api/v1/assessments/form-options/").data
        self.assertEqual({row["id"] for row in data["subjects"]}, {self.subject.pk, self.other_subject.pk})
        self.assertEqual([row["id"] for row in data["groups"]], [self.group.pk])
        self.assertIn("specific_candidates", [row["value"] for row in data["choices"]["candidate_access"]])

    def test_question_picker_is_approved_subject_scoped_and_bounded(self):
        data = self.client.get(f"/api/v1/assessments/question-options/?subject={self.subject.pk}").data
        self.assertEqual([row["id"] for row in data["results"]], [self.question.pk])
        self.assertEqual(self.client.get(f"/api/v1/assessments/question-options/?subject={self.subject_b.pk}").status_code, 404)
        for subject in ("", "bad", "0"):
            self.assertEqual(self.client.get(f"/api/v1/assessments/question-options/?subject={subject}").status_code, 400)

    def test_cross_tenant_or_unapproved_questions_cannot_be_attached(self):
        for question in (self.question_b, self.question_other_subject, self.draft_question):
            response = self.client.post(self.base + "questions/", {"question": question.pk, "order": 2, "marks": 1}, format="json")
            self.assertEqual(response.status_code, 400)

    def test_question_link_from_other_exam_cannot_be_used(self):
        other = AssessmentQuestion.objects.create(assessment=self.exam_b, question=self.question_b, order=1, marks=1)
        self.assertEqual(self.client.patch(self.base + f"questions/{other.pk}/", {"marks": 2}, format="json").status_code, 404)

    def test_effective_group_roster_checks_active_dates_and_same_membership(self):
        from attempts.tenancy import active_local_date
        today = active_local_date(self.a)
        another_group = Group.objects.create(institution=self.a, name="Unrelated", code="U")
        for index, fields in enumerate(({"is_active": False}, {"start_date": today + timedelta(days=1)}, {"end_date": today - timedelta(days=1)})):
            candidate = Candidate.objects.create(institution=self.a, candidate_id=f"X-{index}", first_name="Excluded", last_name=str(index))
            GroupMembership.objects.create(candidate=candidate, group=self.group, **fields)
            GroupMembership.objects.create(candidate=candidate, group=another_group)
        inactive = Candidate.objects.create(institution=self.a, candidate_id="INACTIVE", first_name="Inactive", last_name="Candidate", status="inactive")
        GroupMembership.objects.create(candidate=inactive, group=self.group)
        data = self.client.get(self.base + "eligibility/").data
        self.assertEqual([row["id"] for row in data["results"]], [self.candidate.pk])
        self.assertIn("email", data["results"][0])

    def test_inactive_group_is_not_eligible(self):
        Group.objects.filter(pk=self.group.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.base + "eligibility/").data["count"], 0)

    def test_specific_candidate_mode_is_supported_with_empty_population(self):
        Assessment.objects.filter(pk=self.exam.pk).update(candidate_access="specific_candidates")
        data = self.client.get(self.base + "eligibility/").data
        self.assertTrue(data["delivery_supported"])
        self.assertEqual(data["count"], 0)

    def quick_configuration(self):
        self.exam = Assessment.objects.create(institution=self.a, subject=self.subject, created_by=self.operator,
            title='Synthetic Quick owner exam', assessment_type='test', duration_minutes=30, candidate_access='access_code')
        self.link = AssessmentQuestion.objects.create(assessment=self.exam, question=self.question, order=1, marks=2)
        self.base = f'/api/v1/assessments/{self.exam.pk}/'
        AssessmentCandidate.objects.create(assessment=self.exam, candidate=self.candidate, assigned_by=self.operator)
        return self.client.put(self.base + "quick-access/", {"exam_code": "OWNER-TEST", "enabled": True}, format="json")

    def test_quick_candidate_roster_has_no_credential_state_or_secrets(self):
        self.quick_configuration()
        issued = self.client.post(self.base + "quick-access/credentials/", {"candidate": self.candidate.pk}, format="json")
        self.assertEqual(issued.status_code, 201)
        self.client.force_authenticate(self.teacher)
        data = self.client.get(self.base + "eligibility/").data
        self.assertEqual(set(data["results"][0]), {"id", "candidate_id", "name", "status", "email", "has_participated", "assignment"})
        self.assertNotIn(issued.data["initial_pin"], json.dumps(data))

    def test_quick_response_name_status_no_store_and_cross_tenant_candidate(self):
        self.quick_configuration()
        self.assertEqual(self.client.post(self.base + "quick-access/credentials/", {"candidate": self.candidate_b.pk}, format="json").status_code, 404)
        issued = self.client.post(self.base + "quick-access/credentials/", {"candidate": self.candidate.pk}, format="json")
        self.assertEqual(issued.data["credential"]["candidate_name"], "Amina Candidate")
        self.assertEqual(issued.data["credential"]["candidate_status"], "active")
        self.assertEqual(issued["Cache-Control"], "no-store, private")
        reset = self.client.post(self.base + f"quick-access/credentials/{self.candidate.pk}/reset/", {}, format="json")
        self.assertEqual(reset["Cache-Control"], "no-store, private")
        listing = self.client.get(self.base + "quick-access/credentials/")
        self.assertNotIn("pin_hash", json.dumps(listing.data))
        self.assertNotIn("initial_pin", json.dumps(listing.data))

    def test_teacher_and_examiner_cannot_manage_quick(self):
        self.quick_configuration()
        for user in (self.teacher, self.examiner):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.base + "quick-access/").status_code, 403)
            self.assertEqual(self.client.post(self.base + "quick-access/credentials/", {"candidate": self.candidate.pk}, format="json").status_code, 403)

    def test_mutation_and_workflow_audits_are_safe_and_not_duplicated(self):
        Assessment.objects.filter(pk=self.exam.pk).update(start_at=timezone.now(), end_at=timezone.now() + timedelta(days=1))
        self.client.patch(self.base, {"description": "Owner-only draft change"}, format="json")
        self.client.patch(self.base + f"questions/{self.link.pk}/", {"marks": 3}, format="json")
        for action in ("submit-review", "request-changes", "submit-review", "approve", "reopen", "submit-review", "approve"):
            response = self.client.post(self.base + action + "/", {}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.post(self.base + "schedule/", {}, format="json").status_code, 200)
        self.assertEqual(self.client.post(self.base + "archive/", {}, format="json").status_code, 200)
        events = AuditEvent.objects.all()
        self.assertEqual(events.filter(event_type="assessment_approved").count(), 2)
        for name in ("assessment_edited", "assessment_question_edited", "assessment_review_submitted", "assessment_changes_requested", "assessment_reopened", "assessment_scheduled", "assessment_archived"):
            self.assertTrue(events.filter(event_type=name).exists(), name)
        for event in events:
            self.assertEqual((event.actor_id, event.institution_id), (self.operator.pk, self.a.pk))
            self.assertNotIn("Owner-only", json.dumps(event.metadata))
            self.assertNotIn("is_correct", json.dumps(event.metadata))

    def test_question_remove_and_assessment_delete_are_audited(self):
        self.assertEqual(self.client.delete(self.base + f"questions/{self.link.pk}/").status_code, 204)
        self.assertTrue(AuditEvent.objects.filter(event_type="assessment_question_removed").exists())
        self.assertEqual(self.client.delete(self.base).status_code, 204)
        self.assertTrue(AuditEvent.objects.filter(event_type="assessment_deleted", resource_id=str(self.exam.pk)).exists())

    def test_audit_failure_rolls_back_create_edit_delete_question_and_workflow(self):
        with patch("assessments.assessment_events.record_event", side_effect=RuntimeError("Audit unavailable")):
            operations = (
                lambda: self.client.post("/api/v1/assessments/", self.create_payload(), format="json"),
                lambda: self.client.patch(self.base, {"title": "Must roll back"}, format="json"),
                lambda: self.client.delete(self.base),
                lambda: self.client.patch(self.base + f"questions/{self.link.pk}/", {"marks": 9}, format="json"),
                lambda: self.client.delete(self.base + f"questions/{self.link.pk}/"),
                lambda: self.client.post(self.base + "submit-review/", {}, format="json"),
            )
            for operation in operations:
                with self.assertRaises(RuntimeError):
                    operation()
                self.exam.refresh_from_db(); self.link.refresh_from_db()
                self.assertEqual(self.exam.title, "Managed exam")
                self.assertEqual(self.exam.status, "draft")
                self.assertEqual(self.link.marks, 2)
                self.assertEqual(Assessment.objects.count(), 2)

    def test_audit_failure_rolls_back_question_attachment(self):
        second = self.make_question(self.subject, self.operator, "Second paper")
        with patch("assessments.assessment_events.record_event", side_effect=RuntimeError("Audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.base + "questions/", {"question": second.pk, "order": 2, "marks": 2}, format="json")
        self.assertEqual(self.exam.assessment_questions.count(), 1)
