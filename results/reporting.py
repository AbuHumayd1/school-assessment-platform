"""Read-only owner reporting. One row per participant, using their latest attempt.

Current eligible candidates are unioned with historical participants. Scores are
stored Result values, never recomputed; missing results remain null. No read here
expires, finalizes, marks or publishes an attempt.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import F, OuterRef, Prefetch, Q, Subquery
from django.utils import timezone

from assessments.models import Assessment
from attempts.models import Attempt, AttemptQuestionOption, Answer
from attempts.tenancy import active_local_date, assessment_window_state
from audit.models import AuditEvent
from candidates.models import Candidate
from .models import Result, ResultQuestion


def participant_queryset(assessment):
    candidates = Candidate.objects.filter(institution_id=assessment.institution_id)
    eligible = candidates.none()
    if assessment.candidate_access == Assessment.CandidateAccess.ASSIGNED_GROUP and assessment.group_id and assessment.group.is_active:
        today = active_local_date(assessment.institution)
        eligible = candidates.filter(
            Q(group_memberships__start_date__isnull=True) | Q(group_memberships__start_date__lte=today),
            Q(group_memberships__end_date__isnull=True) | Q(group_memberships__end_date__gte=today),
            status=Candidate.Status.ACTIVE, group_memberships__group_id=assessment.group_id,
            group_memberships__is_active=True,
        )
    elif assessment.candidate_access == Assessment.CandidateAccess.SPECIFIC_CANDIDATES:
        eligible = candidates.filter(assessment_assignments__assessment=assessment, status=Candidate.Status.ACTIVE)
    elif assessment.candidate_access == Assessment.CandidateAccess.ACCESS_CODE:
        eligible = candidates.filter(Q(assessment_assignments__assessment=assessment, status=Candidate.Status.ACTIVE) | Q(quick_credentials__configuration__assessment=assessment))
    attempts = Attempt.objects.filter(assessment=assessment, institution_id=assessment.institution_id)
    latest = attempts.filter(candidate_id=OuterRef("pk")).order_by("-attempt_number", "-pk")
    return candidates.filter(Q(pk__in=eligible.values("pk")) | Q(pk__in=attempts.values("candidate_id"))).annotate(
        latest_attempt_id=Subquery(latest.values("pk")[:1]),
    ).order_by("first_name", "last_name", "pk")


def submission_status(attempt, ended):
    if attempt is not None and attempt.status in {Attempt.Status.SUBMITTED, Attempt.Status.EXPIRED}:
        return "auto_submitted" if attempt.status == Attempt.Status.EXPIRED or getattr(attempt, "integrity_submitted", False) else "submitted"
    if ended:
        return "not_submitted"
    if attempt is not None and attempt.status == Attempt.Status.IN_PROGRESS:
        return "in_progress"
    if attempt is not None and attempt.status == Attempt.Status.CANCELLED:
        return "cancelled"
    return "not_started"


def attempt_queryset(assessment):
    return Attempt.objects.filter(assessment=assessment, institution_id=assessment.institution_id,
                                  candidate__institution_id=assessment.institution_id).select_related(
        "candidate", "result", "result__institution", "result__assessment",
    )


def annotate_automatic_submissions(assessment, attempts):
    """Batch recorded events, avoiding text joins across legacy MySQL collations."""
    attempts = list(attempts)
    event_ids = set(AuditEvent.objects.filter(
        institution_id=assessment.institution_id, resource_type="attempts.attempt",
        event_type="integrity_auto_submitted", resource_id__in=[str(attempt.pk) for attempt in attempts],
    ).values_list("resource_id", flat=True)) if attempts else set()
    for attempt in attempts:
        attempt.integrity_submitted = str(attempt.pk) in event_ids
    return attempts


def result_for_attempt(attempt):
    result = getattr(attempt, "result", None) if attempt is not None else None
    if result and (result.institution_id != attempt.institution_id or
                   result.assessment_id != attempt.assessment_id or result.candidate_id != attempt.candidate_id):
        return None
    return result


def candidate_row(candidate, attempt, ended, now):
    from .views import _candidate_visible
    result = result_for_attempt(attempt)
    released = bool(result and _candidate_visible(result, now))
    seconds = None
    if attempt and attempt.submitted_at:
        seconds = max(0, int((attempt.submitted_at - attempt.started_at).total_seconds()))
    return {
        "candidate": candidate.pk, "candidate_id": candidate.candidate_id,
        "name": f"{candidate.first_name} {candidate.last_name}".strip(),
        "submission_status": submission_status(attempt, ended),
        "attempt": attempt.pk if attempt else None,
        "started_at": attempt.started_at if attempt else None,
        "submitted_at": attempt.submitted_at if attempt else None, "time_used_seconds": seconds,
        "result": result.pk if result else None,
        "score": result.marks_obtained if result else None,
        "total_marks": result.total_marks if result else None,
        "percentage": result.percentage if result else None,
        "grade": result.grade if result else None, "passed": result.passed if result else None,
        "publication": "released" if released else "not_released",
        "result_status": result.status if result else None,
    }


def summarize(rows):
    results = [row for row in rows if row["result"] is not None]
    percentages = [row["percentage"] for row in results]
    passed = sum(row["passed"] for row in results)
    rounded = lambda value: value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    released = sum(row["publication"] == "released" for row in results)
    return {
        "total_candidates": len(rows), "started_count": sum(row["attempt"] is not None for row in rows),
        "not_started_count": sum(row["submission_status"] == "not_started" for row in rows),
        "in_progress_count": sum(row["submission_status"] == "in_progress" for row in rows),
        "submitted_count": sum(row["submission_status"] in {"submitted", "auto_submitted"} for row in rows),
        "auto_submitted_count": sum(row["submission_status"] == "auto_submitted" for row in rows),
        "not_submitted_count": sum(row["submission_status"] == "not_submitted" for row in rows),
        "results_count": len(results), "passed_count": passed, "failed_count": len(results) - passed,
        "average_percentage": rounded(sum(percentages) / len(results)) if results else None,
        "highest_percentage": max(percentages) if results else None,
        "lowest_percentage": min(percentages) if results else None,
        "pass_rate": rounded(Decimal(passed) * 100 / len(results)) if results else None,
        "released_count": released, "unreleased_count": len(results) - released,
        "release_state": release_state(len(results), released),
    }


def release_state(available, released):
    if not available:
        return "no_results"
    if not released:
        return "not_released"
    return "released" if released == available else "partially_released"


def releasable_results(assessment):
    """Existing marked, finalized results with consistent historical ownership."""
    return Result.objects.filter(
        assessment=assessment, institution_id=assessment.institution_id,
        candidate__institution_id=assessment.institution_id,
        attempt__institution_id=assessment.institution_id,
        attempt__assessment_id=assessment.pk, attempt__candidate_id=F("candidate_id"),
        attempt__status__in=(Attempt.Status.SUBMITTED, Attempt.Status.EXPIRED),
        marked_at__isnull=False,
    )


def build_assessment_report(assessment, institution, *, now=None):
    if institution.pk != assessment.institution_id:
        raise ValueError("Report institution must match the assessment.")
    now = now or timezone.now()
    candidates = list(participant_queryset(assessment))
    attempts = {attempt.pk: attempt for attempt in annotate_automatic_submissions(assessment, attempt_queryset(assessment).filter(
        pk__in=[candidate.latest_attempt_id for candidate in candidates if candidate.latest_attempt_id],
    ))}
    ended = assessment_window_state(assessment, now) == "ended"
    rows = [candidate_row(candidate, attempts.get(candidate.latest_attempt_id), ended, now) for candidate in candidates]
    return {
        "institution": {"name": institution.name, "timezone": institution.timezone},
        "assessment": {"title": assessment.title, "start_at": assessment.start_at, "end_at": assessment.end_at,
                       "delivery_supported": True},
        "generated_at": now, "summary": summarize(rows), "rows": rows,
    }


def submission_detail(assessment, attempt):
    from assessments.owner_serializers import InspectionQuestionSerializer
    annotate_automatic_submissions(assessment, [attempt])
    result = result_for_attempt(attempt)
    answers = {answer.question_id: {selection.option_id for selection in answer.selections.all()}
               for answer in Answer.objects.filter(attempt=attempt, question__institution_id=assessment.institution_id).prefetch_related("selections")}
    marks = {row.attempt_question_id: row for row in ResultQuestion.objects.filter(result=result)} if result else {}
    questions = attempt.attempt_questions.filter(question__institution_id=assessment.institution_id).select_related("question", "question__topic").prefetch_related(
        "question__options", "question__media",
        Prefetch("ordered_options", queryset=AttemptQuestionOption.objects.filter(
            option__question_id=F("attempt_question__question_id"),
            option__question__institution_id=assessment.institution_id,
        ).select_related("option")),
    )
    rows = []
    for question in questions:
        marked = marks.get(question.pk)
        selected = answers.get(question.question_id, set())
        content = dict(InspectionQuestionSerializer(question.question).data)
        # Taxonomy references are unnecessary for this response breakdown.
        content.pop("topic", None)
        content.pop("topic_name", None)
        rows.append({
            "order": question.order, "question": content,
            "options": [{"text": offered.option.text, "selected": offered.option_id in selected,
                         "is_correct": offered.option.is_correct} for offered in question.ordered_options.all()],
            "marks_available": marked.marks_available if marked else question.marks_available,
            "marks_obtained": marked.marks_obtained if marked else None,
            "status": marked.status if marked else "not_marked",
        })
    now = timezone.now()
    return {"exam": assessment.title, "candidate": candidate_row(attempt.candidate, attempt,
            assessment_window_state(assessment, now) == "ended", now), "questions": rows}
