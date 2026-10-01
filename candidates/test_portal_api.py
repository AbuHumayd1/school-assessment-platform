from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from assessments.models import Assessment, AssessmentQuestion
from attempts.models import Attempt
from groups.models import Group, GroupMembership
from institutions.models import Institution
from questions.models import Question, QuestionOption
from subjects.models import Subject
from .models import Candidate


class CandidatePortalAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.now = timezone.now()
        cls.school = Institution.objects.create(name="Portal Academy", timezone="Africa/Lagos")
        cls.other_school = Institution.objects.create(name="Other Portal Academy")
        cls.subject = Subject.objects.create(institution=cls.school, name="Mathematics", code="MATH")
        cls.group = Group.objects.create(institution=cls.school, name="Cohort A", code="A1")
        cls.other_group = Group.objects.create(institution=cls.school, name="Cohort B", code="B1")
        cls.user = User.objects.create_user("portal-candidate@example.test", "Safe-pass-8392")
        cls.other_user = User.objects.create_user("other-portal@example.test", "Safe-pass-8392")
        cls.staff = User.objects.create_user("portal-staff@example.test", "Safe-pass-8392")
        cls.candidate = Candidate.objects.create(
            institution=cls.school, user=cls.user, candidate_id="PORTAL-001",
            first_name="Ada", last_name="Learner", email="ada@example.test",
        )
        cls.other_candidate = Candidate.objects.create(
            institution=cls.school, user=cls.other_user, candidate_id="PORTAL-002",
            first_name="Ben", last_name="Learner",
        )
        GroupMembership.objects.create(candidate=cls.candidate, group=cls.group)
        GroupMembership.objects.create(candidate=cls.other_candidate, group=cls.other_group)
        cls.question = Question.objects.create(
            institution=cls.school, subject=cls.subject,
            question_type=Question.Type.MULTIPLE_CHOICE,
            text="Secret question prompt", created_by=cls.staff, status=Question.Status.APPROVED,
        )
        QuestionOption.objects.create(question=cls.question, text="Secret correct choice", order=1, is_correct=True)
        QuestionOption.objects.create(question=cls.question, text="Secret other choice", order=2, is_correct=False)
        cls.available = cls.make_assessment("Available assessment", cls.group)
        cls.upcoming = cls.make_assessment(
            "Upcoming assessment", cls.group,
            start_at=cls.now + timedelta(days=1), end_at=cls.now + timedelta(days=2),
        )
        cls.wrong_group = cls.make_assessment("Other group assessment", cls.other_group)
        cls.draft = cls.make_assessment("Draft assessment", cls.group, status=Assessment.Status.DRAFT)
        cls.archived = cls.make_assessment("Archived assessment", cls.group, status=Assessment.Status.ARCHIVED)
        cls.foreign_subject = Subject.objects.create(institution=cls.other_school, name="Other", code="OTH")
        cls.foreign_group = Group.objects.create(institution=cls.other_school, name="Foreign cohort", code="F1")
        cls.foreign_question = Question.objects.create(
            institution=cls.other_school, subject=cls.foreign_subject,
            question_type=Question.Type.MULTIPLE_CHOICE,
            text="Foreign prompt", created_by=cls.staff, status=Question.Status.APPROVED,
        )
        QuestionOption.objects.create(question=cls.foreign_question, text="Foreign correct", order=1, is_correct=True)
        QuestionOption.objects.create(question=cls.foreign_question, text="Foreign other", order=2, is_correct=False)
        cls.foreign_assessment = cls.make_assessment(
            "Foreign assessment", cls.foreign_group,
            institution=cls.other_school, subject=cls.foreign_subject, question=cls.foreign_question,
        )

    @classmethod
    def make_assessment(cls, title, group, **overrides):
        now = timezone.now()
        values = {
            "institution": cls.school,
            "title": title,
            "assessment_type": Assessment.Type.TERM_EXAM,
            "subject": cls.subject,
            "group": group,
            "duration_minutes": 30,
            "attempt_limit": 1,
            "candidate_access": Assessment.CandidateAccess.ASSIGNED_GROUP,
            "status": Assessment.Status.SCHEDULED,
            "created_by": cls.staff,
            "start_at": now - timedelta(hours=1),
            "end_at": now + timedelta(hours=2),
        }
        values.update(overrides)
        question = values.pop("question", cls.question)
        assessment = Assessment.objects.create(**values)
        AssessmentQuestion.objects.create(
            assessment=assessment, question=question, order=1, marks=Decimal("2.00"),
        )
        return assessment

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.context_url = "/api/v1/candidate/me/"
        self.exams_url = "/api/v1/candidate/me/exams/"

    def test_authenticated_candidate_gets_own_context(self):
        response = self.client.get(self.context_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["candidate"]["id"], self.candidate.pk)
        self.assertEqual(response.data["candidate"]["candidate_id"], "PORTAL-001")
        self.assertEqual(response.data["institution"]["name"], self.school.name)
        self.assertEqual(response.data["groups"][0]["id"], self.group.pk)
        foreign_query = self.client.get(f"{self.context_url}?candidate_id={self.other_candidate.pk}&institution_id={self.other_school.pk}")
        self.assertEqual(foreign_query.status_code, 200)
        self.assertEqual(foreign_query.data["candidate"]["id"], self.candidate.pk)

    def test_unauthenticated_context_and_exam_requests_are_denied(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.context_url).status_code, 403)
        self.assertEqual(self.client.get(self.exams_url).status_code, 403)

    def test_user_without_candidate_profile_is_denied(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(self.context_url).status_code, 403)
        self.assertEqual(self.client.get(self.exams_url).status_code, 403)

    def test_inactive_candidate_and_institution_are_denied(self):
        self.candidate.status = Candidate.Status.INACTIVE
        self.candidate.save(update_fields=("status",))
        self.assertEqual(self.client.get(self.context_url).status_code, 403)
        self.candidate.status = Candidate.Status.ACTIVE
        self.candidate.save(update_fields=("status",))
        self.school.is_active = False
        self.school.save(update_fields=("is_active",))
        self.assertEqual(self.client.get(self.exams_url).status_code, 403)

    def test_ambiguous_candidate_profiles_are_rejected(self):
        Candidate.objects.create(
            institution=self.other_school, user=self.user, candidate_id="PORTAL-003",
            first_name="Ada", last_name="Other",
        )
        response = self.client.get(self.context_url)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "ambiguous_candidate_profiles")

    def test_exam_list_contains_only_currently_eligible_candidate_assessments(self):
        response = self.client.get(self.exams_url)
        self.assertEqual(response.status_code, 200)
        by_title = {exam["title"]: exam for exam in response.data["exams"]}
        self.assertEqual(set(by_title), {"Available assessment", "Upcoming assessment"})
        self.assertEqual(by_title["Available assessment"]["status"], "available")
        self.assertTrue(by_title["Available assessment"]["can_start"])
        self.assertEqual(by_title["Upcoming assessment"]["status"], "upcoming")
        self.assertFalse(by_title["Upcoming assessment"]["can_start"])

    def test_exam_summary_does_not_expose_question_content_or_answers(self):
        response = self.client.get(self.exams_url)
        serialized = str(response.data)
        for secret in ("Secret question prompt", "Secret correct choice", "Secret other choice", "is_correct", "explanation", "reviewed_by", "approved_by"):
            self.assertNotIn(secret, serialized)

    def test_listing_does_not_create_attempts(self):
        self.client.get(self.exams_url)
        self.assertEqual(Attempt.objects.count(), 0)

    def test_attempt_limit_exhaustion_is_classified_completed(self):
        Attempt.objects.create(
            institution=self.school, assessment=self.available, candidate=self.candidate,
            attempt_number=1, status=Attempt.Status.SUBMITTED,
            started_at=self.now - timedelta(minutes=30), expires_at=self.now,
            submitted_at=self.now, last_activity_at=self.now,
        )
        response = self.client.get(self.exams_url)
        result = next(row for row in response.data["exams"] if row["id"] == self.available.pk)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["attempts_used"], 1)
        self.assertFalse(result["can_start"])

    def test_active_attempt_is_listed_as_resumable_without_mutation(self):
        attempt = Attempt.objects.create(
            institution=self.school, assessment=self.available, candidate=self.candidate,
            attempt_number=1, status=Attempt.Status.IN_PROGRESS,
            started_at=self.now - timedelta(minutes=2), expires_at=self.now + timedelta(minutes=28),
            last_activity_at=self.now,
        )
        response = self.client.get(self.exams_url)
        result = next(row for row in response.data["exams"] if row["id"] == self.available.pk)
        self.assertEqual(result["status"], "in_progress")
        self.assertTrue(result["can_resume"])
        self.assertFalse(result["can_start"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.IN_PROGRESS)
