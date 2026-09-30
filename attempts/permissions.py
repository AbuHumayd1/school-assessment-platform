from rest_framework.permissions import BasePermission

from .tenancy import is_candidate_owner, is_attempt_staff


class IsCandidateUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class OwnAttemptOrInstitutionStaff(BasePermission):
    def has_object_permission(self, request, view, obj):
        return is_candidate_owner(request.user, obj) or is_attempt_staff(request.user, obj.institution_id)


class OwnCandidateAttempt(BasePermission):
    def has_object_permission(self, request, view, obj):
        return is_candidate_owner(request.user, obj)
