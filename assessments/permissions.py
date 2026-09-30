from rest_framework.permissions import BasePermission

from questions.tenancy import has_question_role, is_platform_admin
from .models import Assessment
from .tenancy import (
    ASSESSMENT_APPROVE_ROLES, ASSESSMENT_READ_ROLES, ASSESSMENT_REVIEW_ROLES,
    ASSESSMENT_WRITE_ROLES, assessment_institution_ids,
)


class CanAccessAssessments(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and assessment_institution_ids(user).exists())

    def has_object_permission(self, request, view, obj):
        return has_question_role(request.user, obj.institution_id, ASSESSMENT_READ_ROLES)


class CanManageAssessment(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        return user.institution_memberships.filter(is_active=True, institution__is_active=True, role__in=ASSESSMENT_WRITE_ROLES).exists()

    def has_object_permission(self, request, view, obj):
        if obj.status != Assessment.Status.DRAFT:
            return False
        return has_question_role(request.user, obj.institution_id, ASSESSMENT_WRITE_ROLES)


class CanDeleteAssessment(CanManageAssessment):
    def has_object_permission(self, request, view, obj):
        return obj.status == Assessment.Status.DRAFT and has_question_role(request.user, obj.institution_id, ASSESSMENT_WRITE_ROLES)


class CanReviewAssessment(CanAccessAssessments):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        return user.institution_memberships.filter(is_active=True, institution__is_active=True, role__in=ASSESSMENT_REVIEW_ROLES).exists()

    def has_object_permission(self, request, view, obj):
        return has_question_role(request.user, obj.institution_id, ASSESSMENT_REVIEW_ROLES)


class CanApproveAssessment(CanReviewAssessment):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        return user.institution_memberships.filter(is_active=True, institution__is_active=True, role__in=ASSESSMENT_APPROVE_ROLES).exists()

    def has_object_permission(self, request, view, obj):
        return has_question_role(request.user, obj.institution_id, ASSESSMENT_APPROVE_ROLES)
