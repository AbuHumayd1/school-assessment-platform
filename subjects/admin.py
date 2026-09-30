from django.contrib import admin
from institutions.models import Institution
from tenants.admin import TenantScopedAdminMixin, admin_institution_ids
from .models import Subject
@admin.register(Subject)
class SubjectAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "code", "institution", "is_active")
    list_filter = ("institution", "is_active")
    search_fields = ("name", "code")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "institution":
            kwargs["queryset"] = Institution.objects.filter(pk__in=admin_institution_ids(request.user, self.access_roles), is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
