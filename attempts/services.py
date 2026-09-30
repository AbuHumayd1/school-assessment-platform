import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from assessments.models import Assessment, AssessmentQuestion
from audit.models import AuditEvent
from audit.services import record_event
from candidates.models import Candidate
from groups.models import GroupMembership
from questions.models import Question
from .models import Attempt, AttemptQuestion, AttemptQuestionOption
from .tenancy import active_local_date, candidates_for_user


class AttemptConflict(APIException):
    status_code = 409
    default_detail = "The attempt is no longer available for this operation."
    default_code = "attempt_conflict"


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


def _validate_assessment_for_candidate(assessment, candidate, now):
    if assessment.institution_id != candidate.institution_id or not assessment.institution.is_active:
        raise NotFound()
    if candidate.status != Candidate.Status.ACTIVE:
        raise PermissionDenied("This candidate profile is not active.")
    if assessment.status not in {Assessment.Status.APPROVED, Assessment.Status.SCHEDULED}:
        raise PermissionDenied("Only approved or scheduled assessments are available to candidates.")
    if assessment.start_at and now < assessment.start_at:
        raise PermissionDenied("This assessment is not available yet.")
    if assessment.end_at and now > assessment.end_at:
        raise PermissionDenied("The assessment availability window has ended.")
    if assessment.candidate_access != Assessment.CandidateAccess.ASSIGNED_GROUP:
        raise PermissionDenied("This assessment access mode is not configured for candidate delivery.")
    if not assessment.group_id or not assessment.group.is_active:
        raise ValidationError({"group": "An active assigned group is required for candidate access."})
    today = active_local_date(assessment.institution)
    eligible = GroupMembership.objects.filter(candidate=candidate, group_id=assessment.group_id, is_active=True).filter(
        Q(start_date__isnull=True) | Q(start_date__lte=today),
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today),
    ).exists()
    if not eligible:
        raise PermissionDenied("The candidate is not an active member of the assigned group.")
    try:
        assessment.validate_configuration(require_questions=True)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    rows = list(assessment.assessment_questions.select_related("question").prefetch_related("question__options").order_by("order", "id"))
    if not rows:
        raise ValidationError({"questions": "The assessment has no configured questions."})
    for row in rows:
        question = row.question
        if question.status != Question.Status.APPROVED:
            raise ValidationError({"questions": "Every delivered question must still be approved."})
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
    now = now or timezone.now()
    candidate = resolve_candidate(user, institution_id)
    try:
        with transaction.atomic():
            candidate = Candidate.objects.select_for_update().select_related("institution").get(pk=candidate.pk)
            try:
                assessment = Assessment.objects.select_for_update().select_related("institution", "group", "subject").get(pk=assessment_id)
            except Assessment.DoesNotExist:
                raise NotFound()
            if assessment.institution_id != candidate.institution_id or not assessment.institution.is_active:
                raise NotFound()
            if candidate.status != Candidate.Status.ACTIVE:
                raise PermissionDenied("This candidate profile is not active.")
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
            rows = _validate_assessment_for_candidate(assessment, candidate, now)
            question_ids = [row.question_id for row in rows]
            # Lock questions while the validated content and options are copied into the attempt.
            list(Question.objects.select_for_update().filter(pk__in=question_ids).order_by("pk").values_list("pk", flat=True))
            rows = _validate_assessment_for_candidate(assessment, candidate, now)
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
def expire_attempt(attempt, now=None, *, actor=None):
    now = now or timezone.now()
    locked = Attempt.objects.select_for_update().select_related("institution").get(pk=attempt.pk)
    if locked.status == Attempt.Status.IN_PROGRESS and now >= locked.expires_at:
        locked.status = Attempt.Status.EXPIRED
        # submitted_at records an explicit candidate submission only; expiry is represented by status.
        locked.save(update_fields=("status", "updated_at"))
        attempt.status = locked.status
        attempt.updated_at = locked.updated_at
        record_event(institution=locked.institution, actor=actor, event_type=AuditEvent.Type.ATTEMPT_EXPIRED, resource=locked)
        return True
    attempt.status = locked.status
    return False


def lock_candidate_attempt(user, attempt_id):
    try:
        return Attempt.objects.select_for_update().select_related("assessment", "candidate", "institution").get(
            pk=attempt_id, candidate__user=user, candidate__status=Candidate.Status.ACTIVE,
            institution__is_active=True,
        )
    except Attempt.DoesNotExist:
        raise NotFound()


def mark_question_for_review(attempt, question, marked, now=None):
    row = AttemptQuestion.objects.select_for_update().get(attempt=attempt, question=question)
    row.marked_for_review = marked
    row.save(update_fields=("marked_for_review", "updated_at"))
    attempt.last_activity_at = now or timezone.now()
    attempt.save(update_fields=("last_activity_at", "updated_at"))
    return row
