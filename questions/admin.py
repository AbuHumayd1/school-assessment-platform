from django.contrib import admin

from .models import Question, QuestionOption, Topic


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "parent", "institution", "is_active")
    list_filter = ("institution", "subject", "is_active")
    search_fields = ("name", "description", "subject__name")
    readonly_fields = ("created_at", "updated_at")


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0
    fields = ("order", "text", "is_correct", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "question_type", "difficulty", "status", "created_by", "created_at")
    list_filter = ("institution", "subject", "question_type", "difficulty", "status")
    search_fields = ("text", "source", "learning_objective", "created_by__email")
    readonly_fields = ("created_at", "updated_at")
    inlines = (QuestionOptionInline,)


@admin.register(QuestionOption)
class QuestionOptionAdmin(admin.ModelAdmin):
    list_display = ("question", "order", "text", "is_correct")
    list_filter = ("is_correct", "question__institution", "question__question_type")
    search_fields = ("text", "question__text")
    readonly_fields = ("created_at", "updated_at")
