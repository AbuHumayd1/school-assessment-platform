from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from assessments.models import Assessment
from attempts.models import Attempt
from candidates.models import Candidate
from groups.models import Group, GroupMembership
from institutions.models import Institution
from questions.models import Question, Topic
from results.models import Result
from subjects.models import Subject
from tenants.models import InstitutionMembership


@override_settings(DEBUG=True)
class SeedDemoAssessmentCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name="Demo Training Institute")
        cls.candidate_user = User.objects.create_user("teststudent@example.com", "test-only-password")
        cls.candidate = Candidate.objects.create(
            institution=cls.institution,
            user=cls.candidate_user,
            candidate_id="TEST001",
            first_name="Demo",
            last_name="Candidate",
        )
        cls.admin = User.objects.create_user("seed-admin@example.test", "test-only-password")
        InstitutionMembership.objects.create(
            user=cls.admin,
            institution=cls.institution,
            role=InstitutionMembership.Role.INSTITUTION_ADMIN,
        )

    def test_creates_real_candidate_exam_data_idempotently_without_attempts_or_results(self):
        call_command("seed_demo_assessment", stdout=StringIO())
        call_command("seed_demo_assessment", stdout=StringIO())

        group = Group.objects.get(institution=self.institution, code="BEC001")
        self.assertTrue(GroupMembership.objects.filter(candidate=self.candidate, group=group, is_active=True).exists())
        subject = Subject.objects.get(institution=self.institution, code="BEF101")
        topic = Topic.objects.get(institution=self.institution, subject=subject, name="Python & Backend Fundamentals")
        questions = Question.objects.filter(institution=self.institution, subject=subject)
        self.assertEqual(questions.count(), 9)
        self.assertEqual(questions.filter(status=Question.Status.APPROVED, topic=topic).count(), 9)

        assessments = Assessment.objects.filter(institution=self.institution)
        self.assertEqual(assessments.count(), 2)
        self.assertEqual(assessments.get(title="Backend Fundamentals Practice Assessment").assessment_questions.count(), 5)
        self.assertEqual(assessments.get(title="Backend Engineering Progress Test").assessment_questions.count(), 5)

        client = APIClient()
        client.force_authenticate(self.candidate_user)
        response = client.get("/api/v1/candidate/me/exams/")
        self.assertEqual(response.status_code, 200, response.data)
        states = {row["title"]: row["status"] for row in response.data["exams"]}
        self.assertEqual(states["Backend Fundamentals Practice Assessment"], "available")
        self.assertEqual(states["Backend Engineering Progress Test"], "upcoming")
        self.assertEqual(Attempt.objects.count(), 0)
        self.assertEqual(Result.objects.count(), 0)

    @override_settings(DEBUG=False)
    def test_refuses_to_run_when_debug_is_false(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo_assessment", stdout=StringIO())

    def test_fails_without_creating_candidate_or_login(self):
        Candidate.objects.filter(pk=self.candidate.pk).delete()
        before_users = User.objects.count()
        with self.assertRaisesMessage(CommandError, "Create the Phase 1 development account"):
            call_command("seed_demo_assessment", stdout=StringIO())
        self.assertEqual(User.objects.count(), before_users)
