import io
import tempfile
import zipfile
from datetime import timedelta
from unittest.mock import patch
from xml.sax.saxutils import escape

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounts.models import User
from audit.models import AuditEvent
from institutions.models import Institution
from subjects.models import Subject
from tenants.models import InstitutionMembership
from .docx_parser import NS, parse_docx
from .models import DocxImportSession, Question, QuestionMedia


def paragraph(text): return f'<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>'


def fixture(lines=None, extra='', image=False, parts=None, name='fixture.docx'):
    lines = lines or ['1.0 Section','1. Authored typo stays','a. Alpha','b) Beta','C. Gamma','d. Delta','KEY','1 B']
    body = ''.join(paragraph(t) for t in lines)
    if image:
        drawing = '<w:p><w:r><w:drawing><a:blip r:embed="rId1" /></w:drawing></w:r></w:p>'
        body = paragraph(lines[0])+drawing+''.join(paragraph(t) for t in lines[1:])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml" /></Types>')
        z.writestr('_rels/.rels','<Relationships />')
        if 'word/document.xml' not in (parts or {}):
            z.writestr('word/document.xml','<w:document '+ ' '.join(f'xmlns:{k}="{v}"' for k,v in NS.items())+'><w:body>'+body+extra+'</w:body></w:document>')
        if image:
            from PIL import Image
            image_data=io.BytesIO();Image.new('RGB',(4,4),'white').save(image_data,format='PNG')
            z.writestr('word/media/a.png',image_data.getvalue())
            z.writestr('word/_rels/document.xml.rels','<Relationships><Relationship Id="rId1" Target="media/a.png" /></Relationships>')
        for path,data in (parts or {}).items():z.writestr(path,data)
    return SimpleUploadedFile(name,buffer.getvalue())


class DocxParserTests(SimpleTestCase):
    def parse(self, **kwargs): return parse_docx(fixture(**kwargs))[0]
    def question(self, **kwargs): return self.parse(**kwargs)['sections'][0]['questions'][0]

    def test_four_options_varied_markers_and_authored_text(self):
        q=self.question();self.assertEqual(q['readiness'],'ready');self.assertEqual(q['text'],'Authored typo stays');self.assertEqual(q['correct_answer'],'B');self.assertEqual(len(q['options']),4)

    def test_five_options(self):
        q=self.question(lines=['1.0 Five','1. Prompt','a. A','b. B','c. C','d. D','e. E','Answers Key','1. E']);self.assertEqual(len(q['options']),5);self.assertEqual(q['readiness'],'ready')

    def test_true_false(self):
        q=self.question(lines=['1.0 TF','1. Prompt','a. True','b. False','ANSWER','1 FALSE']);self.assertEqual(q['question_type'],'true_false');self.assertEqual(q['correct_answer'],'B')

    def test_sections_reset_even_duplicate_titles(self):
        d=self.parse(lines=['1.0 Same','1. First','a. A','b. B','Key','1 A','1.0 Same','1. Second','a. C','b. D','Key Answers','1 B']);self.assertEqual(len(d['sections']),2);self.assertEqual(d['summary']['answers_matched'],2)

    def test_wrapped_prompt(self):
        self.assertEqual(self.question(lines=['1.0 S','1. First','second authored line','a. A','b. B','KEY','1 A'])['text'],'First\nsecond authored line')

    def test_missing_answer(self): self.assertEqual(self.question(lines=['1.0 S','1. Q','a. A','b. B'])['readiness'],'error')
    def test_invalid_answer(self): self.assertIn('unavailable',self.question(lines=['1.0 S','1. Q','a. A','b. B','KEY','1 E'])['key_issue'])
    def test_duplicate_answer(self): self.assertIsNone(self.question(lines=['1.0 S','1. Q','a. A','b. B','KEY','1 A','1 B'])['correct_answer'])
    def test_nonexistent_answer(self): self.assertTrue(self.parse(lines=['1.0 S','1. Q','a. A','b. B','KEY','2 A'])['key_errors'])
    def test_malformed_answer(self): self.assertTrue(self.parse(lines=['1.0 S','1. Q','a. A','b. B','KEY','1 A B'])['key_errors'])
    def test_duplicate_question_numbers_require_review(self):
        d=self.parse(lines=['1.0 S','1. Q','a. A','b. B','1. Q2','a. C','b. D','KEY','1 A']);self.assertEqual(d['summary']['review_count'],2)

    def test_image_before_question_with_evidence(self):
        q=self.question(lines=['1.0 S','1. In the sample above?','a. A','b. B','KEY','1 A'],image=True);self.assertEqual(q['media'][0]['status'],'converted');self.assertEqual(q['readiness'],'ready')
    def test_image_transparency_is_preserved(self):
        from PIL import Image
        from .docx_parser import raster_image
        source=io.BytesIO();Image.new('RGBA',(4,4),(0,0,0,0)).save(source,format='PNG')
        with Image.open(io.BytesIO(raster_image(source.getvalue(),'image.png'))) as rendered:
            self.assertEqual(rendered.getpixel((0,0)),(0,0,0,0))
    def test_decoder_bomb_exception_is_safe(self):
        from PIL import Image
        from .docx_parser import raster_image
        with patch('PIL.Image.open',side_effect=Image.DecompressionBombError('test')):
            with self.assertRaises(ValueError):raster_image(b'input','image.png')
    def test_ambiguous_image_association(self): self.assertEqual(self.question(image=True)['readiness'],'needs_review')

    def test_equation_preserved_inline_and_in_options(self):
        extra='<w:p><w:r><w:t>1. R is </w:t></w:r><m:oMath><m:sSub><m:e><m:r><m:t>R</m:t></m:r></m:e><m:sub><m:r><m:t>1</m:t></m:r></m:sub></m:sSub></m:oMath></w:p>'+paragraph('a. A')+paragraph('b. B')+paragraph('KEY')+paragraph('1 A')
        q=self.question(lines=['1.0 S'],extra=extra);self.assertEqual(q['text'],'R is R_(1)');self.assertEqual(q['equations'][0]['status'],'converted')
    def test_unsupported_equation_not_silently_lost(self):
        extra='<w:p><w:r><w:t>1. Q</w:t></w:r><m:oMath><m:nary><m:r><m:t>X</m:t></m:r></m:nary></m:oMath></w:p>'+paragraph('a. A')+paragraph('b. B')+paragraph('KEY')+paragraph('1 A')
        q=self.question(lines=['1.0 S'],extra=extra);self.assertEqual(q['readiness'],'error');self.assertIn('source_xml',q['equations'][0])
    def test_unsupported_table(self): self.assertEqual(self.question(extra='<w:tbl />')['readiness'],'needs_review')
    def test_bookmark_metadata_is_not_a_question_object(self):
        self.assertEqual(self.question(extra='<w:bookmarkEnd w:id="0" />')['readiness'],'ready')
    def test_floating_image_in_section_heading_does_not_flag_previous_section(self):
        heading='<w:p><w:r><w:t>2.0 Next</w:t></w:r><w:drawing><wp:anchor xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"><a:blip r:embed="rId1" /></wp:anchor></w:drawing></w:p>'
        extra=heading+paragraph('1. In the sample above?')+paragraph('a. A')+paragraph('b. B')+paragraph('KEY')+paragraph('1 A')
        d=self.parse(lines=['1.0 First','1. In the sample above?','a. A','b. B','KEY','1 A'],image=True,extra=extra)
        self.assertEqual(d['sections'][0]['questions'][0]['readiness'],'ready')
        self.assertEqual(d['sections'][1]['questions'][0]['readiness'],'needs_review')

    def test_fake_docx(self):
        with self.assertRaises(ValidationError):parse_docx(SimpleUploadedFile('fake.docx',b'not ZIP'))
    def test_wrong_extension(self):
        with self.assertRaises(ValidationError):parse_docx(fixture(name='file.docm'))
    def test_corrupt_docx(self):
        upload=fixture();data=upload.read()[:30]
        with self.assertRaises(ValidationError):parse_docx(SimpleUploadedFile('corrupt.docx',data))
    @override_settings(DOCX_IMPORT_LIMITS={'upload_bytes':10})
    def test_upload_limit(self):
        with self.assertRaises(ValidationError):self.parse()
    @override_settings(DOCX_IMPORT_LIMITS={'uncompressed_bytes':10})
    def test_uncompressed_limit(self):
        with self.assertRaises(ValidationError):self.parse()
    @override_settings(DOCX_IMPORT_LIMITS={'members':2})
    def test_member_limit(self):
        with self.assertRaises(ValidationError):self.parse()
    def test_traversal(self):
        with self.assertRaises(ValidationError):self.parse(parts={'../escape':'x'})
    def test_executable_rejected(self):
        with self.assertRaises(ValidationError):self.parse(parts={'word/vbaProject.bin':'x'})
    def test_entity_rejected(self):
        with self.assertRaises(ValidationError):self.parse(parts={'word/document.xml':'<!DOCTYPE x [<!ENTITY e "a">]><x />'})
    def test_utf16_entity_rejected(self):
        from .docx_parser import xml
        with self.assertRaises(ValueError):xml('<!DOCTYPE x [<!ENTITY e "a">]><x />'.encode('utf-16'))
    def test_encrypted_member_rejected(self):
        import struct
        data=bytearray(fixture().read())
        for signature,offset in ((b'PK\x03\x04',6),(b'PK\x01\x02',8)):
            index=data.find(signature)
            flags=struct.unpack_from('<H',data,index+offset)[0]
            struct.pack_into('<H',data,index+offset,flags|1)
        with self.assertRaises(ValidationError):parse_docx(SimpleUploadedFile('encrypted.docx',bytes(data)))
    @override_settings(DOCX_IMPORT_LIMITS={'image_bytes':5})
    def test_image_size_limit(self):
        with self.assertRaises(ValidationError):self.parse(image=True)
    @override_settings(DOCX_IMPORT_LIMITS={'images':0})
    def test_image_count_limit(self):
        with self.assertRaises(ValidationError):self.parse(image=True)
    @override_settings(DOCX_IMPORT_LIMITS={'content_chars':5})
    def test_content_limit(self):
        with self.assertRaises(ValidationError):self.parse()
    @override_settings(DOCX_IMPORT_LIMITS={'questions':1})
    def test_question_limit(self):
        with self.assertRaises(ValidationError):self.parse(lines=['1. Q','a. A','b. B','2. Q','a. A','b. B'])
    def test_automatic_numbering(self):
        numbering='<w:numbering xmlns:w="'+NS['w']+'"><w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num></w:numbering>'
        p='<w:p><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Q</w:t></w:r></w:p>'
        q=self.question(lines=['1.0 S'],extra=p+paragraph('a. A')+paragraph('b. B')+paragraph('KEY')+paragraph('1 A'),parts={'word/numbering.xml':numbering});self.assertEqual(q['source_number'],1)


class DocxWorkflowTests(APITestCase):
    def setUp(self):
        self.storage=tempfile.TemporaryDirectory();self.addCleanup(self.storage.cleanup)
        self.override=override_settings(QUESTION_PRIVATE_ROOT=self.storage.name);self.override.enable();self.addCleanup(self.override.disable)
        # Storage instance is module-global; override its cached location for isolated fixtures.
        from .private_storage import private_storage
        self.storage_patch=patch.object(private_storage,'_location',self.storage.name);self.storage_patch.start();self.addCleanup(self.storage_patch.stop)
        private_storage.__dict__.pop('location',None);private_storage.__dict__.pop('base_location',None)
        self.a=Institution.objects.create(name='A');self.b=Institution.objects.create(name='B')
        self.user=User.objects.create_user('docx@example.test','safe password')
        InstitutionMembership.objects.create(user=self.user,institution=self.a,role='teacher')
        self.other=User.objects.create_user('other-docx@example.test','safe password');InstitutionMembership.objects.create(user=self.other,institution=self.a,role='institution_admin')
        self.subject=Subject.objects.create(institution=self.a,name='Subject',code='S')
        self.foreign_subject=Subject.objects.create(institution=self.b,name='Other',code='S')
        self.client.force_authenticate(self.user)

    def upload(self, **kwargs):
        r=self.client.post('/api/v1/questions/import/docx/preview/',{'file':fixture(**kwargs)},format='multipart');self.assertEqual(r.status_code,201,r.data);return r.data
    def path(self,d):return '/api/v1/questions/import/docx/'+d['import_session_id']+'/'
    def edit(self,d,**changes):
        r=self.client.patch(self.path(d),{'revision':d['revision'],**changes},format='json');self.assertEqual(r.status_code,200,r.data);return r.data
    def confirm(self,d):return self.client.post(self.path(d)+'confirm/',{'revision':d['revision']},format='json')
    def media_status(self,url):
        response=self.client.get(url)
        status=response.status_code
        if response.streaming:
            # TestClient wraps iteration to close the stream without closing TestCase's transaction.
            list(response.streaming_content)
        return status
    def ready(self,**kwargs):return self.edit(self.upload(**kwargs),metadata={'subject':self.subject.pk})

    def test_new_session_seven_day_lifetime_recovery_and_media_security(self):
        data = self.upload(image=True)
        session = DocxImportSession.objects.get(pk=data['import_session_id'])
        self.assertAlmostEqual((session.expires_at-session.created_at).total_seconds(), 7*24*60*60, delta=1)
        media_url = data['sections'][0]['questions'][0]['media'][0]['url']
        with patch('questions.docx_views.timezone.now', return_value=session.created_at+timedelta(days=6)):
            self.assertEqual(self.client.get(self.path(data)).status_code, 200)
            self.assertEqual(self.media_status(media_url), 200)
            self.client.force_authenticate(self.other)
            self.assertEqual(self.client.get(self.path(data)).status_code, 404)
            self.assertEqual(self.media_status(media_url), 404)
            self.client.force_authenticate(self.user)
            self.assertEqual(self.client.get(self.path(data), HTTP_X_INSTITUTION_ID=str(self.b.pk)).status_code, 403)
        with patch('questions.docx_views.timezone.now', return_value=session.expires_at+timedelta(seconds=1)):
            self.assertEqual(self.client.get(self.path(data)).status_code, 400)
            self.assertEqual(self.media_status(media_url), 400)
        session.refresh_from_db()
        self.assertEqual(session.expires_at, data['expires_at'])

    def test_create_subject_and_select_preserves_reviews_and_recovery(self):
        data = self.upload(lines=['1.0 S', '1. Good', 'a. A', 'b. B', '2. Missing', 'a. A', 'b. B', 'KEY', '1 A'])
        data = self.edit(data, question_id='s1q1', changes={'text': 'Saved reviewed wording', 'reviewed': True})
        data = self.edit(data, question_id='s1q2', changes={'included': False})
        self.assertFalse(data['confirmation']['eligible'])
        self.assertEqual(data['confirmation']['unresolved'], 0)
        created = self.client.post('/api/v1/subjects/', {'institution': self.a.pk, 'name': 'Real examination subject', 'code': 'REAL'}, format='json', HTTP_X_INSTITUTION_ID=str(self.a.pk))
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['institution'], self.a.pk)
        choices = self.client.get('/api/v1/questions/import/docx/preview/').data['subjects']
        self.assertIn(created.data['id'], [subject['id'] for subject in choices])
        self.assertNotIn(self.foreign_subject.pk, [subject['id'] for subject in choices])
        selected = self.edit(data, metadata={**data['metadata'], 'subject': created.data['id']})
        self.assertEqual(selected['sections'], data['sections'])
        self.assertEqual(selected['subject_id'], created.data['id'])
        self.assertTrue(selected['confirmation']['eligible'])
        from rest_framework.test import APIClient
        fresh = APIClient(); fresh.force_authenticate(self.user)
        self.assertEqual(fresh.get(self.path(selected)).data, selected)
        recent = fresh.get('/api/v1/questions/import/docx/preview/').data['recent_imports'][0]
        self.assertEqual(recent['subject_id'], created.data['id'])
        self.assertEqual(recent['subject_name'], 'Real examination subject')
        result = self.confirm(selected)
        self.assertEqual(result.status_code, 201)
        question = Question.objects.get()
        self.assertEqual(question.subject_id, created.data['id'])
        self.assertEqual(question.text, 'Saved reviewed wording')
        self.assertEqual(question.status, 'draft')
        self.assertEqual(self.confirm(selected).status_code, 400)
        self.assertEqual(Question.objects.count(), 1)

    def test_failed_subject_creation_leaves_import_work_unchanged(self):
        data = self.upload()
        data = self.edit(data, question_id='s1q1', changes={'text': 'Keep my saved correction'})
        for fields in [{'institution': self.a.pk, 'name': '', 'code': ''},
                       {'institution': self.a.pk, 'name': 'Duplicate', 'code': self.subject.code},
                       {'institution': self.b.pk, 'name': 'Foreign', 'code': 'NO'}]:
            response = self.client.post('/api/v1/subjects/', fields, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.client.get(self.path(data)).data, data)
        self.assertIsNone(data['subject_id'])
        self.assertEqual(Subject.objects.count(), 2)

    def test_subject_is_explicit_persisted_changeable_and_clearable(self):
        data = self.upload()
        self.assertIsNone(data['subject_id'])
        self.assertIsNone(data['subject_name'])
        self.assertIsNone(data['metadata']['subject'])
        self.assertFalse(data['confirmation']['eligible'])
        self.assertIn('subject_required', [b['code'] for b in data['confirmation']['blockers']])
        data = self.edit(data, metadata={'subject': str(self.subject.pk)})
        self.assertEqual(data['subject_id'], self.subject.pk)
        self.assertEqual(data['subject_name'], self.subject.name)
        self.assertEqual(self.client.get(self.path(data)).data, data)
        recent = self.client.get('/api/v1/questions/import/docx/preview/').data['recent_imports'][0]
        self.assertEqual(recent['subject_id'], self.subject.pk)
        self.assertEqual(recent['subject_name'], self.subject.name)
        second = Subject.objects.create(institution=self.a, name='Second', code='SECOND')
        data = self.edit(data, metadata={'subject': second.pk})
        self.assertEqual(self.client.get(self.path(data)).data['subject_id'], second.pk)
        for invalid in [self.foreign_subject.pk, 999999]:
            rejected = self.client.patch(self.path(data), {'revision': data['revision'], 'metadata': {'subject': invalid}}, format='json')
            self.assertEqual(rejected.status_code, 400)
            self.assertEqual(self.client.get(self.path(data)).data, data)
        data = self.edit(data, metadata={'subject': None, 'topic': None})
        self.assertIsNone(self.client.get(self.path(data)).data['subject_id'])
        self.assertFalse(data['confirmation']['eligible'])

    def test_shared_eligibility_excludes_errors_and_uses_persisted_subject(self):
        data = self.ready(lines=['1.0 S', '1. Good', 'a. A', 'b. B', '2. Missing', 'a. A', 'b. B', 'KEY', '1 A'])
        self.assertEqual(data['confirmation']['unresolved'], 1)
        self.assertFalse(data['confirmation']['eligible'])
        rejected = self.confirm(data)
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.data['confirmation'], data['confirmation'])
        data = self.edit(data, question_id='s1q2', changes={'included': False})
        self.assertEqual(data['confirmation']['ready'], 1)
        self.assertEqual(data['confirmation']['excluded'], 1)
        self.assertEqual(data['confirmation']['unresolved'], 0)
        self.assertTrue(data['confirmation']['eligible'])
        session = DocxImportSession.objects.get(pk=data['import_session_id'])
        before = (session.preview, session.metadata, session.revision)
        self.assertEqual(self.client.get(self.path(data)).data, data)
        session.refresh_from_db()
        self.assertEqual((session.preview, session.metadata, session.revision), before)
        self.assertEqual(self.confirm(data).status_code, 201)
        question = Question.objects.get()
        self.assertEqual(question.subject_id, self.subject.pk)
        self.assertEqual(question.status, 'draft')
        self.assertEqual(self.confirm(data).status_code, 400)
        self.assertEqual(Question.objects.count(), 1)

    def test_normal_question_validation_is_in_eligibility_before_confirmation(self):
        data = self.ready()
        data = self.edit(data, question_id='s1q1', changes={'question_type': 'true_false',
            'options': [{'label': 'A', 'text': 'True'}, {'label': 'B', 'text': 'False'}, {'label': 'C', 'text': 'True'}]})
        self.assertFalse(data['confirmation']['eligible'])
        self.assertIn('question_invalid', [b['code'] for b in data['confirmation']['blockers']])
        rejected = self.confirm(data)
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.data['confirmation'], data['confirmation'])
        self.assertEqual(Question.objects.count(), 0)

    def test_preview_does_not_write_bank_and_has_audit(self):
        d=self.upload();self.assertEqual(Question.objects.count(),0);self.assertEqual(DocxImportSession.objects.count(),1);self.assertTrue(AuditEvent.objects.filter(metadata__action='docx_preview_created').exists());self.assertEqual(d['summary']['questions_detected'],1)
    def test_complete_preview_collection_includes_later_section_review_and_errors(self):
        # Small generated OOXML represents the pilot's distribution, without its content.
        distributions = [(26, 2, 0), (14, 1, 5), (17, 3, 0), (20, 0, 0),
                         (20, 0, 0), (0, 0, 20), (15, 5, 0), (20, 0, 0), (0, 0, 3)]
        lines = []
        for index, (ready, review, errors) in enumerate(distributions, 1):
            lines.append(f'{index}.0 Section {index}')
            count = ready + review + errors
            for number in range(1, count + 1):
                lines.append(f'{number}. Section {index} question {number}')
                if ready < number <= ready + review:
                    lines.append('a. Alpha b. Beta')
                elif number > ready + review and index == 2:
                    lines.extend(['a. Alpha', 'a. Repeated marker'])
                else:
                    lines.extend(['a. Alpha', 'b. Beta'])
            if index not in {6, 9}:
                lines.append('KEY')
                lines.extend(f'{number} A' for number in range(1, count + 1))
        uploaded = self.upload(lines=lines)
        response = self.client.get(self.path(uploaded), {'page': 2, 'status': 'error'})
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertNotIn('results', data)
        self.assertNotIn('next', data)
        questions = [q for section in data['sections'] for q in section['questions']]
        self.assertEqual(len(questions), 171)
        self.assertEqual([q['id'] for q in questions],
                         [q['id'] for section in uploaded['sections'] for q in section['questions']])
        for status, summary_key, count in [('ready', 'ready_count', 132),
                                            ('needs_review', 'review_count', 11),
                                            ('error', 'error_count', 28)]:
            self.assertEqual(data['summary'][summary_key], count)
            self.assertEqual(sum(q['readiness'] == status for q in questions), count)
        missing = [q for q in questions if not q['correct_answer']]
        self.assertEqual(len(missing), 23)
        for question in missing:
            self.assertTrue(question['text'])
            self.assertTrue(question['options'])
            self.assertIn('A valid correct answer is required.', question['errors'])
        resolved = self.edit(data, question_id='s1q27', changes={'reviewed': True})
        self.assertEqual(resolved['summary']['ready_count'], 133)
        self.assertEqual(resolved['summary']['review_count'], 10)
        excluded = self.edit(resolved, question_id='s1q28', changes={'included': False})
        self.assertEqual(excluded['summary']['questions_detected'], 171)
        self.assertEqual(excluded['summary']['review_count'], 10)
        self.assertFalse(excluded['sections'][0]['questions'][27]['included'])
        corrected = self.edit(excluded, question_id='s6q1', changes={'correct_answer': 'A'})
        self.assertEqual(corrected['summary']['error_count'], 27)
        self.assertEqual(corrected['summary']['ready_count'], 134)

    def test_review_work_survives_fresh_client_refetch(self):
        from rest_framework.test import APIClient
        data = self.ready(lines=['1.0 S', '1. In the sample above?', 'a. A', 'b. B',
                                 '2. Missing answer', 'a. A', 'b. B', 'KEY', '1 A'], image=True)
        data = self.edit(data, question_id='s1q1', changes={'text': 'Saved corrected text',
            'options': [{'label': 'A', 'text': 'True'}, {'label': 'B', 'text': 'False'}],
            'correct_answer': 'B', 'question_type': 'true_false', 'reviewed': True})
        data = self.edit(data, question_id='s1q2', changes={'included': False})
        data = self.edit(data, section_id='s1', section_title='Saved section')
        fresh = APIClient(); fresh.force_authenticate(self.user)
        restored = fresh.get(self.path(data))
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.data, data)
        question = restored.data['sections'][0]['questions'][0]
        self.assertEqual(question['text'], 'Saved corrected text')
        self.assertEqual(question['options'][1]['text'], 'False')
        self.assertEqual(question['correct_answer'], 'B')
        self.assertEqual(question['question_type'], 'true_false')
        self.assertEqual(question['readiness'], 'ready')
        self.assertTrue(question['media'])
        self.assertFalse(restored.data['sections'][0]['questions'][1]['included'])
        self.assertEqual(Question.objects.count(), 0)

    def test_recent_imports_are_owned_tenant_scoped_and_unexpired(self):
        first = self.upload()
        expired = self.upload()
        DocxImportSession.objects.filter(pk=expired['import_session_id']).update(expires_at=timezone.now()-timedelta(seconds=1))
        other = DocxImportSession.objects.get(pk=first['import_session_id'])
        other.pk = None; other.uploaded_by = self.other; other.save()
        foreign = DocxImportSession.objects.get(pk=first['import_session_id'])
        foreign.pk = None; foreign.institution = self.b; foreign.save()
        response = self.client.get('/api/v1/questions/import/docx/preview/')
        self.assertEqual([r['import_session_id'] for r in response.data['recent_imports']], [first['import_session_id']])
        self.assertNotIn('preview', response.data['recent_imports'][0])
        self.assertEqual(self.client.get(self.path(expired)).status_code, 400)
        self.assertIn('expired', self.client.get(self.path(expired)).data['detail'])

    def test_completion_receipt_survives_refetch_and_retry_creates_no_duplicates(self):
        data = self.ready(lines=['1.0 S', '1. Good', 'a. A', 'b. B',
                                 '2. Excluded error', 'a. A', 'b. B', 'KEY', '1 A'])
        self.assertEqual(self.confirm(data).status_code, 400)
        data = self.edit(data, question_id='s1q2', changes={'included': False})
        result = self.confirm(data)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.data['imported_count'], 1)
        for _ in range(2):
            resumed = self.client.get(self.path(data))
            self.assertEqual(resumed.status_code, 200)
            self.assertEqual(resumed.data['status'], 'completed')
            self.assertEqual(resumed.data['imported_count'], 1)
            self.assertEqual(resumed.data['created_question_ids'], result.data['created_question_ids'])
            self.assertEqual(self.confirm(data).status_code, 400)
        self.assertEqual(Question.objects.count(), 1)
        self.assertEqual(Question.objects.get().status, 'draft')
        self.assertEqual(self.client.get('/api/v1/questions/import/docx/preview/').data['recent_imports'], [])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.path(data)).status_code, 404)

    def test_confirm_creates_draft_and_correct_options_audit(self):
        d=self.ready();r=self.confirm(d);self.assertEqual(r.status_code,201,r.data);q=Question.objects.get();self.assertEqual(q.status,'draft');self.assertEqual(q.options.filter(is_correct=True).get().text,'Beta');self.assertEqual(q.source_metadata['section_title'],'1.0 Section');self.assertTrue(AuditEvent.objects.filter(metadata__action='docx_confirmed').exists())
    def test_duplicate_confirmation(self):
        d=self.ready();self.assertEqual(self.confirm(d).status_code,201);self.assertEqual(self.confirm(d).status_code,400);self.assertEqual(Question.objects.count(),1)
    def test_expiry(self):
        d=self.ready();DocxImportSession.objects.update(expires_at=timezone.now()-timedelta(seconds=1));self.assertEqual(self.confirm(d).status_code,400)
    def test_ownership_even_other_admin(self):
        d=self.upload();self.client.force_authenticate(self.other);self.assertEqual(self.client.get(self.path(d)).status_code,404)
    def test_cross_tenant(self):
        d=self.upload();InstitutionMembership.objects.create(user=self.user,institution=self.b,role='teacher');self.assertEqual(self.client.get(self.path(d),HTTP_X_INSTITUTION_ID=str(self.b.pk)).status_code,404)
    def test_student_denied(self):
        InstitutionMembership.objects.filter(user=self.user).update(role='student');r=self.client.post('/api/v1/questions/import/docx/preview/',{'file':fixture()},format='multipart');self.assertEqual(r.status_code,403)
    def test_inactive_membership_denied(self):
        InstitutionMembership.objects.filter(user=self.user).update(is_active=False);self.assertEqual(self.client.post('/api/v1/questions/import/docx/preview/',{'file':fixture()},format='multipart').status_code,403)
    def test_foreign_subject_denied(self):
        d=self.upload();r=self.client.patch(self.path(d),{'revision':0,'metadata':{'subject':self.foreign_subject.pk}},format='json');self.assertEqual(r.status_code,400)
    def test_import_subject_choices_selected_tenant_only(self):
        response=self.client.get('/api/v1/questions/import/docx/preview/')
        self.assertEqual(response.status_code,200)
        self.assertEqual([s['id'] for s in response.data['subjects']],[self.subject.pk])
    def test_review_edit_corrects_missing_answer(self):
        d=self.ready(lines=['1.0 S','1. Q','a. A','b. B']);self.assertEqual(self.confirm(d).status_code,400)
        d=self.edit(d,question_id='s1q1',changes={'correct_answer':'A','text':'Corrected text'});self.assertTrue(d['sections'][0]['questions'][0]['modified']);self.assertEqual(self.confirm(d).status_code,201)
    def test_exclusion(self):
        d=self.ready(lines=['1.0 S','1. Q','a. A','b. B','2. Q','a. A','b. B','KEY','1 A']);d=self.edit(d,question_id='s1q2',changes={'included':False});self.assertEqual(self.confirm(d).data['imported_count'],1)
    def test_transaction_rollback(self):
        d=self.ready()
        with patch('questions.docx_views.record_event',side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):self.confirm(d)
        self.assertEqual(Question.objects.count(),0);self.assertIsNone(DocxImportSession.objects.get().confirmed_at)
    def test_revision_rejects_stale_confirm(self):
        d=self.upload();self.edit(d,metadata={'subject':self.subject.pk});self.assertEqual(self.confirm(d).status_code,400)
    def test_no_client_reconstructed_confirmation(self):
        d=self.ready();r=self.client.post(self.path(d)+'confirm/',{'revision':d['revision'],'questions':[]},format='json');self.assertEqual(r.status_code,400)
    def test_private_media_owner_only_and_promoted_without_copy(self):
        d=self.ready(lines=['1.0 S','1. In the sample above?','a. A','b. B','KEY','1 A'],image=True);asset=QuestionMedia.objects.get();url=d['sections'][0]['questions'][0]['media'][0]['url'];self.assertEqual(self.media_status(url),200)
        self.client.force_authenticate(self.other);self.assertEqual(self.media_status(url),404)
        self.client.force_authenticate(self.user);filename=asset.file.name;self.assertEqual(self.confirm(d).status_code,201);asset.refresh_from_db();self.assertIsNone(asset.import_session_id);self.assertEqual(asset.file.name,filename);self.assertEqual(self.media_status(url),200)
        self.client.force_authenticate(None);self.assertEqual(self.media_status(url),404)
    def test_anonymous_preview_media_not_available(self):
        d=self.upload(image=True);url=d['sections'][0]['questions'][0]['media'][0]['url'];self.client.force_authenticate(None);self.assertEqual(self.media_status(url),404)
    def test_candidate_media_allowlist_has_no_keys(self):
        from .docx_views import media_representation
        d=self.ready(lines=['1.0 S','1. In the sample above?','a. A','b. B','KEY','1 A'],image=True);self.confirm(d);data=media_representation(Question.objects.get());self.assertEqual(set(data[0]),{'id','url','alt_text','caption','order'});self.assertNotIn('correct',str(data))
    def make_attempt(self, question, access_mode='assigned_group'):
        from assessments.models import Assessment
        from attempts.models import Attempt, AttemptQuestion, AttemptQuestionOption
        from candidates.models import Candidate
        candidate=Candidate.objects.create(institution=self.a,user=self.user,candidate_id='DOCX-C',first_name='Candidate',last_name='Test')
        assessment=Assessment.objects.create(institution=self.a,subject=self.subject,created_by=self.user,title='Media examination',assessment_type='test',duration_minutes=30,candidate_access=access_mode)
        now=timezone.now()
        attempt=Attempt.objects.create(institution=self.a,assessment=assessment,candidate=candidate,attempt_number=1,started_at=now,expires_at=now+timedelta(minutes=30),last_activity_at=now)
        row=AttemptQuestion.objects.create(attempt=attempt,question=question,order=1)
        for option in question.options.all():AttemptQuestionOption.objects.create(attempt_question=row,option=option,order=option.order)
        return attempt,row

    def test_candidate_serializer_and_private_media_require_owned_active_attempt(self):
        from attempts.serializers import CandidateExamQuestionSerializer
        d=self.ready(lines=['1.0 S','1. In the sample above?','a. A','b. B','KEY','1 A'],image=True);self.confirm(d)
        attempt,row=self.make_attempt(Question.objects.get())
        data=CandidateExamQuestionSerializer(row).data
        self.assertEqual(set(data['question']),{'id','text','question_type','media'})
        self.assertNotIn('is_correct',str(data));self.assertNotIn('explanation',str(data));self.assertNotIn('source_metadata',str(data))
        InstitutionMembership.objects.filter(user=self.user).delete()
        url=data['question']['media'][0]['url'];self.assertEqual(self.media_status(url),200)
        attempt.status='submitted';attempt.save(update_fields=['status']);self.assertEqual(self.media_status(url),404)

    def test_media_and_source_content_frozen_after_attempt(self):
        from django.core.exceptions import ValidationError as ModelValidationError
        d=self.ready(lines=['1.0 S','1. In the sample above?','a. A','b. B','KEY','1 A'],image=True);self.confirm(d)
        q=Question.objects.get();self.make_attempt(q);asset=q.media.get();asset.alt_text='Altered'
        with self.assertRaises(ModelValidationError):asset.save()
        with self.assertRaises(ModelValidationError):asset.delete()
        q.source_metadata={'changed':True}
        with self.assertRaises(ModelValidationError):q.save()
    def test_quick_media_uses_existing_session_and_version_invalidation(self):
        from django.contrib.auth.hashers import make_password
        from assessments.models import QuickExamConfiguration, QuickExamCredential, QuickExamSession
        from assessments.quick_sessions import COOKIE_NAME, token_digest
        d=self.ready(lines=['1.0 S','1. In the sample above?','a. A','b. B','KEY','1 A'],image=True);self.confirm(d)
        q=Question.objects.get();attempt,_=self.make_attempt(q,'access_code')
        config=QuickExamConfiguration.objects.create(assessment=attempt.assessment,exam_code='DOCX-MEDIA',enabled=True)
        credential=QuickExamCredential.objects.create(configuration=config,candidate=attempt.candidate,pin_hash=make_password('test media password'))
        token='q'*43
        QuickExamSession.objects.create(credential=credential,token_digest=token_digest(token),credential_version=credential.version,configuration_version=config.session_version,expires_at=timezone.now()+timedelta(hours=1))
        self.client.force_authenticate(None);url=f'/api/v1/quick-exam/media/{q.media.get().pk}/'
        self.assertEqual(self.media_status(url),401)
        self.client.cookies[COOKIE_NAME]=token
        self.assertEqual(self.media_status(url),200)
        credential.version+=1;credential.save(update_fields=['version'])
        self.assertEqual(self.media_status(url),401)
    def test_review_warning_blocks_until_explicit_review(self):
        d=self.ready(image=True);self.assertEqual(self.confirm(d).status_code,400);d=self.edit(d,question_id='s1q1',changes={'reviewed':True});self.assertEqual(self.confirm(d).status_code,201)
    def test_cleanup_removes_expired_uploads(self):
        from django.core.management import call_command
        self.upload(image=True);asset=QuestionMedia.objects.get();storage,name=asset.file.storage,asset.file.name
        DocxImportSession.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.captureOnCommitCallbacks(execute=True):call_command('cleanup_docx_imports')
        self.assertFalse(DocxImportSession.objects.exists());self.assertFalse(QuestionMedia.objects.exists());self.assertFalse(storage.exists(name))
    def test_draft_question_deletion_removes_media_without_null_owner(self):
        d=self.ready(lines=['1.0 S','1. In the sample above?','a. A','b. B','KEY','1 A'],image=True);self.confirm(d)
        asset=QuestionMedia.objects.get();storage,name=asset.file.storage,asset.file.name
        with self.captureOnCommitCallbacks(execute=True):Question.objects.get().delete()
        self.assertFalse(QuestionMedia.objects.exists())
        self.assertFalse(storage.exists(name))
