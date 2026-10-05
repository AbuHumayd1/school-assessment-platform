import copy
import io
import zipfile
from xml.etree import ElementTree as ET

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase, APIClient

from . import test_docx as fixtures
from .answer_keys import parse_answer_key, recompute_matches, replace_key, remove_key
from .docx_parser import parse_docx, validate_preview
from .import_reconciliation import classify_block, diagnostics, template_bytes
from .models import Question, DocxImportSession
from .test_answer_keys import csv_key, xlsx_key, question_document


def twenty(heading='Correct Answers'):
    lines=['SECTION: General']
    for n in range(1,21): lines += [f'{n}. Prompt {n}', 'a. Alpha', 'b. Beta']
    return lines + [heading] + [f'{n}. B' for n in range(1,21)]


class ReconciliationTests(SimpleTestCase):
    def test_real_failure_shape_generic_heading_is_twenty_not_forty(self):
        for heading in ['ANSWER KEYS','Answer Keys.',' ANSWER   KEYS ','Answers','ANSWERS','ANSWER KEY','KEY','KEY ANSWERS','ANSWERS KEY','CORRECT ANSWERS','MARKING KEY','Correct Answers: General','Answer Key:']:
            with self.subTest(heading=heading):
                d=parse_docx(fixtures.fixture(lines=twenty(heading)))[0]
                self.assertEqual((d['summary']['questions_detected'],d['summary']['answers_matched']), (20,20))
                self.assertEqual(d['embedded_answer_key']['summary']['matched_count'],20)

    def test_middle_dot_answer_entries_auto_classify_and_reconcile(self):
        lines=twenty('ANSWER KEYS')[:-20]+[f'Q{n} \u00b7 B' for n in range(1,21)]
        d=parse_docx(fixtures.fixture(lines=lines))[0]
        self.assertEqual(d['summary']['questions_detected'],20)
        self.assertEqual(len(d['embedded_answer_key']['entries']),20)
        self.assertEqual(d['summary']['ready_count'],20)
        self.assertEqual(d['summary']['answers_missing'],0)

    def test_answer_word_in_question_section_is_not_a_key(self):
        d=parse_docx(fixtures.fixture(lines=['SECTION: Answer the following','1. Which answer is correct?','a. Alpha','b. Beta']))[0]
        self.assertEqual(d['summary']['questions_detected'],1)
        self.assertEqual(d['embedded_answer_key']['entries'],[])

    def test_empty_saved_entries_and_middle_dot_recovery(self):
        d=parse_docx(fixtures.fixture(lines=twenty('Unrecognized source heading')))[0]
        b=next(b for b in d['blocks'] if b['uncertain'])
        b['entries']=[]
        for q in b['section']['questions']: q['text']='\u00b7 B'
        d=validate_preview(classify_block(d,b['id'],'answer_key',2))
        self.assertEqual(len(d['embedded_answer_key']['entries']),20)
        self.assertEqual(d['summary']['ready_count'],20)
        self.assertEqual(d['summary']['answers_missing'],0)
        self.assertTrue(all(e['resolution_source']=='automatic' for e in d['embedded_answer_key']['entries']))
        d=validate_preview(classify_block(d,b['id'],'questions',3))
        self.assertEqual(d['summary']['questions_detected'],40)
        self.assertEqual(d['embedded_answer_key']['entries'],[])
        self.assertEqual(d['summary']['answers_matched'],0)
        d=validate_preview(classify_block(d,b['id'],'answer_key',4))
        d=validate_preview(classify_block(d,b['id'],'ignore',5))
        self.assertEqual(d['summary']['questions_detected'],20)
        self.assertEqual(d['summary']['answers_missing'],20)

    def test_unknown_numbered_run_can_be_classified_and_restored(self):
        d=parse_docx(fixtures.fixture(lines=twenty('Unrecognized source heading')))[0]
        self.assertEqual(d['summary']['questions_detected'],40)
        block=next(b for b in d['blocks'] if b['uncertain'])
        original_ids=[q['id'] for s in d['sections'] for q in s['questions']]
        d=validate_preview(classify_block(d,block['id'],'answer_key',2))
        self.assertEqual((d['summary']['questions_detected'],d['summary']['answers_matched']), (20,20))
        self.assertEqual(d['blocks'][-1]['classification'],'answer_key')
        with override_settings(DOCX_IMPORT_LIMITS={'questions':20}):
            with self.assertRaises(ValidationError):
                classify_block(copy.deepcopy(d),block['id'],'questions',3)
        d=validate_preview(classify_block(d,block['id'],'ignore',3))
        self.assertEqual(d['summary']['questions_detected'],20)
        self.assertEqual(d['summary']['answers_missing'],20)
        d=validate_preview(classify_block(d,block['id'],'questions',4))
        self.assertEqual([q['id'] for s in d['sections'] for q in s['questions']],original_ids)

    def test_unknown_heading_common_answer_lines_have_a_reviewable_block(self):
        for line in ['1 B','Q1 - B','Question 1: B','1: B']:
            d=parse_docx(fixtures.fixture(lines=['SECTION: One','1. Prompt','a. Alpha','b. Beta','Unknown block',line]))[0]
            block=next(b for b in d['blocks'] if b['uncertain'])
            d=validate_preview(classify_block(d,block['id'],'answer_key',2))
            self.assertEqual((d['summary']['questions_detected'],d['summary']['answers_matched']),(1,1))

    def test_ignore_identified_embedded_block_removes_its_assignments(self):
        d=parse_docx(fixtures.fixture(lines=twenty()))[0]
        b=next(b for b in d['blocks'] if b['classification']=='answer_key')
        d=validate_preview(classify_block(d,b['id'],'ignore',2))
        self.assertEqual(d['summary']['answers_matched'],0)
        d=validate_preview(classify_block(d,b['id'],'answer_key',3))
        self.assertEqual(d['summary']['answers_matched'],20)

    def test_embedded_link_decision_survives_block_ignore_and_restore(self):
        d=parse_docx(fixtures.fixture(lines=['SECTION: One','1. Prompt','a. Alpha','b. Beta','KEY','Unknown','1 B']))[0]
        key=d['embedded_answer_key'];key['entries'][0]['linked_question_id']='s1q1';recompute_matches(d,2)
        self.assertEqual(d['sections'][0]['questions'][0]['answer_source'],'manual_link')
        b=next(b for b in d['blocks'] if b['classification']=='answer_key')
        classify_block(d,b['id'],'ignore',3);classify_block(d,b['id'],'answer_key',4)
        self.assertEqual(d['embedded_answer_key']['entries'][0]['linked_question_id'],'s1q1')
        self.assertEqual(d['embedded_answer_key']['entries'][0]['status'],'matched')

    def test_missing_answer_requires_review_even_if_reviewed(self):
        d=question_document();q=d['sections'][0]['questions'][0];q['reviewed']=True
        validate_preview(d)
        self.assertEqual(q['readiness'],'needs_review');self.assertIn('Missing answer',q['warnings'])
        self.assertEqual(q['errors'],[])

    def test_malformed_question_is_still_error(self):
        d=question_document();q=d['sections'][0]['questions'][0];q['options']=[]
        validate_preview(d);self.assertEqual(q['readiness'],'error')

    def test_diagnostics_explain_each_safe_rule_and_rejection(self):
        d=question_document([('SECTION: One',[1]),('SECTION: Two',[1])])
        replace_key(d,parse_answer_key(csv_key('section,number,answer\n,1,B\nUnknown,1,B\nOne,9,B\nOne,1,Z\n')),2)
        reasons=[e['reason'] for e in diagnostics(d)['entries']]
        self.assertEqual(reasons,['section_missing_and_number_not_global_unique','section_title_not_found','question_number_not_found','invalid_answer_label'])
        self.assertTrue(all(e['rules_considered'] for e in diagnostics(d)['entries']))
        self.assertTrue(all('option_labels' in q for q in diagnostics(d)['questions']))

    def test_manual_link_resolves_ambiguity_without_overriding_answer(self):
        d=question_document([('SECTION: One',[1]),('SECTION: Two',[1])])
        replace_key(d,parse_answer_key(csv_key()),2)
        e=d['separate_answer_key']['entries'][0];self.assertEqual(e['status'],'ambiguous')
        e['linked_question_id']='s2q1';recompute_matches(d,3)
        self.assertEqual(e['status'],'matched');self.assertEqual(e['resolution_source'],'manual_link')
        self.assertEqual(d['sections'][1]['questions'][0]['answer_source'],'manual_link')
        e['linked_question_id']='s1q1';recompute_matches(d,4)
        self.assertIsNone(d['sections'][1]['questions'][0]['correct_answer'])
        self.assertEqual(d['sections'][0]['questions'][0]['correct_answer'],'B')

    def test_link_cannot_overwrite_embedded_authoritative_answer(self):
        d=question_document(embedded='A');replace_key(d,parse_answer_key(csv_key()),2)
        e=d['separate_answer_key']['entries'][0];e['linked_question_id']='s1q1';recompute_matches(d,3)
        self.assertEqual(e['status'],'conflict');self.assertEqual(e['reason'],'conflicting_existing_answer')
        self.assertEqual(d['sections'][0]['questions'][0]['correct_answer'],'A')

    def test_manual_link_is_removed_with_source_key_but_manual_answer_survives(self):
        d=question_document();replace_key(d,parse_answer_key(csv_key()),2)
        e=d['separate_answer_key']['entries'][0];e['linked_question_id']='s1q1';recompute_matches(d,3)
        d['sections'][0]['questions'][1].update(correct_answer='A',answer_source='manual_review')
        remove_key(d,4)
        self.assertIsNone(d['sections'][0]['questions'][0]['correct_answer'])
        self.assertEqual(d['sections'][0]['questions'][1]['correct_answer'],'A')

    def test_generated_ids_are_stable_session_local_and_not_database_ids(self):
        d=question_document();before=copy.deepcopy(d);template_bytes(d);recompute_matches(d,3)
        for s,old in zip(d['sections'],before['sections']):
            self.assertEqual(s['section_key'],old['section_key'])
            for q,oq in zip(s['questions'],old['questions']):
                self.assertEqual(q['preview_question_id'],oq['id']);self.assertEqual(q['mapping_token'],oq['mapping_token'])
                self.assertTrue(q['mapping_token'].startswith('PQ-'))
        other=question_document();self.assertNotEqual(d['sections'][0]['questions'][0]['mapping_token'],other['sections'][0]['questions'][0]['mapping_token'])

    def test_template_is_safe_text_with_blank_answers_and_prefilled_context(self):
        d=question_document();d['sections'][0]['source_title']='=danger';d['sections'][0]['questions'][0]['text']='@unsafe\x01'
        raw=template_bytes(d)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            root=ET.fromstring(z.read('xl/worksheets/sheet1.xml'));ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            self.assertFalse(root.findall('.//x:f',ns))
            rows=[[c.find('x:is/x:t',ns).text or '' for c in row] for row in root.find('x:sheetData',ns)]
        self.assertEqual(rows[0],['Question ID','Section','Question Number','Question Preview','Correct Answer'])
        self.assertEqual(rows[1][1:],["'=danger",'1',"'@unsafe",''])
        self.assertEqual(rows[1][0],d['sections'][0]['questions'][0]['mapping_token'])

    def test_generated_template_ids_override_edited_section_and_number(self):
        d=question_document([('SECTION: One',[1]),('SECTION: Two',[1])])
        token=d['sections'][1]['questions'][0]['mapping_token']
        key=parse_answer_key(xlsx_key({'Answers':[['Question ID','Section','Question Number','Correct Answer'],[token,'Wrong','99','B']]}))
        replace_key(d,key,2)
        self.assertEqual(key['entries'][0]['question_id'],'s2q1')
        self.assertEqual(d['sections'][1]['questions'][0]['answer_source'],'generated_template')

    def test_generated_entry_can_be_deliberately_relinked(self):
        d=question_document();token=d['sections'][0]['questions'][0]['mapping_token']
        key=parse_answer_key(csv_key(f'Question ID,Correct Answer\n{token},B\n'));replace_key(d,key,2)
        key['entries'][0]['linked_question_id']='s1q2';recompute_matches(d,3)
        self.assertEqual(key['entries'][0]['question_id'],'s1q2')
        self.assertEqual(key['entries'][0]['resolution_source'],'manual_link')
        self.assertIsNone(d['sections'][0]['questions'][0]['correct_answer'])

    def test_explicit_template_id_without_number_is_supported(self):
        d=question_document();token=d['sections'][0]['questions'][0]['mapping_token']
        key=parse_answer_key(csv_key(f'Question ID,Correct Answer\n{token},B\n'));replace_key(d,key,2)
        self.assertEqual(key['entries'][0]['status'],'matched')

    def test_separate_common_heading_is_not_an_extra_unmatched_entry(self):
        key=parse_answer_key(fixtures.fixture(lines=['Correct Answers','Question 1: B']))
        self.assertEqual(key['parsed_entry_count'],1)
        d=question_document();replace_key(d,key,2)
        self.assertEqual(key['entries'][0]['status'],'matched')

    def test_unknown_explicit_embedded_section_does_not_fall_back(self):
        d=parse_docx(fixtures.fixture(lines=['SECTION: One','1. Prompt','a. Alpha','b. Beta','KEY','Unknown section','1 B']))[0]
        self.assertEqual(d['summary']['answers_matched'],0)
        self.assertEqual(d['embedded_answer_key']['entries'][0]['reason'],'section_title_not_found')

    def test_new_key_conflict_with_prior_manual_answer_stays_visible(self):
        d=question_document();q=d['sections'][0]['questions'][0]
        q.update(correct_answer='A',answer_source='manual_review',review_revision=2)
        replace_key(d,parse_answer_key(csv_key()),3)
        self.assertEqual(d['separate_answer_key']['entries'][0]['status'],'conflict')
        self.assertEqual(q['correct_answer'],'A')

    def test_embedded_table_with_unsupported_object_remains_diagnostic(self):
        table='<w:tbl><w:tr><w:tc>'+fixtures.paragraph('1')+'</w:tc><w:tc>'+fixtures.paragraph('B')+'<w:object/></w:tc></w:tr></w:tbl>'
        d=parse_docx(fixtures.fixture(lines=['1. Q','a. Alpha','b. Beta','KEY'],extra=table))[0]
        self.assertTrue(d['key_errors']);self.assertEqual(d['summary']['questions_detected'],1)

    def test_unheaded_table_can_be_classified_without_removing_question_section(self):
        table='<w:tbl><w:tr><w:tc>'+fixtures.paragraph('1')+'</w:tc><w:tc>'+fixtures.paragraph('B')+'</w:tc></w:tr></w:tbl>'
        d=parse_docx(fixtures.fixture(lines=['SECTION: One','1. Prompt','a. Alpha','b. Beta'],extra=table))[0]
        block=next(b for b in d['blocks'] if b['id'].startswith('table-block'))
        self.assertTrue(block['uncertain']);self.assertTrue(block['unparsed'])
        d=validate_preview(classify_block(d,block['id'],'answer_key',2))
        self.assertEqual((d['summary']['questions_detected'],d['summary']['answers_matched']),(1,1))


class ReconciliationAPITests(APITestCase):
    setUp=fixtures.DocxWorkflowTests.setUp
    path=fixtures.DocxWorkflowTests.path
    edit=fixtures.DocxWorkflowTests.edit
    confirm=fixtures.DocxWorkflowTests.confirm

    def start(self,lines=None,mode='separate_key'):
        r=self.client.post('/api/v1/questions/import/docx/preview/',{'file':fixtures.fixture(lines=lines or ['SECTION: One','1. First','a. Alpha','b. Beta','SECTION: Two','1. Second','a. Alpha','b. Beta']),'import_mode':mode},format='multipart')
        self.assertEqual(r.status_code,201,r.data)
        return self.edit(r.data,metadata={'subject':self.subject.pk})

    def upload_key(self,d,file=None):
        return self.client.post(self.path(d)+'answer-key/',{'revision':d['revision'],'file':file or csv_key()},format='multipart')

    def link(self,d,target,entry='k1',**extra):
        return self.client.patch(self.path(d)+f'answer-key/matches/{entry}/',{'revision':d['revision'],'question_id':target,**extra},format='json')

    def classify(self,d,block,value,revision=None):
        return self.client.patch(self.path(d)+f'blocks/{block}/classification/',{'revision':d['revision'] if revision is None else revision,'classification':value},format='json')

    def test_canonical_identity_refresh_and_no_early_bank_records(self):
        d=self.start();self.assertEqual(Question.objects.count(),0)
        self.assertEqual(self.client.get(self.path(d)).data,d)
        q=d['sections'][0]['questions'][0];self.assertEqual(q['section_key'],d['sections'][0]['section_key'])
        self.assertEqual(q['preview_question_id'],q['id'])

    def test_legacy_unfinished_summary_and_blocks_prepare_read_only(self):
        d=self.start();session=DocxImportSession.objects.get(pk=d['import_session_id'])
        session.preview.pop('blocks')
        session.preview['summary'].update(review_count=0,error_count=2)
        for s in session.preview['sections']:
            s.pop('section_key')
            for q in s['questions']:
                q.pop('mapping_token');q.pop('preview_question_id')
        session.save(update_fields=['preview']);before=copy.deepcopy(session.preview)
        r=self.client.get(self.path(d));self.assertEqual(r.status_code,200)
        self.assertEqual(r.data['summary']['review_count'],2);self.assertTrue(r.data['blocks'])
        self.assertEqual(self.client.get(self.path(d)).data,r.data)
        listing=self.client.get('/api/v1/questions/import/docx/preview/').data['recent_imports'][0]
        self.assertEqual(listing['summary'],r.data['summary'])
        session.refresh_from_db();self.assertEqual(session.preview,before)

    def test_template_authorization_tenant_uploader_and_completed_protection(self):
        d=self.start();url=self.path(d)+'answer-key-template/'
        response=self.client.get(url);self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response['Cache-Control']);self.assertIn('attachment',response['Content-Disposition'])
        self.client.force_authenticate(self.other);self.assertEqual(self.client.get(url).status_code,404)
        self.client.force_authenticate(self.user);self.assertEqual(self.client.get(url,HTTP_X_INSTITUTION_ID=str(self.b.pk)).status_code,403)
        self.client.force_authenticate(None);self.assertIn(self.client.get(url).status_code,[401,403])

    def test_template_fill_maps_repeated_numbers_and_confirms_provenance(self):
        d=self.start();rows=[['Question ID','Section','Question Number','Question Preview','Correct Answer']]
        for s in d['sections']:
            for q in s['questions']: rows.append([q['mapping_token'],'Changed','999','Ignored','B'])
        r=self.upload_key(d,xlsx_key({'Answers':rows}));self.assertEqual(r.status_code,200,r.data);d=r.data
        self.assertEqual(d['separate_answer_key']['summary']['matched_count'],2)
        self.assertTrue(d['confirmation']['eligible']);self.assertEqual(self.confirm(d).status_code,201)
        self.assertTrue(all(q.source_metadata['answer_source']=='generated_template' for q in Question.objects.all()))
        self.assertEqual(self.client.get(self.path(d)+'answer-key-template/').status_code,400)
        self.assertEqual(self.client.delete(self.path(d),{'revision':d['revision']},format='json').status_code,400)

    def test_unknown_foreign_duplicate_template_ids_reject_without_revision_change(self):
        d=self.start();other=self.start();valid=d['sections'][0]['questions'][0]['mapping_token'];foreign=other['sections'][0]['questions'][0]['mapping_token']
        for ids in [['PQ-unknown'],[foreign],[valid,valid]]:
            r=self.upload_key(d,csv_key('Question ID,Correct Answer\n'+''.join(f'{token},B\n' for token in ids)))
            self.assertEqual(r.status_code,400,r.data)
            self.assertEqual(DocxImportSession.objects.get(pk=d['import_session_id']).revision,d['revision'])
        self.assertEqual(Question.objects.count(),0)

    def test_invalid_template_answer_reviewable_formula_rejected(self):
        d=self.start();token=d['sections'][0]['questions'][0]['mapping_token']
        r=self.upload_key(d,csv_key(f'Question ID,Correct Answer\n{token},Z\n'));self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(r.data['separate_answer_key']['entries'][0]['status'],'invalid_answer')
        self.assertFalse(r.data['confirmation']['eligible'])
        self.assertEqual(self.upload_key(r.data,xlsx_key(formula=True)).status_code,400)

    def test_manual_link_relink_refresh_revision_and_remove(self):
        d=self.upload_key(self.start()).data;self.assertEqual(d['separate_answer_key']['entries'][0]['status'],'ambiguous')
        r=self.link(d,'s2q1');self.assertEqual(r.status_code,200,r.data);linked=r.data
        self.assertEqual(linked['separate_answer_key']['entries'][0]['resolution_source'],'manual_link')
        self.assertEqual(self.client.get(self.path(linked)).data,linked)
        self.assertEqual(self.link(d,'s1q1').status_code,400)
        d=self.link(linked,'s1q1').data;self.assertIsNone(d['sections'][1]['questions'][0]['correct_answer'])
        r=self.client.delete(self.path(d)+'answer-key/',{'revision':d['revision']},format='json')
        self.assertEqual(r.status_code,200);self.assertIsNone(r.data['sections'][0]['questions'][0]['correct_answer'])

    def test_manual_link_foreign_target_tenant_uploader_and_csrf_denied(self):
        d=self.upload_key(self.start()).data
        self.assertEqual(self.link(d,'another-session-question').status_code,400)
        self.client.force_authenticate(self.other);self.assertEqual(self.link(d,'s1q1').status_code,404)
        self.client.force_authenticate(self.user)
        url=self.path(d)+'answer-key/matches/k1/'
        self.assertEqual(self.client.patch(url,{'revision':d['revision'],'question_id':'s1q1'},format='json',HTTP_X_INSTITUTION_ID=str(self.b.pk)).status_code,403)
        csrf=APIClient(enforce_csrf_checks=True);csrf.force_login(self.user)
        self.assertEqual(csrf.patch(url,{'revision':d['revision'],'question_id':'s1q1'},format='json').status_code,403)

    def test_classification_recovers_twenty_and_survives_refresh(self):
        d=self.start(twenty('Unrecognized source heading'),'embedded_key')
        self.assertEqual(d['summary']['questions_detected'],40)
        b=next(b for b in d['blocks'] if b['uncertain'])
        r=self.classify(d,b['id'],'answer_key');self.assertEqual(r.status_code,200,r.data);d=r.data
        self.assertEqual((d['summary']['questions_detected'],d['summary']['answers_matched']), (20,20))
        self.assertEqual(self.client.get(self.path(d)).data,d);self.assertTrue(d['confirmation']['eligible'])
        self.assertEqual(self.confirm(d).status_code,201);self.assertEqual(Question.objects.count(),20)

    def test_exact_browser_empty_entry_recovery_and_confirmation(self):
        d=self.start(twenty('Unrecognized source heading'),'embedded_key')
        b=next(b for b in d['blocks'] if b['uncertain'])
        session=DocxImportSession.objects.get(pk=d['import_session_id'])
        saved=next(x for x in session.preview['blocks'] if x['id']==b['id'])
        saved['title']='ANSWER KEYS';saved['entries']=[]
        for q in saved['section']['questions']: q['text']='\u00b7 B'
        session.save(update_fields=['preview'])
        d=self.classify(d,b['id'],'answer_key').data
        self.assertEqual(len(d['embedded_answer_key']['entries']),20)
        self.assertEqual((d['summary']['ready_count'],d['summary']['error_count'],d['summary']['answers_missing']),(20,0,0))
        self.assertEqual(d['confirmation']['attention_count'],0)
        self.assertTrue(d['confirmation']['eligible'])
        self.assertEqual(self.client.get(self.path(d)).data,d)

    def test_automatic_plural_heading_is_confirmation_eligible(self):
        d=self.start(twenty('ANSWER KEYS')[:-20]+[f'Q{n} \u00b7 B' for n in range(1,21)],'embedded_key')
        self.assertEqual(d['summary']['ready_count'],20)
        self.assertTrue(d['confirmation']['eligible'])

    def test_real_source_blocker_has_visible_count_and_action(self):
        d=self.start(['Preface to check']+twenty(),'embedded_key')
        self.assertEqual(d['confirmation']['ready'],20)
        self.assertEqual(d['confirmation']['unresolved'],0)
        self.assertFalse(d['confirmation']['eligible'])
        self.assertGreater(d['confirmation']['attention_count'],0)
        self.assertTrue(any(b['code']=='document_review' and b['count']>0 for b in d['confirmation']['blockers']))
        d=self.edit(d,source_reviewed=True)
        self.assertTrue(d['confirmation']['eligible'])

    def test_resolved_matching_notice_does_not_require_unrelated_source_check(self):
        d=self.start(twenty('ANSWER KEYS'),'separate_key')
        session=DocxImportSession.objects.get(pk=d['import_session_id'])
        session.preview['key_errors'].append({'source_order':1,'message':'Answer-key section is unknown or ambiguous; correct affected answers manually.'})
        session.save(update_fields=['preview'])
        d=self.upload_key(d,csv_key('Question Number,Correct Answer\n'+''.join(f'{n},B\n' for n in range(1,21)))).data
        self.assertEqual(d['confirmation']['ready'],20)
        self.assertEqual(d['confirmation']['attention_count'],0)
        self.assertTrue(d['confirmation']['eligible'])

    def test_swapped_real_browser_blocks_can_be_corrected_without_saved_data_rewrite(self):
        d=self.start(['Preface to check']+twenty('Unrecognized source heading'),'embedded_key')
        a,b=d['blocks']
        d=self.classify(d,a['id'],'answer_key').data
        self.assertEqual(d['summary']['error_count'],20)
        d=self.classify(d,a['id'],'questions').data
        d=self.classify(d,b['id'],'answer_key').data
        self.assertEqual(d['summary']['ready_count'],20)
        self.assertEqual(d['summary']['answers_matched'],20)
        self.assertEqual(d['confirmation']['unresolved'],0)
        self.assertEqual(d['confirmation']['additional_issues'],1)
        self.assertEqual(d['confirmation']['document_issues'][0]['text'],'Preface to check')
        self.assertTrue(self.edit(d,source_reviewed=True)['confirmation']['eligible'])

    def test_classification_stale_revision_invalid_choice_and_foreign_session_denied(self):
        d=self.start();b=d['blocks'][0]['id']
        self.assertEqual(self.classify(d,b,'ignore',0).status_code,400)
        for value in ['invalid', [], {}, None, 1]:
            self.assertEqual(self.classify(d,b,value).status_code,400)
        self.assertEqual(self.classify(d,'foreign','ignore').status_code,400)
        self.client.force_authenticate(self.other);self.assertEqual(self.classify(d,b,'ignore').status_code,404)

    def test_embedded_entries_use_same_link_endpoint_and_can_be_excluded(self):
        d=self.start(['SECTION: One','1. First','a. Alpha','b. Beta','SECTION: Two','1. Second','a. Alpha','b. Beta','KEY','1 B'],'embedded_key')
        e=d['embedded_answer_key']['entries'][0];self.assertEqual(e['status'],'ambiguous')
        r=self.link(d,'s2q1',e['id']);self.assertEqual(r.status_code,200,r.data);d=r.data
        self.assertEqual(d['embedded_answer_key']['entries'][0]['status'],'matched')
        r=self.client.patch(self.path(d)+f"answer-key/matches/{e['id']}/",{'revision':d['revision'],'excluded':True},format='json')
        self.assertEqual(r.status_code,200,r.data);self.assertEqual(r.data['embedded_answer_key']['summary']['excluded_count'],1)

    def test_classification_audit_contains_decision_not_answers(self):
        from audit.models import AuditEvent
        d=self.start();b=d['blocks'][0]['id'];r=self.classify(d,b,'ignore');self.assertEqual(r.status_code,200)
        event=AuditEvent.objects.get(metadata__action='source_block_classified')
        self.assertEqual(set(event.metadata),{'action','block_id','classification','revision'})
