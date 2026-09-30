from django.contrib import admin

from .models import Result, ResultQuestion


class ResultQuestionInline(admin.TabularInline):
    model = ResultQuestion
    extra = 0
    can_delete = False
    readonly_fields = tuple(field.name for field in ResultQuestion._meta.fields)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("candidate", "assessment", "marks_obtained", "total_marks", "percentage", "grade", "status", "published_at")
    list_filter = ("institution", "status", "assessment__assessment_type")
    search_fields = ("candidate__candidate_id", "candidate__first_name", "candidate__last_name", "assessment__title")
    readonly_fields = tuple(field.name for field in Result._meta.fields)
    inlines = (ResultQuestionInline,)

    def get_queryset(self, request):
        from .permissions import institution_ids
        return super().get_queryset(request).filter(institution_id__in=institution_ids(request.user))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ResultQuestion)
class ResultQuestionAdmin(admin.ModelAdmin):
    list_display = ("result", "attempt_question", "marks_obtained", "marks_available", "status")
    readonly_fields = tuple(field.name for field in ResultQuestion._meta.fields)

    def get_queryset(self, request):
        from .permissions import institution_ids
        return super().get_queryset(request).filter(result__institution_id__in=institution_ids(request.user))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
