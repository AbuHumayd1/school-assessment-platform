"""Disposable fixtures only: explicit ownership, authority and shared revisions."""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch
from rest_framework.test import APITestCase

from accounts.models import User
from assessments.models import Assessment, AssessmentQuestion
from audit.models import AuditEvent
from institutions.models import Institution
from subjects.models import Subject
from tenants.models import InstitutionMembership
from .models import Question, QuestionOption, QuestionMedia, Topic
from .revisions import create_question_revision


class PlatformLibraryTests(APITestCase):
    def setUp(self):
        self.platform = User.objects.create_superuser('library-platform@example.test', 'safe password')
        self.school = Institution.objects.create(name='Library institution A')
        self.other = Institution.objects.create(name='Library institution B')
        self.subject = Subject.objects.create(institution=self.school, name='Institution subject', code='SAME')
        self.foreign = Subject.objects.create(institution=self.other, name='Foreign subject', code='SAME')
        self.library = Subject.objects.create(owner_scope='platform', name='Platform subject', code='SAME')
        self.topic = Topic.objects.create(owner_scope='platform', subject=self.library, name='Library topic')
        self.client.force_authenticate(self.platform)
        self.base = '/api/v1/platform/library/'

    def payload(self, **changes):
        data = dict(subject=self.library.pk, topic=self.topic.pk, question_type='multiple_choice',
                    text='Original platform question', options=[dict(text='Correct', order=1, is_correct=True),
                    dict(text='Wrong', order=2, is_correct=False)])
        return dict(data, **changes)

    def create(self):
        response = self.client.post(self.base + 'questions/', self.payload(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return Question.objects.get(pk=response.data['id'])

    def approve(self, question):
        for action in ('submit-for-review', 'approve'):
            response = self.client.post(f'{self.base}questions/{question.pk}/{action}/', {}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
        question.refresh_from_db()

    def test_platform_admin_with_selected_workspace_creates_platform_content(self):
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))
        question = self.create()
        self.assertEqual(question.owner_scope, 'platform')
        self.assertIsNone(question.institution_id)
        self.assertEqual(question.created_by, self.platform)
        self.assertFalse(self.platform.institution_memberships.exists())
        event = AuditEvent.objects.get(resource_id=str(question.pk), resource_type='questions.question')
        self.assertIsNone(event.institution_id)
        self.assertEqual(event.metadata['content_scope'], 'platform')

    def test_platform_subject_and_topic_create_update_deactivate(self):
        created = self.client.post(self.base + 'subjects/', dict(name='Disposable', code='NEW'), format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertIsNone(created.data['institution'])
        topic = self.client.post(self.base + 'topics/', dict(subject=created.data['id'], name='New topic'), format='json')
        self.assertEqual(topic.status_code, 201, topic.data)
        updated = self.client.patch(f"{self.base}subjects/{created.data['id']}/", dict(name='Renamed', is_active=False), format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertFalse(updated.data['is_active'])
        self.assertEqual(self.client.patch(f"{self.base}topics/{topic.data['id']}/", dict(is_active=False), format='json').status_code, 200)

    def test_platform_subject_code_uniqueness_in_api_and_database(self):
        response = self.client.post(self.base + 'subjects/', dict(name='Duplicate', code='SAME'), format='json')
        self.assertEqual(response.status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subject.objects.create(owner_scope='platform', name='Duplicate', code='SAME')

    def test_subject_update_duplicate_code_returns_validation(self):
        other = Subject.objects.create(owner_scope='platform', name='Other', code='OTHER')
        response = self.client.patch(f'{self.base}subjects/{other.pk}/', dict(code='SAME'), format='json')
        self.assertEqual(response.status_code, 400)

    def test_roles_and_staff_alone_cannot_manage_library(self):
        for role in ('institution_admin', 'teacher', 'examiner', 'student'):
            user = User.objects.create_user(f'library-{role}@example.test', 'safe password')
            InstitutionMembership.objects.create(user=user, institution=self.school, role=role)
            self.client.force_authenticate(user)
            for resource in ('subjects', 'topics', 'questions'):
                with self.subTest(role=role, resource=resource):
                    self.assertEqual(self.client.get(self.base + resource + '/').status_code, 403)
                    self.assertEqual(self.client.post(self.base + resource + '/', self.payload(), format='json').status_code, 403)
        staff = User.objects.create_user('library-staff@example.test', 'safe password', is_staff=True)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get(self.base + 'questions/').status_code, 403)

    def test_membership_platform_admin_uses_existing_authority(self):
        user = User.objects.create_user('library-member-platform@example.test', 'safe password')
        InstitutionMembership.objects.create(user=user, institution=self.school, role='platform_admin')
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(self.base + 'subjects/').status_code, 200)
        self.create()

    def test_platform_endpoints_exclude_institution_records(self):
        for resource, pk in [('subjects', self.subject.pk)]:
            response = self.client.get(self.base + resource + '/')
            self.assertEqual([row['id'] for row in response.data['results']], [self.library.pk])
            self.assertEqual(self.client.get(f'{self.base}{resource}/{pk}/').status_code, 404)

    def test_platform_relationships_reject_institution_subjects_topics(self):
        institution_topic = Topic.objects.create(institution=self.school, subject=self.subject, name='Own topic')
        for changes in (dict(subject=self.subject.pk), dict(topic=institution_topic.pk)):
            self.assertEqual(self.client.post(self.base + 'questions/', self.payload(**changes), format='json').status_code, 400)
        self.assertEqual(self.client.post(self.base + 'topics/', dict(subject=self.subject.pk, name='Wrong'), format='json').status_code, 400)

    def test_ownership_fields_cannot_be_supplied_to_platform_api(self):
        for changes in (dict(owner_scope='institution'), dict(institution=self.school.pk), dict(institution=None)):
            self.assertEqual(self.client.post(self.base + 'questions/', self.payload(**changes), format='json').status_code, 400)
        self.assertEqual(self.client.post(self.base + 'subjects/', dict(name='Wrong', code='WRONG', institution=None), format='json').status_code, 400)

    def test_platform_workflow_revision_preserves_old_options_and_content(self):
        question = self.create()
        self.approve(question)
        self.assertTrue(question.content_locked)
        original = (question.pk, question.text, list(question.options.values_list('pk', 'text', 'is_correct')))
        self.assertEqual(self.client.patch(f'{self.base}questions/{question.pk}/', dict(text='Forbidden'), format='json').status_code, 400)
        response = self.client.post(f'{self.base}questions/{question.pk}/new-revision/', {}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        revision = Question.objects.get(pk=response.data['id'])
        self.assertEqual((revision.owner_scope, revision.institution_id, revision.revision_family, revision.revision_number, revision.status),
                         ('platform', None, question.revision_family, 2, 'draft'))
        self.assertEqual(self.client.patch(f'{self.base}questions/{revision.pk}/', dict(text='Revised text'), format='json').status_code, 200)
        self.approve(revision)
        question.refresh_from_db()
        self.assertEqual((question.pk, question.text, list(question.options.values_list('pk', 'text', 'is_correct'))), original)
        self.assertEqual(question.status, 'approved')
        self.assertTrue(question.content_locked)
        self.assertFalse(question.available_for_new_assessments)
        with self.assertRaises(ValidationError):
            question.options.update(text='Forbidden')

    def test_revision_creation_requires_correct_owner_and_authority(self):
        question = self.create()
        self.approve(question)
        from rest_framework.exceptions import NotFound, PermissionDenied
        with self.assertRaises(NotFound):
            create_question_revision(question.pk, actor=self.platform, institution=self.school)
        user = User.objects.create_user('library-ordinary@example.test')
        with self.assertRaises(PermissionDenied):
            create_question_revision(question.pk, actor=user, institution=None)

    def test_platform_question_cannot_attach_to_institution_exam(self):
        question = self.create()
        self.approve(question)
        exam = Assessment.objects.create(institution=self.school, subject=self.subject, created_by=self.platform,
                                         title='Disposable', assessment_type='test', duration_minutes=15)
        with self.assertRaises(ValidationError):
            AssessmentQuestion.objects.create(assessment=exam, question=question, order=1, marks=1)

    def test_institution_bank_excludes_platform_and_other_institutions(self):
        platform_question = self.create()
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))
        response = self.client.post('/api/v1/questions/', self.payload(subject=self.subject.pk, topic=None), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        own = response.data['id']
        self.assertEqual(Question.objects.get(pk=own).owner_scope, 'institution')
        for path in ('subjects', 'topics', 'questions'):
            data = self.client.get(f'/api/v1/{path}/').data
            rows = data['results'] if isinstance(data, dict) else data
            self.assertTrue(all(row['institution'] == self.school.pk for row in rows))
        self.assertEqual(self.client.get(f'/api/v1/questions/{platform_question.pk}/').status_code, 404)
        data = self.client.get('/api/v1/questions/').data
        rows = data['results'] if isinstance(data, dict) else data
        self.assertEqual([row['id'] for row in rows], [own])

    def test_multiple_institution_banks_require_explicit_selection(self):
        user = User.objects.create_user('library-multi-workspace@example.test')
        for school in (self.school, self.other):
            InstitutionMembership.objects.create(user=user, institution=school, role='teacher')
        self.client.force_authenticate(user)
        for resource in ('subjects', 'topics', 'questions'):
            self.assertEqual(self.client.get(f'/api/v1/{resource}/').status_code, 400)
            response = self.client.get(f'/api/v1/{resource}/', HTTP_X_INSTITUTION_ID=str(self.school.pk))
            self.assertEqual(response.status_code, 200, response.data)
            rows = response.data['results'] if isinstance(response.data, dict) else response.data
            self.assertTrue(all(row['institution'] == self.school.pk for row in rows))

    def test_institution_create_rejects_platform_scope_null_and_relationships(self):
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))
        for changes in (dict(owner_scope='platform', subject=self.subject.pk, topic=None), dict(institution=None, subject=self.subject.pk, topic=None), dict(subject=self.library.pk), dict(subject=self.foreign.pk, topic=None)):
            self.assertEqual(self.client.post('/api/v1/questions/', self.payload(**changes), format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/v1/topics/', dict(subject=self.library.pk, name='Wrong'), format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/v1/subjects/', dict(institution=self.school.pk, name='Wrong', code='WRONG', owner_scope='platform'), format='json').status_code, 400)

    def test_invalid_owner_shapes_and_cross_owner_models_are_rejected(self):
        invalid = [Subject(name='Bad', code='BAD'), Subject(owner_scope='platform', institution=self.school, name='Bad', code='BAD'),
            Topic(owner_scope='platform', subject=self.subject, name='Bad'),
            Topic(institution=self.school, subject=self.library, name='Bad'),
            Topic(institution=self.school, subject=self.foreign, name='Bad'),
            Question(owner_scope='platform', subject=self.subject, created_by=self.platform, text='Bad', question_type='multiple_choice'),
            Question(institution=self.school, subject=self.library, created_by=self.platform, text='Bad', question_type='multiple_choice'),
            Question(institution=self.school, subject=self.foreign, created_by=self.platform, text='Bad', question_type='multiple_choice')]
        for row in invalid:
            with self.subTest(model=type(row).__name__, scope=row.owner_scope), self.assertRaises(ValidationError):
                row.save()

    def test_cross_subject_platform_topic_and_parent_are_rejected(self):
        other = Subject.objects.create(owner_scope='platform', name='Second', code='SECOND')
        topic = Topic.objects.create(owner_scope='platform', subject=other, name='Second')
        self.assertEqual(self.client.post(self.base + 'questions/', self.payload(topic=topic.pk), format='json').status_code, 400)
        with self.assertRaises(ValidationError):
            Topic.objects.create(owner_scope='platform', subject=self.library, parent=topic, name='Wrong parent')

    def test_unsaved_related_object_cannot_fabricate_platform_ownership(self):
        forged = Subject(pk=self.subject.pk, owner_scope='platform', name='Forged', code='FORGED')
        with self.assertRaises(ValidationError):
            Question.objects.create(owner_scope='platform', subject=forged, created_by=self.platform,
                                    text='Cannot borrow client content', question_type='multiple_choice')

    def test_ownership_transfer_rejected_for_instance_queryset_bulk_writes(self):
        question = self.create()
        for row in (self.library, self.topic, question):
            row.owner_scope = 'institution'
            row.institution = self.school
            with self.subTest(model=type(row).__name__), self.assertRaises(ValidationError):
                row.save()
            row.refresh_from_db()
            with self.assertRaises(ValidationError):
                type(row).objects.filter(pk=row.pk).update(owner_scope='institution', institution=self.school)
        self.subject.institution = self.other
        with self.assertRaises(ValidationError):
            Subject.objects.bulk_update([self.subject], ['institution'])

    def test_platform_import_is_not_exposed(self):
        # The detail URL recognizes this string as a pk; POST is unsupported.
        self.assertEqual(self.client.post(self.base + 'questions/import/', {}, format='json').status_code, 405)
        from .platform_library import PlatformQuestionViewSet
        self.assertNotIn('import_csv', [action.__name__ for action in PlatformQuestionViewSet.get_extra_actions()])

    def test_institution_csv_import_rejects_ownership_column(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))
        content = b'question_text,question_type,difficulty,marks,subject_code,options,correct_options,owner_scope\nBad,multiple_choice,medium,1,SAME,"[""A"",""B""]","[1]",platform\n'
        response = self.client.post('/api/v1/questions/import/', {'file': SimpleUploadedFile('ownership.csv', content, content_type='text/csv')}, format='multipart')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Question.objects.exists())

    def test_import_service_does_not_infer_platform_from_null_institution(self):
        from .import_service import import_questions_csv
        from rest_framework.exceptions import ValidationError as APIValidationError
        with self.assertRaises(APIValidationError):
            import_questions_csv(None, institution=None, actor=self.platform)
        self.assertFalse(Question.objects.exists())

    def test_database_owner_shape_constraints_reject_bypassed_invalid_writes(self):
        from django.db.models import QuerySet
        question = self.create()
        for row in (self.library, self.topic, question):
            # Base QuerySet deliberately bypasses application guards in this negative test.
            with self.subTest(model=type(row).__name__), self.assertRaises(IntegrityError), transaction.atomic():
                QuerySet(model=type(row), using='default').filter(pk=row.pk).update(institution_id=self.school.pk)

    def test_topic_with_questions_cannot_move_to_another_subject(self):
        self.create()
        other = Subject.objects.create(owner_scope='platform', name='Other subject', code='OTHER')
        self.topic.subject = other
        with self.assertRaises(ValidationError):
            self.topic.save()

    def test_platform_workflow_request_changes_and_archive_keep_lock(self):
        question = self.create()
        path = f'{self.base}questions/{question.pk}/'
        self.assertEqual(self.client.post(path + 'submit-for-review/', {}, format='json').status_code, 200)
        self.assertEqual(self.client.post(path + 'request-changes/', {}, format='json').status_code, 200)
        self.approve(question)
        self.assertEqual(self.client.post(path + 'archive/', {}, format='json').status_code, 200)
        question.refresh_from_db()
        self.assertTrue(question.content_locked)
        self.assertEqual(question.status, 'archived')
        self.assertFalse(question.available_for_new_assessments)

    def test_former_platform_creator_does_not_invalidate_locked_history(self):
        question = self.create()
        self.approve(question)
        self.platform.is_superuser = False
        self.platform.save(update_fields=['is_superuser'])
        successor = User.objects.create_superuser('library-successor@example.test', 'safe password')
        self.client.force_authenticate(successor)
        response = self.client.post(f'{self.base}questions/{question.pk}/archive/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        question.refresh_from_db()
        self.assertEqual(question.created_by_id, self.platform.pk)
        self.assertEqual(question.reviewed_by_id, self.platform.pk)
        self.assertTrue(question.content_locked)

    def test_subject_topic_api_reject_ownership_updates(self):
        for resource, row in (('subjects', self.library), ('topics', self.topic)):
            response = self.client.patch(f'{self.base}{resource}/{row.pk}/', {'owner_scope': 'institution'}, format='json')
            self.assertEqual(response.status_code, 400)

    def test_institution_admin_form_rejects_transfer_as_validation(self):
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().get('/admin/subjects/subject/')
        request.user = self.platform
        form_class = admin.site._registry[Subject].get_form(request, self.subject)
        self.assertNotIn('owner_scope', form_class.base_fields)
        form = form_class(data={'institution': self.other.pk, 'name': self.subject.name,
                              'code': self.subject.code, 'description': '', 'is_active': True}, instance=self.subject)
        self.assertFalse(form.is_valid())
        self.assertIn('Content ownership cannot be transferred.', str(form.non_field_errors()))

    def test_platform_media_uses_private_authority_and_revision_guards(self):
        from .test_revision_integrity import close_factory_response
        from .docx_views import QuestionMediaView
        from rest_framework.test import APIRequestFactory, force_authenticate
        with TemporaryDirectory() as directory, patch.object(QuestionMedia._meta.get_field('file'), 'storage', FileSystemStorage(location=directory)):
            question = self.create()
            media = QuestionMedia(question=question, parsed_id='image', source_metadata={'status': 'converted'})
            media.file.save('image.dat', ContentFile(b'test image'), save=False)
            media.save()
            self.approve(question)
            request = APIRequestFactory().get('/media/')
            force_authenticate(request, self.platform)
            response = QuestionMediaView.as_view()(request, media_id=media.pk)
            self.assertEqual(response.status_code, 200)
            close_factory_response(response)
            user = User.objects.create_user('library-media-user@example.test')
            request = APIRequestFactory().get('/media/')
            force_authenticate(request, user)
            self.assertEqual(QuestionMediaView.as_view()(request, media_id=media.pk).status_code, 404)
            with self.assertRaises(ValidationError):
                QuestionMedia.objects.filter(pk=media.pk).update(caption='Forbidden')
            with self.assertRaises(ValidationError):
                media.delete()
            revision = create_question_revision(question.pk, actor=self.platform, institution=None)
            copied = revision.media.get()
            self.assertNotEqual(copied.file.name, media.file.name)
            self.assertEqual(copied.source_metadata, media.source_metadata)
            copied.caption = 'Editable revision'
            copied.save()
            media.refresh_from_db()
            self.assertEqual(media.caption, '')


class OwnershipMigrationTests(TransactionTestCase):
    def test_existing_rows_keep_owners_ids_revisions_and_exam_pins(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        before = [('questions', '0004_question_revision_identity'), ('subjects', '0001_initial')]
        try:
            executor.migrate(before)
            apps = MigrationExecutor(connection)._create_project_state(with_applied_migrations=True).apps
            school = apps.get_model('institutions', 'Institution').objects.create(name='Ownership migration school', slug='ownership-migration')
            actor = apps.get_model('accounts', 'User').objects.create(email='ownership-migration@example.test', password='!')
            subject = apps.get_model('subjects', 'Subject').objects.create(institution=school, name='Kept', code='KEPT')
            topic = apps.get_model('questions', 'Topic').objects.create(institution=school, subject=subject, name='Kept')
            question = apps.get_model('questions', 'Question').objects.create(institution=school, subject=subject, topic=topic,
                created_by=actor, text='Preserved', question_type='multiple_choice', revision_number=1,
                status='approved', content_locked=True)
            family = question.revision_family
            exam = apps.get_model('assessments', 'Assessment').objects.create(institution=school, subject=subject,
                created_by=actor, title='Pinned', assessment_type='test', duration_minutes=15)
            pin = apps.get_model('assessments', 'AssessmentQuestion').objects.create(assessment=exam, question=question, order=1, marks=1)
            now = timezone.now()
            candidate = apps.get_model('candidates', 'Candidate').objects.create(institution=school,
                candidate_id='OWN-MIG', first_name='Disposable', last_name='Migration')
            attempt = apps.get_model('attempts', 'Attempt').objects.create(institution=school, assessment=exam,
                candidate=candidate, attempt_number=1, started_at=now, expires_at=now + timedelta(minutes=15), last_activity_at=now)
            historical = apps.get_model('attempts', 'AttemptQuestion').objects.create(attempt=attempt, question=question, order=1, marks_available=1)
            MigrationExecutor(connection).migrate(leaves)
            for model, pk in ((Subject, subject.pk), (Topic, topic.pk), (Question, question.pk)):
                row = model.objects.get(pk=pk)
                self.assertEqual((row.owner_scope, row.institution_id), ('institution', school.pk))
            question = Question.objects.get(pk=question.pk)
            self.assertEqual((question.revision_family, question.revision_number, question.text), (family, 1, 'Preserved'))
            self.assertTrue(question.content_locked)
            self.assertEqual(AssessmentQuestion.objects.get(pk=pin.pk).question_id, question.pk)
            from attempts.models import AttemptQuestion
            self.assertEqual(AttemptQuestion.objects.get(pk=historical.pk).question_id, question.pk)
            self.assertFalse(Question.objects.filter(owner_scope='platform').exists())
        finally:
            MigrationExecutor(connection).migrate(leaves)
