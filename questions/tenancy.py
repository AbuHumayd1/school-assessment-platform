from institutions.models import Institution
from rest_framework.exceptions import PermissionDenied, ValidationError
from tenants.models import InstitutionMembership

READ_ROLES = {"platform_admin", "institution_admin", "teacher", "examiner"}
WRITE_ROLES = {"platform_admin", "institution_admin", "teacher", "examiner"}
REVIEW_ROLES = {"platform_admin", "institution_admin", "examiner"}
APPROVE_ROLES = {"platform_admin", "institution_admin"}


def is_platform_admin(user):
    return user.is_superuser or user.institution_memberships.filter(is_active=True, institution__is_active=True, role="platform_admin").exists()


def institution_ids_for_question_bank(user):
    if is_platform_admin(user):
        return Institution.objects.filter(is_active=True).values_list("id", flat=True)
    return InstitutionMembership.objects.filter(
        user=user, is_active=True, role__in=READ_ROLES, institution__is_active=True
    ).values_list("institution_id", flat=True)


def has_question_role(user, institution_id, roles):
    if is_platform_admin(user):
        return Institution.objects.filter(pk=institution_id, is_active=True).exists()
    return InstitutionMembership.objects.filter(
        user=user, institution_id=institution_id, is_active=True, institution__is_active=True, role__in=roles
    ).exists()


def write_institution_for_request(request):
    """Resolve a tenant from a valid active membership; selection is never trusted alone."""
    user = request.user
    selector = request.headers.get("X-Institution-ID") or request.query_params.get("institution")
    if is_platform_admin(user):
        if not selector:
            raise ValidationError({"institution": "Platform administrators must select an institution using X-Institution-ID or ?institution=."})
        try:
            institution_id = int(selector)
        except (TypeError, ValueError):
            raise ValidationError({"institution": "Select a valid institution."})
        try:
            return Institution.objects.get(pk=institution_id, is_active=True)
        except Institution.DoesNotExist:
            raise ValidationError({"institution": "Select an active institution."})

    memberships = InstitutionMembership.objects.filter(
        user=user, is_active=True, role__in=WRITE_ROLES, institution__is_active=True
    ).select_related("institution")
    if selector:
        try:
            institution_id = int(selector)
        except (TypeError, ValueError):
            raise ValidationError({"institution": "Select a valid institution."})
        membership = memberships.filter(institution_id=institution_id).first()
        if membership is None:
            raise PermissionDenied("You cannot manage questions for this institution.")
        return membership.institution

    institutions = {m.institution_id: m.institution for m in memberships}
    if len(institutions) == 1:
        return next(iter(institutions.values()))
    if not institutions:
        raise PermissionDenied("You do not have an active question-bank role.")
    raise ValidationError({"institution": "Select an institution using X-Institution-ID or ?institution=."})
