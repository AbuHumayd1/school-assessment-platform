from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "institution", "actor", "event_type", "resource_type", "resource_id")
    list_filter = ("institution", "event_type", "occurred_at")
    search_fields = ("resource_type", "resource_id", "actor__email")
    readonly_fields = tuple(field.name for field in AuditEvent._meta.fields)
    date_hierarchy = "occurred_at"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or request.user.institution_memberships.filter(
            is_active=True, institution__is_active=True, role="platform_admin",
        ).exists():
            return queryset.filter(institution__is_active=True)
        institution_ids = request.user.institution_memberships.filter(
            is_active=True, institution__is_active=True,
            role__in=("institution_admin", "examiner"),
        ).values_list("institution_id", flat=True)
        return queryset.filter(institution_id__in=institution_ids)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
