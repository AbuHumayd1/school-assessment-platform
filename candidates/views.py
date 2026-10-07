from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import ScopedRateThrottle

from assessments.models import Assessment, AssessmentQuestion
from attempts.models import Attempt
from attempts.services import _validate_assessment_for_candidate
from attempts.tenancy import active_group_ids_for_candidate, assessment_window_state
from groups.models import Group
from audit.models import AuditEvent
from audit.services import record_event
from tenants.permissions import CanManageCandidates
from tenants.querysets import can_manage_institution, resolve_institution_context
from tenants.permissions import CanManageInstitution, STAFF_ROLES
from .models import Candidate
from .serializers import CandidateSerializer
from .provisioning import provision_candidate_access


class CandidateProfileConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = {
        "code": "ambiguous_candidate_profiles",
        "detail": "More than one candidate profile is linked to this account. Contact your institution.",
    }


class CandidateDeletionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = {
        "code": "candidate_has_assessment_history",
        "detail": "This candidate has assessment history and cannot be permanently deleted. Deactivate the candidate instead.",
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

        ).filter(
            Q(candidate_access=Assessment.CandidateAccess.ASSIGNED_GROUP, group_id__in=eligible_group_ids, group__is_active=True)
            | Q(candidate_access=Assessment.CandidateAccess.SPECIFIC_CANDIDATES, candidate_assignments__candidate=candidate)
        ).distinct().select_related("institution", "subject", "group").prefetch_related(
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
                    "name": assessment.group.name if assessment.group_id else None,
                    "code": assessment.group.code if assessment.group_id else None,
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


class CandidatePagination(PageNumberPagination):
    page_size = 25


class CandidateViewSet(viewsets.ModelViewSet):
    serializer_class = CandidateSerializer
    permission_classes = [CanManageCandidates]
    pagination_class = CandidatePagination

    @action(detail=False, methods=["post"], url_path="import-preview")
    def import_preview(self, request):
        from .bulk_import import parse_file, validate_rows, sign_preview
        institution = self.get_institution()
        rows, errors = validate_rows(parse_file(request.FILES.get("file")), institution, request, generate_ids=True)
        response = Response({"rows": rows, "errors": errors, "count": len(rows),
                             "token": None if errors else sign_preview(rows, institution, request.user)})
        response["Cache-Control"] = "no-store, private"
        return response

    @action(detail=False, methods=["post"], url_path="import-confirm")
    def import_confirm(self, request):
        from .bulk_import import read_preview, validate_rows
        institution = self.get_institution()
        rows = read_preview(request.data.get("token"), institution, request.user)
        try:
            with transaction.atomic():
                from institutions.models import Institution
                Institution.objects.select_for_update().get(pk=institution.pk)
                rows, errors = validate_rows(rows, institution, request)
                if errors:
                    return Response({"detail": "Import failed validation. No candidates created.", "errors": errors}, status=400)
                for row in rows:
                    serializer = CandidateSerializer(data={key: value for key, value in row.items() if key != "row"},
                                                     context={"institution": institution, "request": request})
                    serializer.is_valid(raise_exception=True)
                    serializer.save(institution=institution)
                record_event(institution=institution, actor=request.user,
                             event_type=AuditEvent.Type.MEMBERSHIP_CHANGED, resource=institution,
                             metadata={"action": "candidates_imported", "count": len(rows)})
        except IntegrityError:
            raise ValidationError({"detail": "A candidate ID is now in use. No candidates created. Upload again."})
        return Response({"created_count": len(rows)}, status=201, headers={"Cache-Control": "no-store, private"})

    def get_permissions(self):
        if self.action == "destroy":
            return [CanManageInstitution()]
        return super().get_permissions()

    def get_institution(self):
        if not hasattr(self, "_institution_context"):
            # Preserve the established create-body selector while preferring the
            # shared workspace header/query convention for all management actions.
            body_id = self.request.data.get("institution") if self.action == "create" else None
            if body_id and not (self.request.headers.get("X-Institution-ID") or self.request.query_params.get("institution")):
                try:
                    body_id = int(body_id)
                except (ValueError, TypeError):
                    raise ValidationError({"institution": "Select a valid institution."})
                if not can_manage_institution(self.request.user, body_id, STAFF_ROLES):
                    raise ValidationError({"institution": "Choose an institution you are authorized to manage."})
                from institutions.models import Institution
                self._institution_context = Institution.objects.get(pk=body_id, is_active=True)
            else:
                roles = {"institution_admin"} if self.action in {"provision_access", "destroy"} else STAFF_ROLES
                self._institution_context = resolve_institution_context(self.request, roles)
        return self._institution_context

    def get_queryset(self):
        candidates = Candidate.objects.filter(institution=self.get_institution()).select_related("user", "institution")
        search = self.request.query_params.get("search", "").strip()[:200]
        # Each word may match any name/identifier/contact field.
        for word in search.split():
            candidates = candidates.filter(Q(first_name__icontains=word) | Q(last_name__icontains=word) | Q(candidate_id__icontains=word) | Q(email__icontains=word))
        candidate_status = self.request.query_params.get("status")
        if candidate_status:
            if candidate_status not in Candidate.Status.values:
                raise ValidationError({"status": "Choose a valid candidate status."})
            candidates = candidates.filter(status=candidate_status)
        return candidates.order_by("first_name", "last_name", "pk")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["institution"] = self.get_institution()
        supplied = self.request.data.get("institution")
        if supplied is not None and str(supplied) != str(context["institution"].pk):
            raise ValidationError({"institution": "Candidates cannot be assigned or moved to another workspace."})
        return context

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save(institution=self.get_institution())
        except IntegrityError:
            raise ValidationError({"candidate_id": "This candidate ID is already used in this workspace."})

    def perform_update(self, serializer):
        if "institution" in self.request.data and str(self.request.data["institution"]) != str(serializer.instance.institution_id):
            raise ValidationError({"institution": "Candidates cannot be moved between institutions through this API."})
        try:
            with transaction.atomic():
                # Reload after locking so a concurrent profile PATCH cannot
                # overwrite the user link created by portal provisioning.
                serializer.instance = Candidate.objects.select_for_update().get(pk=serializer.instance.pk)
                serializer.save()
        except (DjangoValidationError, IntegrityError):
            raise ValidationError({"candidate_id": "Candidate identity is locked or this ID is already in use."})

    def perform_destroy(self, instance):
        try:
            with transaction.atomic():
                # start_attempt uses the same Candidate lock before creating history.
                candidate = Candidate.objects.select_for_update().get(pk=instance.pk)
                if candidate.attempts.exists() or candidate.results.exists():
                    raise CandidateDeletionConflict()
                record_event(
                    institution=candidate.institution, actor=self.request.user,
                    event_type=AuditEvent.Type.MEMBERSHIP_CHANGED, resource=candidate,
                    metadata={"action": "candidate_deleted", "candidate_id": candidate.candidate_id},
                )
                try:
                    candidate.delete()
                except (ProtectedError, IntegrityError):
                    # Retain FK protection for history arriving through another write path.
                    raise CandidateDeletionConflict()
        except Candidate.DoesNotExist:
            raise NotFound()

    @action(detail=True, methods=["post"], url_path="provision-access",
            permission_classes=[CanManageInstitution], throttle_classes=[ScopedRateThrottle])
    def provision_access(self, request, pk=None):
        if request.data:
            raise ValidationError({"detail": "Portal access uses the saved candidate details; no account fields are accepted."})
        credentials = provision_candidate_access(self.get_object(), request.user)
        response = Response(credentials, status=status.HTTP_201_CREATED)
        response["Cache-Control"] = "no-store, private"
        return response

    def get_throttles(self):
        if self.action == "provision_access":
            self.throttle_scope = "candidate_provision"
        return super().get_throttles()
