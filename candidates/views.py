from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from assessments.models import Assessment, AssessmentQuestion
from attempts.models import Attempt
from attempts.services import _validate_assessment_for_candidate
from attempts.tenancy import active_group_ids_for_candidate, assessment_window_state
from groups.models import Group
from tenants.permissions import CanManageCandidates
from tenants.querysets import can_manage_institution, institutions_for_user
from .models import Candidate
from .serializers import CandidateSerializer


class CandidateProfileConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = {
        "code": "ambiguous_candidate_profiles",
        "detail": "More than one candidate profile is linked to this account. Contact your institution.",
    }


def resolve_portal_candidate(user):
    profiles = list(
        Candidate.objects.filter(user=user).select_related("institution").order_by("pk")[:2]
    )
    if not profiles:
        raise PermissionDenied({
            "code": "candidate_not_linked",
            "detail": "Your account is not linked to a candidate profile.",
        })
    if len(profiles) > 1:
        raise CandidateProfileConflict()

    candidate = profiles[0]
    if not candidate.institution.is_active:
        raise PermissionDenied({
            "code": "institution_inactive",
            "detail": "Candidate access is unavailable for this institution.",
        })
    if candidate.status != Candidate.Status.ACTIVE:
        raise PermissionDenied({
            "code": "candidate_inactive",
            "detail": "This candidate profile is not active.",
        })
    return candidate


class CandidateMeView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        candidate = resolve_portal_candidate(request.user)
        active_group_ids = active_group_ids_for_candidate(candidate)
        groups = Group.objects.filter(
            pk__in=active_group_ids,
            institution_id=candidate.institution_id,
        ).order_by("name", "pk")
        return Response({
            "candidate": {
                "id": candidate.pk,
                "candidate_id": candidate.candidate_id,
                "first_name": candidate.first_name,
                "last_name": candidate.last_name,
                "email": candidate.email or request.user.email,
            },
            "institution": {
                "id": candidate.institution_id,
                "name": candidate.institution.name,
                "timezone": candidate.institution.timezone,
            },
            "groups": [
                {"id": group.pk, "name": group.name, "code": group.code}
                for group in groups
            ],
        })


class CandidateExamListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        candidate = resolve_portal_candidate(request.user)
        now = timezone.now()
        eligible_group_ids = active_group_ids_for_candidate(candidate)
        if not eligible_group_ids:
            return Response({"exams": []})

        question_rows = AssessmentQuestion.objects.select_related("question").prefetch_related(
            "question__options",
        ).order_by("order", "id")
        attempts = Attempt.objects.filter(candidate=candidate).only(
            "id", "assessment_id", "status", "expires_at", "started_at",
        )
        assessments = Assessment.objects.filter(
            institution_id=candidate.institution_id,
            institution__is_active=True,
            status__in=(Assessment.Status.APPROVED, Assessment.Status.SCHEDULED),
            candidate_access=Assessment.CandidateAccess.ASSIGNED_GROUP,
            group_id__in=eligible_group_ids,
            group__is_active=True,
        ).select_related("institution", "subject", "group").prefetch_related(
            Prefetch("assessment_questions", queryset=question_rows),
            Prefetch("attempts", queryset=attempts, to_attr="candidate_attempts"),
        ).order_by("start_at", "title", "pk")

        summaries = []
        for assessment in assessments:
            window = assessment_window_state(assessment, now)
            if window == "upcoming" and assessment.end_at and now > assessment.end_at:
                continue

            rows = list(assessment.assessment_questions.all())
            try:
                _validate_assessment_for_candidate(
                    assessment,
                    candidate,
                    now,
                    check_window=False,
                    question_rows=rows,
                    eligible_group_ids=eligible_group_ids,
                )
            except (APIException, DjangoValidationError):
                # Invalid or no-longer-deliverable assessments are not candidate-visible.
                continue

            candidate_attempts = assessment.candidate_attempts
            attempts_used = len(candidate_attempts)
            active_attempt = next((
                attempt for attempt in candidate_attempts
                if attempt.status == Attempt.Status.IN_PROGRESS and attempt.expires_at > now
            ), None)
            can_resume = bool(active_attempt and assessment.resume_allowed)
            can_start = bool(
                not active_attempt and window == "open"
                and attempts_used < assessment.attempt_limit
            )

            if active_attempt:
                candidate_status = "in_progress"
            elif window == "upcoming":
                candidate_status = "upcoming"
            elif window == "ended":
                if not candidate_attempts:
                    continue
                candidate_status = "completed"
            elif attempts_used >= assessment.attempt_limit:
                candidate_status = "completed"
            else:
                candidate_status = "available"

            # An active attempt is resumable before considering the assessment window,
            # matching Phase 3's existing resume-before-new-eligibility behavior.
            if active_attempt:
                can_start = False

            total_marks = sum((row.marks for row in rows), Decimal("0.00"))
            summaries.append({
                "id": assessment.pk,
                "title": assessment.title,
                "assessment_type": assessment.assessment_type,
                "assessment_type_label": assessment.get_assessment_type_display(),
                "subject": {"id": assessment.subject_id, "name": assessment.subject.name},
                "group": {
                    "id": assessment.group_id,
                    "name": assessment.group.name,
                    "code": assessment.group.code,
                },
                "duration_minutes": assessment.duration_minutes,
                "total_marks": str(total_marks),
                "start_at": assessment.start_at.isoformat() if assessment.start_at else None,
                "end_at": assessment.end_at.isoformat() if assessment.end_at else None,
                "attempt_limit": assessment.attempt_limit,
                "attempts_used": attempts_used,
                "attempts_remaining": max(assessment.attempt_limit - attempts_used, 0),
                "status": candidate_status,
                "has_active_attempt": active_attempt is not None,
                "can_start": can_start,
                "can_resume": can_resume,
            })

        return Response({"exams": summaries})


class CandidateViewSet(viewsets.ModelViewSet):
    serializer_class = CandidateSerializer
    permission_classes = [CanManageCandidates]
    def get_queryset(self):
        return Candidate.objects.filter(institution_id__in=institutions_for_user(self.request.user), institution__is_active=True)
    def perform_create(self, serializer):
        institution_id = self.request.data.get("institution")
        if not institution_id or not can_manage_institution(self.request.user, institution_id, ["institution_admin", "teacher", "examiner"]):
            raise ValidationError({"institution": "Choose an institution you are authorized to manage."})
        serializer.save(institution_id=institution_id)
    def perform_update(self, serializer):
        if "institution" in self.request.data and str(self.request.data["institution"]) != str(serializer.instance.institution_id):
            raise ValidationError({"institution": "Candidates cannot be moved between institutions through this API."})
        serializer.save()
