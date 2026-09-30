from django.db import transaction
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from audit.models import AuditEvent
from audit.services import record_event
from tenants.models import InstitutionMembership
from .models import Institution
from .permissions import CanManageInstitutionProfile, is_platform_administrator
from .serializers import InstitutionSerializer


class InstitutionViewSet(viewsets.ModelViewSet):
    serializer_class = InstitutionSerializer
    permission_classes = (CanManageInstitutionProfile,)
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        user = self.request.user
        if is_platform_administrator(user):
            return Institution.objects.all()
        return Institution.objects.filter(
            memberships__user=user,
            memberships__is_active=True,
            memberships__role=InstitutionMembership.Role.INSTITUTION_ADMIN,
            is_active=True,
        ).distinct()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        if not is_platform_administrator(request.user):
            raise PermissionDenied("Only platform administrators can create institutions.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        institution = serializer.save()
        membership, created = InstitutionMembership.objects.get_or_create(
            user=self.request.user,
            institution=institution,
            defaults={"role": InstitutionMembership.Role.INSTITUTION_ADMIN, "is_active": True},
        )
        if created:
            record_event(
                institution=institution,
                actor=self.request.user,
                event_type=AuditEvent.Type.MEMBERSHIP_CHANGED,
                resource=membership,
                metadata={"action": "created", "role": membership.role},
            )

    @transaction.atomic
    def perform_update(self, serializer):
        original = serializer.instance
        changed_fields = [
            field for field in ("name", "institution_type", "logo", "email", "phone", "address", "timezone", "is_active")
            if getattr(original, field) != serializer.validated_data.get(field, getattr(original, field))
        ]
        institution = serializer.save()
        if changed_fields:
            record_event(
                institution=institution,
                actor=self.request.user,
                event_type=AuditEvent.Type.INSTITUTION_PROFILE_UPDATED,
                resource=institution,
                metadata={"fields": sorted(changed_fields)},
            )
