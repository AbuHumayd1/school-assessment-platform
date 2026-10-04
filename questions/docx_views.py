import copy
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import record_event
from assessments.quick_authentication import QuickExamAuthentication
from .docx_parser import limits, parse_docx, validate_preview
from .models import DocxImportSession, QuestionMedia
from .permissions import CanManageQuestionBank
from .serializers import QuestionSerializer
from .tenancy import has_question_role, READ_ROLES, write_institution_for_request


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
    return {**data, 'import_session_id': str(session.pk), 'revision': session.revision,
            'expires_at': session.expires_at, 'metadata': {**session.metadata, 'subject': eligibility['subject_id']},
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
    document = validate_preview(copy.deepcopy(session.preview))
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
    if document['key_errors'] and not document.get('source_reviewed'):
        blockers.append({'code': 'document_review', 'message': 'Review the document-level source issues before confirmation.'})
    if not subject_id: blockers.append({'code': 'subject_required', 'message': 'Select or create a subject before importing.'})
    metadata = None
    if subject_id:
        try: metadata = metadata_for(request, session.institution, session.metadata, required=True)
        except ValidationError as error:
            blockers.append({'code': 'metadata_invalid', 'message': 'Import metadata requires correction.', 'details': error.detail})
    pending = []
    if not blockers:
        for section, q in included:
            payload = dict(text=q.get('equation_replacement') or q['text'], question_type=q['question_type'],
                subject=metadata['subject'], topic=metadata.get('topic') or None, difficulty=metadata.get('difficulty','medium'),
                marks=metadata.get('default_marks','1.00'), source='DOCX',
                options=[dict(text=o['text'],order=i,is_correct=o['label']==q['correct_answer']) for i,o in enumerate(q['options'],1)])
            serializer = QuestionSerializer(data=payload, context={'request': request, 'institution': session.institution})
            if not serializer.is_valid():
                blockers.append({'code': 'question_invalid', 'question_id': q['id'],
                    'message': 'Question validation requires correction.', 'details': serializer.errors})
            else: pending.append((section,q,serializer))
    state['eligible'] = not blockers
    state['status'] = 'eligible' if state['eligible'] else 'blocked'
    return state, pending, document


class DocxPreviewView(APIView):
    permission_classes = [CanManageQuestionBank]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        from subjects.models import Subject
        institution = write_institution_for_request(request)
        recent = DocxImportSession.objects.filter(institution=institution, uploaded_by=request.user,
            confirmed_at__isnull=True, expires_at__gt=timezone.now()).order_by('-created_at')[:5]
        return private_response(Response({
            'subjects': list(Subject.objects.filter(institution=institution).order_by('name').values('id','name','code')),
            'recent_imports': [{'import_session_id': str(s.pk), 'created_at': s.created_at,
                'expires_at': s.expires_at, 'questions_detected': s.preview['summary']['questions_detected'],
                'subject_id': subject_selection(s)[0], 'subject_name': subject_selection(s)[1]}
                for s in recent]}))

    def post(self, request):
        institution = write_institution_for_request(request)
        metadata = metadata_for(request, institution, {k: request.data[k] for k in ('subject', 'topic', 'difficulty', 'default_marks') if request.data.get(k)})
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

    def get(self, request, session_id):
        return private_response(Response(session_data(session_for(request, session_id, allow_completed=True), request)))

    @transaction.atomic
    def patch(self, request, session_id):
        session = session_for(request, session_id, lock=True)
        if not isinstance(request.data, dict): raise ValidationError({'detail': 'Use a review object.'})
        if set(request.data) - {'revision', 'question_id', 'changes', 'section_id', 'section_title', 'metadata', 'source_reviewed'}:
            raise ValidationError({'detail': 'Unsupported review fields.'})
        if request.data.get('revision') != session.revision: raise ValidationError({'detail': 'The preview changed. Reload before saving.'})
        document = copy.deepcopy(session.preview)
        if 'metadata' in request.data: session.metadata = metadata_for(request, session.institution, request.data['metadata'])
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
                elif not isinstance(value, str) or len(value) > limits()['item_chars']: raise ValidationError({key: 'Use bounded text.'})
                question[key] = value
            question['modified'] = True
            question['review_revision'] = session.revision + 1
        session.preview = validate_preview(document)
        session.revision += 1
        session.save(update_fields=['preview','metadata','revision'])
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
            question.save(update_fields=['source_metadata'])
            ids.append(question.pk)
            for order, media in enumerate(q['media'],1):
                asset = session.media.get(parsed_id=media['id'])
                asset.question, asset.import_session, asset.order = question, None, order
                asset.save()
        completion = {'created_question_ids': ids, 'imported_count': len(ids), 'question_status': 'draft',
            'original_parsed_count': document.get('original_parsed_count', document['summary']['questions_detected']),
            'included_count': eligibility['included'], 'excluded_count': eligibility['excluded'],
            'unresolved_count': eligibility['unresolved'], 'blocker_count': len(eligibility['blockers']),
            'source_document': document.get('source_document', {})}
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
            session = session_for(request, asset.import_session_id)
            if session.pk != asset.import_session_id: raise NotFound()
        elif not request.user.is_authenticated or not has_question_role(request.user, asset.question.institution_id, READ_ROLES):
            from attempts.models import AttemptQuestion
            from assessments.models import Assessment
            if not request.user.is_authenticated or not AttemptQuestion.objects.filter(question=asset.question,
                attempt__candidate__user=request.user, attempt__candidate__status='active',
                attempt__assessment__candidate_access=Assessment.CandidateAccess.ASSIGNED_GROUP,
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
