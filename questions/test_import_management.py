import copy
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APITestCase, APIClient

from . import test_docx as fixtures
from .test_answer_keys import csv_key, xlsx_key
from .docx_parser import parse_docx
from .models import DocxImportSession, Question, QuestionMedia


class EmbeddedRegressionTests(SimpleTestCase):
    def test_legacy_letter_terminating_period_remains_supported(self):
        d=parse_docx(fixtures.fixture(lines=['1.0 S','1. First','a. Alpha','b. Beta','KEY','1 B.']))[0]
        self.assertEqual(d['summary']['answers_matched'],1)

    def test_consolidated_section_headings_reference_existing_questions(self):
        lines=['SECTION: One','1. First','a. Alpha','b. Beta','SECTION: Two','1. Second','a. Alpha','b. Beta',
               'Answer Key','SECTION: One','Q1 - B','SECTION: Two','Question 1: A']
        data=parse_docx(fixtures.fixture(lines=lines))[0]
        self.assertEqual(len(data['sections']),2)
        self.assertEqual(data['summary']['questions_detected'],2)
        self.assertEqual(data['summary']['answers_matched'],2)
        self.assertEqual([s['questions'][0]['correct_answer'] for s in data['sections']],['B','A'])

    def test_generic_171_question_148_embedded_answer_distribution(self):
        lines=[]
        for section in range(9):
            lines.append(f'SECTION: Part {section}')
            for number in range(1,20):lines.extend([f'{number}. Prompt','a. Alpha','b. Beta'])
        lines.append('Answer Key')
        remaining=148
        for section in range(9):
            lines.append(f'SECTION: Part {section}')
            for number in range(1,min(19,remaining)+1):lines.append(f'{number} B')
            remaining=max(0,remaining-19)
        data=parse_docx(fixtures.fixture(lines=lines))[0]
        self.assertEqual((data['summary']['questions_detected'],data['summary']['answer_key_entries'],data['summary']['answers_matched'],data['summary']['answers_missing']),(171,148,148,23))

    def test_unknown_and_colliding_key_sections_do_not_cross_match(self):
        for title in ['SECTION: Same','SECTION: Unknown','Unknown section']:
            lines=['SECTION: Same','1. First','a. Alpha','b. Beta','SECTION: SAME','1. Second','a. Alpha','b. Beta','KEY',title,'1 B']
            data=parse_docx(fixtures.fixture(lines=lines))[0]
            self.assertEqual(data['summary']['answers_matched'],0)
            self.assertTrue(data['key_errors'])

    def test_embedded_table_is_parsed_not_question(self):
        table='<w:tbl><w:tr><w:tc>'+fixtures.paragraph('1')+'</w:tc><w:tc>'+fixtures.paragraph('B')+'</w:tc></w:tr></w:tbl>'
        data=parse_docx(fixtures.fixture(lines=['SECTION: One','1. First','a. Alpha','b. Beta','KEY'],extra=table))[0]
        self.assertEqual(data['summary']['questions_detected'],1)
        self.assertEqual(data['summary']['answers_matched'], 1)
        self.assertFalse(data['key_errors'])


class ImportManagementTests(APITestCase):
    setUp=fixtures.DocxWorkflowTests.setUp
    path=fixtures.DocxWorkflowTests.path
    edit=fixtures.DocxWorkflowTests.edit
    confirm=fixtures.DocxWorkflowTests.confirm

    def start(self,mode='embedded_key',embedded=True,image=False):
        lines=['SECTION: One','1. First','a. Alpha','b. Beta','2. Second','a. Alpha','b. Beta']
        if embedded:lines+=['KEY','1 B','2 A']
        r=self.client.post('/api/v1/questions/import/docx/preview/',{'file':fixtures.fixture(lines=lines,image=image),'import_mode':mode},format='multipart')
        self.assertEqual(r.status_code,201,r.data)
        return self.edit(r.data,metadata={'subject':self.subject.pk})

    def key(self,d,file=None):
        r=self.client.post(self.path(d)+'answer-key/',{'revision':str(d['revision']),'file':file or csv_key('number,answer\n1,B\n2,A\n')},format='multipart')
        self.assertEqual(r.status_code,200,r.data)
        return r.data

    def remove(self,d):return self.client.delete(self.path(d)+'answer-key/',{'revision':d['revision']},format='json')
    def delete(self,d):return self.client.delete(self.path(d),{'revision':d['revision']},format='json')
    def listing(self):return self.client.get('/api/v1/questions/import/docx/preview/').data['recent_imports']

    def test_embedded_mode_automaps_recovers_and_confirms_without_key(self):
        d=self.start()
        self.assertEqual(d['import_mode'],'embedded_key');self.assertTrue(d['confirmation']['eligible'])
        self.assertEqual(d['summary']['answers_matched'],2)
        self.assertEqual(self.client.get(self.path(d)).data,d)
        self.assertEqual(self.confirm(d).status_code,201)
        self.assertTrue(all(q.source_metadata['answer_source']=='embedded_key' for q in Question.objects.all()))

    def test_embedded_missing_answer_blocks_and_manual_fix_satisfies(self):
        d=self.start(embedded=False);self.assertFalse(d['confirmation']['eligible'])
        for q,answer in [('s1q1','B'),('s1q2','A')]:d=self.edit(d,question_id=q,changes={'correct_answer':answer})
        self.assertTrue(d['confirmation']['eligible']);self.assertEqual(self.confirm(d).status_code,201)
        self.assertTrue(all(q.source_metadata['answer_source']=='manual_review' for q in Question.objects.all()))

    def test_excluded_invalid_embedded_answer_does_not_require_an_answer(self):
        d=self.start()
        session=DocxImportSession.objects.get(pk=d['import_session_id'])
        session.preview['sections'][0]['questions'][0]['correct_answer']='Z'
        session.preview['sections'][0]['questions'][0]['key_issue']='Answer key refers to an unavailable option.'
        session.save(update_fields=['preview'])
        d=self.edit(d,question_id='s1q1',changes={'included':False})
        self.assertTrue(d['confirmation']['eligible'])

    def test_mode_invalid_or_changed_rejected_and_embedded_key_actions_rejected(self):
        r=self.client.post('/api/v1/questions/import/docx/preview/',{'file':fixtures.fixture(),'import_mode':'wrong'},format='multipart')
        self.assertEqual(r.status_code,400)
        d=self.start()
        for body in [{'revision':d['revision'],'import_mode':'separate_key'},{'revision':d['revision'],'metadata':{'import_mode':'separate_key'}}]:
            self.assertEqual(self.client.patch(self.path(d),body,format='json').status_code,400)
        self.assertEqual(self.remove(d).status_code,400)
        self.assertEqual(self.client.post(self.path(d)+'answer-key/',{'revision':str(d['revision']),'file':csv_key()},format='multipart').status_code,400)

    def test_separate_mode_persists_with_each_supported_key_format(self):
        for file in [csv_key('number,answer\n1,B\n2,A\n'),xlsx_key({'Key':[['Number','Answer'],['1','B'],['2','A']]}),fixtures.fixture(lines=['1 B','2 A'],name='key.docx')]:
            d=self.key(self.start('separate_key',embedded=False),file)
            self.assertEqual(d['import_mode'],'separate_key');self.assertTrue(d['confirmation']['eligible'])
            self.assertEqual(self.client.get(self.path(d)).data,d)

    def test_separate_mode_requires_matched_or_explicit_manual_answers(self):
        d=self.start('separate_key');self.assertFalse(d['confirmation']['eligible'])
        self.assertTrue(any(b['code']=='separate_answer_required' for b in d['confirmation']['blockers']))
        d=self.edit(d,question_id='s1q1',changes={'correct_answer':'B'})
        d=self.edit(d,question_id='s1q2',changes={'correct_answer':'A'})
        self.assertTrue(d['confirmation']['eligible'])

    def test_remove_restores_automatic_baseline_preserves_manual_and_recovers(self):
        d=self.key(self.start('separate_key',embedded=False))
        d=self.edit(d,question_id='s1q2',changes={'correct_answer':'B'})
        old=d['revision'];r=self.remove(d);self.assertEqual(r.status_code,200,r.data);d=r.data
        self.assertEqual(d['revision'],old+1);self.assertNotIn('separate_answer_key',d)
        self.assertIsNone(d['sections'][0]['questions'][0]['correct_answer'])
        self.assertEqual(d['sections'][0]['questions'][1]['correct_answer'],'B')
        self.assertFalse(d['confirmation']['eligible']);self.assertEqual(self.client.get(self.path(d)).data,d)
        self.assertEqual(Question.objects.count(),0)
        self.assertEqual(self.remove(d).status_code,400)

    def test_remove_preserves_embedded_baseline_and_reupload_recomputes(self):
        d=self.key(self.start('separate_key'))
        d=self.remove(d).data
        self.assertEqual([q['correct_answer'] for q in d['sections'][0]['questions']],['B','A'])
        self.assertFalse(d['confirmation']['eligible'])
        d=self.key(d);self.assertTrue(d['confirmation']['eligible'])

    def test_stale_removal_and_deletion_are_nonmutating(self):
        before=self.start('separate_key',embedded=False);current=self.key(before)
        state=copy.deepcopy(DocxImportSession.objects.get(pk=current['import_session_id']).preview)
        self.assertEqual(self.remove(before).status_code,400);self.assertEqual(self.delete(before).status_code,400)
        self.assertEqual(DocxImportSession.objects.get(pk=current['import_session_id']).preview,state)

    def test_delete_unfinished_session_key_media_listing_and_route(self):
        d=self.key(self.start('separate_key',embedded=False,image=True))
        media=QuestionMedia.objects.get(import_session_id=d['import_session_id']);name=media.file.name;storage=media.file.storage
        self.assertTrue(storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):r=self.delete(d)
        self.assertEqual(r.status_code,204)
        self.assertFalse(DocxImportSession.objects.filter(pk=d['import_session_id']).exists())
        self.assertFalse(QuestionMedia.objects.filter(pk=media.pk).exists());self.assertFalse(storage.exists(name))
        self.assertEqual(self.client.get(self.path(d)).status_code,404);self.assertEqual(self.listing(),[])
        self.assertEqual(Question.objects.count(),0)

    def test_completed_session_and_promoted_media_are_protected(self):
        d=self.start(image=True)
        d=self.edit(d,question_id='s1q1',changes={'reviewed':True})
        self.assertEqual(self.confirm(d).status_code,201)
        session=DocxImportSession.objects.get(pk=d['import_session_id']);before=(session.preview,session.metadata,session.revision)
        media=QuestionMedia.objects.get(question__isnull=False);name=media.file.name
        self.assertEqual(self.delete(d).status_code,400)
        session.refresh_from_db();self.assertEqual((session.preview,session.metadata,session.revision),before)
        self.assertEqual(Question.objects.count(),2);self.assertTrue(media.file.storage.exists(name));self.assertEqual(self.listing(),[])

    def test_shared_private_file_is_preserved_for_another_owner(self):
        d=self.start(image=True);asset=QuestionMedia.objects.get(import_session_id=d['import_session_id'])
        other=self.start()
        QuestionMedia.objects.create(import_session_id=other['import_session_id'],parsed_id='shared',file=asset.file.name)
        with self.captureOnCommitCallbacks(execute=True):self.assertEqual(self.delete(d).status_code,204)
        self.assertTrue(asset.file.storage.exists(asset.file.name))

    def test_wrong_uploader_anonymous_and_student_cannot_delete(self):
        d=self.start()
        for user in [self.other,None]:
            self.client.force_authenticate(user);self.assertIn(self.delete(d).status_code,[403,404])
        self.client.force_authenticate(self.user)
        from tenants.models import InstitutionMembership
        InstitutionMembership.objects.filter(user=self.user).update(role='student')
        self.assertEqual(self.delete(d).status_code,403)

    def test_cross_tenant_delete_denied(self):
        d=self.start()
        from tenants.models import InstitutionMembership
        InstitutionMembership.objects.create(institution=self.b,user=self.user,role='teacher')
        r=self.client.delete(self.path(d),{'revision':d['revision']},format='json',HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(r.status_code,404);self.assertTrue(DocxImportSession.objects.filter(pk=d['import_session_id']).exists())

    def test_real_session_csrf_required_for_both_delete_actions(self):
        d=self.key(self.start('separate_key',embedded=False));client=APIClient(enforce_csrf_checks=True);client.force_login(self.user)
        for path in [self.path(d),self.path(d)+'answer-key/']:
            self.assertEqual(client.delete(path,{'revision':d['revision']},format='json').status_code,403)

    def test_list_reports_mode_filename_counts_key_and_update_time(self):
        d=self.key(self.start('separate_key',embedded=False));item=self.listing()[0]
        self.assertEqual(item['import_mode'],'separate_key');self.assertEqual(item['status'],'unfinished')
        self.assertEqual(item['filename'],'fixture.docx');self.assertEqual(item['summary']['answers_matched'],2)
        self.assertEqual(item['answer_key_document']['filename'],'key.csv');self.assertEqual(item['revision'],d['revision'])
        self.assertEqual(item['subject_name'],self.subject.name);self.assertIn('updated_at',item)

    def test_legacy_active_key_removal_persists_separate_mode_without_history_backfill(self):
        d=self.key(self.start('separate_key',embedded=False))
        session=DocxImportSession.objects.get(pk=d['import_session_id'])
        session.metadata.pop('import_mode');session.save(update_fields=['metadata'])
        r=self.remove(d);self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(r.data['import_mode'],'separate_key')
        self.assertEqual(self.client.get(self.path(r.data)).data['import_mode'],'separate_key')

    def test_shared_private_file_is_preserved_for_confirmed_question(self):
        confirmed=self.start();self.assertEqual(self.confirm(confirmed).status_code,201)
        d=self.start(image=True);asset=QuestionMedia.objects.get(import_session_id=d['import_session_id'])
        QuestionMedia.objects.create(question=Question.objects.first(),parsed_id='confirmed-shared',file=asset.file.name)
        with self.captureOnCommitCallbacks(execute=True):self.assertEqual(self.delete(d).status_code,204)
        self.assertTrue(asset.file.storage.exists(asset.file.name))

    def test_audits_remove_delete_do_not_retain_answers(self):
        from audit.models import AuditEvent
        d=self.key(self.start('separate_key',embedded=False));d=self.remove(d).data;self.delete(d)
        events=list(AuditEvent.objects.filter(metadata__action__in=['answer_key_removed','docx_import_deleted']).values_list('metadata',flat=True))
        self.assertEqual(len(events),2)
        self.assertTrue(all(set(e)=={'action','revision'} for e in events))
