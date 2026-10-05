import copy
import io
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from . import test_docx as fixtures
from .answer_keys import answer_labels, parse_answer_key, recompute_matches, replace_key
from .docx_parser import parse_docx, validate_preview
from .models import DocxImportSession, Question


def csv_key(text='question_number,answer\n1,B\n', name='key.csv'):
    return SimpleUploadedFile(name, text.encode('utf-8-sig'))


def xlsx_key(sheets=None, formula=False, external=False):
    from xml.sax.saxutils import escape
    sheets = sheets or {'Answers': [['question_number', 'answer'], ['1', 'B']]}
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml" /></Types>')
        archive.writestr('_rels/.rels', '<Relationships/>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'+''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="r{i}"/>' for i,name in enumerate(sheets,1))+'</sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships>'+''.join(f'<Relationship Id="r{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+('</Relationships>'))
        for i,rows in enumerate(sheets.values(),1):
            cells = ''.join('<row>'+''.join(f'<c r="{chr(65+j)}{r}" t="inlineStr"><is><t>{escape(str(v))}</t></is>'+('<f>1+1</f>' if formula and r==2 and j==1 else '')+'</c>' for j,v in enumerate(row))+'</row>' for r,row in enumerate(rows,1))
            archive.writestr(f'xl/worksheets/sheet{i}.xml',f'<worksheet xmlns="{ns}"><sheetData>{cells}</sheetData></worksheet>')
        if external:
            archive.writestr('xl/_rels/external.rels','<Relationships><Relationship TargetMode="External" Target="https://example.invalid"/></Relationships>')
    return SimpleUploadedFile('key.xlsx',stream.getvalue())


def question_document(sections=None, embedded=None):
    lines=[]
    for title,numbers in sections or [('SECTION: Part One',[1,2])]:
        lines.append(title)
        for number in numbers:
            lines += [f'{number}. Prompt {number}', 'a. Alpha', 'b. Beta', 'c. Gamma']
        if embedded:
            lines += ['KEY']+[f'{number} {embedded}' for number in numbers]
    return parse_docx(fixtures.fixture(lines=lines))[0]


class AnswerKeyParserTests(SimpleTestCase):
    def test_csv_bom_and_header_aliases(self):
        result=parse_answer_key(csv_key('Part,Question No.,Correct Option\nPart One,Q1,Option b\n'))
        self.assertEqual(result['entries'][0]['question_number'],1)
        self.assertEqual(result['entries'][0]['section'],'Part One')
        self.assertEqual(result['source_document']['file_type'],'csv')
        self.assertEqual(len(result['source_document']['sha256']),64)

    def test_structured_columns_never_infer_section_from_option_text(self):
        for headings in [['Section','Question Number','Correct Answer','Option Text'],['section','question number','correct answer','Option Text']]:
            for upload in [csv_key(','.join(headings)+'\nGeneral,1,B,Beta option text\n'),xlsx_key({'Answers':[headings,['General','1','B','Beta option text']]})]:
                item=parse_answer_key(upload)['entries'][0]
                self.assertEqual((item['section'],item['question_number'],item['answer']),('General',1,'B'))
        for headings in ['Question,Answer','Question Number,Answer','Q No,Correct Option']:
            item=parse_answer_key(csv_key(headings+'\n1,B\n'))['entries'][0]
            self.assertEqual((item['section'],item['question_number'],item['answer']),('',1,'B'))

    def test_duplicate_or_unknown_section_headers_request_mapping_without_guessing(self):
        for content in ['Section,Section,Question Number,Correct Answer\nGeneral,Beta,1,B\n','Label,Prompt,Value\nBeta,1,B\n']:
            with self.assertRaises(ValidationError) as error: parse_answer_key(csv_key(content))
            self.assertIn('columns',error.exception.detail)

    def test_csv_headerless_simple_key(self):
        self.assertEqual(parse_answer_key(csv_key('1,B\n2,A\n'))['parsed_entry_count'],2)

    def test_csv_semicolon_and_quoted_multiple_answers(self):
        self.assertEqual(parse_answer_key(csv_key('question_number;answer\n1;A,C\n'))['entries'][0]['answer'],'A,C')
        self.assertEqual(parse_answer_key(csv_key('question_number,answer\n1,"A,C"\n'))['entries'][0]['answer'],'A,C')

    def test_csv_unknown_headers_require_explicit_distinct_mapping(self):
        with self.assertRaises(ValidationError) as error:
            parse_answer_key(csv_key('Index,Value\n1,B\n'))
        self.assertIn('columns',error.exception.detail)
        self.assertEqual(parse_answer_key(csv_key('Index,Value\n1,B\n'),columns={'number':0,'answer':1})['entries'][0]['answer'],'B')
        with self.assertRaises(ValidationError):
            parse_answer_key(csv_key('Index,Value\n1,B\n'),columns={'number':0,'answer':0})

    def test_docx_paragraph_representations_and_headings(self):
        lines=['SECTION: Part One','1. B','Q2 - A','3) D','Question 4: C','5 B']
        result=parse_answer_key(fixtures.fixture(lines=lines,name='answers.docx'))
        self.assertEqual([i['question_number'] for i in result['entries']],[1,2,3,4,5])
        self.assertEqual({i['section'] for i in result['entries']},{'SECTION: Part One'})

    def test_docx_table(self):
        table='<w:tbl>'+''.join('<w:tr>'+''.join('<w:tc>'+fixtures.paragraph(v)+'</w:tc>' for v in row)+'</w:tr>' for row in [['No.','Correct Answer'],['1','B'],['2','A']])+'</w:tbl>'
        key=parse_answer_key(fixtures.fixture(lines=['SECTION: Tables'],extra=table,name='key.docx'))
        self.assertEqual(key['parsed_entry_count'],2)
        self.assertEqual(key['entries'][0]['section'],'SECTION: Tables')

    def test_docx_automatic_numbering(self):
        numbering='<w:numbering xmlns:w="'+fixtures.NS['w']+'"><w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num></w:numbering>'
        paragraphs=''.join('<w:p><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>'+answer+'</w:t></w:r></w:p>' for answer in ['B','A'])
        key=parse_answer_key(fixtures.fixture(lines=['KEY'],extra=paragraphs,parts={'word/numbering.xml':numbering},name='key.docx'))
        self.assertEqual([(i['question_number'],i['answer']) for i in key['entries']],[(1,'B'),(2,'A')])

    def test_docx_overlong_heading_is_rejected_without_truncation(self):
        with self.assertRaises(ValidationError):
            parse_answer_key(fixtures.fixture(lines=['SECTION: '+('x'*501),'1 B'],name='key.docx'))

    def test_xlsx_simple_and_section_columns(self):
        self.assertEqual(parse_answer_key(xlsx_key())['entries'][0]['answer'],'B')
        result=parse_answer_key(xlsx_key({'Key':[['section','number','answer'],['Part One','1','B']]}))
        self.assertEqual(result['entries'][0]['section'],'Part One')

    def test_xlsx_multiple_sheets_require_selection(self):
        sheets={'One':[['Question','Answer'],['1','A']], 'Two':[['Question','Answer'],['1','B']]}
        with self.assertRaises(ValidationError) as error:
            parse_answer_key(xlsx_key(sheets))
        self.assertIn('sheets',error.exception.detail)
        self.assertEqual(parse_answer_key(xlsx_key(sheets),sheet='Two')['entries'][0]['answer'],'B')

    def test_xlsx_shared_strings_and_numeric_cells(self):
        source=xlsx_key();output=io.BytesIO()
        ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        with zipfile.ZipFile(io.BytesIO(source.read())) as original,zipfile.ZipFile(output,'w') as result:
            for name in original.namelist():
                if name!='xl/worksheets/sheet1.xml':result.writestr(name,original.read(name))
            result.writestr('xl/sharedStrings.xml',f'<sst xmlns="{ns}"><si><t>Question</t></si><si><t>Answer</t></si><si><t>B</t></si></sst>')
            result.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}"><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row><row><c r="A2"><v>1.0</v></c><c r="B2" t="s"><v>2</v></c></row></sheetData></worksheet>')
        data=parse_answer_key(SimpleUploadedFile('key.xlsx',output.getvalue()))
        self.assertEqual(data['entries'][0]['question_number'],1)
        self.assertEqual(data['entries'][0]['answer'],'B')

    def test_xlsx_formulas_and_external_relationships_rejected(self):
        for kwargs in [{'formula':True},{'external':True}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                parse_answer_key(xlsx_key(**kwargs))

    def test_invalid_archives_dtd_macros_and_extensions(self):
        files=[SimpleUploadedFile('key.xlsx',b'invalid'),csv_key(name='key.xlsm'),csv_key(name='key.txt'),
               fixtures.fixture(parts={'evil.bin':b'bad'},name='key.docx'),
               fixtures.fixture(parts={'word/document.xml':b'<!DOCTYPE x><x/>'},name='key.docx')]
        for file in files:
            with self.subTest(name=file.name),self.assertRaises(ValidationError): parse_answer_key(file)

    def test_size_rows_columns_and_cells_are_bounded(self):
        files=[SimpleUploadedFile('key.csv',b'x'*(2*1024*1024+1)),csv_key('question_number,answer\n'+('1,B\n'*2001)),
               csv_key(','.join(['x']*17)+'\n'),csv_key('question_number,answer\n1,'+'B'*1001+'\n')]
        for file in files:
            with self.subTest(size=file.size),self.assertRaises(ValidationError):parse_answer_key(file)


class AnswerMatchingTests(SimpleTestCase):
    def match(self, text, document=None):
        document=document or question_document()
        replace_key(document,parse_answer_key(csv_key(text)),1)
        return document

    def test_unique_global_numbers_match_without_sections(self):
        d=self.match('number,answer\n1,B\n2,A\n')
        self.assertEqual(d['separate_answer_key']['summary']['matched_count'],2)
        self.assertEqual(d['sections'][0]['questions'][0]['correct_answer'],'B')

    def test_section_resets_never_infer_from_entry_sequence(self):
        doc=question_document([('SECTION: One',[1]),('SECTION: Two',[1])])
        d=self.match('number,answer\n1,B\n1,A\n',doc)
        self.assertEqual(d['separate_answer_key']['summary']['ambiguous_count'],2)
        self.assertTrue(all(q['correct_answer'] is None for s in d['sections'] for q in s['questions']))

    def test_section_titles_are_normalized_conservatively(self):
        doc=question_document([('SECTION: Part One',[1]),('SECTION: Part Two',[1])])
        d=self.match('section,number,answer\n  PART   ONE ,1,B\nPart-Two,1,A\n',doc)
        self.assertEqual(d['separate_answer_key']['summary']['matched_count'],2)
        self.assertEqual(d['sections'][1]['questions'][0]['correct_answer'],'A')

    def test_stable_section_identity_has_priority(self):
        doc=question_document([('SECTION: Same',[1]),('SECTION: Same',[1])])
        d=self.match('section_id,section,number,answer\ns2,Wrong title,1,B\n',doc)
        self.assertEqual(d['separate_answer_key']['entries'][0]['question_id'],'s2q1')

    def test_normalization_collisions_are_ambiguous(self):
        d=self.match('section,number,answer\nSame,1,B\n',question_document([('SECTION: Same',[1]),('SECTION: SAME',[2])]))
        self.assertEqual(d['separate_answer_key']['entries'][0]['status'],'ambiguous')

    def test_unknown_section_does_not_fall_back_to_unique_global_number(self):
        d=self.match('section,number,answer\nUnrelated,1,B\n')
        self.assertEqual(d['separate_answer_key']['entries'][0]['status'],'unmatched')

    def test_invalid_source_numbers_are_not_matched_and_remain_inspectable(self):
        d=self.match('number,answer\nnot-a-number,B\n')
        item=d['separate_answer_key']['entries'][0]
        self.assertEqual(item['status'],'unmatched')
        self.assertEqual(item['raw_question_number'],'not-a-number')

    def test_overlong_sections_cannot_silently_match_truncated_titles(self):
        title='x'*490
        doc=question_document([('SECTION: '+title,[1])])
        d=self.match('section,number,answer\n'+('SECTION: '+title+'suffix-too-long')+',1,B\n',doc)
        self.assertIsNone(d['sections'][0]['questions'][0]['correct_answer'])
        self.assertEqual(d['separate_answer_key']['summary']['blocker_count'],1)

    def test_letters_and_exact_unique_option_text(self):
        q=question_document()['sections'][0]['questions'][0]
        for value in ['B','b','Option B','Beta',' beta ']: self.assertEqual(answer_labels(q,value),('B',))
        self.assertEqual(answer_labels(q,'almost Beta'),())
        q['options'][0]['text']='Beta'
        self.assertEqual(answer_labels(q,'Beta'),())

    def test_competing_letter_and_text_interpretations_are_invalid(self):
        q=question_document()['sections'][0]['questions'][0];q['options'][0]['text']='B'
        self.assertEqual(answer_labels(q,'B'),())

    def test_multiple_select_normalizes_sets(self):
        q=question_document()['sections'][0]['questions'][0];q['question_type']='multiple_select'
        for value in ['A,C','A, C','A & C','A and C','A/C','C,A,A']:
            self.assertEqual(answer_labels(q,value),('A','C'))
        self.assertEqual(answer_labels(q,'A,Z'),())

    def test_true_false_values(self):
        q=question_document()['sections'][0]['questions'][0];q.update(question_type='true_false',options=[{'label':'A','text':'True'},{'label':'B','text':'False'}])
        for value in ['True','TRUE','T']:self.assertEqual(answer_labels(q,value),('A',))
        for value in ['False','f']:self.assertEqual(answer_labels(q,value),('B',))

    def test_invalid_extra_and_missing_answers_are_visible(self):
        d=self.match('number,answer\n1,Z\n99,B\n')
        summary=d['separate_answer_key']['summary']
        self.assertEqual(summary['invalid_answer_count'],1);self.assertEqual(summary['unmatched_count'],1)
        self.assertEqual(summary['questions_missing_answer'],2)
        self.assertEqual(validate_preview(d)['summary']['answers_missing'],2)

    def test_equivalent_duplicates_are_nonblocking(self):
        d=self.match('number,answer\n1,B\n1,Option b\n')
        self.assertEqual(d['separate_answer_key']['summary']['duplicate_count'],1)
        self.assertEqual(d['separate_answer_key']['summary']['blocker_count'],0)

    def test_conflicting_duplicate_answers_do_not_assign(self):
        d=self.match('number,answer\n1,B\n1,A\n')
        self.assertEqual(d['separate_answer_key']['summary']['conflict_count'],2)
        self.assertIsNone(d['sections'][0]['questions'][0]['correct_answer'])

    def test_embedded_agreement_and_conflict(self):
        agree=self.match('number,answer\n1,B\n',question_document(embedded='B'))
        self.assertTrue(agree['separate_answer_key']['entries'][0]['agreement'])
        conflict=self.match('number,answer\n1,C\n',question_document(embedded='B'))
        self.assertEqual(conflict['separate_answer_key']['entries'][0]['status'],'conflict')
        self.assertEqual(conflict['sections'][0]['questions'][0]['correct_answer'],'B')

    def test_replacement_clears_automatic_answers_but_keeps_manual_questions(self):
        d=self.match('number,answer\n1,B\n2,C\n')
        d['sections'][0]['questions'][1].update(correct_answer='A',answer_source='manual_review')
        replace_key(d,parse_answer_key(csv_key('number,answer\n99,B\n')),2)
        self.assertIsNone(d['sections'][0]['questions'][0]['correct_answer'])
        self.assertEqual(d['sections'][0]['questions'][1]['correct_answer'],'A')
        self.assertEqual(d['separate_answer_key']['parsed_entry_count'],1)


class AnswerKeyWorkflowTests(APITestCase):
    setUp=fixtures.DocxWorkflowTests.setUp
    def upload(self, **kwargs):
        response=self.client.post('/api/v1/questions/import/docx/preview/',{'file':fixtures.fixture(**kwargs),'import_mode':'separate_key'},format='multipart')
        self.assertEqual(response.status_code,201,response.data)
        return response.data
    edit=fixtures.DocxWorkflowTests.edit
    path=fixtures.DocxWorkflowTests.path
    confirm=fixtures.DocxWorkflowTests.confirm

    def start(self, embedded=False):
        lines=['SECTION: One','1. First','a. Alpha','b. Beta','2. Second','a. Alpha','b. Beta']
        if embedded:lines+=['KEY','1 B','2 A']
        data=self.upload(lines=lines)
        return self.edit(data,metadata={'subject':self.subject.pk})

    def key(self,data,file=None,**fields):
        return self.client.post(self.path(data)+'answer-key/',{'revision':str(data['revision']),'file':file or csv_key('number,answer\n1,B\n2,A\n'),**fields},format='multipart')

    def resolve(self,data,entry='k1',**fields):
        return self.client.patch(self.path(data)+f'answer-key/matches/{entry}/',{'revision':data['revision'],**fields},format='json')

    def test_key_upload_only_stages_answers_and_recovers_after_refresh(self):
        data=self.start();response=self.key(data);self.assertEqual(response.status_code,200,response.data)
        data=response.data;self.assertEqual(Question.objects.count(),0)
        self.assertTrue(data['confirmation']['eligible'])
        self.assertEqual(self.client.get(self.path(data)).data,data)
        self.assertEqual(self.client.get(self.path(data)+'answer-key/').data,data)
        self.assertEqual(data['separate_answer_key']['matching_revision'],data['revision'])

    def test_confirmation_creates_correct_options_provenance_and_no_duplicates(self):
        data=self.key(self.start()).data
        response=self.confirm(data);self.assertEqual(response.status_code,201,response.data)
        questions=list(Question.objects.order_by('id'))
        self.assertEqual([q.options.get(is_correct=True).text for q in questions],['Beta','Alpha'])
        self.assertTrue(all(q.source_metadata['answer_source']=='separate_key' for q in questions))
        self.assertEqual(questions[0].source_metadata['answer_key_document']['file_type'],'csv')
        self.assertEqual(self.confirm(data).status_code,400);self.assertEqual(Question.objects.count(),2)
        self.assertEqual(self.key(data).status_code,400)

    def test_missing_invalid_unmatched_entries_block_until_resolved_or_excluded(self):
        data=self.key(self.start(),csv_key('number,answer\n1,Z\n99,B\n')).data
        self.assertFalse(data['confirmation']['eligible']);self.assertEqual(self.confirm(data).status_code,400)
        data=self.resolve(data,question_id='s1q1',answer='B').data
        data=self.resolve(data,entry='k2',excluded=True).data
        data=self.edit(data,question_id='s1q2',changes={'correct_answer':'A'})
        self.assertTrue(data['confirmation']['eligible']);self.assertEqual(self.confirm(data).status_code,201)

    def test_embedded_conflict_requires_explicit_resolution(self):
        data=self.key(self.start(embedded=True),csv_key('number,answer\n1,A\n2,A\n')).data
        self.assertFalse(data['confirmation']['eligible'])
        self.assertEqual(data['sections'][0]['questions'][0]['correct_answer'],'B')
        data=self.resolve(data,question_id='s1q1',answer='A').data
        self.assertTrue(data['confirmation']['eligible'])
        self.confirm(data)
        self.assertEqual(Question.objects.order_by('id')[0].source_metadata['answer_source'],'manual_review')

    def test_question_manual_correction_resolves_key_conflict(self):
        data=self.key(self.start(embedded=True),csv_key('number,answer\n1,A\n2,A\n')).data
        data=self.edit(data,question_id='s1q1',changes={'correct_answer':'A'})
        self.assertTrue(data['confirmation']['eligible'])
        self.assertEqual(data['separate_answer_key']['entries'][0]['status'],'matched')

    def test_duplicate_conflict_is_resolved_by_explicit_authoritative_answer(self):
        data=self.key(self.start(),csv_key('number,answer\n1,B\n1,A\n2,A\n')).data
        self.assertFalse(data['confirmation']['eligible'])
        data=self.resolve(data,question_id='s1q1',answer='B').data
        self.assertTrue(data['confirmation']['eligible'])
        self.assertEqual(data['separate_answer_key']['summary']['duplicate_count'],1)

    def test_manual_resolution_can_be_changed_again(self):
        data=self.key(self.start()).data
        data=self.resolve(data,question_id='s1q1',answer='A').data
        data=self.resolve(data,question_id='s1q1',answer='B').data
        self.assertEqual(data['sections'][0]['questions'][0]['correct_answer'],'B')

    def test_wrong_key_replacement_drops_old_matches_and_preserves_manual_correction(self):
        data=self.key(self.start()).data
        data=self.edit(data,question_id='s1q2',changes={'correct_answer':'B'})
        response=self.key(data,csv_key('number,answer\n99,A\n',name='replacement.csv'))
        self.assertEqual(response.status_code,200,response.data);data=response.data
        self.assertIsNone(data['sections'][0]['questions'][0]['correct_answer'])
        self.assertEqual(data['sections'][0]['questions'][1]['correct_answer'],'B')
        self.assertEqual(data['separate_answer_key']['source_document']['filename'],'replacement.csv')
        self.assertEqual(data['separate_answer_key']['parsed_entry_count'],1)

    def test_stale_upload_and_match_edits_do_not_mutate(self):
        initial=self.start();data=self.key(initial).data
        before=copy.deepcopy(DocxImportSession.objects.get(pk=data['import_session_id']).preview)
        self.assertEqual(self.key(initial).status_code,400)
        self.assertEqual(self.resolve(initial,question_id='s1q1',answer='A').status_code,400)
        self.assertEqual(DocxImportSession.objects.get(pk=data['import_session_id']).preview,before)

    def test_cross_tenant_other_uploader_student_and_anonymous_denied(self):
        from tenants.models import InstitutionMembership
        data=self.start()
        for user in [self.other,None]:
            self.client.force_authenticate(user)
            self.assertIn(self.key(data).status_code,[403,404])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.path(data)+'answer-key/',HTTP_X_INSTITUTION_ID=str(self.b.pk)).status_code,403)
        InstitutionMembership.objects.create(user=self.user,institution=self.b,role='teacher')
        self.assertEqual(self.client.get(self.path(data)+'answer-key/',HTTP_X_INSTITUTION_ID=str(self.b.pk)).status_code,404)
        InstitutionMembership.objects.filter(user=self.user).update(role='student')
        self.assertEqual(self.key(data).status_code,403)

    def test_multiple_select_answers_use_normal_question_option_rules(self):
        data=self.start()
        data=self.edit(data,question_id='s1q1',changes={'question_type':'multiple_select'})
        data=self.key(data,csv_key('number,answer\n1,"A,B"\n2,A\n')).data
        self.assertTrue(data['confirmation']['eligible'],data['confirmation'])
        self.assertEqual(self.confirm(data).status_code,201)
        self.assertEqual(Question.objects.order_by('id')[0].options.filter(is_correct=True).count(),2)

    def test_xlsx_and_docx_uploads_integrate_with_session(self):
        for file in [xlsx_key({'Key':[['Number','Answer'],['1','B'],['2','A']]}),fixtures.fixture(lines=['1 B','2 A'],name='key.docx')]:
            response=self.key(self.start(),file)
            self.assertEqual(response.status_code,200,response.data)
            self.assertTrue(response.data['confirmation']['eligible'])

    def test_candidate_allowlist_does_not_gain_key_content(self):
        from attempts.serializers import CandidateExamQuestionSerializer
        data=self.key(self.start()).data;self.confirm(data)
        attempt,row=fixtures.DocxWorkflowTests.make_attempt(self,Question.objects.order_by('id')[0])
        payload=CandidateExamQuestionSerializer(row).data
        self.assertNotIn('source_metadata',str(payload));self.assertNotIn('is_correct',str(payload))
        self.assertNotIn('answer_key',str(payload))

    def test_audits_never_store_raw_answers(self):
        from audit.models import AuditEvent
        data=self.key(self.start(embedded=True),csv_key('number,answer\n1,A\n2,A\n')).data
        data=self.resolve(data,question_id='s1q1',answer='A').data
        actions=list(AuditEvent.objects.values_list('metadata',flat=True))
        self.assertTrue(any(a['action']=='answer_key_uploaded' for a in actions))
        self.assertTrue(any(a['action']=='answer_conflict_resolved' for a in actions))
        self.assertFalse(any('answer' in a or 'entries' in a for a in actions))

    def test_invalid_correction_and_out_of_session_target_do_not_mutate(self):
        data=self.key(self.start()).data
        before=copy.deepcopy(DocxImportSession.objects.get(pk=data['import_session_id']).preview)
        for fields in [{'question_id':'s99q1','answer':'A'},{'question_id':'s1q1','answer':'Z'},{'question_id':{'id':'s1q1'}}]:
            self.assertEqual(self.resolve(data,**fields).status_code,400)
        self.assertEqual(DocxImportSession.objects.get(pk=data['import_session_id']).preview,before)

    def test_relinking_manual_entry_restores_its_previous_question(self):
        data=self.key(self.start(),csv_key('number,answer\n99,B\n')).data
        data=self.resolve(data,question_id='s1q1',answer='B').data
        data=self.resolve(data,question_id='s1q2',answer='A').data
        self.assertIsNone(data['sections'][0]['questions'][0]['correct_answer'])
        self.assertEqual(data['sections'][0]['questions'][1]['correct_answer'],'A')

    def test_csrf_is_required_for_real_session_key_upload(self):
        from rest_framework.test import APIClient
        data=self.start()
        client=APIClient(enforce_csrf_checks=True);client.force_login(self.user)
        response=client.post(self.path(data)+'answer-key/',{'revision':str(data['revision']),'file':csv_key()},format='multipart')
        self.assertEqual(response.status_code,403)
        self.assertNotIn('separate_answer_key',DocxImportSession.objects.get(pk=data['import_session_id']).preview)

    def test_expired_and_completed_sessions_cannot_receive_or_edit_keys(self):
        from django.utils import timezone
        from datetime import timedelta
        data=self.start()
        DocxImportSession.objects.filter(pk=data['import_session_id']).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.key(data).status_code,400)
        data=self.key(self.start()).data;self.confirm(data)
        self.assertEqual(self.key(data).status_code,400)
        self.assertEqual(self.resolve(data,question_id='s1q1',answer='A').status_code,400)

    def test_answer_key_read_and_edits_require_session_uploader(self):
        data=self.key(self.start()).data
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.path(data)+'answer-key/').status_code,404)
        self.assertEqual(self.resolve(data,question_id='s1q1',answer='A').status_code,404)

    def test_true_false_key_upload_uses_boolean_answers(self):
        data=self.upload(lines=['SECTION: Boolean','1. First','a. True','b. False','2. Second','a. True','b. False'])
        data=self.edit(data,metadata={'subject':self.subject.pk})
        data=self.key(data,csv_key('number,answer\n1,T\n2,False\n')).data
        self.assertTrue(data['confirmation']['eligible'])
        self.assertEqual(self.confirm(data).status_code,201)
        self.assertEqual([q.options.get(is_correct=True).text for q in Question.objects.order_by('id')],['True','False'])
