from django.contrib import admin
from .models import Institution
@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("name", "institution_type", "email", "is_active")
    list_filter = ("institution_type", "is_active")
    search_fields = ("name", "slug", "email")
