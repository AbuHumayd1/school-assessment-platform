from django.contrib import admin
from .models import Subject
@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "institution", "is_active")
    list_filter = ("institution", "is_active")
    search_fields = ("name", "code")
