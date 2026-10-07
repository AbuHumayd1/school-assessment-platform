"""Bounded productionization of the reviewed Activus preparation receipt."""
import copy
import hashlib
import json
import uuid
from collections import Counter
from types import SimpleNamespace

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from audit.models import AuditEvent
from audit.services import record_event
from institutions.models import Institution
from questions.models import DocxImportSession, Question, QuestionMedia, QuestionOption
from questions.serializers import QuestionSerializer
from questions.tenancy import is_platform_admin
from questions.views import QuestionViewSet
from subjects.models import Subject

SOURCE_SESSION = "54fde495-77b7-4d27-85dc-f688bebf50ef"
SOURCE_FINGERPRINT = "105e7ccd7f2729a3bf40c2067f8731a9cac78c26a44f0c2cc2e3e023b5f61466"
SUBJECT_NAME = "ACTIVUS EEG Comprehensive Examination (Cohort 2.0)"
SUBJECT_CODE = "AEC-2026-C2"
OPERATION = "controlled_production_clone"
LINEAGE = "production_clone"
CONTENT_FIELDS = ("question_type", "text", "marks", "difficulty", "source", "source_year",
                  "explanation", "learning_objective")
MEDIA_FIELDS = ("media_type", "order", "parsed_id", "caption", "alt_text", "source_metadata")
SECTION_COUNTS = {
    "1.0 EEG Instrumentation and Polarity": 28,
    "2.0 EEG Machine Introduction MCQ": 20,
    "3.0 EEG TERMINOLOGY": 20,
    "4.0 BASIC PRINCIPLE OF ELECTRICITY": 20,
    "5.0 ELECTRICAL SAFETY": 20,
    "6.0 Montages": 20,
    "7.0 Activation during EEG, MCQ": 20,
    "8.0 Pattern Recognition": 3,
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def source_fingerprint(session, ids):
    # Exactly the serialization used by the approved read-only audit.
    questions = list(Question.objects.filter(pk__in=ids).order_by("pk").prefetch_related("options"))
    return digest({
        "questions": list(Question.objects.filter(pk__in=ids).order_by("pk").values()),
        "options": [dict(id=o.pk, question_id=o.question_id, text=o.text, is_correct=o.is_correct,
                         order=o.order, created_at=o.created_at, updated_at=o.updated_at)
                    for q in questions for o in q.options.all()],
        "media": list(QuestionMedia.objects.filter(question__in=questions).order_by("question_id", "order").values()),
        "session": list(DocxImportSession.objects.filter(pk=session.pk).values()),
    })


def file_bytes(asset):
    with asset.file.storage.open(asset.file.name, "rb") as stream:
        return stream.read()


def canonical(question, *, destination=False):
    metadata = copy.deepcopy(question.source_metadata)
    if destination:
        metadata.pop(LINEAGE, None)
    return {
        "content": {field: getattr(question, field) for field in CONTENT_FIELDS},
        "source_metadata": metadata,
        "options": list(question.options.order_by("order", "id").values("text", "order", "is_correct")),
        "media": [{**{field: getattr(asset, field) for field in MEDIA_FIELDS},
                   "file_sha256": hashlib.sha256(file_bytes(asset)).hexdigest()}
                  for asset in question.media.order_by("order", "id")],
    }


def validate_payload(question, institution, actor, subject=None):
    payload = {field: getattr(question, field) for field in CONTENT_FIELDS}
    payload.update(subject=(subject or question.subject).pk, topic=None,
                   options=list(question.options.order_by("order", "id").values("text", "order", "is_correct")))
    serializer = QuestionSerializer(data=payload, context={"institution": institution,
                                                           "request": SimpleNamespace(user=actor)})
    if not serializer.is_valid():
        raise CommandError(f"Question {question.pk} fails objective payload validation.")
    return serializer


class Command(BaseCommand):
    help = "Clone only the approved Activus preparation receipt; defaults to read-only dry run."

    def add_arguments(self, parser):
        parser.add_argument("--source-session", required=True)
        parser.add_argument("--expected-revision", type=int, required=True)
        parser.add_argument("--expected-question-count", type=int, required=True)
        parser.add_argument("--destination-institution", type=int, required=True)
        parser.add_argument("--actor", type=int, required=True, help="Active Platform Administrator User ID")
        parser.add_argument("--expected-source-fingerprint", default=SOURCE_FINGERPRINT)
        parser.add_argument("--apply", action="store_true")

    def preflight(self, options):
        if options["source_session"] != SOURCE_SESSION:
            raise CommandError("This command accepts only the audited source session.")
        if options["expected_revision"] != 22 or options["expected_question_count"] != 151:
            raise CommandError("This bounded batch requires revision 22 and 151 questions.")
        if options["expected_source_fingerprint"] != SOURCE_FINGERPRINT:
            raise CommandError("Expected fingerprint differs from the audited fingerprint.")
        try:
            session = DocxImportSession.objects.select_for_update().get(pk=SOURCE_SESSION)
            destination = Institution.objects.select_for_update().get(pk=options["destination_institution"], is_active=True)
            actor = User.objects.get(pk=options["actor"], is_active=True)
        except (DocxImportSession.DoesNotExist, Institution.DoesNotExist, User.DoesNotExist) as error:
            raise CommandError("Source session, active destination or active actor not found.") from error
        if not is_platform_admin(actor):
            raise CommandError("An active Platform Administrator actor is required.")
        if (session.institution.name != "Demo Training Institute" or not session.institution.is_active
                or destination.name != "ACTIVUS HEALTHCARE" or destination.pk == session.institution_id
                or destination.workspace_mode != "managed_exam"):
            raise CommandError("Source or destination institution does not match the audited batch.")
        if session.revision != 22 or not session.confirmed_at or session.preview:
            raise CommandError("Source must be the confirmed revision-22 receipt with cleared preview.")
        completion = session.metadata.get("completion", {})
        ids = completion.get("created_question_ids")
        if (not isinstance(ids, list) or len(ids) != 151 or any(type(i) is not int for i in ids)
                or len(set(ids)) != 151 or completion.get("imported_count") != 151):
            raise CommandError("Source receipt does not identify exactly 151 unique questions.")
        # Lock destination before rerun checks: concurrent applies serialize even if no subject exists.
        previous = AuditEvent.objects.filter(institution=destination, event_type="question_import",
            metadata__operation=OPERATION, metadata__source_import_session_uuid=SOURCE_SESSION)
        copies = Question.objects.filter(institution=destination,
            source_metadata__production_clone__source_import_session_uuid=SOURCE_SESSION)
        if previous.exists() or copies.exists():
            raise CommandError("This source batch has already been productionized; refusing a duplicate apply.")
        subjects = list(Subject.objects.select_for_update().filter(institution=destination).filter(
            Q(code__iexact=SUBJECT_CODE) | Q(name__iexact=SUBJECT_NAME)))
        subject = subjects[0] if len(subjects) == 1 else None
        if subjects and (len(subjects) != 1 or subject.code != SUBJECT_CODE or subject.name != SUBJECT_NAME
                         or not subject.is_active or subject.description != ""
                         or subject.questions.exists() or subject.topics.exists()
                         or subject.assessments.exists()):
            raise CommandError("Destination subject conflict; only an exact, active, unused subject may be reused.")
        questions = list(Question.objects.select_for_update().filter(pk__in=ids).order_by("pk").prefetch_related("options", "media"))
        if len(questions) != 151 or source_fingerprint(session, ids) != SOURCE_FINGERPRINT:
            raise CommandError("Source record fingerprint/count mismatch; no changes made.")
        source_subject = questions[0].subject
        if (source_subject.institution_id != session.institution_id or source_subject.pk != session.metadata.get("subject")
                or source_subject.name != SUBJECT_NAME or source_subject.code != SUBJECT_CODE or not source_subject.is_active):
            raise CommandError("Source subject does not match the audited receipt.")
        if any(q.institution_id != session.institution_id or q.subject_id != source_subject.pk
               or q.topic_id is not None or q.status != "draft" or LINEAGE in q.source_metadata for q in questions):
            raise CommandError("Unexpected source ownership, topic, status or lineage.")
        self.validate_counts(questions)
        if Counter(q.question_type for q in questions) != {"multiple_choice": 147, "true_false": 4}:
            raise CommandError("Source objective question-type distribution changed.")
        for question in questions:
            question.full_clean()
            validate_payload(question, session.institution, actor)
            for asset in question.media.all():
                if asset.import_session_id or asset.source_metadata.get("status") != "converted":
                    raise CommandError("Source media is not a converted question-owned asset.")
                if not asset.file.name or not asset.file.storage.exists(asset.file.name):
                    raise CommandError("A source media file is missing.")
                file_bytes(asset)
        return session, ids, questions, destination, subject, actor

    def validate_counts(self, questions):
        counts = {
            "questions": len(questions),
            "options": sum(q.options.count() for q in questions),
            "media": sum(q.media.count() for q in questions),
            "converted_equations": sum(e.get("status") == "converted" for q in questions
                                       for e in q.source_metadata.get("equations", [])),
        }
        if counts != {"questions": 151, "options": 698, "media": 4, "converted_equations": 11}:
            raise CommandError("Question/option/media/equation counts do not match the audited batch.")
        if Counter(q.source_metadata.get("section_title") for q in questions) != SECTION_COUNTS:
            raise CommandError("Source section distribution changed.")
        return counts

    def approve(self, question, actor):
        factory = APIRequestFactory()
        for action in ("submit_for_review", "approve"):
            request = factory.post(f"/api/v1/questions/{question.pk}/{action}/",
                                   HTTP_X_INSTITUTION_ID=str(question.institution_id))
            force_authenticate(request, user=actor)
            response = QuestionViewSet.as_view({"post": action})(request, pk=question.pk)
            if response.status_code != 200:
                raise CommandError(f"Destination question {question.pk} could not complete {action}.")
        question.refresh_from_db()

    def handle(self, **options):
        new_files = []
        try:
            with transaction.atomic():
                session, ids, sources, destination, subject, actor = self.preflight(options)
                source_canonical = {q.pk: canonical(q) for q in sources}
                source_subject_hash = digest(list(Subject.objects.filter(pk=sources[0].subject_id).values()))
                content_hash = digest([source_canonical[q.pk] for q in sources])
                manifest = {"operation": OPERATION, "mode": "apply" if options["apply"] else "dry_run",
                            "source_import_session_uuid": SOURCE_SESSION, "source_import_revision": 22,
                            "source_institution_id": session.institution_id, "destination_institution_id": destination.pk,
                            "source_fingerprint": SOURCE_FINGERPRINT, "counts": self.validate_counts(sources),
                            "section_distribution": SECTION_COUNTS, "content_fingerprint": content_hash,
                            "destination_subject_id": subject.pk if subject else None,
                            "subject_action": "reuse" if subject else "create", "actor_id": actor.pk}
                if options["apply"]:
                    if subject is None:
                        subject = Subject(institution=destination, name=SUBJECT_NAME, code=SUBJECT_CODE)
                        subject.full_clean()
                        subject.save()
                    mapping, copies = [], []
                    for source in sources:
                        serializer = validate_payload(source, destination, actor, subject)
                        question = serializer.save()
                        question.source_metadata = copy.deepcopy(source.source_metadata)
                        question.source_metadata[LINEAGE] = {
                            "operation": OPERATION, "source_question_id": source.pk,
                            "source_institution_id": source.institution_id, "source_subject_id": source.subject_id,
                            "source_import_session_uuid": SOURCE_SESSION, "source_import_revision": 22,
                        }
                        question.full_clean()
                        question.save(update_fields=["source_metadata"])
                        for original in source.media.order_by("order", "id"):
                            asset = QuestionMedia(question=question, **{field: copy.deepcopy(getattr(original, field))
                                                                      for field in MEDIA_FIELDS})
                            storage = asset.file.storage
                            name = f"{uuid.uuid4().hex}/{uuid.uuid4().hex}.dat"
                            if storage.exists(name):
                                raise CommandError("Unexpected destination media filename collision.")
                            new_files.append((storage, name))
                            saved_name = storage.save(name, ContentFile(file_bytes(original)))
                            if saved_name != name:
                                new_files.append((storage, saved_name))
                            asset.file.name = saved_name
                            asset.full_clean()
                            asset.save()
                        if canonical(question, destination=True) != source_canonical[source.pk]:
                            raise CommandError("Destination content/media equality check failed.")
                        self.approve(question, actor)
                        question.full_clean()
                        validate_payload(question, destination, actor, subject)
                        if (question.status != "approved" or question.reviewed_by_id != actor.pk
                                or question.created_by_id != actor.pk or question.topic_id is not None
                                or question.institution_id != destination.pk or question.subject_id != subject.pk):
                            raise CommandError("Destination approval/ownership verification failed.")
                        copies.append(question)
                        mapping.append({"source_question_id": source.pk, "destination_question_id": question.pk,
                                        "content_sha256": digest(source_canonical[source.pk])})
                    counts = self.validate_counts(copies)
                    eligible = Question.objects.filter(pk__in=[q.pk for q in copies], institution=destination,
                                                       subject=subject, status="approved").count()
                    if eligible != 151 or len({item["destination_question_id"] for item in mapping}) != 151:
                        raise CommandError("Destination mapping/question-picker eligibility verification failed.")
                    destination_hash = digest([canonical(q, destination=True) for q in copies])
                    if destination_hash != content_hash:
                        raise CommandError("Destination batch fingerprint mismatch.")
                    manifest.update(destination_subject_id=subject.pk, counts=counts,
                                    destination_verification_fingerprint=destination_hash, mapping=mapping)
                    record_event(institution=destination, actor=actor, event_type="question_import", resource=subject,
                                 metadata={**{k: v for k, v in manifest.items() if k != "mapping"},
                                           "action": OPERATION})
                if source_fingerprint(session, ids) != SOURCE_FINGERPRINT:
                    raise CommandError("Source changed during the operation; rolling back.")
                if (digest(list(Subject.objects.filter(pk=sources[0].subject_id).values())) != source_subject_hash
                        or any(canonical(q) != source_canonical[q.pk] for q in sources)):
                    raise CommandError("Source subject or media changed during the operation; rolling back.")
        except Exception as error:
            cleanup_errors = []
            for storage, name in reversed(new_files):
                try:
                    storage.delete(name)
                except Exception:
                    cleanup_errors.append(name)
            if cleanup_errors:
                raise CommandError("Database rolled back; cleanup failed for new destination files: "
                                   + ", ".join(cleanup_errors)) from error
            if isinstance(error, CommandError):
                raise
            raise CommandError("Clone validation or write failed; database rolled back and new files cleaned up.") from error
        self.stdout.write(json.dumps(manifest, sort_keys=True, ensure_ascii=True))
