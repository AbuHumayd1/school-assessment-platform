from institutions.workspace_access import WorkspaceAccessMixin
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from assessments.models import Assessment
from attempts.models import Attempt
from audit.models import AuditEvent
from audit.services import record_event
from candidates.models import Candidate
from groups.models import Group
from questions.models import Question
from questions.tenancy import is_platform_admin
from results.models import Result
from subjects.models import Subject
from .models import InstitutionMembership
from .querysets import resolve_institution_context
from .serializers import InstitutionMembershipSerializer


class InstitutionMembershipViewSet(WorkspaceAccessMixin, viewsets.ModelViewSet):
    workspace_module = "memberships"
    serializer_class = InstitutionMembershipSerializer
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_institution(self):
        if not hasattr(self, "_institution_context"):
            self._institution_context = resolve_institution_context(
                self.request,
                {InstitutionMembership.Role.INSTITUTION_ADMIN},
            )
        return self._institution_context

    def get_queryset(self):
        institution = self.get_institution()
        return InstitutionMembership.objects.filter(institution=institution).select_related("user", "institution").order_by("pk")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["institution"] = self.get_institution()
        return context

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save()

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.save()


class InstitutionDashboardView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        institution = resolve_institution_context(
            request,
            {InstitutionMembership.Role.INSTITUTION_ADMIN, InstitutionMembership.Role.TEACHER,
             InstitutionMembership.Role.EXAMINER},
        )
        section = request.query_params.get("section")
        if section not in (None, "assessments", "results"):
            raise ValidationError({"section": "Select assessments or results."})
        now = timezone.now()
        all_assessments = Assessment.objects.filter(institution=institution)
        if section == "assessments":
            upcoming = all_assessments.filter(status=Assessment.Status.SCHEDULED).filter(
                Q(end_at__isnull=True) | Q(end_at__gte=now),
            ).order_by("start_at", "pk")

            def assessment_rows(queryset):
                return [{
                    "id": row.pk, "title": row.title, "status": row.status,
                    "subject": row.subject.name, "group": row.group.name if row.group else None,
                    "start_at": row.start_at, "end_at": row.end_at,
                    "duration_minutes": row.duration_minutes,
                } for row in queryset.filter(subject__institution=institution).filter(
                    Q(group__isnull=True) | Q(group__institution=institution),
                ).select_related("subject", "group")[:5]]

            return Response({
                "institution_id": institution.pk,
                "timezone": institution.timezone,
                "upcoming_assessments": assessment_rows(upcoming),
                "recent_assessments": assessment_rows(all_assessments.order_by("-created_at", "-pk")),
            })
        if section == "results":
            # Existing result read roles include all workspace staff. Return summary
            # fields only, never answers, per-question marking, or candidate contacts.
            rows = Result.objects.filter(
                institution=institution, candidate__institution=institution,
                assessment__institution=institution, attempt__institution=institution,
            ).select_related("candidate", "assessment").order_by("-marked_at", "-pk")[:5]
            return Response({"institution_id": institution.pk, "timezone": institution.timezone, "recent_results": [{
                "id": row.pk, "candidate_id": row.candidate.candidate_id,
                "assessment_title": row.assessment.title, "status": row.status,
                "marks_obtained": str(row.marks_obtained), "total_marks": str(row.total_marks),
                "marked_at": row.marked_at,
            } for row in rows]})
        assessments = all_assessments.filter(
            status__in=(Assessment.Status.APPROVED, Assessment.Status.SCHEDULED),
        ).filter(
            Q(start_at__isnull=True) | Q(start_at__lte=now),
            Q(end_at__isnull=True) | Q(end_at__gte=now),
        )
        counts = {
            "active_candidates": Candidate.objects.filter(
                institution=institution, status=Candidate.Status.ACTIVE,
            ).count(),
            "questions": Question.objects.filter(institution=institution).count(),
            "assessments": all_assessments.count(),
            "results": Result.objects.filter(institution=institution).count(),
            "active_groups": Group.objects.filter(institution=institution, is_active=True).count(),
            "active_subjects": Subject.objects.filter(institution=institution, is_active=True).count(),
            "available_assessments": assessments.count(),
            "published_results": Result.objects.filter(institution=institution, status=Result.Status.PUBLISHED).count(),
        }
        admin = is_platform_admin(request.user) or InstitutionMembership.objects.filter(
            user=request.user, institution=institution, is_active=True, role="institution_admin",
        ).exists()
        if admin:
            counts["active_members"] = InstitutionMembership.objects.filter(
                institution=institution, is_active=True, user__is_active=True,
            ).count()
        if admin or InstitutionMembership.objects.filter(
            user=request.user, institution=institution, is_active=True, role="examiner",
        ).exists():
            counts["submitted_attempts"] = Attempt.objects.filter(
                institution=institution, status=Attempt.Status.SUBMITTED,
            ).count()
        status_counts = dict(all_assessments.order_by().values("status").annotate(
            total=Count("pk"),
        ).values_list("status", "total"))
        return Response({
            "institution": {
                "id": institution.pk,
                "name": institution.name,
                "slug": institution.slug,
                "institution_type": institution.institution_type,
                "timezone": institution.timezone,
            },
            "counts": counts,
            "assessment_status_counts": {value: status_counts.get(value, 0) for value in Assessment.Status.values},
        })
