def institutions_for_user(user):
    if user.is_superuser or user.institution_memberships.filter(is_active=True, institution__is_active=True, role="platform_admin").exists():
        from institutions.models import Institution
        return Institution.objects.all()
    return user.institution_memberships.filter(is_active=True).values_list("institution_id", flat=True)

def can_manage_institution(user, institution_id, roles):
    if user.is_superuser or user.institution_memberships.filter(is_active=True, institution__is_active=True, role="platform_admin").exists():
        from institutions.models import Institution
        return Institution.objects.filter(pk=institution_id, is_active=True).exists()
    return user.institution_memberships.filter(
        institution_id=institution_id, is_active=True, institution__is_active=True, role__in=roles
    ).exists()


def resolve_institution_context(request, roles, *, allow_platform_admin=True):
    """Return an active, authorized tenant selected by header/query or a sole membership."""
    from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
    from institutions.models import Institution
    from tenants.models import InstitutionMembership

    user = request.user
    is_platform = user.is_superuser or (
        allow_platform_admin and user.institution_memberships.filter(
            is_active=True, institution__is_active=True, role="platform_admin",
        ).exists()
    )
    selector = request.headers.get("X-Institution-ID") or request.query_params.get("institution")

    if is_platform:
        institutions = Institution.objects.filter(is_active=True)
    else:
        institutions = Institution.objects.filter(
            memberships__user=user,
            memberships__is_active=True,
            memberships__role__in=roles,
            is_active=True,
        ).distinct()

    if selector:
        try:
            institution_id = int(selector)
        except (TypeError, ValueError):
            raise ValidationError({"institution": "Select a valid institution."})
        institution = institutions.filter(pk=institution_id).first()
        if institution is None:
            raise NotFound()
        return institution

    accessible = list(institutions.order_by("pk")[:2])
    if not accessible:
        raise PermissionDenied("You do not have access to manage an active institution.")
    if len(accessible) > 1:
        raise ValidationError({"institution": "Select an institution using X-Institution-ID or ?institution=."})
    return accessible[0]
