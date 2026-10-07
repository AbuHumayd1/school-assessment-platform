from institutions.workspace_access import WorkspaceAccessMixin
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from tenants.querysets import resolve_institution_context
from .models import User
from .serializers import UserSerializer


USER_DIRECTORY_ROLES = {"platform_admin", "institution_admin", "teacher", "examiner"}


class UserViewSet(WorkspaceAccessMixin, viewsets.ReadOnlyModelViewSet):
    workspace_module = "memberships"
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        selector = self.request.headers.get("X-Institution-ID") or self.request.query_params.get("institution")
        if selector:
            institution = resolve_institution_context(self.request, USER_DIRECTORY_ROLES)
            return User.objects.filter(institution_memberships__institution=institution,
                institution_memberships__is_active=True).distinct()
        if self.request.user.is_superuser:
            return User.objects.all()
        memberships = self.request.user.institution_memberships.filter(
            is_active=True, institution__is_active=True, role__in=USER_DIRECTORY_ROLES,
        )
        institution_ids = memberships.values_list("institution_id", flat=True)
        if not institution_ids.exists():
            return User.objects.none()
        return User.objects.filter(
            institution_memberships__institution_id__in=institution_ids,
            institution_memberships__is_active=True,
            institution_memberships__institution__is_active=True,
        ).distinct()
