from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import User
from .serializers import UserSerializer


USER_DIRECTORY_ROLES = {"platform_admin", "institution_admin", "teacher", "examiner"}


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
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
