from institutions.models import Institution
from questions.tenancy import institution_ids_for_question_bank, is_platform_admin, write_institution_for_request
from tenants.models import InstitutionMembership


ASSESSMENT_READ_ROLES = {"platform_admin", "institution_admin", "teacher", "examiner"}
ASSESSMENT_WRITE_ROLES = {"platform_admin", "institution_admin", "teacher", "examiner"}
ASSESSMENT_REVIEW_ROLES = {"platform_admin", "institution_admin", "examiner"}
ASSESSMENT_APPROVE_ROLES = {"platform_admin", "institution_admin"}


def assessment_institution_ids(user):
    return institution_ids_for_question_bank(user)


def can_access_assessment_tenant(user, institution_id, roles=ASSESSMENT_READ_ROLES):
    from questions.tenancy import has_question_role
    return has_question_role(user, institution_id, roles)


def writable_assessment_institutions(user):
    if is_platform_admin(user):
        return Institution.objects.filter(is_active=True)
    return Institution.objects.filter(
        memberships__user=user,
        memberships__is_active=True,
        memberships__role__in=ASSESSMENT_WRITE_ROLES,
        is_active=True,
    ).distinct()


def assessment_institution_for_request(request):
    from tenants.querysets import resolve_institution_context
    return resolve_institution_context(request, ASSESSMENT_READ_ROLES)
