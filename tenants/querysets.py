def institutions_for_user(user):
    if user.is_superuser or user.institution_memberships.filter(is_active=True, role="platform_admin").exists():
        from institutions.models import Institution
        return Institution.objects.all()
    return user.institution_memberships.filter(is_active=True).values_list("institution_id", flat=True)

def can_manage_institution(user, institution_id, roles):
    if user.is_superuser or user.institution_memberships.filter(is_active=True, role="platform_admin").exists():
        return True
    return user.institution_memberships.filter(
        institution_id=institution_id, is_active=True, role__in=roles
    ).exists()
