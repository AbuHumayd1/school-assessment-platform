"""Existing visibility/publication combinations, exposed through normal editing."""
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APITestCase

from assessments.models import Assessment
from .models import Result
from .services import mark_attempt
from .tests import ResultFixtureMixin


class VisibilityWorkflowTests(ResultFixtureMixin, APITestCase):
    def setUp(self):
        self.client.force_authenticate(self.admin)

    def url(self, suffix="", assessment=None, institution=None):
        return f'/api/v1/assessments/{(assessment or self.assessment).pk}/{suffix}?institution={institution or self.school.pk}'

    def configure(self, visibility="after_submission", mode="manual_release", **extra):
        response = self.client.patch(self.url(), {"result_visibility": visibility, "result_release_mode": mode, **extra}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assessment.refresh_from_db()
        return response

    def marked(self):
        attempt = self.make_attempt()
        self.add_question(attempt, self.mcq[0].question, self.mcq, marks="3.00", selection=[self.mcq[0]])
        return mark_attempt(attempt.pk)

    def own(self):
        self.client.force_authenticate(self.student)
        response = self.client.get('/api/v1/results/my/')
        self.client.force_authenticate(self.admin)
        return response.data

    def test_form_options_expose_existing_fields_and_manual_release(self):
        response = self.client.get(f'/api/v1/assessments/form-options/?institution={self.school.pk}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['value'] for row in response.data['choices']['result_visibility']}, {'hidden', 'after_submission', 'scheduled_release'})
        self.assertIn('manual_release', {row['value'] for row in response.data['choices']['result_release_mode']})

    def test_create_manual_release_through_authorized_assessment_api(self):
        response = self.client.post(f'/api/v1/assessments/?institution={self.school.pk}', {
            'title': 'Manual publication', 'assessment_type': 'test', 'subject': self.subject.pk,
            'duration_minutes': 30, 'result_visibility': 'after_submission', 'result_release_mode': 'manual_release',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['result_visibility'], 'after_submission')
        self.assertEqual(response.data['result_release_mode'], 'manual_release')

    def test_draft_edit_persists_and_get_loads_manual_fields(self):
        self.configure()
        response = self.client.get(self.url())
        self.assertEqual(response.data['result_visibility'], 'after_submission')
        self.assertEqual(response.data['result_release_mode'], 'manual_release')

    def test_manual_marked_result_not_published_or_candidate_visible(self):
        self.configure()
        result = self.marked()
        self.assertEqual(result.status, Result.Status.PROVISIONAL)
        self.assertIsNone(result.published_at)
        self.assertEqual(self.own(), [])

    def test_manual_bulk_release_makes_own_result_visible(self):
        self.configure()
        result = self.marked()
        self.assertEqual(self.own(), [])
        response = self.client.post(self.url('results/release/'), {})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['released_count'], 1)
        self.assertEqual(response.data['release_state'], 'released')
        self.assertEqual([row['id'] for row in self.own()], [result.pk])

    def test_manual_individual_release_makes_own_result_visible(self):
        self.configure()
        result = self.marked()
        self.assertEqual(self.own(), [])
        self.assertEqual(self.client.post(self.url(f'results/{result.pk}/release/'), {}).status_code, 200)
        self.assertEqual([row['id'] for row in self.own()], [result.pk])

    def test_legacy_approval_required_is_same_manual_publication_gate(self):
        self.configure(mode='approval_required')
        self.marked()
        self.assertEqual(self.own(), [])
        self.assertEqual(self.client.post(self.url('results/release/'), {}).status_code, 200)
        self.assertEqual(len(self.own()), 1)

    def test_after_submit_immediate_publishes_on_marking(self):
        self.configure(mode='immediate')
        result = self.marked()
        self.assertEqual(result.status, Result.Status.PUBLISHED)
        self.assertEqual([row['id'] for row in self.own()], [result.pk])

    def test_after_close_policy_blocks_both_release_actions_before_close(self):
        self.configure('scheduled_release', end_at=(timezone.now() + timedelta(hours=1)).isoformat())
        result = self.marked()
        self.assertEqual(self.own(), [])
        for suffix in ('results/release/', f'results/{result.pk}/release/'):
            self.assertEqual(self.client.post(self.url(suffix), {}).status_code, 400)
        result.refresh_from_db()
        self.assertEqual(result.status, Result.Status.PROVISIONAL)

    def test_after_close_still_requires_publication_when_manual(self):
        self.configure('scheduled_release', end_at=(timezone.now() - timedelta(hours=1)).isoformat())
        result = self.marked()
        self.assertEqual(self.own(), [])
        self.assertEqual(self.client.post(self.url('results/release/'), {}).status_code, 200)
        self.assertEqual([row['id'] for row in self.own()], [result.pk])

    def test_legacy_after_close_immediate_is_not_a_background_scheduler(self):
        self.configure('scheduled_release', 'immediate', end_at=(timezone.now() + timedelta(hours=1)).isoformat())
        result = self.marked()
        self.assertEqual(result.status, Result.Status.PROVISIONAL)
        with patch('django.utils.timezone.now', return_value=timezone.now() + timedelta(hours=2)):
            self.assertEqual(self.own(), [])
            self.assertEqual(self.client.post(self.url('results/release/'), {}).status_code, 200)
            self.assertEqual([row['id'] for row in self.own()], [result.pk])

    def test_hidden_policy_blocks_both_actions_and_candidate_visibility(self):
        self.configure('hidden', 'manual_release')
        result = self.marked()
        for suffix in ('results/release/', f'results/{result.pk}/release/'):
            self.assertEqual(self.client.post(self.url(suffix), {}).status_code, 400)
        self.assertEqual(self.own(), [])

    def test_started_draft_cannot_change_policy(self):
        self.configure('hidden', 'approval_required')
        self.make_attempt()
        response = self.client.patch(self.url(), {'result_visibility': 'after_submission', 'result_release_mode': 'manual_release'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.result_visibility, 'hidden')

    def test_scheduled_assessment_cannot_edit_policy(self):
        self.assessment.status = Assessment.Status.SCHEDULED
        self.assessment.save()
        response = self.client.patch(self.url(), {'result_visibility': 'after_submission', 'result_release_mode': 'manual_release'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_candidate_cannot_edit_or_release(self):
        self.configure()
        result = self.marked()
        self.client.force_authenticate(self.student)
        self.assertIn(self.client.patch(self.url(), {'result_visibility': 'hidden'}, format='json').status_code, (403, 404))
        self.assertEqual(self.client.post(self.url('results/release/'), {}).status_code, 404)
        self.assertEqual(self.client.post(self.url(f'results/{result.pk}/release/'), {}).status_code, 404)

    def test_cross_tenant_edit_and_release_denied(self):
        response = self.client.patch(self.url(assessment=self.foreign_assessment), {'result_visibility': 'after_submission', 'result_release_mode': 'manual_release'}, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.post(self.url('results/release/', assessment=self.foreign_assessment), {}).status_code, 404)
