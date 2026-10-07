from institutions.workspace_access import enforce_workspace_mode
from rest_framework.permissions import BasePermission

from .tenancy import APPROVE_ROLES, READ_ROLES, REVIEW_ROLES, WRITE_ROLES, has_question_role, institution_ids_for_question_bank, is_platform_admin


class CanAccessQuestionBank(BasePermission):
    def has_permission(self, request, view):
        enforce_workspace_mode(request, "questions")
        return bool(request.user and request.user.is_authenticated and institution_ids_for_question_bank(request.user).exists())

    def has_object_permission(self, request, view, obj):
        return has_question_role(request.user, obj.institution_id, READ_ROLES)


class CanManageTopics(CanAccessQuestionBank):
    def has_permission(self, request, view):
        enforce_workspace_mode(request, "questions")
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return super().has_permission(request, view)
        if is_platform_admin(request.user):
            return True
        return request.user.institution_memberships.filter(is_active=True, institution__is_active=True, role__in=WRITE_ROLES).exists()

    def has_object_permission(self, request, view, obj):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return super().has_object_permission(request, view, obj)
        return has_question_role(request.user, obj.institution_id, WRITE_ROLES)


class CanManageQuestionBank(BasePermission):
    def has_permission(self, request, view):
        enforce_workspace_mode(request, "questions")
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        return user.institution_memberships.filter(is_active=True, institution__is_active=True, role__in=WRITE_ROLES).exists()


class CanEditQuestion(CanManageQuestionBank):
    def has_object_permission(self, request, view, obj):
        if has_question_role(request.user, obj.institution_id, APPROVE_ROLES):
            return obj.status in {obj.Status.DRAFT, obj.Status.REVIEW}
        return (
            obj.created_by_id == request.user.pk
            and obj.status in {obj.Status.DRAFT, obj.Status.REVIEW}
            and has_question_role(request.user, obj.institution_id, {"teacher", "examiner"})
        )


class CanDeleteQuestion(CanManageQuestionBank):
    def has_object_permission(self, request, view, obj):
        if obj.status != obj.Status.DRAFT:
            return False
        if has_question_role(request.user, obj.institution_id, APPROVE_ROLES):
            return True
        return obj.created_by_id == request.user.pk and has_question_role(request.user, obj.institution_id, {"teacher", "examiner"})


class CanSubmitQuestion(CanManageQuestionBank):
    def has_object_permission(self, request, view, obj):
        return obj.created_by_id == request.user.pk or has_question_role(request.user, obj.institution_id, APPROVE_ROLES)


class CanReviewQuestion(CanManageQuestionBank):
    def has_permission(self, request, view):
        enforce_workspace_mode(request, "questions")
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        return user.institution_memberships.filter(is_active=True, institution__is_active=True, role__in=REVIEW_ROLES).exists()

    def has_object_permission(self, request, view, obj):
        return has_question_role(request.user, obj.institution_id, REVIEW_ROLES)


class CanApproveQuestion(CanReviewQuestion):
    def has_permission(self, request, view):
        enforce_workspace_mode(request, "questions")
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        return user.institution_memberships.filter(is_active=True, institution__is_active=True, role__in=APPROVE_ROLES).exists()

    def has_object_permission(self, request, view, obj):
        return has_question_role(request.user, obj.institution_id, APPROVE_ROLES)
