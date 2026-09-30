from django.contrib import admin

from .models import Assessment, AssessmentQuestion


class AssessmentQuestionInline(admin.TabularInline):
    model = AssessmentQuestion
    extra = 0
    autocomplete_fields = ("question",)


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("title", "institution", "assessment_type", "subject", "status", "total_marks", "start_at")
    list_filter = ("institution", "assessment_type", "status", "security_level")
    search_fields = ("title", "institution__name", "subject__name")
    readonly_fields = ("status", "created_by", "reviewed_by", "approved_by", "created_at", "updated_at")
    autocomplete_fields = ("institution", "subject", "group")
    inlines = (AssessmentQuestionInline,)

    def get_inline_instances(self, request, obj=None):
        if obj and obj.status != obj.Status.DRAFT:
            return []
        return super().get_inline_instances(request, obj)

    def get_queryset(self, request):
        from .tenancy import assessment_institution_ids
        return super().get_queryset(request).filter(institution_id__in=assessment_institution_ids(request.user))

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AssessmentQuestion)
class AssessmentQuestionAdmin(admin.ModelAdmin):
    list_display = ("assessment", "question", "order", "marks")
    list_filter = ("assessment__institution", "assessment__status")
    search_fields = ("assessment__title", "question__text")
    autocomplete_fields = ("assessment", "question")

    def get_queryset(self, request):
        from .tenancy import assessment_institution_ids
        return super().get_queryset(request).filter(assessment__institution_id__in=assessment_institution_ids(request.user))
