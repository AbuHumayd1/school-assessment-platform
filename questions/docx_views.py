import copy
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import record_event
from assessments.quick_authentication import QuickExamAuthentication
from institutions.workspace_access import enforce_workspace_mode
from .docx_parser import limits, parse_docx, validate_preview
from .models import DocxImportSession, QuestionMedia
from .import_reconciliation import canonicalize, classify_block, initialize_blocks, template_bytes
from .permissions import CanManageQuestionBank
from .serializers import QuestionSerializer
from .tenancy import has_question_role, READ_ROLES, write_institution_for_request
from .answer_keys import answer_labels, assign_answer, parse_answer_key, recompute_matches, replace_key, remove_key, valid_labels


def review_document(session):
    return initialize_blocks(canonicalize(copy.deepcopy(session.preview), str(session.pk)))


def import_mode(session):
    # Legacy sessions remain usable without rewriting historical metadata.
    return session.metadata.get('import_mode') or ('separate_key' if session.preview.get('separate_answer_key') else 'embedded_key')


def require_separate_mode(session):
    if import_mode(session) != 'separate_key':
        raise ValidationError({'detail': 'This import uses embedded answers. Start a separate-key import to upload a key.'})
    session.metadata.setdefault('import_mode', 'separate_key')


def private_response(response):
    response['Cache-Control'] = 'no-store, private'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def session_for(request, session_id, *, lock=False, allow_completed=False):
    if not request.user.is_authenticated: raise NotFound()
    institution = write_institution_for_request(request)
    queryset = DocxImportSession.objects.select_for_update() if lock else DocxImportSession.objects
    session = get_object_or_404(queryset, pk=session_id, institution=institution, uploaded_by=request.user)
    if session.expires_at <= timezone.now(): raise ValidationError({'detail': 'This import session has expired. Upload the document again.'})
    if session.confirmed_at and not allow_completed: raise ValidationError({'detail': 'This import session has already been confirmed.'})
    return session


def session_data(session, request):
    if session.confirmed_at:
        return {'import_session_id': str(session.pk), 'status': 'completed',
                'confirmed_at': session.confirmed_at, **session.metadata.get('completion', {})}
    eligibility, _, data = import_eligibility(request, session)
    assets = {m.parsed_id: m for m in session.media.all()}
    for section in data['sections']:
        for question in section['questions']:
            for media in question['media']:
                asset = assets.get(media['id'])
                if asset and media['status'] == 'converted': media['url'] = f'/api/v1/questions/media/{asset.pk}/?institution={session.institution_id}'
    return {**data, 'import_mode': import_mode(session), 'import_session_id': str(session.pk), 'revision': session.revision,
            'expires_at': session.expires_at, 'metadata': {**{k:v for k,v in session.metadata.items() if k not in {'import_mode', 'review_updated_at'}}, 'subject': eligibility['subject_id']},
            'subject_id': eligibility['subject_id'], 'subject_name': eligibility['subject_name'],
            'confirmation': eligibility}


def metadata_for(request, institution, data, *, required=False):
    # Reuse the normal Question serializer's tenant/type/marks validation at confirmation.
    allowed = {'subject', 'topic', 'difficulty', 'default_marks'}
    if not isinstance(data, dict): raise ValidationError({'metadata': 'Use an object containing supported metadata.'})
    if set(data) - allowed: raise ValidationError({'metadata': 'Unsupported import metadata.'})
    result = dict(data)
    result['subject'] = result.get('subject') or None
    if required and not result.get('subject'): raise ValidationError({'subject': 'Select or create a subject before importing.'})
    if result.get('subject'):
        serializer = QuestionSerializer(data=dict(subject=result['subject'], topic=result.get('topic') or None,
            difficulty=result.get('difficulty', 'medium'), marks=result.get('default_marks', '1.00'),
            text='Metadata validation', question_type='multiple_choice',
            options=[dict(text='A', order=1, is_correct=True), dict(text='B', order=2, is_correct=False)]),
            context={'request': request, 'institution': institution})
        serializer.is_valid(raise_exception=True)
        result['subject'] = serializer.validated_data['subject'].pk
    return result


def subject_selection(session):
    from subjects.models import Subject
    subject_id = session.metadata.get('subject') or None
    subject = Subject.objects.filter(pk=subject_id, institution_id=session.institution_id).first() if subject_id else None
    return subject_id, subject.name if subject else None


def import_eligibility(request, session):
    """One read-only eligibility/preparation contract, also used by atomic confirmation."""
    document = validate_preview(review_document(session))
    questions = [q for section in document['sections'] for q in section['questions']]
    included = [(section, q) for section in document['sections'] for q in section['questions'] if q['included']]
    subject_id, subject_name = subject_selection(session)
    state = {'ready': sum(q['readiness'] == 'ready' for _, q in included),
        'included': len(included), 'excluded': len(questions) - len(included),
        'unresolved': sum(q['readiness'] != 'ready' for _, q in included),
        'errors': sum(q['readiness'] == 'error' for _, q in included),
        'review': sum(q['readiness'] == 'needs_review' for _, q in included),
        'subject_id': subject_id, 'subject_name': subject_name, 'blockers': []}
    blockers = state['blockers']
    if not included: blockers.append({'code': 'no_included', 'message': 'No included questions.'})
    if state['unresolved']: blockers.append({'code': 'unresolved', 'count': state['unresolved'],
        'message': 'Correct, review or exclude every unresolved included question.'})
    key = document.get('separate_answer_key')
    if import_mode(session) == 'separate_key':
        covered = {i.get('question_id') for i in key['entries'] if i['status'] in {'matched', 'duplicate'}} if key else set()
        if any(valid_labels(q) and q.get('answer_source') not in {'separate_key', 'manual_review', 'manual_link', 'generated_template'} and q['id'] not in covered for _, q in included):
            blockers.append({'code': 'separate_answer_required', 'message': 'Upload a separate answer key or explicitly review the correct answers.'})
    unresolved_entries = sum(document.get(name, {}).get('summary', {}).get('blocker_count', 0) for name in ('embedded_answer_key', 'separate_answer_key'))
    if unresolved_entries:
        blockers.append({'code': 'answer_key_review', 'count': unresolved_entries,
                         'message': 'Resolve or exclude every unresolved answer-key entry.'})
    decisions = [b for b in document.get('blocks', []) if b.get('needs_classification')]
    if decisions:
        blockers.append({'code': 'classification_required', 'count': len(decisions),
                         'message': 'Tell us whether the highlighted document parts contain questions or answers, or should be ignored.'})
    # Matching problems are already counted above. Old section-reference notices
    # cease to block once every embedded entry has been explicitly resolved.
    matching_notices = {'Answer-key section is unknown or ambiguous; correct affected answers manually.',
                        'Answer-key section is ambiguous; correct affected answers manually.'}
    source_issues = [e for e in document['key_errors'] if not e.get('reconciliation') and
                    not (e['message'] in matching_notices and document.get('embedded_answer_key', {}).get('entries') and
                         not document.get('embedded_answer_key', {}).get('summary', {}).get('blocker_count', 0))]
    if source_issues and not document.get('source_reviewed'):
        blockers.append({'code': 'document_review', 'count': len(source_issues),
                         'message': 'Check the highlighted document content against your Word file, then confirm that you have reviewed it.'})
    state['document_issues'] = source_issues
    if not subject_id: blockers.append({'code': 'subject_required', 'message': 'Select or create a subject before importing.'})
    metadata = None
    if subject_id:
        try: metadata = metadata_for(request, session.institution, {k:v for k,v in session.metadata.items() if k in {'subject','topic','difficulty','default_marks'}}, required=True)
        except ValidationError as error:
            blockers.append({'code': 'metadata_invalid', 'message': 'Import metadata requires correction.', 'details': error.detail})
    pending = []
    if not blockers:
        for section, q in included:
            payload = dict(text=q.get('equation_replacement') or q['text'], question_type=q['question_type'],
                subject=metadata['subject'], topic=metadata.get('topic') or None, difficulty=metadata.get('difficulty','medium'),
                marks=metadata.get('default_marks','1.00'), source='DOCX',
                options=[dict(text=o['text'],order=i,is_correct=o['label'] in valid_labels(q)) for i,o in enumerate(q['options'],1)])
            serializer = QuestionSerializer(data=payload, context={'request': request, 'institution': session.institution})
            if not serializer.is_valid():
                blockers.append({'code': 'question_invalid', 'question_id': q['id'],
                    'message': 'Question validation requires correction.', 'details': serializer.errors})
            else: pending.append((section,q,serializer))
    state['eligible'] = not blockers
    state['additional_issues'] = sum(b.get('count', 1) for b in blockers if b['code'] != 'unresolved')
    state['attention_count'] = state['unresolved'] + state['additional_issues']
    state['status'] = 'eligible' if state['eligible'] else 'blocked'
    return state, pending, document


class DocxPreviewView(APIView):
    permission_classes = [CanManageQuestionBank]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        from subjects.models import Subject
        institution = write_institution_for_request(request)
        recent = DocxImportSession.objects.filter(institution=institution, uploaded_by=request.user,
            confirmed_at__isnull=True, expires_at__gt=timezone.now()).order_by('-created_at')
        return private_response(Response({
            'subjects': list(Subject.objects.filter(institution=institution).order_by('name').values('id','name','code')),
            'recent_imports': [{'import_session_id': str(s.pk), 'created_at': s.created_at,
                'revision': s.revision, 'import_mode': import_mode(s), 'status': 'unfinished',
                'updated_at': s.metadata.get('review_updated_at', s.created_at),
                'filename': s.preview.get('source_document', {}).get('filename', ''),
                'summary': summary,
                'answer_key_document': s.preview.get('separate_answer_key', {}).get('source_document'),
                'expires_at': s.expires_at, 'questions_detected': summary['questions_detected'],
                'subject_id': subject_selection(s)[0], 'subject_name': subject_selection(s)[1]}
                for s in recent for summary in [validate_preview(review_document(s))['summary']]]}))

    def post(self, request):
        institution = write_institution_for_request(request)
        mode = request.data.get('import_mode', 'embedded_key')
        if mode not in {'embedded_key', 'separate_key'}:
            raise ValidationError({'import_mode': 'Choose embedded answers or a separate answer key.'})
        metadata = metadata_for(request, institution, {k: request.data[k] for k in ('subject', 'topic', 'difficulty', 'default_marks') if request.data.get(k)})
        metadata['import_mode'] = mode
        document, binaries = parse_docx(request.FILES.get('file'))
        saved_files = []
        try:
            with transaction.atomic():
                session = DocxImportSession.objects.create(institution=institution, uploaded_by=request.user,
                    preview=document, metadata=metadata,
                    expires_at=timezone.now()+timedelta(days=7))
                items = {m['id']: m for s in document['sections'] for q in s['questions'] for m in q['media']}
                for parsed_id, binary in binaries.items():
                    asset = QuestionMedia(import_session=session, parsed_id=parsed_id,
                        source_metadata=items.get(parsed_id, {'status': 'needs_review'}))
                    asset.file.save('asset', ContentFile(binary), save=False)
                    saved_files.append((asset.file.storage, asset.file.name))
                    asset.save()
                record_event(institution=institution, actor=request.user, event_type='question_import', resource=session,
                    metadata={'action': 'docx_preview_created', 'questions': document['summary']['questions_detected']})
                result = session_data(session, request)
        except Exception:
            for storage, name in saved_files: storage.delete(name)
            raise
        return private_response(Response(result, status=201))


class DocxReviewView(APIView):
    permission_classes = [CanManageQuestionBank]

    @transaction.atomic
    def delete(self, request, session_id):
        session = session_for(request, session_id, lock=True)
        if not isinstance(request.data, dict) or set(request.data) != {'revision'} or type(request.data['revision']) is not int or request.data['revision'] != session.revision:
            raise ValidationError({'detail': 'Delete the current server preview revision.'})
        record_event(institution=session.institution, actor=request.user, event_type='question_import', resource=session,
                     metadata={'action': 'docx_import_deleted', 'revision': session.revision})
        session.delete()
        return private_response(Response(status=204))

    def get(self, request, session_id):
        return private_response(Response(session_data(session_for(request, session_id, allow_completed=True), request)))

    @transaction.atomic
    def patch(self, request, session_id):
        session = session_for(request, session_id, lock=True)
        if not isinstance(request.data, dict): raise ValidationError({'detail': 'Use a review object.'})
        if set(request.data) - {'revision', 'question_id', 'changes', 'section_id', 'section_title', 'metadata', 'source_reviewed'}:
            raise ValidationError({'detail': 'Unsupported review fields.'})
        if request.data.get('revision') != session.revision: raise ValidationError({'detail': 'The preview changed. Reload before saving.'})
        document = review_document(session)
        if 'metadata' in request.data:
            session.metadata = {**{k:v for k,v in session.metadata.items() if k in {'import_mode','review_updated_at'}},
                                **metadata_for(request, session.institution, request.data['metadata'])}
        if 'source_reviewed' in request.data:
            if not isinstance(request.data['source_reviewed'], bool): raise ValidationError({'source_reviewed': 'Use a boolean.'})
            document['source_reviewed'] = request.data['source_reviewed']
        if 'section_title' in request.data:
            title = request.data['section_title']
            if not isinstance(title, str) or not title.strip() or len(title) > 500: raise ValidationError({'section_title': 'Use a non-empty title of at most 500 characters.'})
            section = next((s for s in document['sections'] if s['id'] == request.data.get('section_id')), None)
            if section is None: raise NotFound()
            section.setdefault('original_title', section['source_title'])
            section['source_title'] = title
        if 'question_id' in request.data:
            question = next((q for s in document['sections'] for q in s['questions'] if q['id']==request.data['question_id']), None)
            if question is None: raise NotFound()
            changes = request.data.get('changes', {})
            if not isinstance(changes, dict) or set(changes)-{'text','options','correct_answer','question_type','included','reviewed','equation_replacement'}: raise ValidationError({'changes': 'Unsupported review fields.'})
            for key, value in changes.items():
                if key in {'included','reviewed'}:
                    if not isinstance(value, bool): raise ValidationError({key: 'Use a boolean.'})
                elif key == 'options':
                    if not isinstance(value, list) or not 2 <= len(value) <= 5 or any(not isinstance(o, dict) or set(o) != {'label','text'} or not isinstance(o['label'], str) or o['label'] not in list('ABCDE') or not isinstance(o['text'], str) or len(o['text']) > limits()['item_chars'] for o in value):
                        raise ValidationError({'options': 'Use two to five labeled text options.'})
                elif key == 'correct_answer' and isinstance(value, list):
                    if len(value) > 5 or any(not isinstance(v, str) or v not in list('ABCDE') for v in value):
                        raise ValidationError({'correct_answer': 'Use supported option labels.'})
                elif not isinstance(value, str) or len(value) > limits()['item_chars']: raise ValidationError({key: 'Use bounded text.'})
                question[key] = value
            question['modified'] = True
            question['review_revision'] = session.revision + 1
            if 'correct_answer' in changes:
                question['answer_source'] = 'manual_review'
                question['answer_review_revision'] = session.revision + 1
                question.pop('answer_manual_entry_id', None)
                record_event(institution=session.institution, actor=request.user, event_type='question_import', resource=session,
                             metadata={'action': 'answer_match_corrected', 'source_question_id': question['id'], 'revision': session.revision + 1})
        recompute_matches(document, session.revision + 1)
        session.preview = validate_preview(document)
        session.revision += 1
        session.metadata['review_updated_at'] = timezone.now().isoformat()
        session.save(update_fields=['preview','metadata','revision'])
        return private_response(Response(session_data(session, request)))


class DocxAnswerKeyView(APIView):
    permission_classes = [CanManageQuestionBank]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @transaction.atomic
    def post(self, request, session_id):
        import json
        session = session_for(request, session_id, lock=True)
        require_separate_mode(session)
        try:
            revision = int(request.data.get('revision', -1))
            columns = json.loads(request.data['columns']) if request.data.get('columns') else None
        except (ValueError, TypeError):
            raise ValidationError({'detail': 'Use the current revision and valid column mapping.'}) from None
        if revision != session.revision:
            raise ValidationError({'detail': 'The preview changed. Reload before saving.'})
        document = review_document(session)
        key = parse_answer_key(request.FILES.get('file'), sheet=request.data.get('sheet') or None,
                               columns=columns, known_sections=[s['source_title'] for s in document['sections']])
        tokens = {q.get('mapping_token') for section in document['sections'] for q in section['questions']}
        provided = [i['mapping_token'] for i in key['entries'] if i.get('mapping_token')]
        if any(token not in tokens for token in provided) or len(provided) != len(set(provided)):
            raise ValidationError({'file': 'Unknown, foreign or duplicate Question ID. Use the template for this import session.'})
        key['uploaded_at'] = timezone.now().isoformat()
        replacing = bool(document.get('separate_answer_key'))
        replace_key(document, key, session.revision + 1)
        session.preview = validate_preview(document)
        session.revision += 1
        session.metadata['review_updated_at'] = timezone.now().isoformat()
        session.save(update_fields=['preview', 'revision', 'metadata'])
        metadata = {'action': 'answer_key_replaced' if replacing else 'answer_key_uploaded',
                    'revision': session.revision, 'file_type': key['source_document']['file_type'],
                    'sha256': key['source_document']['sha256'], 'parsed_entry_count': key['parsed_entry_count']}
        record_event(institution=session.institution, actor=request.user, event_type='question_import', resource=session, metadata=metadata)
        record_event(institution=session.institution, actor=request.user, event_type='question_import', resource=session,
                     metadata={'action': 'answer_key_parsed', 'revision': session.revision, **key['summary']})
        return private_response(Response(session_data(session, request)))

    @transaction.atomic
    def delete(self, request, session_id):
        session = session_for(request, session_id, lock=True)
        require_separate_mode(session)
        if not isinstance(request.data, dict) or set(request.data) != {'revision'} or type(request.data['revision']) is not int or request.data['revision'] != session.revision:
            raise ValidationError({'detail': 'Remove the key from the current server preview revision.'})
        if not session.preview.get('separate_answer_key'):
            raise ValidationError({'detail': 'No answer key uploaded.'})
        session.preview = validate_preview(remove_key(copy.deepcopy(session.preview), session.revision + 1))
        session.revision += 1
        session.metadata['review_updated_at'] = timezone.now().isoformat()
        session.save(update_fields=['preview', 'revision', 'metadata'])
        record_event(institution=session.institution, actor=request.user, event_type='question_import', resource=session,
                     metadata={'action': 'answer_key_removed', 'revision': session.revision})
        return private_response(Response(session_data(session, request)))

    def get(self, request, session_id):
        return private_response(Response(session_data(session_for(request, session_id), request)))


class DocxAnswerMatchView(APIView):
    permission_classes = [CanManageQuestionBank]

    @transaction.atomic
    def patch(self, request, session_id, entry_id):
        session = session_for(request, session_id, lock=True)
        if not isinstance(request.data, dict) or set(request.data) - {'revision', 'question_id', 'answer', 'excluded'}:
            raise ValidationError({'detail': 'Use supported answer-match fields.'})
        if type(request.data.get('revision')) is not int or request.data['revision'] != session.revision:
            raise ValidationError({'detail': 'The preview changed. Reload before saving.'})
        document = review_document(session)
        item = next((i for name in ('embedded_answer_key','separate_answer_key') for i in document.get(name, {}).get('entries', []) if i['id'] == entry_id), None)
        if item is None: raise NotFound()
        previous_status = item['status']
        questions = {q['id']: q for s in document['sections'] for q in s['questions']}
        if 'question_id' in request.data:
            target = request.data['question_id']
            if not isinstance(target, str) or target not in questions: raise ValidationError({'question_id': 'Select a question from this import session.'})
            old_target = item.get('linked_question_id') or item.get('question_id')
            if old_target != target:
                item.pop('manual_answer_resolution', None)
            if old_target in questions and old_target != target and questions[old_target].get('answer_manual_entry_id') == item['id']:
                questions[old_target]['correct_answer'] = copy.deepcopy(questions[old_target].get('answer_baseline'))
                questions[old_target]['answer_source'] = 'embedded_key'
                questions[old_target].pop('answer_manual_entry_id', None)
                questions[old_target]['review_revision'] = session.revision + 1
            item['linked_question_id'] = target
        if 'excluded' in request.data:
            if type(request.data['excluded']) is not bool: raise ValidationError({'excluded': 'Use a boolean.'})
            item['excluded'] = request.data['excluded']
        if 'answer' in request.data:
            value = request.data['answer']
            if not isinstance(value, str) or len(value) > 1000: raise ValidationError({'answer': 'Use a bounded answer value.'})
            target = item.get('linked_question_id') or item.get('question_id')
            if target not in questions: raise ValidationError({'question_id': 'Select the intended question before resolving the answer.'})
            labels = answer_labels(questions[target], value)
            if not labels: raise ValidationError({'answer': 'The answer does not uniquely match the selected question options.'})
            item['answer_override'] = value
            assign_answer(questions[target], labels, 'manual_review')
            questions[target]['answer_review_revision'] = session.revision + 1
            questions[target]['answer_manual_entry_id'] = item['id']
            questions[target]['modified'] = True
            questions[target]['review_revision'] = session.revision + 1
        recompute_matches(document, session.revision + 1)
        session.preview = validate_preview(document)
        session.revision += 1
        session.metadata['review_updated_at'] = timezone.now().isoformat()
        session.save(update_fields=['preview', 'revision', 'metadata'])
        record_event(institution=session.institution, actor=request.user, event_type='question_import', resource=session,
                     metadata={'action': 'answer_conflict_resolved' if previous_status == 'conflict' and item['status'] not in {'conflict', 'invalid_answer'} else 'answer_match_corrected',
                               'entry_id': item['id'], 'revision': session.revision,
                               'resolution_source': item.get('resolution_source'),
                               'source_question_id': item.get('question_id')})
        return private_response(Response(session_data(session, request)))


class DocxAnswerTemplateView(APIView):
    permission_classes = [CanManageQuestionBank]

    def get(self, request, session_id):
        session = session_for(request, session_id)
        require_separate_mode(session)
        response = HttpResponse(template_bytes(review_document(session)),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="answer-key-template.xlsx"'
        return private_response(response)


class DocxBlockClassificationView(APIView):
    permission_classes = [CanManageQuestionBank]

    @transaction.atomic
    def patch(self, request, session_id, block_id):
        session = session_for(request, session_id, lock=True)
        if not isinstance(request.data, dict) or set(request.data) != {'revision','classification'}:
            raise ValidationError({'detail': 'Use the current revision and block classification.'})
        if type(request.data['revision']) is not int or request.data['revision'] != session.revision:
            raise ValidationError({'detail': 'The preview changed. Reload before saving.'})
        document = classify_block(review_document(session), block_id, request.data['classification'], session.revision + 1)
        session.preview = validate_preview(document)
        session.revision += 1
        session.metadata['review_updated_at'] = timezone.now().isoformat()
        session.save(update_fields=['preview','revision','metadata'])
        record_event(institution=session.institution, actor=request.user, event_type='question_import', resource=session,
            metadata={'action':'source_block_classified','block_id':block_id,'classification':request.data['classification'],'revision':session.revision})
        return private_response(Response(session_data(session, request)))


class DocxConfirmView(APIView):
    permission_classes = [CanManageQuestionBank]

    @transaction.atomic
    def post(self, request, session_id):
        session = session_for(request, session_id, lock=True)
        if not isinstance(request.data, dict): raise ValidationError({'detail': 'Use a confirmation object.'})
        if set(request.data) != {'revision'} or request.data['revision'] != session.revision: raise ValidationError({'detail': 'Confirm the current server preview revision.'})
        eligibility, pending, document = import_eligibility(request, session)
        if not eligibility['eligible']:
            # ValidationError coerces every scalar to text; retain the typed contract.
            return private_response(Response({'detail': [blocker['message'] for blocker in eligibility['blockers']],
                                              'confirmation': eligibility}, status=400))
        ids = []
        for section,q,serializer in pending:
            question = serializer.save()
            question.source_metadata = {'section_title':section['source_title'], 'section_order':section['source_order'],
                'question_number':q['source_number'], 'document_order':q['source_order'],
                'equations':[{k:v for k,v in e.items() if k!='source_xml'} for e in q['equations']], 'review_modified':q['modified'],
                'import_session_id': str(session.pk), 'source_document': document.get('source_document', {}),
                'section_id': section['id'], 'section_directions': section.get('directions', ''),
                'original_question_type': q.get('original', {}).get('question_type', q['question_type'])}
            question.source_metadata['answer_source'] = q.get('answer_source') or 'embedded_key'
            if document.get('separate_answer_key') and q.get('answer_source') in {'separate_key', 'manual_review', 'manual_link', 'generated_template'}:
                question.source_metadata['answer_key_document'] = document['separate_answer_key']['source_document']
            question.save(update_fields=['source_metadata'])
            ids.append(question.pk)
            for order, media in enumerate(q['media'],1):
                asset = session.media.get(parsed_id=media['id'])
                asset.question, asset.import_session, asset.order = question, None, order
                asset.save()
        completion = {'created_question_ids': ids, 'imported_count': len(ids), 'question_status': 'draft',
            'import_mode': import_mode(session),
            'original_parsed_count': document.get('original_parsed_count', document['summary']['questions_detected']),
            'included_count': eligibility['included'], 'excluded_count': eligibility['excluded'],
            'unresolved_count': eligibility['unresolved'], 'blocker_count': len(eligibility['blockers']),
            'source_document': document.get('source_document', {})}
        if document.get('separate_answer_key'):
            completion['answer_key_summary'] = document['separate_answer_key']['summary']
            completion['answer_key_document'] = document['separate_answer_key']['source_document']
        session.metadata = {**session.metadata, 'completion': completion}
        session.confirmed_at, session.preview = timezone.now(), {}
        session.save(update_fields=['confirmed_at','preview','metadata'])
        record_event(institution=session.institution, actor=request.user, event_type='question_import', resource=session,
            metadata={'action':'docx_confirmed', **{key: value for key, value in completion.items() if key != 'created_question_ids'}})
        return private_response(Response({**completion,'status':'draft'},status=201))


def media_representation(question):
    return [{'id':str(m.pk), 'url':f'/api/v1/questions/media/{m.pk}/?institution={question.institution_id}',
             'alt_text':m.alt_text or 'Question illustration', 'caption':m.caption, 'order':m.order} for m in question.media.all()]


class QuestionMediaView(APIView):
    permission_classes = [AllowAny]  # Each branch below authorizes the exact asset owner.

    def get(self, request, media_id):
        asset = get_object_or_404(QuestionMedia.objects.select_related('question','import_session'), pk=media_id)
        if asset.import_session_id:
            enforce_workspace_mode(request, "questions")
            session = session_for(request, asset.import_session_id)
            if session.pk != asset.import_session_id: raise NotFound()
        elif not request.user.is_authenticated or not has_question_role(request.user, asset.question.institution_id, READ_ROLES):
            from attempts.models import AttemptQuestion
            from assessments.models import Assessment
            if not request.user.is_authenticated or not AttemptQuestion.objects.filter(question=asset.question,
                attempt__candidate__user=request.user, attempt__candidate__status='active',
                attempt__assessment__candidate_access__in=(Assessment.CandidateAccess.ASSIGNED_GROUP, Assessment.CandidateAccess.SPECIFIC_CANDIDATES),
                attempt__assessment__quick_configuration__isnull=True,
                attempt__status='in_progress', attempt__expires_at__gt=timezone.now(), attempt__institution__is_active=True).exists(): raise NotFound()
        else:
            if write_institution_for_request(request).pk != asset.question.institution_id: raise NotFound()
        if asset.source_metadata.get('status') != 'converted': raise NotFound()
        return private_response(FileResponse(asset.file.open('rb'), content_type='image/png'))


class QuickQuestionMediaView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [QuickExamAuthentication]

    def get(self, request, media_id):
        from attempts.models import AttemptQuestion
        context = request.auth
        asset = get_object_or_404(QuestionMedia, pk=media_id, question__institution=context.institution,
            import_session__isnull=True, source_metadata__status='converted')
        if not AttemptQuestion.objects.filter(question=asset.question, attempt__candidate=context.candidate,
                attempt__assessment=context.assessment, attempt__status='in_progress',
                attempt__expires_at__gt=timezone.now()).exists(): raise NotFound()
        return private_response(FileResponse(asset.file.open('rb'), content_type='image/png'))
