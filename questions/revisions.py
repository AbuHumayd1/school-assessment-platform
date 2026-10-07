"""Create content revisions without changing any existing assessment references."""
from copy import deepcopy
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from rest_framework.exceptions import NotFound, PermissionDenied

from audit.services import record_event
from institutions.workspace_access import enforce_workspace_mode
from .models import Question, QuestionMedia, QuestionOption
from .tenancy import WRITE_ROLES, has_question_role


def create_question_revision(question_id, *, actor, institution):
    if not has_question_role(actor, institution.pk, WRITE_ROLES):
        raise PermissionDenied()
    enforce_workspace_mode(SimpleNamespace(user=actor, headers={'X-Institution-ID': str(institution.pk)},
        query_params={}, method='POST'), 'questions')
    identity = Question.objects.filter(pk=question_id, institution=institution).values('revision_family').first()
    if identity is None:
        raise NotFound()
    created_files = []
    try:
        with transaction.atomic():
            # Every creator serializes on the permanent first revision, including when
            # creating from an older revision after newer drafts already exist.
            Question.objects.select_for_update().get(revision_family=identity['revision_family'], revision_number=1)
            source = Question.objects.select_for_update().get(pk=question_id, institution=institution)
            if not source.content_locked:
                raise ValidationError('Create a revision from an approved, locked question.')
            number = Question.objects.filter(revision_family=source.revision_family).aggregate(n=Max('revision_number'))['n'] + 1
            values = {key: deepcopy(getattr(source, key)) for key in Question.CONTENT_FIELDS
                      if key not in {'created_by_id', 'reviewed_by_id'}}
            revision = Question.objects.create(**values, revision_family=source.revision_family,
                revision_number=number, created_by=actor, status=Question.Status.DRAFT)
            QuestionOption.objects.bulk_create([QuestionOption(question=revision, text=option.text,
                is_correct=option.is_correct, order=option.order) for option in source.options.order_by('order', 'pk')])
            for asset in source.media.order_by('order', 'pk'):
                copy = QuestionMedia(question=revision, parsed_id=asset.parsed_id, media_type=asset.media_type,
                    alt_text=asset.alt_text, caption=asset.caption, order=asset.order,
                    source_metadata=deepcopy(asset.source_metadata))
                with asset.file.open('rb') as stream:
                    copy.file.save('revision.dat', ContentFile(stream.read()), save=False)
                created_files.append((copy.file.storage, copy.file.name))
                copy.save()
            record_event(institution=institution, actor=actor, event_type='question_revision_created', resource=revision,
                metadata={'source_question_id': source.pk, 'revision_family': str(source.revision_family), 'revision_number': number})
            return revision
    except Exception:
        for storage, name in created_files:
            storage.delete(name)
        raise
