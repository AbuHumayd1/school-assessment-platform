from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from assessments.models import Assessment, AssessmentQuestion
from attempts.models import Answer, AnswerSelection, Attempt, AttemptQuestion
from attempts.services import expire_attempt, start_attempt
from audit.models import AuditEvent
from candidates.models import Candidate
from groups.models import Group, GroupMembership
from institutions.models import Institution
from questions.models import Question, QuestionOption
from results.models import Result
from results.services import mark_attempt, publish_result, withhold_result
from subjects.models import Subject
from tenants.models import InstitutionMembership


class PhaseFiveSecurityTests(APITestCase):
    def setUp(self):
        self.a = Institution.objects.create(name="Security Academy A")
        self.b = Institution.objects.create(name="Security Academy B")
        self.admin_a = self.make_user("admin-a-sec@example.test", self.a, "institution_admin")
        self.examiner_a = self.make_user("examiner-a-sec@example.test", self.a, "examiner")
        self.teacher_a = self.make_user("teacher-a-sec@example.test", self.a, "teacher")
        self.student_a = self.make_user("student-a-sec@example.test", self.a, "student")
        self.admin_b = self.make_user("admin-b-sec@example.test", self.b, "institution_admin")
        self.student_b = self.make_user("student-b-sec@example.test", self.b, "student")
        self.subject_a = Subject.objects.create(institution=self.a, name="Math", code="MATH")
        self.subject_b = Subject.objects.create(institution=self.b, name="Math", code="MATH")
        self.group_a = Group.objects.create(institution=self.a, name="Class A", code="A")
        self.group_b = Group.objects.create(institution=self.b, name="Class B", code="B")
        self.candidate_a = Candidate.objects.create(
            institution=self.a, user=self.student_a, candidate_id="A-01", first_name="Ada", last_name="A",
        )
        self.candidate_b = Candidate.objects.create(
            institution=self.b, user=self.student_b, candidate_id="B-01", first_name="Ben", last_name="B",
        )
        GroupMembership.objects.create(candidate=self.candidate_a, group=self.group_a, is_active=True)
        GroupMembership.objects.create(candidate=self.candidate_b, group=self.group_b, is_active=True)
        self.question_a, self.options_a = self.make_question(self.a, self.subject_a, self.admin_a, "A question")
        self.question_b, self.options_b = self.make_question(self.b, self.subject_b, self.admin_b, "B question")
        now = timezone.now()
        self.assessment_a = self.make_assessment(self.a, self.subject_a, self.group_a, self.admin_a, self.question_a, now)
        self.assessment_b = self.make_assessment(self.b, self.subject_b, self.group_b, self.admin_b, self.question_b, now)
        self.attempt_a, _ = start_attempt(self.student_a, self.assessment_a.pk)
        self.attempt_b, _ = start_attempt(self.student_b, self.assessment_b.pk)
        self.attempt_question_a = self.attempt_a.attempt_questions.get()

    @staticmethod
    def make_user(email, institution, role):
        user = User.objects.create_user(email, "Safe-test-84293")
        InstitutionMembership.objects.create(user=user, institution=institution, role=role, is_active=True)
        return user

    @staticmethod
    def make_question(institution, subject, creator, text):
        question = Question.objects.create(
            institution=institution, subject=subject, question_type=Question.Type.MULTIPLE_CHOICE,
            text=text, explanation="Hidden explanation", source="Internal source", status=Question.Status.APPROVED,
            created_by=creator,
        )
        options = [
            QuestionOption.objects.create(question=question, text="First option", order=1, is_correct=True),
            QuestionOption.objects.create(question=question, text="Second option", order=2, is_correct=False),
        ]
        return question, options

    @staticmethod
    def make_assessment(institution, subject, group, creator, question, now):
        assessment = Assessment.objects.create(
            institution=institution, title="Security assessment", assessment_type=Assessment.Type.TEST,
            subject=subject, group=group, duration_minutes=30, pass_mark=Decimal("1.00"), attempt_limit=3,
            status=Assessment.Status.SCHEDULED, start_at=now - timedelta(hours=1), end_at=now + timedelta(hours=1),
            candidate_access=Assessment.CandidateAccess.ASSIGNED_GROUP,
            result_visibility=Assessment.ResultVisibility.AFTER_SUBMISSION,
            result_release_mode=Assessment.ResultReleaseMode.APPROVAL_REQUIRED, created_by=creator,
        )
        AssessmentQuestion.objects.create(assessment=assessment, question=question, order=1, marks=Decimal("1.00"))
        return assessment

    def mark_result(self, attempt=None):
        attempt = attempt or self.attempt_a
        actor = self.admin_b if attempt.institution_id == self.b.pk else self.examiner_a
        attempt.status = Attempt.Status.SUBMITTED
        attempt.submitted_at = timezone.now()
        attempt.save(update_fields=("status", "submitted_at"))
        return mark_attempt(attempt.pk, actor=actor)

    def test_student_cannot_list_institutions(self):
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.get("/api/v1/institutions/").status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_list_candidates(self):
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.get("/api/v1/candidates/").status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_list_groups(self):
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.get("/api/v1/groups/").status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_list_subjects(self):
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.get("/api/v1/subjects/").status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_list_question_bank(self):
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.get("/api/v1/questions/").status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_list_assessments(self):
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.get("/api/v1/assessments/").status_code, status.HTTP_403_FORBIDDEN)

    def test_question_detail_from_other_tenant_is_not_found(self):
        self.client.force_authenticate(self.teacher_a)
        self.assertEqual(self.client.get(f"/api/v1/questions/{self.question_b.pk}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_candidate_detail_from_other_tenant_is_not_found(self):
        self.client.force_authenticate(self.teacher_a)
        self.assertEqual(self.client.get(f"/api/v1/candidates/{self.candidate_b.pk}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_foreign_candidate_cannot_be_updated_by_url_id(self):
        self.client.force_authenticate(self.teacher_a)
        response = self.client.patch(f"/api/v1/candidates/{self.candidate_b.pk}/", {"first_name": "Changed"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_foreign_candidate_cannot_be_deleted_by_url_id(self):
        self.client.force_authenticate(self.teacher_a)
        response = self.client.delete(f"/api/v1/candidates/{self.candidate_b.pk}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin_a)
        response = self.client.delete(f"/api/v1/candidates/{self.candidate_b.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Candidate.objects.filter(pk=self.candidate_b.pk).exists())

    def test_candidate_creation_cannot_assign_foreign_institution(self):
        self.client.force_authenticate(self.teacher_a)
        response = self.client.post("/api/v1/candidates/", {
            "institution": self.b.pk, "candidate_id": "X", "first_name": "X", "last_name": "Y",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_candidate_cannot_be_linked_to_foreign_tenant_user(self):
        self.client.force_authenticate(self.teacher_a)
        response = self.client.post("/api/v1/candidates/", {
            "institution": self.a.pk, "user": self.student_b.pk, "candidate_id": "X", "first_name": "X", "last_name": "Y",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_cannot_create_candidate_records(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.post("/api/v1/candidates/", {
            "institution": self.a.pk, "candidate_id": "X", "first_name": "X", "last_name": "Y",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_linked_candidate_cannot_change_candidate_id(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.patch(f"/api/v1/candidates/{self.candidate_a.pk}/", {"candidate_id": "NEW"}, format="json")
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_teacher_cannot_change_candidate_id(self):
        self.client.force_authenticate(self.teacher_a)
        response = self.client.patch(f"/api/v1/candidates/{self.candidate_a.pk}/", {"candidate_id": "NEW"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teacher_cannot_reassign_candidate_account(self):
        self.client.force_authenticate(self.teacher_a)
        response = self.client.patch(f"/api/v1/candidates/{self.candidate_a.pk}/", {"user": self.teacher_a.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_directory_is_empty_for_student(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.get("/api/v1/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_user_directory_does_not_expose_password_or_staff_flags(self):
        self.client.force_authenticate(self.teacher_a)
        response = self.client.get("/api/v1/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for row in response.data:
            self.assertNotIn("password", row)
            self.assertNotIn("is_staff", row)
            self.assertNotIn("is_superuser", row)

    def test_user_directory_is_tenant_scoped(self):
        self.client.force_authenticate(self.teacher_a)
        response = self.client.get("/api/v1/users/")
        self.assertNotIn(self.student_b.pk, {row["id"] for row in response.data})

    def test_user_directory_is_read_only(self):
        self.client.force_authenticate(self.teacher_a)
        self.assertEqual(self.client.post("/api/v1/users/", {"role": "platform_admin"}, format="json").status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_membership_route_rejects_unprivileged_user(self):
        self.client.force_authenticate(self.student_a)
        before = InstitutionMembership.objects.count()
        response = self.client.post("/api/v1/memberships/", {"role": "platform_admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(InstitutionMembership.objects.count(), before)

    def test_candidate_question_response_omits_correctness_and_explanation(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.get(f"/api/v1/attempts/{self.attempt_a.pk}/questions/{self.question_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        encoded = str(response.data)
        self.assertNotIn("is_correct", encoded)
        self.assertNotIn("explanation", encoded)

    def test_candidate_question_response_omits_source_and_workflow_state(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.get(f"/api/v1/attempts/{self.attempt_a.pk}/questions/{self.question_a.pk}/")
        self.assertNotIn("source", response.data["question"])
        self.assertNotIn("status", response.data["question"])
        self.assertNotIn("difficulty", response.data["question"])

    def test_candidate_cannot_view_another_candidates_attempt(self):
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.get(f"/api/v1/attempts/{self.attempt_b.pk}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_candidate_cannot_submit_another_candidates_attempt(self):
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.post(f"/api/v1/attempts/{self.attempt_b.pk}/submit/").status_code, status.HTTP_404_NOT_FOUND)

    def test_candidate_cannot_open_another_candidates_attempt_questions(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.get(f"/api/v1/attempts/{self.attempt_b.pk}/questions/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_candidate_cannot_set_server_timestamps_when_starting(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.post("/api/v1/attempts/start/", {
            "assessment": self.assessment_a.pk, "started_at": "2000-01-01T00:00:00Z",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_candidate_cannot_choose_attempt_number(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.post("/api/v1/attempts/start/", {
            "assessment": self.assessment_a.pk, "attempt_number": 99,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_candidate_cannot_extend_expiry_at_start(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.post("/api/v1/attempts/start/", {
            "assessment": self.assessment_a.pk, "expires_at": "2099-01-01T00:00:00Z",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_attempt_detail_has_no_write_method(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.patch(f"/api/v1/attempts/{self.attempt_a.pk}/", {"status": "submitted"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_foreign_option_cannot_be_saved_as_answer(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.put(
            f"/api/v1/attempts/{self.attempt_a.pk}/questions/{self.question_a.pk}/answer/",
            {"selected_options": [self.options_b[0].pk]}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_answer_request_rejects_server_controlled_fields(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.put(
            f"/api/v1/attempts/{self.attempt_a.pk}/questions/{self.question_a.pk}/answer/",
            {"selected_options": [self.options_a[0].pk], "answered_at": "2000-01-01T00:00:00Z"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_answer_for_question_not_in_attempt_is_not_found(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.put(
            f"/api/v1/attempts/{self.attempt_a.pk}/questions/{self.question_b.pk}/answer/",
            {"selected_options": [self.options_b[0].pk]}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_submitted_attempt_rejects_answer_changes(self):
        self.attempt_a.status = Attempt.Status.SUBMITTED
        self.attempt_a.save(update_fields=("status",))
        self.client.force_authenticate(self.student_a)
        response = self.client.put(
            f"/api/v1/attempts/{self.attempt_a.pk}/questions/{self.question_a.pk}/answer/",
            {"selected_options": [self.options_a[0].pk]}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_expired_attempt_rejects_answer_changes(self):
        self.attempt_a.status = Attempt.Status.EXPIRED
        self.attempt_a.save(update_fields=("status",))
        self.client.force_authenticate(self.student_a)
        response = self.client.put(
            f"/api/v1/attempts/{self.attempt_a.pk}/questions/{self.question_a.pk}/answer/",
            {"selected_options": [self.options_a[0].pk]}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_second_submission_returns_existing_terminal_state(self):
        self.attempt_a.status = Attempt.Status.SUBMITTED
        self.attempt_a.save(update_fields=("status",))
        self.client.force_authenticate(self.student_a)
        response = self.client.post(f"/api/v1/attempts/{self.attempt_a.pk}/submit/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Attempt.Status.SUBMITTED)
        self.assertEqual(Attempt.objects.get(pk=self.attempt_a.pk).status, Attempt.Status.SUBMITTED)
        self.assertEqual(Result.objects.filter(attempt=self.attempt_a).count(), 1)

    def test_foreign_tenant_staff_cannot_mark_attempt(self):
        self.client.force_authenticate(self.admin_b)
        self.assertEqual(self.client.post(f"/api/v1/results/attempts/{self.attempt_a.pk}/mark/").status_code, status.HTTP_404_NOT_FOUND)

    def test_candidate_cannot_mark_attempt(self):
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.post(f"/api/v1/results/attempts/{self.attempt_a.pk}/mark/").status_code, status.HTTP_403_FORBIDDEN)

    def test_candidate_cannot_retrieve_unpublished_result(self):
        result = self.mark_result()
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.get(f"/api/v1/results/{result.pk}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_candidate_cannot_retrieve_foreign_result(self):
        result = self.mark_result(self.attempt_b)
        publish_result(result.pk, actor=self.admin_b)
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.get(f"/api/v1/results/{result.pk}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_candidate_result_has_no_question_marking_details(self):
        result = self.mark_result()
        publish_result(result.pk, actor=self.admin_a)
        self.client.force_authenticate(self.student_a)
        response = self.client.get(f"/api/v1/results/{result.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("questions", response.data)
        self.assertNotIn("pass_mark", response.data)

    def test_candidate_cannot_publish_result(self):
        result = self.mark_result()
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.post(f"/api/v1/results/{result.pk}/publish/").status_code, status.HTTP_403_FORBIDDEN)

    def test_candidate_cannot_withhold_result(self):
        result = self.mark_result()
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.post(f"/api/v1/results/{result.pk}/withhold/").status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_tenant_result_publication_is_not_found(self):
        result = self.mark_result(self.attempt_b)
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.post(f"/api/v1/results/{result.pk}/publish/").status_code, status.HTTP_404_NOT_FOUND)

    def test_cross_tenant_result_withholding_is_not_found(self):
        result = self.mark_result(self.attempt_b)
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.post(f"/api/v1/results/{result.pk}/withhold/").status_code, status.HTTP_404_NOT_FOUND)

    def test_published_result_is_not_writable_by_candidate(self):
        result = self.mark_result()
        publish_result(result.pk, actor=self.admin_a)
        self.client.force_authenticate(self.student_a)
        response = self.client.patch(f"/api/v1/results/{result.pk}/", {"marks_obtained": "100"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_assessment_configuration_is_frozen_after_attempt(self):
        assessment = Assessment.objects.get(pk=self.assessment_a.pk)
        assessment.pass_mark = Decimal("0.00")
        with self.assertRaises(DjangoValidationError):
            assessment.save()

    def test_assessment_cannot_reopen_after_attempt(self):
        assessment = Assessment.objects.get(pk=self.assessment_a.pk)
        assessment.status = Assessment.Status.DRAFT
        with self.assertRaises(DjangoValidationError):
            assessment.save()

    def test_assessment_question_marks_are_frozen_after_attempt(self):
        row = AssessmentQuestion.objects.get(assessment=self.assessment_a)
        row.marks = Decimal("2.00")
        with self.assertRaises(DjangoValidationError):
            row.save()

    def test_assessment_question_cannot_be_deleted_after_attempt(self):
        row = AssessmentQuestion.objects.get(assessment=self.assessment_a)
        with self.assertRaises(DjangoValidationError):
            row.delete()

    def test_question_content_is_frozen_after_attempt(self):
        question = Question.objects.get(pk=self.question_a.pk)
        question.text = "Mutated question"
        with self.assertRaises(DjangoValidationError):
            question.save()

    def test_question_option_correctness_is_frozen_after_attempt(self):
        option = QuestionOption.objects.get(pk=self.options_a[0].pk)
        option.is_correct = False
        with self.assertRaises(DjangoValidationError):
            option.save()

    def test_question_option_cannot_be_deleted_after_attempt(self):
        option = QuestionOption.objects.get(pk=self.options_a[0].pk)
        with self.assertRaises(DjangoValidationError):
            option.delete()

    def test_group_membership_rejects_cross_tenant_relationship(self):
        invalid = GroupMembership(candidate=self.candidate_a, group=self.group_b, is_active=True)
        with self.assertRaises(DjangoValidationError):
            invalid.save()

    def test_candidate_identity_is_frozen_after_attempt(self):
        candidate = Candidate.objects.get(pk=self.candidate_a.pk)
        candidate.candidate_id = "MUTATED"
        with self.assertRaises(DjangoValidationError):
            candidate.save()

    def test_attempt_start_creates_tenant_audit_event(self):
        event = AuditEvent.objects.get(event_type=AuditEvent.Type.ATTEMPT_STARTED, resource_id=str(self.attempt_a.pk))
        self.assertEqual(event.institution_id, self.a.pk)
        self.assertEqual(event.actor_id, self.student_a.pk)

    def test_attempt_submission_creates_audit_event(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.post(f"/api/v1/attempts/{self.attempt_a.pk}/submit/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(AuditEvent.objects.filter(event_type=AuditEvent.Type.ATTEMPT_SUBMITTED, resource_id=str(self.attempt_a.pk)).exists())

    def test_attempt_expiry_creates_audit_event(self):
        self.attempt_a.expires_at = timezone.now() - timedelta(seconds=1)
        self.attempt_a.save(update_fields=("expires_at",))
        self.assertTrue(expire_attempt(self.attempt_a, actor=self.student_a))
        event = AuditEvent.objects.get(event_type=AuditEvent.Type.ATTEMPT_EXPIRED, resource_id=str(self.attempt_a.pk))
        self.assertEqual(event.institution_id, self.a.pk)

    def test_assessment_approval_creates_audit_event(self):
        assessment = self.make_assessment(self.a, self.subject_a, self.group_a, self.admin_a, self.question_a, timezone.now())
        assessment.status = Assessment.Status.REVIEW
        assessment.save(update_fields=("status",))
        self.client.force_authenticate(self.admin_a)
        response = self.client.post(f"/api/v1/assessments/{assessment.pk}/approve/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(AuditEvent.objects.filter(event_type=AuditEvent.Type.ASSESSMENT_APPROVED, resource_id=str(assessment.pk)).exists())

    def test_assessment_schedule_creates_audit_event(self):
        assessment = self.make_assessment(self.a, self.subject_a, self.group_a, self.admin_a, self.question_a, timezone.now())
        assessment.status = Assessment.Status.APPROVED
        assessment.save(update_fields=("status",))
        self.client.force_authenticate(self.admin_a)
        response = self.client.post(f"/api/v1/assessments/{assessment.pk}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(AuditEvent.objects.filter(event_type=AuditEvent.Type.ASSESSMENT_SCHEDULED, resource_id=str(assessment.pk)).exists())

    def test_result_mark_creates_audit_event(self):
        result = self.mark_result()
        self.assertTrue(AuditEvent.objects.filter(event_type=AuditEvent.Type.RESULT_MARKED, resource_id=str(result.pk)).exists())

    def test_result_publish_creates_audit_event(self):
        result = self.mark_result()
        publish_result(result.pk, actor=self.admin_a)
        event = AuditEvent.objects.get(event_type=AuditEvent.Type.RESULT_PUBLISHED, resource_id=str(result.pk))
        self.assertEqual(event.actor_id, self.admin_a.pk)

    def test_result_withhold_creates_audit_event(self):
        result = self.mark_result()
        withhold_result(result.pk, actor=self.admin_a)
        self.assertTrue(AuditEvent.objects.filter(event_type=AuditEvent.Type.RESULT_WITHHELD, resource_id=str(result.pk)).exists())

    def test_audit_events_cannot_be_updated(self):
        event = AuditEvent.objects.first()
        event.resource_id = "forged"
        with self.assertRaises(DjangoValidationError):
            event.save()

    def test_audit_events_cannot_be_deleted(self):
        event = AuditEvent.objects.first()
        with self.assertRaises(DjangoValidationError):
            event.delete()

    def test_audit_metadata_does_not_include_answer_content(self):
        event = AuditEvent.objects.get(event_type=AuditEvent.Type.ATTEMPT_STARTED, resource_id=str(self.attempt_a.pk))
        self.assertNotIn("answer", str(event.metadata).lower())
        self.assertNotIn("password", str(event.metadata).lower())

    def test_audit_log_has_no_candidate_api_route(self):
        self.client.force_authenticate(self.student_a)
        self.assertEqual(self.client.get("/api/v1/audit-events/").status_code, status.HTTP_404_NOT_FOUND)
