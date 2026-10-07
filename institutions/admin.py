from django.contrib import admin
from django.db import transaction
from tenants.admin import TenantScopedAdminMixin
from .models import Institution
@admin.register(Institution)
class InstitutionAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    # Use the audited platform console for these settings.
    readonly_fields = ("workspace_mode", "can_release_candidate_results")
    tenant_lookup = "pk"
    access_roles = {"platform_admin", "institution_admin"}
    write_roles = {"platform_admin", "institution_admin"}
    list_display = ("name", "institution_type", "email", "is_active")
    list_filter = ("institution_type", "is_active")
    search_fields = ("name", "slug", "email")

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if change:
            current = Institution.objects.select_for_update().get(pk=obj.pk)
            obj.workspace_mode = current.workspace_mode
            obj.can_release_candidate_results = current.can_release_candidate_results
        else:
            obj.workspace_mode = Institution.WorkspaceMode.FULL_WORKSPACE
            obj.can_release_candidate_results = False
        super().save_model(request, obj, form, change)
