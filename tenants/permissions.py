from rest_framework.permissions import BasePermission, SAFE_METHODS

MANAGER_ROLES = {"platform_admin", "institution_admin"}
STAFF_ROLES = MANAGER_ROLES | {"teacher", "examiner"}

class InstitutionScopedPermission(BasePermission):
    allowed_roles = STAFF_ROLES
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
    def has_object_permission(self, request, view, obj):
        from .querysets import can_manage_institution
        if request.user.is_superuser or request.user.institution_memberships.filter(is_active=True, role="platform_admin").exists():
            return True
        institution = getattr(obj, "institution", obj)
        return can_manage_institution(request.user, institution.pk, self.allowed_roles)

class CanManageInstitution(InstitutionScopedPermission):
    allowed_roles = MANAGER_ROLES
class CanManageCandidates(InstitutionScopedPermission):
    pass
class CanManageGroups(InstitutionScopedPermission):
    pass
class CanManageSubjects(InstitutionScopedPermission):
    pass
