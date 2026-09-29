from django.contrib import admin
from .models import InstitutionMembership
@admin.register(InstitutionMembership)
class InstitutionMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "institution", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "institution__name")
