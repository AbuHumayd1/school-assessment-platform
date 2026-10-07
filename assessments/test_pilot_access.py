import csv
import io
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase, APIClient

from accounts.models import User
from audit.models import AuditEvent
from attempts.models import Attempt
from candidates.models import Candidate
from groups.models import Group
from institutions.models import Institution
from questions.models import Question, QuestionOption
from subjects.models import Subject
from tenants.models import InstitutionMembership
from .models import Assessment, AssessmentCandidate, AssessmentQuestion, QuickExamConfiguration, QuickExamCredential, QuickExamSession
from .quick_services import generate_assigned_credentials, generate_credential


# Speed up large fixture tests only; production PIN hashing is not changed.
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PilotAccessTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = Institution.objects.create(name='Pilot managed client', workspace_mode='managed_exam')
        cls.other = Institution.objects.create(name='Other pilot client')
        cls.platform = User.objects.create_superuser('pilot-platform@example.test', None)
        cls.admin = User.objects.create_user('pilot-managed-admin@example.test')
        InstitutionMembership.objects.create(institution=cls.school, user=cls.admin, role='institution_admin')
        cls.subject = Subject.objects.create(institution=cls.school, name='Pilot subject', code='PILOT')
        cls.exam = Assessment.objects.create(institution=cls.school, subject=cls.subject, created_by=cls.platform,
            title='Pilot exam', assessment_type='test', duration_minutes=30, candidate_access='access_code',
            start_at=timezone.now() - timedelta(minutes=5), end_at=timezone.now() + timedelta(hours=3))
        Candidate.objects.bulk_create([Candidate(institution=cls.school, candidate_id=f'PILOT{i:03}',
            first_name='Pilot', last_name=f'Candidate{i:03}') for i in range(300)])
        cls.candidates = list(Candidate.objects.filter(institution=cls.school).order_by('candidate_id'))
        cls.foreign = Candidate.objects.create(institution=cls.other, candidate_id='PILOT000', first_name='Foreign', last_name='Candidate')
        cls.inactive = Candidate.objects.create(institution=cls.school, candidate_id='INACTIVE', first_name='Inactive', last_name='Candidate', status='inactive')
        question = Question.objects.create(institution=cls.school, subject=cls.subject, created_by=cls.platform,
            text='Pilot question', question_type='multiple_choice', status='draft')
        for order in (1, 2):
            QuestionOption.objects.create(question=question, text=f'Option {order}', order=order, is_correct=order == 1)
        question.status = 'approved'
        question.save(update_fields=['status'])
        AssessmentQuestion.objects.create(assessment=cls.exam, question=question, order=1, marks=1)

    def setUp(self):
        cache.clear()
        self.client.force_authenticate(self.platform)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))
        self.base = f'/api/v1/assessments/{self.exam.pk}/'

    def assign(self, candidates=None, **selection):
        return self.client.post(self.base + 'candidate-assignments/', selection if selection else
            {'candidates': [c.pk for c in (candidates or self.candidates[:3])]}, format='json')

    def configure(self, enabled=True):
        response = self.client.put(self.base + 'quick-access/', {'exam_code': 'PILOT-ACCESS', 'enabled': enabled}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return QuickExamConfiguration.objects.get(assessment=self.exam)

    def sheet(self, **body):
        return self.client.post(self.base + 'quick-access/credentials/generate-sheet/', body, format='json')

    def rows(self, response):
        self.assertEqual(response.status_code, 200, getattr(response, 'data', response.content))
        return list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))

    def counts(self):
        return self.client.get(self.base + 'quick-access/credentials/').data

    def test_select_all_assigns_all_300_across_pages_and_retries_do_not_duplicate(self):
        for page in (1, 2):
            picker = self.client.get(self.base + f'candidate-assignments/?page={page}&status=active')
            self.assertEqual(picker.data['available_count'], 300)
            self.assertEqual(len(picker.data['results']), 25)
        response = self.assign(select_all=True, expected_count=300, status='active')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['added_count'], 300)
        self.assertEqual(self.exam.candidate_assignments.count(), 300)
        self.assertEqual(self.assign(select_all=True).data['added_count'], 0)
        self.assertEqual(len(set(self.exam.candidate_assignments.values_list('candidate_id', flat=True))), 300)
        self.assertFalse(self.exam.candidate_assignments.filter(candidate__in=[self.foreign, self.inactive]).exists())

    def test_search_select_all_matches_only_search_excludes_existing_and_stale_count_aborts(self):
        self.assign(self.candidates[:1])
        picker = self.client.get(self.base + 'candidate-assignments/?search=Candidate00')
        self.assertEqual(picker.data['available_count'], 9)
        self.assertEqual(self.assign(select_all=True, search='Candidate00', expected_count=10).status_code, 400)
        self.assertEqual(self.exam.candidate_assignments.count(), 1)
        self.assertEqual(self.assign(select_all=True, search='Candidate00', expected_count=9).data['added_count'], 9)
        self.assertEqual(set(self.exam.candidate_assignments.values_list('candidate_id', flat=True)), {c.pk for c in self.candidates[:10]})

    def test_explicit_foreign_inactive_and_tampered_batches_rejected_atomically(self):
        for candidate in (self.foreign, self.inactive):
            self.assertEqual(self.assign([self.candidates[0], candidate]).status_code, 400)
        self.assertEqual(self.assign(select_all=True, institution=self.other.pk).status_code, 400)
        self.assertEqual(self.assign(select_all=True, status='inactive').status_code, 400)
        self.assertFalse(self.exam.candidate_assignments.exists())

    def test_managed_admin_denied_assignment_configuration_generation_and_sheet(self):
        self.assign(); configuration = self.configure()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.assign(select_all=True).status_code, 403)
        self.assertEqual(self.client.put(self.base + 'quick-access/', {'enabled': True}, format='json').status_code, 403)
        self.assertEqual(self.sheet().status_code, 403)
        self.assertEqual(self.client.post(self.base + 'quick-access/credentials/', {'candidate': self.candidates[0].pk}, format='json').status_code, 403)
        with self.assertRaises(PermissionDenied):
            generate_assigned_credentials(configuration, self.admin)

    def test_wrong_workspace_and_noneditable_assignment_and_generation_are_rejected(self):
        self.assign(); self.configure()
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.other.pk))
        self.assertEqual(self.assign(select_all=True).status_code, 404)
        self.assertEqual(self.sheet().status_code, 404)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))
        Assessment.objects.filter(pk=self.exam.pk).update(status='review')
        self.assertEqual(self.assign(select_all=True).status_code, 403)
        self.assertEqual(self.sheet().status_code, 400)
        self.assertFalse(QuickExamCredential.objects.exists())

    def test_participation_locks_removal_assignment_and_generation(self):
        self.assign(); self.configure()
        now = timezone.now()
        Attempt.objects.create(institution=self.school, assessment=self.exam, candidate=self.candidates[0],
            attempt_number=1, started_at=now, expires_at=now + timedelta(minutes=30), last_activity_at=now)
        self.assertEqual(self.assign(select_all=True).status_code, 400)
        self.assertEqual(self.sheet().status_code, 400)
        self.assertEqual(self.client.delete(self.base + f'candidate-assignments/{self.candidates[0].pk}/').status_code, 400)

    def test_configuration_preserves_saved_quick_delivery_assignments_and_no_automatic_credentials(self):
        self.assign(); before = list(self.exam.candidate_assignments.values())
        self.configure()
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.candidate_access, 'access_code')
        self.assertEqual(list(self.exam.candidate_assignments.values()), before)
        self.assertFalse(QuickExamCredential.objects.exists())
        data = self.client.get(self.base).data
        self.assertEqual(data['delivery_mode'], 'quick_exam')
        self.assertEqual(data['eligibility_strategy'], 'specific_candidates')
        self.assertEqual(self.assign(self.candidates[3:4]).status_code, 200)
        self.assertEqual(self.client.get(self.base + 'eligibility/').data['eligible_count'], 4)

    def test_group_quick_unavailable_and_locked_switch_rejected_without_writes(self):
        group = Group.objects.create(institution=self.school, name='Pilot group', code='PILOT')
        Assessment.objects.filter(pk=self.exam.pk).update(candidate_access='assigned_group', group=group)
        self.assertEqual(self.client.put(self.base + 'quick-access/', {'exam_code': 'GROUP-QUICK'}, format='json').status_code, 400)
        Assessment.objects.filter(pk=self.exam.pk).update(candidate_access='specific_candidates', group=None, status='approved')
        self.assertEqual(self.client.put(self.base + 'quick-access/', {'exam_code': 'LOCKED-QUICK'}, format='json').status_code, 400)
        self.assertFalse(QuickExamConfiguration.objects.exists())

    def test_sheet_only_assigned_active_candidates_preserves_candidates_users_and_hashes_pins(self):
        self.assign(self.candidates[:4]); self.configure()
        Candidate.objects.filter(pk=self.candidates[3].pk).update(status='inactive')
        before = list(Candidate.objects.order_by('pk').values()); users = User.objects.count()
        response = self.sheet(expected_count=3); rows = self.rows(response)
        self.assertEqual([r['Candidate ID'] for r in rows], [c.candidate_id for c in self.candidates[:3]])
        self.assertEqual(set(rows[0]), {'Candidate Name', 'Candidate ID', 'Exam Code', 'PIN', 'Exam Title'})
        for row in rows:
            credential = QuickExamCredential.objects.get(candidate__candidate_id=row['Candidate ID'], configuration__assessment=self.exam)
            self.assertTrue(check_password(row['PIN'], credential.pin_hash))
            self.assertNotIn(credential.pin_hash, response.content.decode())
            self.assertEqual(row['Exam Code'], 'PILOT-ACCESS')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(list(Candidate.objects.order_by('pk').values()), before)
        self.assertEqual(User.objects.count(), users)
        self.assertFalse(QuickExamSession.objects.exists())
        self.assertNotIn('token', response.content.decode())
        self.assertNotIn('pin_hash', response.content.decode())
        self.assertEqual(self.sheet().status_code, 400)

    def test_273_existing_credentials_27_needed_no_existing_pin_regenerated(self):
        self.assign(select_all=True); configuration = self.configure()
        QuickExamCredential.objects.bulk_create([QuickExamCredential(configuration=configuration, candidate=c,
            pin_hash=make_password('TEST-EXISTING')) for c in self.candidates[:273]])
        before = list(configuration.credentials.order_by('pk').values())
        counts = self.counts()
        self.assertEqual([counts[k] for k in ('assigned_count', 'generated_count', 'needed_count', 'generatable_count')], [300, 273, 27, 27])
        self.assertEqual(len(self.rows(self.sheet(expected_count=27))), 27)
        self.assertEqual(list(configuration.credentials.filter(candidate__in=self.candidates[:273]).order_by('pk').values()), before)
        self.assertEqual(configuration.credentials.count(), 300)

    def test_expired_and_revoked_existing_credentials_require_explicit_reset(self):
        self.assign(); self.configure(); self.rows(self.sheet())
        QuickExamCredential.objects.filter(candidate=self.candidates[0]).update(expires_at=timezone.now() - timedelta(seconds=1))
        QuickExamCredential.objects.filter(candidate=self.candidates[1]).update(active=False, revoked_at=timezone.now())
        before = list(QuickExamCredential.objects.values())
        counts = self.counts()
        self.assertEqual(counts['needed_count'], 2); self.assertEqual(counts['reset_needed_count'], 2)
        self.assertEqual(counts['generatable_count'], 0)
        self.assertEqual(self.sheet().status_code, 400)
        self.assertEqual(list(QuickExamCredential.objects.values()), before)

    def test_unassigned_individual_issuance_rejected_existing_individual_assignment_works(self):
        self.configure()
        url = self.base + 'quick-access/credentials/'
        self.assertEqual(self.client.post(url, {'candidate': self.candidates[0].pk}, format='json').status_code, 400)
        self.assertEqual(self.assign(self.candidates[:1]).status_code, 200)
        self.assertEqual(self.client.post(url, {'candidate': self.candidates[0].pk}, format='json').status_code, 201)

    def test_stale_generation_count_disabled_configuration_and_payload_tampering_abort(self):
        self.assign(); configuration = self.configure(enabled=False)
        self.assertEqual(self.sheet().status_code, 400)
        configuration.enabled = True; configuration.save()
        self.assertEqual(self.sheet(expected_count=2).status_code, 400)
        self.assertEqual(self.sheet(candidates=[self.foreign.pk]).status_code, 400)
        self.assertFalse(QuickExamCredential.objects.exists())

    def test_sheet_formula_injection_protection_and_deterministic_order(self):
        Candidate.objects.filter(pk=self.candidates[0].pk).update(first_name='=HYPERLINK("bad")', candidate_id='@FIRST')
        Assessment.objects.filter(pk=self.exam.pk).update(title='+DANGEROUS')
        self.assign(); self.configure()
        rows = self.rows(self.sheet())
        dangerous = next(r for r in rows if r['Candidate ID'] == "'@FIRST")
        self.assertTrue(dangerous['Candidate Name'].startswith("'="))
        self.assertTrue(all(r['Exam Title'] == "'+DANGEROUS" for r in rows))

    def test_generation_failure_rolls_back_every_credential_and_audit(self):
        self.assign(); self.configure()
        original = generate_credential
        calls = []
        def issue(*args, **kwargs):
            calls.append(args)
            if len(calls) == 2:
                raise RuntimeError('Controlled failure')
            return original(*args, **kwargs)
        with patch('assessments.quick_services.generate_credential', side_effect=issue):
            with self.assertRaises(RuntimeError):
                self.sheet()
        self.assertFalse(QuickExamCredential.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(metadata__action='quick_credential_generated').exists())

    def test_assignment_failure_rolls_back_all_assignments_and_audits(self):
        original = AssessmentCandidate.save
        calls = []
        def save(instance, *args, **kwargs):
            calls.append(instance)
            if len(calls) == 2:
                raise RuntimeError('Controlled assignment failure')
            return original(instance, *args, **kwargs)
        with patch.object(AssessmentCandidate, 'save', save):
            with self.assertRaises(RuntimeError):
                self.assign(select_all=True)
        self.assertFalse(self.exam.candidate_assignments.exists())
        self.assertFalse(AuditEvent.objects.filter(event_type='assessment_candidate_assigned').exists())

    def test_safe_removal_revokes_new_quick_eligibility_without_deleting_candidate(self):
        self.assign(self.candidates[:1]); self.configure(); row = self.rows(self.sheet())[0]
        client = APIClient(enforce_csrf_checks=True)
        client.defaults['HTTP_X_CSRFTOKEN'] = client.get('/api/v1/auth/csrf/').data['csrfToken']
        self.assertEqual(client.post('/api/v1/quick-exam/verify/', {'exam_code': row['Exam Code'],
            'candidate_id': row['Candidate ID'], 'pin': row['PIN']}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(self.base + f'candidate-assignments/{self.candidates[0].pk}/').status_code, 204)
        self.assertEqual(client.get('/api/v1/quick-exam/session/').status_code, 401)
        self.assertTrue(Candidate.objects.filter(pk=self.candidates[0].pk).exists())

    def test_same_candidate_separate_exam_credentials_and_overlapping_tenant_ids(self):
        self.assign(self.candidates[:1]); self.configure()
        first = self.rows(self.sheet())[0]
        second = Assessment.objects.create(institution=self.school, subject=self.subject, created_by=self.platform,
            title='Second pilot', assessment_type='test', duration_minutes=30, candidate_access='specific_candidates')
        AssessmentCandidate.objects.create(assessment=second, candidate=self.candidates[0], assigned_by=self.platform)
        configuration = QuickExamConfiguration.objects.create(assessment=second, exam_code='PILOT-SECOND', enabled=True)
        other, pin = generate_credential(configuration, self.candidates[0], self.platform)
        self.assertNotEqual(first['PIN'], pin)
        self.assertEqual(self.candidates[0].quick_credentials.count(), 2)
        self.assertTrue(check_password(pin, other.pin_hash))
        self.assertFalse(check_password(first['PIN'], other.pin_hash))
        self.assertFalse(self.foreign.quick_credentials.exists())

    def test_assigned_quick_verify_session_start_resume_and_removal_revokes_eligibility(self):
        self.assign(self.candidates[:1]); self.configure(); row = self.rows(self.sheet())[0]
        Assessment.objects.filter(pk=self.exam.pk).update(status='scheduled')
        client = APIClient(enforce_csrf_checks=True)
        client.defaults['HTTP_X_CSRFTOKEN'] = client.get('/api/v1/auth/csrf/').data['csrfToken']
        self.assertEqual(client.post('/api/v1/quick-exam/verify/', {'exam_code': row['Exam Code'],
            'candidate_id': row['Candidate ID'], 'pin': row['PIN']}, format='json').status_code, 200)
        self.assertEqual(client.get('/api/v1/quick-exam/session/').status_code, 200)
        start = client.post('/api/v1/quick-exam/start/', {}, format='json')
        self.assertEqual(start.status_code, 201, start.data)
        self.assertEqual(client.post('/api/v1/quick-exam/start/', {}, format='json').status_code, 200)
        self.assertEqual(Attempt.objects.count(), 1)

    def test_account_login_direct_assignment_still_starts_and_quick_mode_blocks_portal_entry(self):
        user = User.objects.create_user('pilot-candidate@example.test')
        InstitutionMembership.objects.create(user=user, institution=self.school, role='student')
        Candidate.objects.filter(pk=self.candidates[0].pk).update(user=user)
        self.assign(self.candidates[:1])
        # Configuring Quick retains eligibility but prevents using an account to bypass its PIN.
        self.configure(); Assessment.objects.filter(pk=self.exam.pk).update(status='scheduled')
        self.client.force_authenticate(user)
        self.assertEqual(self.client.post('/api/v1/attempts/start/', {'assessment': self.exam.pk}, format='json').status_code, 403)
        QuickExamConfiguration.objects.filter(assessment=self.exam).delete()
        start = self.client.post('/api/v1/attempts/start/', {'assessment': self.exam.pk}, format='json')
        self.assertEqual(start.status_code, 403, start.data)

    def test_candidate_upload_alone_never_creates_credentials(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile('pilot.csv', b'candidate_id,first_name,last_name\nUPLOAD001,Upload,Only\n', content_type='text/csv')
        users = User.objects.count()
        preview = self.client.post('/api/v1/candidates/import-preview/', {'file': upload}, format='multipart')
        self.assertEqual(preview.status_code, 200, preview.data)
        confirmation = self.client.post('/api/v1/candidates/import-confirm/', {'token': preview.data['token']}, format='json')
        self.assertEqual(confirmation.status_code, 201, confirmation.data)
        self.assertIsNone(Candidate.objects.get(institution=self.school, candidate_id='UPLOAD001').user_id)
        self.assertEqual(User.objects.count(), users)
        self.assertFalse(QuickExamCredential.objects.exists())

    def create_exam(self, delivery, **extra):
        return self.client.post('/api/v1/assessments/', {
            'title': 'Isolated delivery fixture', 'assessment_type': 'test',
            'subject': self.subject.pk, 'duration_minutes': 30,
            'delivery_mode': delivery, **extra,
        }, format='json')

    def test_create_persists_each_delivery_before_configuration_or_assignment(self):
        for delivery, marker in [('quick_exam', 'access_code'), ('account_login', 'assigned_group')]:
            response = self.create_exam(delivery)
            self.assertEqual(response.status_code, 201, response.data)
            exam = Assessment.objects.get(pk=response.data['id'])
            self.assertEqual(exam.candidate_access, marker)
            self.assertEqual(self.client.get(f'/api/v1/assessments/{exam.pk}/').data['delivery_mode'], delivery)
            self.assertFalse(exam.candidate_assignments.exists())
            self.assertFalse(QuickExamConfiguration.objects.filter(assessment=exam).exists())
            self.assertFalse(QuickExamCredential.objects.filter(configuration__assessment=exam).exists())

    def test_delivery_cannot_change_via_api_or_model_before_configuration(self):
        from django.core.exceptions import ValidationError
        for delivery, opposite, marker in [('quick_exam', 'account_login', 'specific_candidates'),
                                            ('account_login', 'quick_exam', 'access_code')]:
            response = self.create_exam(delivery)
            self.assertEqual(response.status_code, 201, response.data)
            url = f"/api/v1/assessments/{response.data['id']}/"
            for body in [{'delivery_mode': opposite}, {'candidate_access': marker},
                         {'delivery_mode': opposite, 'candidate_access': marker}]:
                self.assertEqual(self.client.patch(url, body, format='json').status_code, 400)
                self.assertEqual(self.client.get(url).data['delivery_mode'], delivery)
            exam = Assessment.objects.get(pk=response.data['id'])
            exam.candidate_access = marker
            with self.assertRaises(ValidationError):
                exam.save()

    def test_account_eligibility_can_change_but_configuration_cannot_select_quick(self):
        response = self.create_exam('account_login')
        url = f"/api/v1/assessments/{response.data['id']}/"
        self.assertEqual(self.client.patch(url, {'candidate_access': 'specific_candidates', 'group': None}, format='json').status_code, 200)
        self.assertEqual(self.client.get(url).data['delivery_mode'], 'account_login')
        self.assertEqual(self.client.put(url + 'quick-access/', {'exam_code': 'ACCOUNT-BYPASS'}, format='json').status_code, 400)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            QuickExamConfiguration.objects.create(assessment_id=response.data['id'], exam_code='MODEL-BYPASS')
        self.assertFalse(QuickExamConfiguration.objects.filter(assessment_id=response.data['id']).exists())

    def test_quick_creation_assignment_and_configuration_do_not_issue_credentials(self):
        users = User.objects.count()
        response = self.create_exam('quick_exam')
        url = f"/api/v1/assessments/{response.data['id']}/"
        self.assertEqual(self.client.post(url + 'candidate-assignments/', {'candidates': [self.candidates[0].pk]}, format='json').status_code, 200)
        self.assertEqual(self.client.put(url + 'quick-access/', {'exam_code': 'CREATED-QUICK', 'enabled': True}, format='json').status_code, 201)
        self.assertFalse(QuickExamCredential.objects.exists())
        self.assertIsNone(self.candidates[0].user_id)
        self.assertEqual(User.objects.count(), users)
        sheet = self.client.post(url + 'quick-access/credentials/generate-sheet/', {'expected_count': 1}, format='json')
        self.assertEqual(len(self.rows(sheet)), 1)
        self.assertEqual(User.objects.count(), users)
        self.assertEqual(self.client.get(url).data['delivery_mode'], 'quick_exam')
        self.assertEqual(self.client.patch(url, {'delivery_mode': 'account_login'}, format='json').status_code, 400)

    def test_contradictory_creation_delivery_and_eligibility_rejected(self):
        before = Assessment.objects.count()
        self.assertEqual(self.create_exam('account_login', candidate_access='access_code').status_code, 400)
        self.assertEqual(self.create_exam('quick_exam', candidate_access='assigned_group').status_code, 400)
        self.assertEqual(self.create_exam('unsupported').status_code, 400)
        self.assertEqual(Assessment.objects.count(), before)

    def test_legacy_configured_specific_candidate_exam_keeps_quick_delivery(self):
        self.configure()
        # Represent a historical configured Quick exam without changing real records.
        Assessment.objects.filter(pk=self.exam.pk).update(candidate_access='specific_candidates')
        data = self.client.get(self.base).data
        self.assertEqual(data['delivery_mode'], 'quick_exam')
        self.assertEqual(data['eligibility_strategy'], 'specific_candidates')
        self.assertEqual(self.client.patch(self.base, {'delivery_mode': 'account_login'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(self.base + 'quick-access/', {'enabled': False}, format='json').status_code, 200)
        self.assertEqual(self.client.get(self.base).data['delivery_mode'], 'quick_exam')
