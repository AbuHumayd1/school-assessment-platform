from django.contrib import admin
from institutions.models import Institution
from tenants.admin import TenantScopedAdminMixin, admin_institution_ids
from .models import Group, GroupMembership
@admin.register(Group)
class GroupAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "code", "institution", "group_type", "is_active")
    list_filter = ("institution", "group_type", "is_active")
    search_fields = ("name", "code")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "institution":
            kwargs["queryset"] = Institution.objects.filter(pk__in=admin_institution_ids(request.user, self.access_roles), is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
@admin.register(GroupMembership)
class GroupMembershipAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    tenant_lookup = "group__institution_id"
    list_display = ("candidate", "group", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        from candidates.models import Candidate
        from .models import Group
        institution_ids = admin_institution_ids(request.user, self.access_roles)
        if db_field.name == "group":
            kwargs["queryset"] = Group.objects.filter(institution_id__in=institution_ids, institution__is_active=True)
        elif db_field.name == "candidate":
            kwargs["queryset"] = Candidate.objects.filter(institution_id__in=institution_ids, institution__is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
