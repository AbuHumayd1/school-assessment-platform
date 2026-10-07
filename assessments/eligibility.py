"""Portal eligibility strategies; Quick credentials remain a separate authority."""
from .models import Assessment
from attempts.tenancy import active_group_ids_for_candidate
from candidates.models import Candidate
from django.db.models import Q, Value, CharField
from django.db.models.functions import Concat


def institution_candidates(institution, search="", status=Candidate.Status.ACTIVE):
    queryset = Candidate.objects.filter(institution=institution, status=status)
    if search:
        queryset = queryset.annotate(full_name=Concat("first_name", Value(" "), "last_name", output_field=CharField())).filter(
            Q(full_name__icontains=search) | Q(candidate_id__icontains=search) | Q(email__icontains=search))
    return queryset


def directly_assigned_candidates(assessment):
    return institution_candidates(assessment.institution).filter(assessment_assignments__assessment=assessment)


def eligible_subject_questions(institution, subject, search=""):
    from questions.models import Question
    queryset = Question.objects.filter(institution=institution, subject=subject, status=Question.Status.APPROVED,
        content_locked=True, available_for_new_assessments=True)
    if search:
        queryset = queryset.filter(text__icontains=search)
    return queryset


def question_document_order(question):
    """Retain import document/section order; ordinary bank questions fall back to ID."""
    metadata = question.source_metadata if isinstance(question.source_metadata, dict) else {}
    clone = metadata.get("production_clone")
    clone = clone if isinstance(clone, dict) else {}
    document = metadata.get("import_session_id") or clone.get("source_import_session_uuid") or ""
    def position(key):
        value = metadata.get(key)
        return value if type(value) is int and value >= 0 else float("inf")
    return (str(document), position("section_order"), position("document_order"), question.pk)


def portal_candidate_is_assigned(assessment, candidate, eligible_group_ids=None):
    if assessment.institution_id != candidate.institution_id or assessment.uses_quick_delivery:
        return False
    if assessment.candidate_access == Assessment.CandidateAccess.SPECIFIC_CANDIDATES:
        return assessment.candidate_assignments.filter(candidate=candidate).exists()
    if assessment.candidate_access == Assessment.CandidateAccess.ASSIGNED_GROUP:
        if not assessment.group_id or not assessment.group.is_active:
            return False
        groups = active_group_ids_for_candidate(candidate) if eligible_group_ids is None else eligible_group_ids
        return assessment.group_id in groups
    return False
