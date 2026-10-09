from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase
from accounts.models import User
from institutions.models import Institution
from tenants.models import InstitutionMembership
from .models import Subject

class SubjectTests(TestCase):
    def test_code_unique_per_institution(self):
        school = Institution.objects.create(name="School")
        other = Institution.objects.create(name="Other School")
        Subject.objects.create(institution=school, name="Math", code="MATH")
        Subject.objects.create(institution=other, name="Math", code="MATH")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subject.objects.create(institution=school, name="Duplicate", code="MATH")


class SubjectAPITests(APITestCase):
    def setUp(self):
        self.a = Institution.objects.create(name='Subject tenant A')
        self.b = Institution.objects.create(name='Subject tenant B')
        self.user = User.objects.create_user('subject-api@example.test', 'safe password')
        InstitutionMembership.objects.create(user=self.user, institution=self.a, role='teacher')
        self.client.force_authenticate(self.user)

    def test_creation_and_duplicate_code_return_normal_validation(self):
        fields = {'institution': self.a.pk, 'name': 'Test subject', 'code': 'CODE'}
        created = self.client.post('/api/v1/subjects/', fields, format='json')
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data['institution'], self.a.pk)
        duplicate = self.client.post('/api/v1/subjects/', fields, format='json')
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn('already exists', str(duplicate.data['code']))
        invalid = self.client.post('/api/v1/subjects/', {'institution': self.a.pk, 'name': '', 'code': ''}, format='json')
        self.assertEqual(invalid.status_code, 400)
        self.assertIn('name', invalid.data); self.assertIn('code', invalid.data)
        self.assertEqual(Subject.objects.count(), 1)

    def test_foreign_creation_and_nonstaff_access_remain_rejected(self):
        Subject.objects.create(institution=self.b, name='Private foreign subject', code='PRIVATE')
        denied = self.client.post('/api/v1/subjects/', {'institution': self.b.pk, 'name': 'Wrong tenant', 'code': 'WRONG'}, format='json')
        self.assertEqual(denied.status_code, 400)
        listed = self.client.get('/api/v1/subjects/')
        self.assertEqual(listed.data['results'] if isinstance(listed.data, dict) else listed.data, [])
        InstitutionMembership.objects.filter(user=self.user).update(role='student')
        self.assertEqual(self.client.post('/api/v1/subjects/', {'institution': self.a.pk, 'name': 'Denied', 'code': 'DENIED'}, format='json').status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post('/api/v1/subjects/', {'institution': self.a.pk, 'name': 'Denied', 'code': 'DENIED'}, format='json').status_code, 403)
        self.assertEqual(Subject.objects.count(), 1)

    def test_duplicate_scope_is_per_institution(self):
        Subject.objects.create(institution=self.b, name='Foreign same code', code='SHARED')
        created = self.client.post('/api/v1/subjects/', {'institution': self.a.pk, 'name': 'Own same code', 'code': 'SHARED'}, format='json')
        self.assertEqual(created.status_code, 201)
        self.assertEqual(Subject.objects.count(), 2)

    def test_institution_admin_bootstraps_subject_and_lists_it_in_selected_workspace(self):
        InstitutionMembership.objects.filter(user=self.user).update(role='institution_admin')
        response = self.client.post('/api/v1/subjects/', {'institution': self.a.pk, 'name': 'First subject', 'code': 'FIRST'}, format='json', HTTP_X_INSTITUTION_ID=str(self.a.pk))
        self.assertEqual(response.status_code, 201, response.data)
        listed = self.client.get('/api/v1/subjects/', HTTP_X_INSTITUTION_ID=str(self.a.pk))
        self.assertEqual(listed.status_code, 200)
        rows = listed.data['results'] if isinstance(listed.data, dict) else listed.data
        self.assertEqual([row['id'] for row in rows], [response.data['id']])
        options = self.client.get('/api/v1/assessments/form-options/', HTTP_X_INSTITUTION_ID=str(self.a.pk))
        self.assertEqual(options.status_code, 200, options.data)
        self.assertEqual([row['id'] for row in options.data['subjects']], [response.data['id']])
        self.assertEqual(self.client.get('/api/v1/subjects/', HTTP_X_INSTITUTION_ID=str(self.b.pk)).status_code, 404)

    def test_platform_authority_can_bootstrap_managed_client_subjects(self):
        InstitutionMembership.objects.filter(user=self.user).update(role='platform_admin')
        self.b.workspace_mode = Institution.WorkspaceMode.MANAGED_EXAM
        self.b.save(update_fields=['workspace_mode'])
        response = self.client.post('/api/v1/subjects/', {'institution': self.b.pk, 'name': 'Managed subject', 'code': 'MANAGED'}, format='json', HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(response.status_code, 201, response.data)
        listed = self.client.get('/api/v1/subjects/', HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(listed.status_code, 200)
        rows = listed.data['results'] if isinstance(listed.data, dict) else listed.data
        self.assertEqual([row['id'] for row in rows], [response.data['id']])
        mismatch = self.client.post('/api/v1/subjects/', {'institution': self.a.pk, 'name': 'Wrong workspace', 'code': 'WRONG'}, format='json', HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(Subject.objects.count(), 1)
