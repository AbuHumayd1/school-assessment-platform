from tenants.models import InstitutionMembership

RESULT_STAFF_ROLES = {"platform_admin", "institution_admin", "examiner", "teacher"}
MARKER_ROLES = {"platform_admin", "institution_admin", "examiner"}
ADMIN_ROLES = {"platform_admin", "institution_admin"}


def is_platform_admin(user):
    return bool(user.is_superuser or InstitutionMembership.objects.filter(user=user, is_active=True, role="platform_admin", institution__is_active=True).exists())


def institution_ids(user, roles=RESULT_STAFF_ROLES):
    if is_platform_admin(user):
        from institutions.models import Institution
        return Institution.objects.filter(is_active=True).values_list("id", flat=True)
    return InstitutionMembership.objects.filter(user=user, is_active=True, institution__is_active=True, role__in=roles).values_list("institution_id", flat=True)

