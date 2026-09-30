from django.contrib import admin
from tenants.admin import TenantScopedAdminMixin
from .models import Institution
@admin.register(Institution)
class InstitutionAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    tenant_lookup = "pk"
    access_roles = {"platform_admin", "institution_admin"}
    write_roles = {"platform_admin", "institution_admin"}
    list_display = ("name", "institution_type", "email", "is_active")
    list_filter = ("institution_type", "is_active")
    search_fields = ("name", "slug", "email")
