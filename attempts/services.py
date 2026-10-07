import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from assessments.models import Assessment, AssessmentQuestion
from audit.models import AuditEvent
from audit.services import record_event
from candidates.models import Candidate
from questions.models import Question
from .models import Attempt, AttemptQuestion, AttemptQuestionOption
from .access import ExamAccessContext, validate_quick_context
from .tenancy import (
    active_group_ids_for_candidate, assessment_window_state, candidates_for_user,
)


class AttemptConflict(APIException):
    status_code = 409
    default_detail = "The attempt is no longer available for this operation."
    default_code = "attempt_conflict"


class CompletionReason:
    MANUAL = "manual"
    TIME_EXPIRED = "time_expired"
    INTEGRITY = "integrity"

    VALUES = {MANUAL, TIME_EXPIRED, INTEGRITY}


INTEGRITY_AUTO_SUBMITTED_EVENT = "integrity_auto_submitted"


def resolve_candidate(user, institution_id=None):
    qs = candidates_for_user(user)
    if institution_id is not None:
        qs = qs.filter(institution_id=institution_id)
    candidates = list(qs.select_related("institution")[:2])
    if not candidates:
        raise PermissionDenied("No candidate profile is linked to this account for the selected institution.")
    if len(candidates) > 1:
        raise ValidationError({"institution": "Select a candidate institution using X-Institution-ID."})
    return candidates[0]


AVAILABILITY_MESSAGES = {
    "upcoming": "Exam has not started yet.",
    "ended": "Exam has ended.",
    "not_open": "Exam is not open for candidates.",
    "not_eligible": "Candidate is not eligible.",
    "not_ready": "Exam is not ready for candidates.",
    "attempt_limit_reached": "No attempts remaining.",
    "resume_disabled": "This exam cannot be resumed.",
}


def assessment_unavailability_reason(error):
    """Expose only safe candidate reasons, never configuration/answer details."""
    code = "not_eligible" if isinstance(error, NotFound) else error.get_codes()
    return code if isinstance(code, str) and code in AVAILABILITY_MESSAGES else "not_ready"


def _validate_assessment_for_candidate(
    assessment, candidate, now, *, check_window=True, question_rows=None,
    eligible_group_ids=None, access_mode="portal",
):
    if assessment.institution_id != candidate.institution_id or not assessment.institution.is_active:
        raise NotFound()
    if candidate.status != Candidate.Status.ACTIVE:
        raise PermissionDenied(AVAILABILITY_MESSAGES["not_eligible"], code="not_eligible")
    if assessment.status not in {Assessment.Status.APPROVED, Assessment.Status.SCHEDULED}:
        raise PermissionDenied(AVAILABILITY_MESSAGES["not_open"], code="not_open")
    if check_window:
        window = assessment_window_state(assessment, now)
        if window == "upcoming":
            raise PermissionDenied(AVAILABILITY_MESSAGES["upcoming"], code="upcoming")
        if window == "ended":
            raise PermissionDenied(AVAILABILITY_MESSAGES["ended"], code="ended")
    if access_mode == "quick":
        if not assessment.uses_quick_delivery:
            raise PermissionDenied(AVAILABILITY_MESSAGES["not_eligible"], code="not_eligible")
    else:
        from assessments.eligibility import portal_candidate_is_assigned
        if not portal_candidate_is_assigned(assessment, candidate, eligible_group_ids):
            raise PermissionDenied(AVAILABILITY_MESSAGES["not_eligible"], code="not_eligible")

    rows = question_rows
    if rows is None:
        rows = list(assessment.assessment_questions.select_related("question").prefetch_related(
            "question__options",
        ).order_by("order", "id"))
    specs = [{"question": row.question, "order": row.order, "marks": row.marks} for row in rows]
    try:
        assessment.validate_configuration(question_specs=specs, require_questions=True)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    if not rows:
        raise ValidationError({"questions": "The assessment has no configured questions."})
    for row in rows:
        question = row.question
        if not question.is_deliverable_revision:
            raise ValidationError({"questions": "Every delivered question must be an approved immutable revision."})
        options = list(question.options.all())
        correct = sum(option.is_correct for option in options)
        if question.question_type == Question.Type.MULTIPLE_CHOICE and (len(options) < 2 or correct != 1):
            raise ValidationError({"questions": f"Question {question.pk} is not a valid multiple-choice question."})
        if question.question_type == Question.Type.MULTIPLE_SELECT and (len(options) < 2 or correct < 1):
            raise ValidationError({"questions": f"Question {question.pk} is not a valid multiple-select question."})
        if question.question_type == Question.Type.TRUE_FALSE and (len(options) != 2 or correct != 1):
            raise ValidationError({"questions": f"Question {question.pk} is not a valid true/false question."})
    return rows


def start_attempt(user, assessment_id, *, institution_id=None, now=None):
    candidate = resolve_candidate(user, institution_id)
    try:
        assessment = Assessment.objects.get(pk=assessment_id)
    except Assessment.DoesNotExist:
        raise NotFound()
    context = ExamAccessContext("portal", candidate, assessment, candidate.institution, user=user)
    return start_access_attempt(context, now=now)


def start_access_attempt(context, *, now=None):
    now = now or timezone.now()
    candidate, assessment_id, user = context.candidate, context.assessment.pk, context.user
    try:
        with transaction.atomic():
            if context.access_mode == "quick":
                context = validate_quick_context(context)
                candidate = context.candidate
                assessment_id, user = context.assessment.pk, context.user
            candidate = Candidate.objects.select_for_update().select_related("institution").get(pk=candidate.pk)
            try:
                assessment = Assessment.objects.select_for_update().select_related("institution", "group", "subject").get(pk=assessment_id)
            except Assessment.DoesNotExist:
                raise NotFound()
            if assessment.institution_id != candidate.institution_id or not assessment.institution.is_active:
                raise NotFound()
            if candidate.status != Candidate.Status.ACTIVE:
                raise PermissionDenied(AVAILABILITY_MESSAGES["not_eligible"], code="not_eligible")
            if context.access_mode == "portal" and assessment.uses_quick_delivery:
                raise PermissionDenied(AVAILABILITY_MESSAGES["not_eligible"], code="not_eligible")
            active = Attempt.objects.select_for_update().filter(
                candidate=candidate, assessment=assessment, status=Attempt.Status.IN_PROGRESS,
            ).first()
            if active:
                if now >= active.expires_at:
                    expire_attempt(active, now, actor=user)
                else:
                    if not assessment.resume_allowed:
                        raise AttemptConflict("An active attempt already exists and resume is disabled.")
                    return active, False
            rows = _validate_assessment_for_candidate(assessment, candidate, now, access_mode=context.access_mode)
            question_ids = [row.question_id for row in rows]
            # Lock questions while the validated content and options are copied into the attempt.
            list(Question.objects.select_for_update().filter(pk__in=question_ids).order_by("pk").values_list("pk", flat=True))
            rows = _validate_assessment_for_candidate(assessment, candidate, now, access_mode=context.access_mode)
            used = Attempt.objects.filter(candidate=candidate, assessment=assessment).count()
            if used >= assessment.attempt_limit:
                # Return normally so any expiry transition made above is committed.
                return None, False
            previous = Attempt.objects.filter(candidate=candidate, assessment=assessment).aggregate(last=Max("attempt_number"))["last"] or 0
            attempt = Attempt.objects.create(
                institution=assessment.institution, assessment=assessment, candidate=candidate,
                attempt_number=previous + 1, status=Attempt.Status.IN_PROGRESS,
                started_at=now, expires_at=now + timedelta(minutes=assessment.duration_minutes), last_activity_at=now,
                pass_mark_snapshot=assessment.pass_mark,
            )
            order_rows = list(rows)
            if assessment.randomize_questions:
                secrets.SystemRandom().shuffle(order_rows)
            for position, assessment_question in enumerate(order_rows, start=1):
                attempt_question = AttemptQuestion.objects.create(
                    attempt=attempt, question=assessment_question.question, order=position,
                    marks_available=assessment_question.marks,
                )
                options = list(assessment_question.question.options.all().order_by("order", "id"))
                if assessment.randomize_options:
                    secrets.SystemRandom().shuffle(options)
                AttemptQuestionOption.objects.bulk_create([
                    AttemptQuestionOption(attempt_question=attempt_question, option=option, order=position)
                    for position, option in enumerate(options, start=1)
                ])
            record_event(institution=assessment.institution, actor=user, event_type=AuditEvent.Type.ATTEMPT_STARTED, resource=attempt,
                         metadata={"assessment_id": assessment.pk})
            return attempt, True
    except IntegrityError:
        # A concurrent start may win the unique attempt-number race; return that active session.
        existing = Attempt.objects.filter(candidate=candidate, assessment_id=assessment_id, status=Attempt.Status.IN_PROGRESS).first()
        if existing and existing.expires_at > now and existing.assessment.resume_allowed:
            return existing, False
        raise AttemptConflict("A concurrent request changed the attempt state. Refresh and retry.")


@transaction.atomic
def finalize_attempt(attempt_or_id, *, reason, now=None, actor=None, metadata=None):
    """Close and mark an attempt atomically; the deadline always overrides the requested reason."""
    if reason not in CompletionReason.VALUES:
        raise ValueError(f"Unsupported attempt completion reason: {reason}")
    attempt_id = getattr(attempt_or_id, "pk", attempt_or_id)
    locked = Attempt.objects.select_for_update().select_related("institution", "assessment", "candidate").get(pk=attempt_id)
    # Measure the deadline after acquiring the row lock so lock wait cannot extend the attempt.
    now = now or timezone.now()
    newly_finalized = False

    if locked.status == Attempt.Status.IN_PROGRESS:
        if reason == CompletionReason.TIME_EXPIRED and now < locked.expires_at:
            return locked, False
        actual_reason = CompletionReason.TIME_EXPIRED if now >= locked.expires_at else reason
        locked.status = (Attempt.Status.EXPIRED if actual_reason == CompletionReason.TIME_EXPIRED
                         else Attempt.Status.SUBMITTED)
        locked.submitted_at = now
        locked.last_activity_at = now
        locked.save(update_fields=("status", "submitted_at", "last_activity_at", "updated_at"))
        newly_finalized = True

        if actual_reason == CompletionReason.TIME_EXPIRED:
            record_event(
                institution=locked.institution, actor=actor, event_type=AuditEvent.Type.ATTEMPT_EXPIRED,
                resource=locked, metadata={"reason": actual_reason},
            )
        else:
            record_event(
                institution=locked.institution, actor=actor, event_type=AuditEvent.Type.ATTEMPT_SUBMITTED,
                resource=locked,
                metadata={"reason": "integrity_interruption_limit" if actual_reason == CompletionReason.INTEGRITY else actual_reason},
            )
            if actual_reason == CompletionReason.INTEGRITY:
                record_event(
                    institution=locked.institution, actor=actor, event_type=INTEGRITY_AUTO_SUBMITTED_EVENT,
                    resource=locked, metadata=metadata or {},
                )
    elif locked.status not in (Attempt.Status.SUBMITTED, Attempt.Status.EXPIRED):
        raise AttemptConflict("Only an in-progress attempt can be finalized.")
    elif locked.status == Attempt.Status.EXPIRED and locked.submitted_at is None:
        # Repair legacy lazy-expiry rows using their authoritative deadline.
        locked.submitted_at = locked.expires_at
        locked.save(update_fields=("submitted_at", "updated_at"))

    # Keep marking inside this transaction so a failure rolls back the completion too.
    # The trusted finalization service invokes the existing Results Engine without
    # treating a candidate actor as a result marker.
    from results.models import Result
    if not Result.objects.filter(attempt_id=locked.pk).exists():
        from results.services import mark_attempt
        mark_attempt(locked.pk, now=now)
    return locked, newly_finalized


@transaction.atomic
def expire_attempt(attempt, now=None, *, actor=None):
    locked, newly_expired = finalize_attempt(
        attempt, reason=CompletionReason.TIME_EXPIRED, now=now, actor=actor,
    )
    attempt.status = locked.status
    attempt.submitted_at = locked.submitted_at
    attempt.last_activity_at = locked.last_activity_at
    attempt.updated_at = locked.updated_at
    return newly_expired


def lock_candidate_attempt(user, attempt_id):
    try:
        owned = Attempt.objects.select_related("candidate__institution", "assessment").get(
            pk=attempt_id, candidate__user=user, candidate__status=Candidate.Status.ACTIVE,
            institution__is_active=True,
        )
    except Attempt.DoesNotExist:
        raise NotFound()
    context = ExamAccessContext("portal", owned.candidate, owned.assessment, owned.candidate.institution, user=user)
    return lock_access_attempt(context, attempt_id)


def lock_access_attempt(context, attempt_id):
    if context.access_mode == "quick":
        context = validate_quick_context(context)
    filters = dict(pk=attempt_id, candidate_id=context.candidate.pk, assessment_id=context.assessment.pk,
                   institution_id=context.institution.pk, candidate__status=Candidate.Status.ACTIVE,
                   institution__is_active=True)
    if context.access_mode == "portal":
        filters["candidate__user"] = context.user
        filters["assessment__candidate_access__in"] = (Assessment.CandidateAccess.ASSIGNED_GROUP, Assessment.CandidateAccess.SPECIFIC_CANDIDATES)
        filters["assessment__quick_configuration__isnull"] = True
    try:
        return Attempt.objects.select_for_update().select_related("assessment", "candidate", "institution").get(**filters)
    except Attempt.DoesNotExist:
        raise NotFound()


def mark_question_for_review(attempt, question, marked, now=None):
    row = AttemptQuestion.objects.select_for_update().get(attempt=attempt, question=question)
    row.marked_for_review = marked
    row.save(update_fields=("marked_for_review", "updated_at"))
    attempt.last_activity_at = now or timezone.now()
    attempt.save(update_fields=("last_activity_at", "updated_at"))
    return row
