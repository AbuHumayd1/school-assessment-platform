from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from attempts.models import Answer, Attempt, AttemptQuestion, AttemptQuestionOption
from audit.models import AuditEvent
from audit.services import record_event
from questions.models import Question
from .grading import grade_for_percentage
from .models import Result, ResultQuestion


def _authorize_actor(actor, institution_id, roles):
    if actor is None:
        return
    if actor.is_superuser or actor.institution_memberships.filter(
        is_active=True, institution__is_active=True, role="platform_admin",
    ).exists():
        return
    if not actor.institution_memberships.filter(
        institution_id=institution_id, is_active=True, institution__is_active=True, role__in=roles,
    ).exists():
        raise PermissionDenied("You do not have permission to perform this result action.")


def _question_mark(attempt, row):
    answer = Answer.objects.filter(attempt_id=attempt.pk, question_id=row.question_id).prefetch_related("selections__option").first()
    available = Decimal(row.marks_available or 0)
    if row.question.institution_id != attempt.institution_id or row.question.subject_id != attempt.assessment.subject_id:
        return ResultQuestion.Status.INVALID, Decimal("0.00"), "Attempt question does not match the assessment tenant and subject."
    if not attempt.assessment.assessment_questions.filter(question_id=row.question_id).exists():
        return ResultQuestion.Status.INVALID, Decimal("0.00"), "Attempt question is not part of the assessment configuration."
    if answer is None:
        return ResultQuestion.Status.UNANSWERED, Decimal("0.00"), ""
    if answer.attempt_id != attempt.pk or answer.question_id != row.question_id:
        return ResultQuestion.Status.INVALID, Decimal("0.00"), "Stored answer does not match this attempt question."
    selections = list(answer.selections.all())
    selected = {selection.option_id for selection in selections}
    offered = set(AttemptQuestionOption.objects.filter(attempt_question=row).values_list("option_id", flat=True))
    if len(selected) != len(selections) or not selected.issubset(offered) or any(s.option.question_id != row.question_id for s in selections):
        return ResultQuestion.Status.INVALID, Decimal("0.00"), "Stored selection is not valid for this attempt question."
    if not selected:
        return ResultQuestion.Status.UNANSWERED, Decimal("0.00"), ""
    question = row.question
    options = list(question.options.all())
    correct = {option.pk for option in options if option.is_correct}
    if question.question_type in (Question.Type.MULTIPLE_CHOICE, Question.Type.TRUE_FALSE):
        structurally_valid = len(correct) == 1 and len(options) >= 2
        structurally_valid = structurally_valid and (question.question_type != Question.Type.TRUE_FALSE or len(options) == 2)
        structurally_valid = structurally_valid and len(selected) == 1
    elif question.question_type == Question.Type.MULTIPLE_SELECT:
        structurally_valid = bool(correct) and len(options) >= 2
    else:
        structurally_valid = False
    if not structurally_valid or not correct.issubset(offered):
        return ResultQuestion.Status.INVALID, Decimal("0.00"), "Question answer key or option snapshot is invalid."
    is_correct = selected == correct
    return (ResultQuestion.Status.CORRECT if is_correct else ResultQuestion.Status.INCORRECT,
            available if is_correct else Decimal("0.00"), "")


def _eligible_for_immediate_publish(attempt, now):
    assessment = attempt.assessment
    if assessment.result_visibility == assessment.ResultVisibility.HIDDEN:
        return False
    if assessment.result_visibility == assessment.ResultVisibility.SCHEDULED_RELEASE:
        return bool(assessment.end_at and now >= assessment.end_at)
    return assessment.result_visibility == assessment.ResultVisibility.AFTER_SUBMISSION


@transaction.atomic
def mark_attempt(attempt_id, *, now=None, actor=None):
    now = now or timezone.now()
    try:
        attempt = Attempt.objects.select_for_update().select_related("assessment", "candidate", "institution").get(pk=attempt_id)
    except Attempt.DoesNotExist:
        from rest_framework.exceptions import NotFound
        raise NotFound()
    if attempt.status not in (Attempt.Status.SUBMITTED, Attempt.Status.EXPIRED):
        raise ValidationError({"attempt": "Only submitted or expired attempts can be marked."})
    _authorize_actor(actor, attempt.institution_id, {"platform_admin", "institution_admin", "examiner"})
    rows = list(AttemptQuestion.objects.filter(attempt=attempt).select_related("question").prefetch_related("question__options").order_by("order", "id"))
    total = sum((Decimal(row.marks_available or 0) for row in rows), Decimal("0.00"))
    obtained = Decimal("0.00")
    marks = []
    for row in rows:
        state, value, note = _question_mark(attempt, row)
        obtained += value
        marks.append((row, state, value, note))
    percentage = ((obtained * Decimal("100")) / total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total > 0 else Decimal("0.00")
    passed = total > 0 and obtained >= Decimal(attempt.pass_mark_snapshot or 0)
    result, _ = Result.objects.select_for_update().get_or_create(
        attempt=attempt,
        defaults={"institution": attempt.institution, "candidate": attempt.candidate, "assessment": attempt.assessment,
                  "total_marks": total, "marks_obtained": obtained, "pass_mark": attempt.pass_mark_snapshot,
                  "percentage": percentage, "grade": grade_for_percentage(percentage), "passed": passed,
                  "status": Result.Status.PROVISIONAL, "marked_at": now},
    )
    # Re-marking reflects the unchanged historical evidence and remains idempotent.
    result.institution = attempt.institution
    result.candidate = attempt.candidate
    result.assessment = attempt.assessment
    result.total_marks = total
    result.marks_obtained = obtained
    result.pass_mark = attempt.pass_mark_snapshot
    result.percentage = percentage
    result.grade = grade_for_percentage(percentage)
    result.passed = passed
    was_published = result.status == Result.Status.PUBLISHED
    if result.status not in (Result.Status.PUBLISHED, Result.Status.WITHHELD):
        if (attempt.assessment.result_release_mode == attempt.assessment.ResultReleaseMode.IMMEDIATE
                and _eligible_for_immediate_publish(attempt, now)):
            result.status = Result.Status.PUBLISHED
            result.published_at = now
        else:
            result.status = Result.Status.PROVISIONAL
            result.published_at = None
    result.save()
    record_event(institution=result.institution, actor=actor, event_type=AuditEvent.Type.RESULT_MARKED,
                 resource=result, metadata={"attempt_id": attempt.pk, "result_status": result.status})
    if result.status == Result.Status.PUBLISHED and not was_published:
        record_event(institution=result.institution, actor=actor, event_type=AuditEvent.Type.RESULT_PUBLISHED,
                     resource=result, metadata={"release_mode": attempt.assessment.result_release_mode})
    keep_ids = []
    for row, state, value, note in marks:
        detail, _ = ResultQuestion.objects.update_or_create(
            result=result, attempt_question=row,
            defaults={"marks_available": row.marks_available, "marks_obtained": value, "status": state, "validation_note": note},
        )
        keep_ids.append(detail.pk)
    result.questions.exclude(pk__in=keep_ids).delete()
    return result


@transaction.atomic
def publish_result(result_id, *, now=None, actor=None):
    now = now or timezone.now()
    try:
        result = Result.objects.select_for_update().select_related("assessment").get(pk=result_id)
    except Result.DoesNotExist:
        from rest_framework.exceptions import NotFound
        raise NotFound()
    if not result.marked_at:
        raise ValidationError({"result": "The result must be marked before publication."})
    _authorize_actor(actor, result.institution_id, {"platform_admin", "institution_admin"})
    assessment = result.assessment
    if assessment.result_visibility == assessment.ResultVisibility.HIDDEN:
        raise ValidationError({"result_visibility": "This assessment is configured to keep results hidden."})
    if assessment.result_visibility == assessment.ResultVisibility.SCHEDULED_RELEASE and (not assessment.end_at or now < assessment.end_at):
        raise ValidationError({"result_visibility": "The scheduled result release time has not arrived."})
    result.status = Result.Status.PUBLISHED
    result.published_at = result.published_at or now
    result.save(update_fields=("status", "published_at", "updated_at"))
    record_event(institution=result.institution, actor=actor, event_type=AuditEvent.Type.RESULT_PUBLISHED, resource=result)
    return result


@transaction.atomic
def withhold_result(result_id, *, actor=None):
    try:
        result = Result.objects.select_for_update().get(pk=result_id)
    except Result.DoesNotExist:
        from rest_framework.exceptions import NotFound
        raise NotFound()
    _authorize_actor(actor, result.institution_id, {"platform_admin", "institution_admin"})
    result.status = Result.Status.WITHHELD
    result.save(update_fields=("status", "updated_at"))
    record_event(institution=result.institution, actor=actor, event_type=AuditEvent.Type.RESULT_WITHHELD, resource=result)
    return result
