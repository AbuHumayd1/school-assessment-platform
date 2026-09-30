from rest_framework.permissions import BasePermission

from tenants.models import InstitutionMembership


def is_platform_administrator(user):
    return bool(
        user.is_authenticated and (
            user.is_superuser or user.institution_memberships.filter(
                is_active=True,
                institution__is_active=True,
                role=InstitutionMembership.Role.PLATFORM_ADMIN,
            ).exists()
        )
    )


class CanManageInstitutionProfile(BasePermission):
    message = "Only institution or platform administrators may manage institution profiles."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return is_platform_administrator(user) or user.institution_memberships.filter(
            is_active=True,
            institution__is_active=True,
            role=InstitutionMembership.Role.INSTITUTION_ADMIN,
        ).exists()

    def has_object_permission(self, request, view, obj):
        if is_platform_administrator(request.user):
            return True
        return request.user.institution_memberships.filter(
            institution_id=obj.pk,
            is_active=True,
            institution__is_active=True,
            role=InstitutionMembership.Role.INSTITUTION_ADMIN,
        ).exists()
