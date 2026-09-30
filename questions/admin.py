from django.contrib import admin
from accounts.models import User
from institutions.models import Institution
from subjects.models import Subject
from tenants.admin import TenantScopedAdminMixin, admin_institution_ids

from .models import Question, QuestionOption, Topic


@admin.register(Topic)
class TopicAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "subject", "parent", "institution", "is_active")
    list_filter = ("institution", "subject", "is_active")
    search_fields = ("name", "description", "subject__name")
    readonly_fields = ("created_at", "updated_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        institution_ids = admin_institution_ids(request.user, self.access_roles)
        if db_field.name == "institution":
            kwargs["queryset"] = Institution.objects.filter(pk__in=institution_ids, is_active=True)
        elif db_field.name == "subject":
            kwargs["queryset"] = Subject.objects.filter(institution_id__in=institution_ids, institution__is_active=True)
        elif db_field.name == "parent":
            kwargs["queryset"] = Topic.objects.filter(institution_id__in=institution_ids, institution__is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0
    fields = ("order", "text", "is_correct", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Question)
class QuestionAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("id", "subject", "question_type", "difficulty", "status", "created_by", "created_at")
    list_filter = ("institution", "subject", "question_type", "difficulty", "status")
    search_fields = ("text", "source", "learning_objective", "created_by__email")
    readonly_fields = ("status", "created_by", "reviewed_by", "created_at", "updated_at")
    inlines = (QuestionOptionInline,)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        institution_ids = admin_institution_ids(request.user, self.access_roles)
        if db_field.name == "institution":
            kwargs["queryset"] = Institution.objects.filter(pk__in=institution_ids, is_active=True)
        elif db_field.name == "subject":
            kwargs["queryset"] = Subject.objects.filter(institution_id__in=institution_ids, institution__is_active=True)
        elif db_field.name == "topic":
            kwargs["queryset"] = Topic.objects.filter(institution_id__in=institution_ids, institution__is_active=True)
        elif db_field.name in {"created_by", "reviewed_by"}:
            kwargs["queryset"] = User.objects.filter(institution_memberships__institution_id__in=institution_ids,
                                                       institution_memberships__is_active=True,
                                                       institution_memberships__institution__is_active=True).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(QuestionOption)
class QuestionOptionAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    tenant_lookup = "question__institution_id"
    list_display = ("question", "order", "text", "is_correct")
    list_filter = ("is_correct", "question__institution", "question__question_type")
    search_fields = ("text", "question__text")
    readonly_fields = ("created_at", "updated_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "question":
            kwargs["queryset"] = Question.objects.filter(
                institution_id__in=admin_institution_ids(request.user, self.access_roles),
                institution__is_active=True,
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
