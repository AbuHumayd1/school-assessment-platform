from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from rest_framework.test import APITestCase

from attempts import tests as attempt_fixtures
from attempts.models import Attempt
from candidates.models import Candidate
from groups.models import GroupMembership
from questions.models import Question
from questions.revisions import create_question_revision
from results.reporting import participant_queryset
from .models import Assessment, AssessmentCandidate, AssessmentQuestion


class ExamSetupTests(APITestCase):
    setUpTestData = classmethod(attempt_fixtures.CandidateAttemptAPITests.setUpTestData.__func__)
    make_question = staticmethod(attempt_fixtures.CandidateAttemptAPITests.make_question)
    make_assessment = staticmethod(attempt_fixtures.CandidateAttemptAPITests.make_assessment)

    def setUp(self):
        Assessment.objects.filter(pk=self.assessment.pk).update(status='draft')
        self.assessment.status = 'draft'
        self.assessment.candidate_access = 'specific_candidates'
        self.assessment.group = None
        self.assessment.save()
        self.client.force_authenticate(self.staff)
        self.base = f'/api/v1/assessments/{self.assessment.pk}/'
        self.query = f'?institution={self.school.pk}'

    def assign(self, ids=None):
        return self.client.post(self.base + 'candidate-assignments/' + self.query, {'candidates': ids or [self.candidate.pk]}, format='json')

    def ready(self):
        self.assign()
        GroupMembership.objects.filter(candidate=self.candidate).delete()
        self.assessment.status = 'scheduled'
        self.assessment.save()
        self.client.force_authenticate(self.user)

    def test_add_multiple_and_duplicate_safe(self):
        self.assertEqual(self.assign([self.candidate.pk, self.other_candidate.pk, self.candidate.pk]).status_code, 200)
        self.assertEqual(self.assign().status_code, 200)
        self.assertEqual(AssessmentCandidate.objects.count(), 2)
        row = AssessmentCandidate.objects.first()
        self.assertEqual(row.assigned_by, self.staff)
        self.assertIsNotNone(row.assigned_at)

    def test_cross_tenant_batch_is_atomic(self):
        self.assertEqual(self.assign([self.candidate.pk, self.foreign_candidate.pk]).status_code, 400)
        self.assertFalse(AssessmentCandidate.objects.exists())

    def test_search_by_name_and_id_and_no_email(self):
        for query in (self.candidate.candidate_id, self.candidate.first_name, f"{self.candidate.first_name} {self.candidate.last_name}"):
            response = self.client.get(self.base + 'candidate-assignments/' + self.query + '&search=' + query)
            self.assertIn(self.candidate.pk, [row['id'] for row in response.data['results']])
        blank = Candidate.objects.create(institution=self.school, candidate_id='NOEMAIL', first_name='No', last_name='Email')
        self.assertEqual(self.assign([blank.pk]).status_code, 200)

    def test_specific_candidate_is_listed_without_group_and_starts(self):
        self.ready()
        from candidates.views import CandidateExamListView
        from rest_framework.test import APIRequestFactory, force_authenticate
        request = APIRequestFactory().get('/api/v1/candidate/exams/')
        force_authenticate(request, self.user)
        response = CandidateExamListView.as_view()(request)
        self.assertIn(self.assessment.pk, [row['id'] for row in response.data['exams']])
        self.assertEqual(self.client.post('/api/v1/attempts/start/', {'assessment': self.assessment.pk}, format='json').status_code, 201)

    def test_unassigned_candidate_cannot_start(self):
        self.ready()
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.post('/api/v1/attempts/start/', {'assessment': self.assessment.pk}, format='json').status_code, 403)

    def test_unassigned_candidate_not_listed(self):
        self.ready()
        from candidates.views import CandidateExamListView
        from rest_framework.test import APIRequestFactory, force_authenticate
        request = APIRequestFactory().get('/')
        force_authenticate(request, self.other_user)
        response = CandidateExamListView.as_view()(request)
        self.assertNotIn(self.assessment.pk, [row['id'] for row in response.data['exams']])

    def test_unused_assignment_removed_not_candidate(self):
        self.assign()
        response = self.client.delete(self.base + f'candidate-assignments/{self.candidate.pk}/' + self.query)
        self.assertEqual(response.status_code, 204)
        self.assertTrue(Candidate.objects.filter(pk=self.candidate.pk).exists())

    def test_participation_prevents_removal(self):
        self.ready()
        self.client.post('/api/v1/attempts/start/', {'assessment': self.assessment.pk}, format='json')
        with self.assertRaises(ValidationError):
            Assessment.objects.filter(pk=self.assessment.pk).update(status='draft')
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.delete(self.base + f'candidate-assignments/{self.candidate.pk}/' + self.query).status_code, 403)
        with self.assertRaises(ValidationError):
            self.assessment.candidate_assignments.get(candidate=self.candidate).delete()
        self.assertEqual(Attempt.objects.count(), 1)
        self.assertEqual(AssessmentCandidate.objects.count(), 1)

    def test_unique_and_independent_assignment_constraints(self):
        self.assign()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssessmentCandidate.objects.create(assessment=self.assessment, candidate=self.candidate, assigned_by=self.staff)
        AssessmentCandidate.objects.create(assessment=self.assessment, candidate=self.other_candidate, assigned_by=self.staff)
        second = self.make_assessment(self, self.school, self.subject, None, self.staff)
        AssessmentCandidate.objects.create(assessment=second, candidate=self.candidate, assigned_by=self.staff)
        self.assertEqual(AssessmentCandidate.objects.count(), 3)

    def test_model_cross_tenant_rejected(self):
        with self.assertRaises(ValidationError):
            AssessmentCandidate.objects.create(assessment=self.assessment, candidate=self.foreign_candidate, assigned_by=self.staff)

    def test_assigned_candidate_and_actor_protected(self):
        self.assign()
        with self.assertRaises(ProtectedError):
            self.candidate.delete()
        with self.assertRaises(ProtectedError):
            self.staff.delete()

    def test_assessment_deletion_only_removes_assignment(self):
        self.assign()
        self.assessment.delete()
        self.assertFalse(AssessmentCandidate.objects.exists())
        self.assertTrue(Candidate.objects.filter(pk=self.candidate.pk).exists())

    def test_non_draft_and_candidate_cannot_assign(self):
        self.assign()
        self.assessment.status = 'scheduled'; self.assessment.save()
        self.assertEqual(self.assign().status_code, 403)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.assign().status_code, 403)

    def test_delivery_change_rejected_preserves_direct_assignments(self):
        self.assign()
        response = self.client.patch(self.base + self.query, {'candidate_access': 'access_code'}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertTrue(self.assessment.candidate_assignments.filter(candidate=self.candidate).exists())

    def test_group_strategy_requires_group_when_explicitly_saved(self):
        response = self.client.patch(self.base + self.query, {'candidate_access': 'assigned_group', 'group': None}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_scheduling_specific_requires_assignment(self):
        with self.assertRaises(ValidationError):
            self.assessment.validate_configuration(require_schedule=True)

    def test_report_population_includes_assigned_without_attempt(self):
        self.assign()
        self.assertEqual(list(participant_queryset(self.assessment).values_list('pk', flat=True)), [self.candidate.pk])

    def test_question_batch_duplicate_safe_and_remove_bank_survives(self):
        self.assessment.assessment_questions.all().delete()
        response = self.client.post(self.base + 'questions/add/' + self.query, {'questions': [self.mcq.pk, self.mcq_two.pk, self.mcq.pk]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['question_count'], 2)
        self.assertEqual(self.client.post(self.base + 'questions/add/' + self.query, {'questions': [self.mcq.pk]}, format='json').status_code, 200)
        row = self.assessment.assessment_questions.get(question=self.mcq)
        self.assertEqual(self.client.delete(self.base + f'questions/{row.pk}/' + self.query).status_code, 204)
        self.assertTrue(Question.objects.filter(pk=self.mcq.pk).exists())

    def test_invalid_question_batch_rolls_back(self):
        self.assessment.assessment_questions.all().delete()
        self.assertEqual(self.client.post(self.base + 'questions/add/' + self.query, {'questions': [self.mcq.pk, self.foreign_q.pk]}, format='json').status_code, 400)
        self.assertFalse(self.assessment.assessment_questions.exists())

    def test_question_picker_scopes_status_subject_and_attached(self):
        url = f'/api/v1/assessments/question-options/{self.query}&subject={self.subject.pk}&assessment={self.assessment.pk}'
        response = self.client.get(url)
        self.assertTrue(all(row['attached'] for row in response.data['results']))
        for status in ('draft', 'review'):
            question = Question.objects.create(institution=self.school, subject=self.subject,
                created_by=self.staff, text=f'Unapproved {status}', question_type='multiple_choice')
            question.status = status
            question.save(update_fields=['status'])
            response = self.client.get(url)
            self.assertNotIn(question.pk, [row['id'] for row in response.data['results']])

    def test_subject_change_rejected_with_attached_questions(self):
        from subjects.models import Subject
        other = Subject.objects.create(institution=self.school, name='Other', code='OTH')
        self.assertEqual(self.client.patch(self.base + self.query, {'subject': other.pk}, format='json').status_code, 400)

    def test_specific_portal_submission_manual_release_journey(self):
        from tenants.models import InstitutionMembership
        from results.models import Result
        InstitutionMembership.objects.filter(user=self.staff, institution=self.school).update(role='institution_admin')
        # This journey exercises an administrator explicitly permitted to publish.
        self.school.can_release_candidate_results = True
        self.school.save(update_fields=['can_release_candidate_results'])
        self.assessment.result_visibility = 'after_submission'
        self.assessment.result_release_mode = 'manual_release'
        self.assessment.save()
        self.ready()
        started = self.client.post('/api/v1/attempts/start/', {'assessment': self.assessment.pk}, format='json')
        self.assertEqual(started.status_code, 201, started.data)
        attempt = Attempt.objects.get(assessment=self.assessment, candidate=self.candidate)
        response = self.client.post(f'/api/v1/attempts/{attempt.pk}/submit/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        result = Result.objects.get(attempt=attempt)
        self.assertEqual(result.status, 'provisional')
        before = self.client.get('/api/v1/results/my/')
        self.assertFalse(before.data)
        self.client.force_authenticate(self.staff)
        report = self.client.get(self.base + 'results/' + self.query)
        self.assertEqual(report.data['summary']['release_state'], 'not_released')
        published = self.client.post(self.base + 'results/release/' + self.query, {}, format='json')
        self.assertEqual(published.status_code, 200, published.data)
        self.assertEqual(published.data['release_state'], 'released')
        self.client.force_authenticate(self.user)
        visible = self.client.get('/api/v1/results/my/')
        self.assertEqual(len(visible.data), 1)
        self.assertNotIn('correct_options', str(visible.data))
        self.client.force_authenticate(self.other_user)
        self.assertFalse(self.client.get('/api/v1/results/my/').data)

    def test_assignment_cannot_be_created_after_participation(self):
        self.ready()
        self.client.post('/api/v1/attempts/start/', {'assessment': self.assessment.pk}, format='json')
        with self.assertRaises(ValidationError):
            AssessmentCandidate.objects.create(assessment=self.assessment, candidate=self.other_candidate, assigned_by=self.staff)

    def test_assigning_actor_requires_same_workspace_management_role(self):
        with self.assertRaises(ValidationError):
            AssessmentCandidate.objects.create(assessment=self.assessment, candidate=self.candidate, assigned_by=self.foreign_user)

    def test_migration_creates_only_assignment_structure(self):
        from importlib import import_module
        from django.db.migrations import CreateModel
        migration = import_module('assessments.migrations.0004_assessment_candidate').Migration
        self.assertEqual(len(migration.operations), 1)
        self.assertIsInstance(migration.operations[0], CreateModel)
        self.assertEqual(migration.operations[0].name, 'AssessmentCandidate')

    def test_empty_approved_question_picker_and_default_bank_marks(self):
        question = create_question_revision(self.mcq.pk, actor=self.staff, institution=self.school)
        question.marks = '2.50'
        question.save(update_fields=['marks'])
        question.status = 'approved'
        question.save(update_fields=['status'])
        self.assessment.assessment_questions.all().delete()
        response = self.client.post(self.base + 'questions/add/' + self.query, {'questions': [question.pk]}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(self.assessment.assessment_questions.get().marks), '2.50')
        Question.objects.filter(subject=self.subject, status='approved').update(status='archived')
        response = self.client.get('/api/v1/assessments/question-options/' + self.query + f'&subject={self.subject.pk}')
        self.assertEqual(response.data['count'], 0)
