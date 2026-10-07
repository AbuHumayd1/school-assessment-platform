"""Revision and exam integrity regressions; all records are isolated test fixtures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from django.contrib.admin.sites import AdminSite
from django.core.signals import request_finished
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.test import APITestCase

from accounts.models import User
from assessments.models import Assessment, AssessmentCandidate, AssessmentQuestion
from assessments.eligibility import eligible_subject_questions
from attempts.models import Answer, AnswerSelection, Attempt, AttemptQuestion
from attempts.services import start_attempt
from audit.models import AuditEvent
from candidates.models import Candidate
from institutions.models import Institution
from results.services import mark_attempt
from subjects.models import Subject
from tenants.models import InstitutionMembership
from .admin import QuestionAdmin, QuestionOptionInline
from .docx_views import QuestionMediaView, QuickQuestionMediaView
from .models import Question, QuestionMedia, QuestionOption
from .revisions import create_question_revision


NOW = datetime(2026, 10, 7, 10, 45, tzinfo=datetime_timezone.utc)


def fixture():
    school = Institution.objects.create(name='Revision test school')
    subject = Subject.objects.create(institution=school, name='Revision subject', code='REV')
    actor = User.objects.create_user('revision-admin@example.test')
    InstitutionMembership.objects.create(user=actor, institution=school, role='institution_admin')
    question = Question.objects.create(institution=school, subject=subject, created_by=actor,
        text='Original immutable question', question_type='multiple_choice', explanation='Original explanation')
    QuestionOption.objects.bulk_create([
        QuestionOption(question=question, text='Correct original answer', is_correct=True, order=1),
        QuestionOption(question=question, text='Wrong original answer', is_correct=False, order=2)])
    return school, subject, actor, question


def approve(question):
    question.status = Question.Status.REVIEW
    question.save(update_fields=['status'])
    question.status = Question.Status.APPROVED
    question.save(update_fields=['status'])


def close_factory_response(response):
    # Match Django's test client: request_finished must not close the connection
    # owned by TestCase's outer transaction when a factory response is closed.
    request_finished.disconnect(close_old_connections)
    try:
        response.close()
    finally:
        request_finished.connect(close_old_connections)


class RevisionIntegrityTests(APITestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        field = QuestionMedia._meta.get_field('file')
        self.storage_patch = patch.object(field, 'storage', FileSystemStorage(location=self.temp.name))
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)
        self.school, self.subject, self.actor, self.question = fixture()
        self.media = QuestionMedia(question=self.question, parsed_id='image-1',
            source_metadata={'status': 'converted'}, alt_text='Original image')
        self.media.file.save('test.png', ContentFile(b'isolated test image'), save=False)
        self.media.save()
        approve(self.question)
        self.exam = Assessment.objects.create(institution=self.school, subject=self.subject, created_by=self.actor,
            title='Revision integrity exam', assessment_type='test', duration_minutes=15,
            candidate_access='specific_candidates', start_at=NOW-timedelta(hours=1), end_at=NOW+timedelta(hours=1))
        self.link = AssessmentQuestion.objects.create(assessment=self.exam, question=self.question, order=1, marks=1)
        self.users, self.candidates = [], []
        for number in (1, 2):
            user = User.objects.create_user(f'revision-student-{number}@example.test')
            InstitutionMembership.objects.create(user=user, institution=self.school, role='student')
            candidate = Candidate.objects.create(institution=self.school, user=user, candidate_id=f'REV-{number}',
                first_name='Synthetic', last_name=str(number))
            AssessmentCandidate.objects.create(assessment=self.exam, candidate=candidate, assigned_by=self.actor)
            self.users.append(user)
            self.candidates.append(candidate)
        self.exam.status = Assessment.Status.REVIEW
        self.exam.save(update_fields=['status'])
        self.exam.status = Assessment.Status.APPROVED
        self.exam.save(update_fields=['status'])
        self.client.force_authenticate(self.actor)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))

    def revision(self):
        return create_question_revision(self.question.pk, actor=self.actor, institution=self.school)

    def test_metadata_defaults_and_approval_lock(self):
        self.assertEqual(self.question.revision_number, 1)
        self.assertTrue(self.question.revision_family)
        self.assertTrue(self.question.content_locked)
        self.assertTrue(self.question.available_for_new_assessments)
        draft = self.revision()
        self.assertFalse(draft.content_locked)

    def test_all_content_fields_and_unlock_workflow_are_immutable(self):
        changes = {'text': 'Changed', 'explanation': 'Changed', 'marks': Decimal('2'),
            'source_metadata': {'changed': True}, 'question_type': 'multiple_select', 'content_locked': False,
            'status': 'draft', 'revision_number': 9}
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaises(ValidationError):
                row = Question.objects.get(pk=self.question.pk)
                setattr(row, field, value)
                row.save()
        self.assertEqual(self.client.patch(f'/api/v1/questions/{self.question.pk}/',
            {'text': 'API change'}, format='json').status_code, 403)

    def test_options_and_media_all_supported_orm_writes_are_guarded(self):
        option = self.question.options.first()
        for field, value in [('text', 'Changed'), ('is_correct', False), ('order', 3)]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                QuestionOption.objects.filter(pk=option.pk).update(**{field: value})
        with self.assertRaises(ValidationError):
            QuestionOption.objects.filter(question=self.question).delete()
        with self.assertRaises(ValidationError):
            QuestionOption.objects.bulk_create([QuestionOption(question=self.question, text='Third', order=3)])
        with self.assertRaises(ValidationError):
            QuestionMedia.objects.filter(pk=self.media.pk).update(alt_text='Changed')
        with self.assertRaises(ValidationError):
            self.media.delete()
        with self.assertRaises(ValidationError):
            self.question.delete()
        row = Question.objects.get(pk=self.question.pk)
        row.text = 'Bulk changed'
        with self.assertRaises(ValidationError):
            Question.objects.bulk_update([row], ['text'])
        self.assertEqual(self.question.options.count(), 2)
        self.assertEqual(QuestionMedia.objects.get(pk=self.media.pk).alt_text, 'Original image')
        self.assert_participated_draft_integrity()

    def assert_participated_draft_integrity(self):
        legacy, editable = self.revision(), self.revision()
        attempt = Attempt.objects.create(institution=self.school, assessment=self.exam,
            candidate=self.candidates[0], attempt_number=1, started_at=NOW,
            expires_at=NOW + timedelta(minutes=15), last_activity_at=NOW)
        AttemptQuestion.objects.create(attempt=attempt, question=legacy, order=1, marks_available=1)
        self.assertFalse(legacy.content_locked)
        self.assertEqual(legacy.status, 'draft')
        changes = {'institution_id': self.school.pk + 1000, 'subject_id': self.subject.pk + 1000,
            'topic_id': 999999, 'question_type': 'true_false', 'text': 'Changed',
            'explanation': 'Changed', 'difficulty': 'easy', 'marks': Decimal('2'),
            'source': 'Changed', 'source_metadata': {'changed': True}, 'source_year': 2000,
            'learning_objective': 'Changed', 'created_by_id': self.actor.pk + 1000,
            'reviewed_by_id': self.actor.pk, 'revision_family': uuid.uuid4(), 'revision_number': 99}
        for field, value in changes.items():
            for mode in ('save', 'update', 'bulk_update'):
                with self.subTest(legacy_question_field=field, mode=mode), self.assertRaises(ValidationError):
                    row = Question.objects.get(pk=legacy.pk)
                    setattr(row, field, value)
                    if mode == 'save':
                        row.save()
                    elif mode == 'update':
                        Question.objects.filter(pk=row.pk).update(**{field: value})
                    else:
                        Question.objects.bulk_update([row], [field])
        for model, fields in (
                (QuestionOption, {'text': 'Changed', 'is_correct': False, 'order': 99}),
                (QuestionMedia, {'alt_text': 'Changed', 'caption': 'Changed', 'file': 'changed.dat',
                    'parsed_id': 'changed', 'media_type': 'changed', 'order': 99,
                    'source_metadata': {'changed': True}})):
            original = model.objects.filter(question=legacy).first()
            for field, value in fields.items():
                for mode in ('save', 'update', 'bulk_update'):
                    with self.subTest(model=model.__name__, field=field, mode=mode), self.assertRaises(ValidationError):
                        row = model.objects.get(pk=original.pk)
                        setattr(row, field, value)
                        if mode == 'save':
                            row.save()
                        elif mode == 'update':
                            model.objects.filter(pk=row.pk).update(**{field: value})
                        else:
                            model.objects.bulk_update([row], [field])
            for source, target in ((legacy, editable), (editable, legacy)):
                child = model.objects.filter(question=source).first()
                with self.subTest(model=model.__name__, move_from=source.pk), self.assertRaises(ValidationError):
                    model.objects.filter(pk=child.pk).update(question=target)
            with self.assertRaises(ValidationError):
                original.delete()
            with self.assertRaises(ValidationError):
                model.objects.filter(question=legacy).delete()
            values = {'question': legacy}
            if model is QuestionOption:
                values.update(text='New option', order=99)
            else:
                values.update(parsed_id='new', file='new.dat')
            with self.assertRaises(ValidationError):
                model.objects.create(**values)
            with self.assertRaises(ValidationError):
                model.objects.bulk_create([model(**values)])
        with self.assertRaises(ValidationError):
            legacy.delete()
        with self.assertRaises(ValidationError):
            Question.objects.filter(pk=legacy.pk).delete()
        legacy.refresh_from_db()
        self.assertFalse(legacy.content_locked)
        self.assertEqual(legacy.text, 'Original immutable question')
        self.assertEqual(legacy.options.count(), 2)
        self.assertEqual(legacy.media.get().alt_text, 'Original image')

    def test_bulk_creation_serializes_lineage_and_rolls_back_invalid_batch(self):
        draft = self.revision()
        values = {key: getattr(draft, key) for key in Question.CONTENT_FIELDS}
        values.update(revision_family=draft.revision_family, status='draft')
        before = Question.objects.count()
        with self.assertRaises(ValidationError):
            Question.objects.bulk_create([
                Question(**values, revision_number=3),
                Question(**values, revision_number=5),
            ])
        self.assertEqual(Question.objects.count(), before)

    def test_stale_child_instances_cannot_delete_locked_rows(self):
        draft = self.revision()
        for row in (self.question.options.first(), self.media):
            with self.subTest(model=type(row).__name__):
                row.question = draft
                with self.assertRaises(ValidationError):
                    row.delete()
        self.link.assessment = Assessment.objects.create(institution=self.school,
            subject=self.subject, created_by=self.actor, title='Unused draft',
            assessment_type='test', duration_minutes=15)
        with self.assertRaises(ValidationError):
            self.link.delete()
        self.exam.status = 'draft'
        with self.assertRaises(ValidationError):
            self.exam.delete()

    def test_cascade_cannot_remove_frozen_assessment_attachments(self):
        # Institution deletion normally cascades to assessments. Their collector
        # must enforce the same boundary without calling Assessment.delete().
        from django.db.models.deletion import Collector
        collector = Collector(using='default')
        collector.collect([self.exam])
        # Collector uses atomic(savepoint=False), even for a pre_delete
        # ValidationError. Isolate that rejection from TestCase's transaction.
        with CaptureQueriesContext(connection) as queries, self.assertRaises(ValidationError), transaction.atomic():
            collector.delete()
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('DELETE', 'UPDATE', 'INSERT'))
            for query in queries.captured_queries))
        self.assertFalse(connection.needs_rollback)
        self.assertTrue(AssessmentQuestion.objects.filter(pk=self.link.pk).exists())

    def test_child_moves_and_bulk_attachments_use_model_guards(self):
        draft = self.revision()
        for row in (self.question.options.first(), self.media):
            with self.subTest(model=type(row).__name__), self.assertRaises(ValidationError):
                type(row).objects.filter(pk=row.pk).update(question=draft)
        with self.assertRaises(ValidationError):
            AssessmentQuestion.objects.bulk_create([AssessmentQuestion(
                assessment=self.exam, question=self.question, order=2, marks=1)])
        row = self.link
        row.marks = Decimal('2')
        with self.assertRaises(ValidationError):
            AssessmentQuestion.objects.bulk_update([row], ['marks'])

    def test_admin_is_readonly_and_prevents_child_edits(self):
        request = SimpleNamespace(user=self.actor)
        admin = QuestionAdmin(Question, AdminSite())
        self.assertIn('text', admin.get_readonly_fields(request, self.question))
        self.assertFalse(admin.has_delete_permission(request, self.question))
        inline = QuestionOptionInline(Question, AdminSite())
        self.assertFalse(inline.has_add_permission(request, self.question))
        self.assertFalse(inline.has_change_permission(request, self.question))
        self.assertFalse(inline.has_delete_permission(request, self.question))

    def test_new_revision_copies_content_and_separate_media_without_repointing(self):
        revision = self.revision()
        next_revision = self.revision()
        self.assertEqual((revision.revision_number, next_revision.revision_number), (2, 3))
        self.assertEqual(revision.revision_family, self.question.revision_family)
        self.assertEqual(revision.institution_id, self.school.pk)
        self.assertEqual(revision.status, 'draft')
        self.assertEqual(list(revision.options.values_list('text', 'is_correct', 'order')),
            list(self.question.options.values_list('text', 'is_correct', 'order')))
        copy = revision.media.get()
        self.assertNotEqual(copy.file.name, self.media.file.name)
        with copy.file.open('rb') as stream:
            self.assertEqual(stream.read(), b'isolated test image')
        revision.text = 'New independently editable text'
        revision.save()
        self.question.refresh_from_db()
        self.link.refresh_from_db()
        self.assertEqual(self.question.text, 'Original immutable question')
        self.assertEqual(self.link.question_id, self.question.pk)

    def test_revision_failure_rolls_back_question_options_media(self):
        before = (Question.objects.count(), QuestionOption.objects.count(), QuestionMedia.objects.count())
        with patch('questions.revisions.record_event', side_effect=RuntimeError('Synthetic failure')):
            with self.assertRaises(RuntimeError):
                self.revision()
        self.assertEqual(before, (Question.objects.count(), QuestionOption.objects.count(), QuestionMedia.objects.count()))

    def test_approval_order_does_not_supersede_a_higher_approved_revision(self):
        second, third = self.revision(), self.revision()
        approve(third)
        approve(second)
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertFalse(second.available_for_new_assessments)
        self.assertTrue(third.available_for_new_assessments)

    def test_superseded_revision_cannot_be_reenabled_even_after_successor_retirement(self):
        revision = self.revision()
        approve(revision)
        revision.status = 'archived'
        revision.save(update_fields=['status'])
        with self.assertRaises(ValidationError):
            Question.objects.filter(pk=self.question.pk).update(available_for_new_assessments=True)

    def test_mixed_bulk_update_rolls_back_editable_rows_when_locked_row_fails(self):
        draft = self.revision()
        draft.text = 'Must roll back'
        self.question.text = 'Forbidden locked edit'
        with self.assertRaises(ValidationError):
            Question.objects.bulk_update([draft, self.question], ['text'])
        draft.refresh_from_db()
        self.assertEqual(draft.text, 'Original immutable question')

    def test_reopened_nested_edit_preserves_retired_pin_and_ordering(self):
        revision = self.revision()
        approve(revision)
        self.question.refresh_from_db()
        self.question.status = 'archived'
        self.question.save(update_fields=['status'])
        response = self.client.post(f'/api/v1/assessments/{self.exam.pk}/reopen/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.patch(f'/api/v1/assessments/{self.exam.pk}/', {'questions': [
            {'question': revision.pk, 'order': 1, 'marks': '1.00'},
            {'question': self.question.pk, 'order': 2, 'marks': '2.00'}]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.link.refresh_from_db()
        self.assertEqual((self.link.question_id, self.link.order, self.link.marks),
            (self.question.pk, 2, Decimal('2')))
        new_exam = Assessment.objects.create(institution=self.school, subject=self.subject,
            created_by=self.actor, title='New synthetic exam', assessment_type='test', duration_minutes=15)
        with self.assertRaises(ValidationError):
            AssessmentQuestion.objects.create(assessment=new_exam, question=self.question, order=1, marks=1)

    def test_new_revision_endpoint_and_tenant_authority(self):
        response = self.client.post(f'/api/v1/questions/{self.question.pk}/new-revision/', {}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        other = Institution.objects.create(name='Foreign revision school')
        with self.assertRaises(PermissionDenied):
            create_question_revision(self.question.pk, actor=self.actor, institution=other)
        stranger = User.objects.create_superuser('revision-platform@example.test', None)
        with self.assertRaises(NotFound):
            create_question_revision(self.question.pk, actor=stranger, institution=other)
        self.school.workspace_mode = 'managed_exam'
        self.school.save(update_fields=['workspace_mode'])
        with self.assertRaises(PermissionDenied):
            self.revision()

    def test_approved_exam_attachment_and_configuration_mutations_are_blocked(self):
        for field, value in [('order', 2), ('marks', Decimal('3'))]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                AssessmentQuestion.objects.filter(pk=self.link.pk).update(**{field: value})
        with self.assertRaises(ValidationError):
            self.link.delete()
        new = self.revision()
        approve(new)
        with self.assertRaises(ValidationError):
            AssessmentQuestion.objects.create(assessment=self.exam, question=new, order=2, marks=1)
        with self.assertRaises(ValidationError):
            Assessment.objects.filter(pk=self.exam.pk).update(duration_minutes=60)

    def test_audited_reopen_allows_preparation_but_requires_reapproval(self):
        response = self.client.post(f'/api/v1/assessments/{self.exam.pk}/reopen/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(AuditEvent.objects.filter(resource_id=str(self.exam.pk), institution=self.school).exists())
        AssessmentQuestion.objects.filter(pk=self.link.pk).update(marks=Decimal('2'))
        with self.assertRaises(PermissionDenied):
            start_attempt(self.users[0], self.exam.pk, institution_id=self.school.pk, now=NOW)
        self.exam.refresh_from_db()
        self.exam.status = 'review'
        self.exam.save(update_fields=['status'])
        self.exam.status = 'approved'
        self.exam.save(update_fields=['status'])
        attempt, created = start_attempt(self.users[0], self.exam.pk, institution_id=self.school.pk, now=NOW)
        self.assertTrue(created)
        self.assertEqual(attempt.attempt_questions.get().marks_available, Decimal('2'))
        self.assertEqual(self.client.post(f'/api/v1/assessments/{self.exam.pk}/reopen/', {}, format='json').status_code, 400)
        with self.assertRaises(ValidationError):
            Assessment.objects.filter(pk=self.exam.pk).update(status='draft')

    def test_two_candidates_keep_original_revision_key_and_media_after_superseding(self):
        first, _ = start_attempt(self.users[0], self.exam.pk, institution_id=self.school.pk, now=NOW)
        revision = self.revision()
        revision.text = 'Revision two text'
        revision.save()
        revision.options.update(is_correct=False)
        revision.options.filter(order=2).update(is_correct=True)
        approve(revision)
        self.question.refresh_from_db()
        self.assertFalse(self.question.available_for_new_assessments)
        self.question.status = 'archived'
        self.question.save(update_fields=['status'])
        self.assertFalse(eligible_subject_questions(self.school, self.subject).filter(pk=self.question.pk).exists())
        second, _ = start_attempt(self.users[1], self.exam.pk, institution_id=self.school.pk, now=NOW)
        for attempt in (first, second):
            self.assertEqual(attempt.attempt_questions.get().question_id, self.question.pk)
            self.assertEqual(attempt.attempt_questions.get().question.text, 'Original immutable question')
        self.client.force_authenticate(self.users[1])
        with patch('questions.docx_views.timezone.now', return_value=NOW):
            from rest_framework.test import APIRequestFactory
            from rest_framework.test import force_authenticate
            request = APIRequestFactory().get('/media/')
            force_authenticate(request, user=self.users[1])
            response = QuestionMediaView.as_view()(request, media_id=self.media.pk)
            self.assertEqual(response.status_code, 200)
            close_factory_response(response)
            self.assertTrue(response.file_to_stream.closed)
            self.assertFalse(connection.closed_in_transaction)
            self.assertFalse(connection.needs_rollback)
            request = APIRequestFactory().get('/media/')
            force_authenticate(request, user=self.users[1])
            self.assertEqual(QuestionMediaView.as_view()(request, media_id=revision.media.get().pk).status_code, 404)
            # The Quick asset endpoint applies the same pinned-question/own-attempt rule.
            request = APIRequestFactory().get('/quick-media/')
            force_authenticate(request, user=self.users[1], token=SimpleNamespace(
                institution=self.school, assessment=self.exam, candidate=self.candidates[1]))
            response = QuickQuestionMediaView.as_view()(request, media_id=self.media.pk)
            self.assertEqual(response.status_code, 200)
            close_factory_response(response)
            self.assertTrue(response.file_to_stream.closed)
            self.assertFalse(connection.closed_in_transaction)
            self.assertFalse(connection.needs_rollback)
            request = APIRequestFactory().get('/quick-media/')
            force_authenticate(request, user=self.users[1], token=SimpleNamespace(
                institution=self.school, assessment=self.exam, candidate=self.candidates[1]))
            self.assertEqual(QuickQuestionMediaView.as_view()(request, media_id=revision.media.get().pk).status_code, 404)
        for attempt in (first, second):
            answer = Answer.objects.create(attempt=attempt, question=self.question, answered_at=NOW)
            AnswerSelection.objects.create(answer=answer, option=self.question.options.get(order=1))
            attempt.status = Attempt.Status.SUBMITTED
            attempt.submitted_at = NOW
            attempt.save(update_fields=['status', 'submitted_at'])
            with patch('results.services.timezone.now', return_value=NOW):
                self.assertEqual(mark_attempt(attempt.pk).marks_obtained, Decimal('1'))


class RevisionConcurrencyTests(TransactionTestCase):
    def test_concurrent_revision_numbers_serialize_on_family_root(self):
        school, subject, actor, question = fixture()
        approve(question)

        def create(_):
            close_old_connections()
            try:
                return create_question_revision(question.pk, actor=User.objects.get(pk=actor.pk),
                    institution=Institution.objects.get(pk=school.pk)).revision_number
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(create, range(2))), [2, 3])


class RevisionMigrationTests(TransactionTestCase):
    def test_existing_questions_gain_independent_identity_without_content_changes(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        before = ('questions', '0003_alter_questionmedia_import_session_and_more')
        try:
            executor.migrate([before])
            apps = MigrationExecutor(connection)._create_project_state(with_applied_migrations=True).apps
            # Use the pre-revision historical schema rather than runtime model guards.
            OldInstitution = apps.get_model('institutions', 'Institution')
            OldUser = apps.get_model('accounts', 'User')
            OldSubject = apps.get_model('subjects', 'Subject')
            OldQuestion = apps.get_model('questions', 'Question')
            OldOption = apps.get_model('questions', 'QuestionOption')
            school = OldInstitution.objects.create(name='Migration revision school', slug='migration-revision')
            user = OldUser.objects.create(email='migration-revision@example.test', password='!')
            subject = OldSubject.objects.create(institution=school, name='Migration subject', code='REV')
            rows = [OldQuestion.objects.create(institution=school, subject=subject, created_by=user,
                text='Same text, independent families', question_type='multiple_choice', status=status)
                for status in ('approved', 'draft')]
            option = OldOption.objects.create(question=rows[0], text='Preserved option', order=1, is_correct=True)
            exam = apps.get_model('assessments', 'Assessment').objects.create(institution=school, subject=subject,
                created_by=user, title='Migration pinned exam', assessment_type='test', duration_minutes=15)
            attachment = apps.get_model('assessments', 'AssessmentQuestion').objects.create(
                assessment=exam, question=rows[0], order=1, marks=1)
            candidate = apps.get_model('candidates', 'Candidate').objects.create(institution=school,
                candidate_id='MIG-REV', first_name='Migration', last_name='Candidate')
            attempt = apps.get_model('attempts', 'Attempt').objects.create(institution=school,
                assessment=exam, candidate=candidate, attempt_number=1, started_at=NOW,
                expires_at=NOW + timedelta(minutes=15), last_activity_at=NOW)
            historical_pin = apps.get_model('attempts', 'AttemptQuestion').objects.create(
                attempt=attempt, question=rows[0], order=1, marks_available=1)
            executor = MigrationExecutor(connection)
            executor.migrate(leaves)
            current = list(Question.objects.filter(pk__in=[row.pk for row in rows]).order_by('pk'))
            self.assertEqual([row.pk for row in current], [row.pk for row in rows])
            self.assertEqual(len({row.revision_family for row in current}), 2)
            self.assertTrue(all(row.revision_number == 1 for row in current))
            self.assertEqual([row.content_locked for row in current], [True, False])
            self.assertTrue(all(row.text == 'Same text, independent families' and row.institution_id == school.pk for row in current))
            self.assertEqual(QuestionOption.objects.get(pk=option.pk).question_id, rows[0].pk)
            self.assertEqual(AssessmentQuestion.objects.get(pk=attachment.pk).question_id, rows[0].pk)
            self.assertEqual(Attempt.objects.get(pk=attempt.pk).attempt_questions.get(pk=historical_pin.pk).question_id, rows[0].pk)
        finally:
            MigrationExecutor(connection).migrate(leaves)
