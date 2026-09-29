from django.contrib import admin
from .models import Candidate
@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("candidate_id", "first_name", "last_name", "institution", "status")
    list_filter = ("institution", "status")
    search_fields = ("candidate_id", "first_name", "last_name", "email")
