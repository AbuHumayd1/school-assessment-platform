from django.contrib import admin

from .models import Answer, AnswerSelection, Attempt, AttemptQuestion, AttemptQuestionOption


class AttemptQuestionInline(admin.TabularInline):
    model = AttemptQuestion
    extra = 0
    can_delete = False
    readonly_fields = ("question", "order", "marked_for_review", "created_at", "updated_at")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


class AnswerSelectionInline(admin.TabularInline):
    model = AnswerSelection
    extra = 0
    can_delete = False
    readonly_fields = ("option", "created_at")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("candidate", "assessment", "attempt_number", "status", "started_at", "expires_at", "submitted_at")
    list_filter = ("institution", "status", "assessment__assessment_type")
    search_fields = ("candidate__candidate_id", "candidate__first_name", "candidate__last_name", "assessment__title")
    readonly_fields = tuple(field.name for field in Attempt._meta.fields)
    inlines = (AttemptQuestionInline,)

    def get_queryset(self, request):
        from .views import _linked_assessment_institutions
        return super().get_queryset(request).filter(institution_id__in=_linked_assessment_institutions(request.user))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AttemptQuestion)
class AttemptQuestionAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "order", "marked_for_review")
    list_filter = ("attempt__institution", "attempt__status", "marked_for_review")
    readonly_fields = tuple(field.name for field in AttemptQuestion._meta.fields)

    def get_queryset(self, request):
        from .views import _linked_assessment_institutions
        return super().get_queryset(request).filter(attempt__institution_id__in=_linked_assessment_institutions(request.user))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "answered_at")
    list_filter = ("attempt__institution", "attempt__status")
    search_fields = ("attempt__candidate__candidate_id", "question__text")
    readonly_fields = tuple(field.name for field in Answer._meta.fields)
    inlines = (AnswerSelectionInline,)

    def get_queryset(self, request):
        from .views import _linked_assessment_institutions
        return super().get_queryset(request).filter(attempt__institution_id__in=_linked_assessment_institutions(request.user))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AnswerSelection)
class AnswerSelectionAdmin(admin.ModelAdmin):
    list_display = ("answer", "option", "created_at")
    list_filter = ("answer__attempt__institution", "answer__attempt__status")
    readonly_fields = tuple(field.name for field in AnswerSelection._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        from .views import _linked_assessment_institutions
        return super().get_queryset(request).filter(answer__attempt__institution_id__in=_linked_assessment_institutions(request.user))


@admin.register(AttemptQuestionOption)
class AttemptQuestionOptionAdmin(admin.ModelAdmin):
    list_display = ("attempt_question", "option", "order")
    readonly_fields = tuple(field.name for field in AttemptQuestionOption._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        from .views import _linked_assessment_institutions
        return super().get_queryset(request).filter(attempt_question__attempt__institution_id__in=_linked_assessment_institutions(request.user))
