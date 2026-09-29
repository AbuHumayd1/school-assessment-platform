from django.contrib import admin
from .models import Group, GroupMembership
@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "institution", "group_type", "is_active")
    list_filter = ("institution", "group_type", "is_active")
    search_fields = ("name", "code")
@admin.register(GroupMembership)
class GroupMembershipAdmin(admin.ModelAdmin):
    list_display = ("candidate", "group", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)
