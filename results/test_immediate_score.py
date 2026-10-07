from unittest.mock import patch

from django.core.cache import cache
from django.contrib.auth.hashers import make_password
from django.test import TestCase, TransactionTestCase
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APIClient

from assessments.models import Assessment, QuickExamCredential
from accounts.models import User
from tenants.models import InstitutionMembership
from assessments import test_quick_sessions as quick_fixtures
from attempts.models import Attempt
from results.models import Result, ResultQuestion
from results.services import publish_result
from results.immediate_score import immediate_score
from types import SimpleNamespace


class ImmediateScoreTests(TestCase):
    PIN = quick_fixtures.QuickSessionTests.PIN
    make_question = staticmethod(quick_fixtures.QuickSessionTests.make_question)
    make_assessment = staticmethod(quick_fixtures.QuickSessionTests.make_assessment)

    @classmethod
    def setUpTestData(cls):
        quick_fixtures.QuickSessionTests.setUpTestData.__func__(cls)

    def setUp(self):
        cache.clear()
        self.portal = APIClient()
        self.portal.force_authenticate(self.user)
        self.quick = APIClient(enforce_csrf_checks=True)
        self.quick.defaults['HTTP_X_CSRFTOKEN'] = self.quick.get('/api/v1/auth/csrf/').data['csrfToken']
        verified = self.quick.post('/api/v1/quick-exam/verify/', {
            'exam_code': self.configuration.exam_code, 'candidate_id': self.quick_candidate.candidate_id,
            'pin': self.PIN}, format='json')
        self.assertEqual(verified.status_code, 200)

    def start(self, quick=False, enabled=True):
        exam = self.quick_assessment if quick else self.assessment
        Assessment.objects.filter(pk=exam.pk).update(status='draft')
        Assessment.objects.filter(pk=exam.pk).update(show_score_immediately=enabled,
            result_visibility='after_submission', result_release_mode='manual_release')
        Assessment.objects.filter(pk=exam.pk).update(status='approved')
        client = self.quick if quick else self.portal
        response = client.post('/api/v1/quick-exam/start/' if quick else '/api/v1/attempts/start/',
            {} if quick else {'assessment': exam.pk}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return client, response.data['id'], '/api/v1/quick-exam/attempt/' if quick else '/api/v1/attempts/'

    def submit(self, quick=False, enabled=True):
        client, pk, base = self.start(quick, enabled)
        saved = client.put(f'{base}{pk}/questions/{self.mcq.pk}/answer/', {
            'selected_options': [self.mcq.options.get(is_correct=True).pk]}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        response = client.post(f'{base}{pk}/submit/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return client, pk, base, response

    def test_default_off(self):
        self.assertFalse(self.assessment.show_score_immediately)
        self.assertFalse(self.quick_assessment.show_score_immediately)

    def test_both_delivery_modes_disclose_only_authoritative_own_unpublished_score(self):
        for quick in (False, True):
            with self.subTest(quick=quick):
                client, pk, base, response = self.submit(quick)
                result = Result.objects.get(attempt_id=pk)
                self.assertEqual(result.status, 'provisional')
                self.assertIsNone(result.published_at)
                expected = {'marks_obtained': str(result.marks_obtained), 'total_marks': str(result.total_marks)}
                self.assertEqual(response.data['immediate_score'], expected)
                detail = client.get(f'{base}{pk}/')
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.data['immediate_score'], expected)
                forbidden = {'passed', 'pass_mark', 'grade', 'percentage', 'questions', 'correct_answers',
                    'answer_key', 'explanations', 'marks_available', 'validation_note', 'published_at', 'result'}
                self.assertFalse(forbidden.intersection(response.data))
                self.assertFalse(forbidden.intersection(detail.data))
                self.assertFalse(forbidden.intersection(expected))
                self.assertNotEqual(client.get(f'/api/v1/results/{result.pk}/').status_code, 200)
        self.assertEqual(self.portal.get('/api/v1/results/my/').data, [])

    def test_disabled_submission_and_reload_have_no_score(self):
        for quick in (False, True):
            client, pk, base, response = self.submit(quick, enabled=False)
            self.assertIsNone(response.data['immediate_score'])
            self.assertIsNone(client.get(f'{base}{pk}/').data['immediate_score'])

    def test_unfinished_missing_or_invalid_marking_never_discloses_score(self):
        client, pk, base = self.start()
        self.assertIsNone(client.get(f'{base}{pk}/').data['immediate_score'])
        # A closed attempt without completed marking cannot disclose a score.
        attempt = Attempt.objects.get(pk=pk)
        Attempt.objects.filter(pk=pk).update(status='submitted', submitted_at=attempt.started_at)
        attempt.refresh_from_db()
        self.assertIsNone(immediate_score(attempt, SimpleNamespace(auth=None, user=self.user)))
        from results.services import mark_attempt
        result = mark_attempt(pk)
        result.questions.update(status=ResultQuestion.Status.INVALID)
        self.assertIsNone(client.get(f'{base}{pk}/').data['immediate_score'])
        result.questions.all().delete()
        self.assertIsNone(client.get(f'{base}{pk}/').data['immediate_score'])

    def test_marking_failure_rolls_back_submission_without_score(self):
        client, pk, base = self.start()
        with patch('results.services.mark_attempt', side_effect=RuntimeError('Synthetic marking failure')):
            with self.assertRaises(RuntimeError):
                client.post(f'{base}{pk}/submit/', {}, format='json')
        self.assertEqual(Attempt.objects.get(pk=pk).status, 'in_progress')
        self.assertFalse(Result.objects.filter(attempt_id=pk).exists())
        self.assertIsNone(client.get(f'{base}{pk}/').data['immediate_score'])

    def test_other_candidate_and_other_delivery_cannot_read_score(self):
        _, account_pk, _, _ = self.submit()
        _, quick_pk, _, _ = self.submit(True)
        other = APIClient()
        other.force_authenticate(self.other_user)
        for client, path in ((other, f'/api/v1/attempts/{account_pk}/'),
                (self.portal, f'/api/v1/attempts/{quick_pk}/'),
                (self.quick, f'/api/v1/quick-exam/attempt/{account_pk}/')):
            self.assertNotEqual(client.get(path).status_code, 200)
            self.assertNotEqual(client.post(path + 'submit/', {}, format='json').status_code, 200)
        QuickExamCredential.objects.create(configuration=self.configuration, candidate=self.other_candidate,
            pin_hash=make_password(self.PIN))
        other_quick = APIClient(enforce_csrf_checks=True)
        other_quick.defaults['HTTP_X_CSRFTOKEN'] = other_quick.get('/api/v1/auth/csrf/').data['csrfToken']
        verified = other_quick.post('/api/v1/quick-exam/verify/', {'exam_code': self.configuration.exam_code,
            'candidate_id': self.other_candidate.candidate_id, 'pin': self.PIN}, format='json')
        self.assertEqual(verified.status_code, 200, verified.data)
        self.assertEqual(other_quick.get(f'/api/v1/quick-exam/attempt/{quick_pk}/').status_code, 404)

    def test_published_result_representation_unchanged(self):
        _, pk, _, _ = self.submit()
        result = Result.objects.get(attempt_id=pk)
        self.school.can_release_candidate_results = True
        self.school.save(update_fields=['can_release_candidate_results'])
        publish_result(result.pk, actor=self.admin)
        response = self.portal.get(f'/api/v1/results/{result.pk}/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('grade', response.data)
        self.assertIn('passed', response.data)
        self.assertIn('percentage', response.data)

    def test_create_edit_reload_and_managed_preparation_restriction(self):
        staff = APIClient()
        staff.force_authenticate(self.admin)
        base = f'/api/v1/assessments/?institution={self.school.pk}'
        response = staff.post(base, {'title': 'Synthetic score configuration', 'assessment_type': 'test',
            'subject': self.subject.pk, 'group': self.group.pk, 'duration_minutes': 5,
            'show_score_immediately': True}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        path = f'/api/v1/assessments/{response.data["id"]}/?institution={self.school.pk}'
        self.assertTrue(staff.get(path).data['show_score_immediately'])
        changed = staff.patch(path, {'show_score_immediately': False}, format='json')
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertFalse(staff.get(path).data['show_score_immediately'])
        self.school.workspace_mode = 'managed_exam'
        self.school.save(update_fields=['workspace_mode'])
        self.assertEqual(staff.patch(path, {'show_score_immediately': True}, format='json').status_code, 403)
        platform = User.objects.create_user('synthetic-platform@example.test', 'Safe-pass-8392')
        InstitutionMembership.objects.create(user=platform, institution=self.school, role='platform_admin')
        staff.force_authenticate(platform)
        changed = staff.patch(path, {'show_score_immediately': True}, format='json')
        self.assertEqual(changed.status_code, 200, changed.data)


class ImmediateScoreMigrationTests(TransactionTestCase):
    def test_existing_assessment_gets_off_schema_default(self):
        before = ('assessments', '0004_assessment_candidate')
        after = ('assessments', '0005_assessment_show_score_immediately')
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        executor.migrate([before])
        try:
            apps = MigrationExecutor(connection)._create_project_state(with_applied_migrations=True).apps
            school = apps.get_model('institutions', 'Institution').objects.create(name='Synthetic migration school', slug='synthetic-migration-school')
            user = apps.get_model('accounts', 'User').objects.create(email='migration@example.test', password='')
            subject = apps.get_model('subjects', 'Subject').objects.create(institution_id=school.pk, name='Math', code='SYNTH')
            exam = apps.get_model('assessments', 'Assessment').objects.create(institution_id=school.pk,
                subject_id=subject.pk, created_by_id=user.pk, title='Existing synthetic exam',
                assessment_type='test', duration_minutes=5)
            executor = MigrationExecutor(connection)
            executor.migrate(leaves)
            apps = executor.loader.project_state(leaves).apps
            self.assertFalse(apps.get_model('assessments', 'Assessment').objects.get(pk=exam.pk).show_score_immediately)
        finally:
            MigrationExecutor(connection).migrate(leaves)
