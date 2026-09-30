from django.contrib import admin
from django.core.exceptions import PermissionDenied
from accounts.models import User
from tenants.admin import TenantScopedAdminMixin, admin_institution_ids
from .models import Candidate
@admin.register(Candidate)
class CandidateAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("candidate_id", "first_name", "last_name", "institution", "status")
    list_filter = ("institution", "status")
    search_fields = ("candidate_id", "first_name", "last_name", "email")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        institution_ids = admin_institution_ids(request.user, self.access_roles)
        if db_field.name == "institution":
            from institutions.models import Institution
            kwargs["queryset"] = Institution.objects.filter(pk__in=institution_ids, is_active=True)
        elif db_field.name == "user":
            kwargs["queryset"] = User.objects.filter(
                institution_memberships__institution_id__in=institution_ids,
                institution_memberships__is_active=True,
                institution_memberships__institution__is_active=True,
                is_active=True,
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if obj.user_id and not obj.user.institution_memberships.filter(
            institution_id=obj.institution_id, institution__is_active=True, is_active=True,
        ).exists():
            raise PermissionDenied("The linked account must have an active membership in the candidate institution.")
        super().save_model(request, obj, form, change)
