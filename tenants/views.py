from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from assessments.models import Assessment
from attempts.models import Attempt
from audit.models import AuditEvent
from audit.services import record_event
from candidates.models import Candidate
from groups.models import Group
from results.models import Result
from subjects.models import Subject
from .models import InstitutionMembership
from .querysets import resolve_institution_context
from .serializers import InstitutionMembershipSerializer


class InstitutionMembershipViewSet(viewsets.ModelViewSet):
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
            {InstitutionMembership.Role.INSTITUTION_ADMIN},
        )
        now = timezone.now()
        assessments = Assessment.objects.filter(
            institution=institution,
            status__in=(Assessment.Status.APPROVED, Assessment.Status.SCHEDULED),
        ).filter(
            Q(start_at__isnull=True) | Q(start_at__lte=now),
            Q(end_at__isnull=True) | Q(end_at__gte=now),
        )
        return Response({
            "institution": {
                "id": institution.pk,
                "name": institution.name,
                "slug": institution.slug,
                "institution_type": institution.institution_type,
                "timezone": institution.timezone,
            },
            "counts": {
                "active_members": InstitutionMembership.objects.filter(
                    institution=institution, is_active=True, user__is_active=True,
                ).count(),
                "active_candidates": Candidate.objects.filter(
                    institution=institution, status=Candidate.Status.ACTIVE,
                ).count(),
                "active_groups": Group.objects.filter(institution=institution, is_active=True).count(),
                "active_subjects": Subject.objects.filter(institution=institution, is_active=True).count(),
                "available_assessments": assessments.count(),
                "submitted_attempts": Attempt.objects.filter(
                    institution=institution, status=Attempt.Status.SUBMITTED,
                ).count(),
                "published_results": Result.objects.filter(
                    institution=institution, status=Result.Status.PUBLISHED,
                ).count(),
            },
        })
