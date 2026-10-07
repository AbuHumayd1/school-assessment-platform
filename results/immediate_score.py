from attempts.access import ExamAccessContext
from attempts.models import Attempt
from .models import Result, ResultQuestion


def immediate_score(attempt, request):
    """A candidate-only allowlist, independent of result publication."""
    if request is None or not attempt.assessment.show_score_immediately:
        return None
    context = request.auth
    if isinstance(context, ExamAccessContext):
        owns = (context.access_mode == "quick" and context.candidate.pk == attempt.candidate_id
                and context.assessment.pk == attempt.assessment_id
                and context.institution.pk == attempt.institution_id)
    else:
        owns = (request.user.is_authenticated and attempt.candidate.user_id == request.user.pk
                and not attempt.assessment.uses_quick_delivery)
    if not owns or attempt.status not in (Attempt.Status.SUBMITTED, Attempt.Status.EXPIRED) or not attempt.submitted_at:
        return None
    result = Result.objects.filter(attempt=attempt, candidate_id=attempt.candidate_id,
        assessment_id=attempt.assessment_id, institution_id=attempt.institution_id, marked_at__isnull=False).first()
    if result is None or result.total_marks <= 0:
        return None
    rows = result.questions.all()
    if (rows.count() != attempt.attempt_questions.count() or not rows.exists()
            or rows.filter(status=ResultQuestion.Status.INVALID).exists()):
        return None
    return {"marks_obtained": str(result.marks_obtained), "total_marks": str(result.total_marks)}
