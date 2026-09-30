from django.contrib import admin
from django.core.exceptions import PermissionDenied

from institutions.models import Institution
from .models import InstitutionMembership


def admin_institution_ids(user, roles):
    if user.is_superuser or user.institution_memberships.filter(
        is_active=True, institution__is_active=True, role=InstitutionMembership.Role.PLATFORM_ADMIN,
    ).exists():
        return Institution.objects.filter(is_active=True).values_list("pk", flat=True)
    return InstitutionMembership.objects.filter(
        user=user, is_active=True, institution__is_active=True, role__in=roles,
    ).values_list("institution_id", flat=True)


class TenantScopedAdminMixin:
    tenant_lookup = "institution_id"
    access_roles = {"platform_admin", "institution_admin", "teacher", "examiner"}
    write_roles = {"platform_admin", "institution_admin", "teacher", "examiner"}

    def _tenant_id(self, obj):
        value = obj
        for part in self.tenant_lookup.split("__"):
            value = getattr(value, part)
        return value

    def _has_role(self, user, roles, obj=None):
        if user.is_superuser:
            return True
        memberships = user.institution_memberships.filter(is_active=True, institution__is_active=True)
        if memberships.filter(role="platform_admin").exists():
            return obj is None or Institution.objects.filter(pk=self._tenant_id(obj), is_active=True).exists()
        memberships = memberships.filter(role__in=roles)
        if obj is not None:
            memberships = memberships.filter(institution_id=self._tenant_id(obj))
        return memberships.exists()

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.filter(**{f"{self.tenant_lookup}__in": admin_institution_ids(request.user, self.access_roles)})

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and self._has_role(request.user, self.access_roles, obj)

    def has_add_permission(self, request):
        return super().has_add_permission(request) and self._has_role(request.user, self.write_roles)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and self._has_role(request.user, self.write_roles, obj)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and self._has_role(request.user, self.write_roles, obj)


@admin.register(InstitutionMembership)
class InstitutionMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "institution", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "institution__name")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            institution_id__in=admin_institution_ids(request.user, {"platform_admin", "institution_admin"}),
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "institution":
            kwargs["queryset"] = Institution.objects.filter(
                pk__in=admin_institution_ids(request.user, {"platform_admin", "institution_admin"}),
                is_active=True,
            )
        elif db_field.name == "user":
            from accounts.models import User
            institution_ids = admin_institution_ids(request.user, {"platform_admin", "institution_admin"})
            kwargs["queryset"] = User.objects.filter(
                institution_memberships__institution_id__in=institution_ids,
                institution_memberships__is_active=True,
                institution_memberships__institution__is_active=True,
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        field = super().formfield_for_choice_field(db_field, request, **kwargs)
        is_platform = request.user.is_superuser or request.user.institution_memberships.filter(
            is_active=True, institution__is_active=True, role="platform_admin",
        ).exists()
        if db_field.name == "role" and not is_platform:
            field.choices = tuple(choice for choice in field.choices if choice[0] != InstitutionMembership.Role.PLATFORM_ADMIN)
        return field

    def save_model(self, request, obj, form, change):
        is_platform = request.user.is_superuser or request.user.institution_memberships.filter(
            is_active=True, institution__is_active=True, role="platform_admin",
        ).exists()
        if not is_platform and obj.role == InstitutionMembership.Role.PLATFORM_ADMIN:
            raise PermissionDenied("Only platform administrators may grant the platform administrator role.")
        if not request.user.is_superuser and not request.user.institution_memberships.filter(
            institution=obj.institution, is_active=True, institution__is_active=True,
            role__in=("platform_admin", "institution_admin"),
        ).exists():
            raise PermissionDenied("You cannot manage membership in this institution.")
        super().save_model(request, obj, form, change)
