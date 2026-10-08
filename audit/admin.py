from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Q

from .models import AuditEvent


class AuditEventTypeFilter(SimpleListFilter):
    title = "event type"
    parameter_name = "event_type"

    def lookups(self, request, model_admin):
        return (*AuditEvent.Type.choices,
            ("page_hidden", "Page hidden"),
            ("page_visible", "Page visible"),
            ("page_hide", "Page hide (unclassified)"),
            ("window_blur", "Window blur"),
            ("window_focus", "Window focus"),
            ("navigation_attempt", "Navigation attempt"),
            ("copy_attempt", "Copy attempt"),
            ("cut_attempt", "Cut attempt"),
            ("select_all_attempt", "Select all attempt"),
            ("context_menu_attempt", "Context menu attempt"),
            ("screenshot_key_attempt", "Screenshot key signal"),
            ("integrity_auto_submitted", "Integrity auto-submitted"),
        )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(event_type=self.value())
        return queryset


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "institution", "actor", "event_type", "resource_type", "resource_id")
    list_filter = ("institution", AuditEventTypeFilter, "occurred_at")
    search_fields = ("resource_type", "resource_id", "actor__email")
    readonly_fields = tuple(field.name for field in AuditEvent._meta.fields)
    date_hierarchy = "occurred_at"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or request.user.institution_memberships.filter(
            is_active=True, institution__is_active=True, role="platform_admin",
        ).exists():
            return queryset.filter(Q(institution__is_active=True) | Q(institution__isnull=True))
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
