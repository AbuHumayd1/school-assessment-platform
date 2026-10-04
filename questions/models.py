from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone


class Topic(models.Model):
    institution = models.ForeignKey("institutions.Institution", on_delete=models.CASCADE, related_name="topics")
    subject = models.ForeignKey("subjects.Subject", on_delete=models.CASCADE, related_name="topics")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("subject__name", "name")
        constraints = [models.UniqueConstraint(fields=("institution", "subject", "name"), name="unique_topic_name_per_subject")]

    def clean(self):
        errors = {}
        if self.institution_id and self.subject_id and self.subject.institution_id != self.institution_id:
            errors["subject"] = "The subject must belong to the same institution as the topic."
        if self.parent_id:
            if self.institution_id and self.parent.institution_id != self.institution_id:
                errors["parent"] = "The parent topic must belong to the same institution."
            if self.subject_id and self.parent.subject_id != self.subject_id:
                errors["parent"] = "The parent topic must belong to the same subject."
            ancestor = self.parent
            while ancestor is not None:
                if self.pk and ancestor.pk == self.pk:
                    errors["parent"] = "A topic cannot be its own ancestor."
                    break
                ancestor = ancestor.parent
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.subject}: {self.name}"


class Question(models.Model):
    class Type(models.TextChoices):
        MULTIPLE_CHOICE = "multiple_choice", "Multiple choice"
        MULTIPLE_SELECT = "multiple_select", "Multiple select"
        TRUE_FALSE = "true_false", "True/false"

    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "In review"
        APPROVED = "approved", "Approved"
        ARCHIVED = "archived", "Archived"

    institution = models.ForeignKey("institutions.Institution", on_delete=models.CASCADE, related_name="questions")
    subject = models.ForeignKey("subjects.Subject", on_delete=models.CASCADE, related_name="questions")
    topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.SET_NULL, related_name="questions")
    question_type = models.CharField(max_length=24, choices=Type.choices)
    difficulty = models.CharField(max_length=12, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    text = models.TextField()
    explanation = models.TextField(blank=True)
    marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("1.00"), validators=[MinValueValidator(Decimal("0.01"))])
    source = models.TextField(blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)
    source_year = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(9999)])
    learning_objective = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_questions")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_questions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "id")
        indexes = [
            models.Index(fields=("institution", "status"), name="question_tenant_status_idx"),
            models.Index(fields=("institution", "subject", "difficulty"), name="question_subject_diff_idx"),
        ]

    def clean(self):
        errors = {}
        if self.pk:
            from django.apps import apps
            AttemptQuestion = apps.get_model("attempts", "AttemptQuestion")
            if AttemptQuestion.objects.filter(question_id=self.pk).exists():
                original = type(self).objects.get(pk=self.pk)
                protected = ("institution_id", "subject_id", "topic_id", "question_type", "text", "explanation", "difficulty", "marks", "source", "source_metadata", "source_year", "learning_objective")
                if any(getattr(original, field) != getattr(self, field) for field in protected):
                    errors["text"] = "Question content cannot be edited after it has been used in an attempt."
        if self.subject_id and self.institution_id and self.subject.institution_id != self.institution_id:
            errors["subject"] = "The subject must belong to the same institution as the question."
        if self.topic_id:
            if self.institution_id and self.topic.institution_id != self.institution_id:
                errors["topic"] = "The topic must belong to the same institution as the question."
            if self.subject_id and self.topic.subject_id != self.subject_id:
                errors["topic"] = "The topic must belong to the selected subject."
        if self.institution_id and self.created_by_id:
            from tenants.models import InstitutionMembership
            creator_is_member = InstitutionMembership.objects.filter(user_id=self.created_by_id, institution_id=self.institution_id, is_active=True).exists()
            platform_admin = self.created_by.is_superuser or InstitutionMembership.objects.filter(user_id=self.created_by_id, is_active=True, role="platform_admin").exists()
            if not creator_is_member and not platform_admin:
                errors["created_by"] = "The creator must be an active member of the institution."
        if self.institution_id and self.reviewed_by_id:
            from tenants.models import InstitutionMembership
            reviewer_is_member = InstitutionMembership.objects.filter(user_id=self.reviewed_by_id, institution_id=self.institution_id, is_active=True).exists()
            platform_admin = self.reviewed_by.is_superuser or InstitutionMembership.objects.filter(user_id=self.reviewed_by_id, is_active=True, role="platform_admin").exists()
            if not reviewer_is_member and not platform_admin:
                errors["reviewed_by"] = "The reviewer must belong to the institution."
        if self.source_year and self.source_year > timezone.localdate().year + 1:
            errors["source_year"] = "The source year cannot be more than one year in the future."
        if errors:
            raise ValidationError(errors)

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.pk:
            from django.apps import apps
            AttemptQuestion = apps.get_model("attempts", "AttemptQuestion")
            original = type(self).objects.select_for_update().filter(pk=self.pk).first()
            if AttemptQuestion.objects.filter(question_id=self.pk).exists():
                self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject}: {self.text[:80]}"


class QuestionOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "id")
        constraints = [models.UniqueConstraint(fields=("question", "order"), name="unique_option_order_per_question")]

    def clean(self):
        from django.apps import apps
        AttemptQuestion = apps.get_model("attempts", "AttemptQuestion")
        if self.question_id and AttemptQuestion.objects.filter(question_id=self.question_id).exists():
            if not self.pk:
                raise ValidationError({"question": "Options cannot be added after the question has been used in an attempt."})
            original = type(self).objects.get(pk=self.pk)
            protected = ("question_id", "text", "is_correct", "order")
            if any(getattr(original, field) != getattr(self, field) for field in protected):
                raise ValidationError({"text": "Question options cannot be changed after the question has been used in an attempt."})

    @transaction.atomic
    def save(self, *args, **kwargs):
        from django.apps import apps
        AttemptQuestion = apps.get_model("attempts", "AttemptQuestion")
        if self.question_id:
            Question.objects.select_for_update().get(pk=self.question_id)
            if AttemptQuestion.objects.filter(question_id=self.question_id).exists():
                self.full_clean()
        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        from django.apps import apps
        AttemptQuestion = apps.get_model("attempts", "AttemptQuestion")
        if self.question_id:
            Question.objects.select_for_update().get(pk=self.question_id)
        if self.question_id and AttemptQuestion.objects.filter(question_id=self.question_id).exists():
            raise ValidationError("Question options cannot be deleted after the question is used in an attempt.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"Option {self.order} for question {self.question_id}"


class DocxImportSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey('institutions.Institution', on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    preview = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)


from .private_storage import private_storage


def question_media_path(instance, filename):
    return f'{uuid.uuid4().hex}/{uuid.uuid4().hex}.dat'


def cascade_private_media(collector, field, sub_objects, using):
    # MySQL cannot defer constraints. Standard nullable CASCADE clears the FK first,
    # violating single ownership. Record a strict child-before-parent dependency instead.
    collector.collect(sub_objects, source=field.remote_field.model, source_attr=field.name,
                      nullable=False, fail_on_restricted=False)


class QuestionMedia(models.Model):
    # An asset is promoted from a temporary session to a normal question without copying binaries.
    # A future stimulus may own this same asset model rather than duplicating files per question/attempt.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, null=True, blank=True, on_delete=cascade_private_media, related_name='media')
    import_session = models.ForeignKey(DocxImportSession, null=True, blank=True, on_delete=cascade_private_media, related_name='media')
    parsed_id = models.CharField(max_length=40)
    media_type = models.CharField(max_length=20, default='image')
    file = models.FileField(storage=private_storage, upload_to=question_media_path)
    alt_text = models.CharField(max_length=300, blank=True)
    caption = models.CharField(max_length=500, blank=True)
    order = models.PositiveSmallIntegerField(default=1)
    source_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('order', 'id')
        constraints = [models.CheckConstraint(condition=(models.Q(question__isnull=False, import_session__isnull=True) | models.Q(question__isnull=True, import_session__isnull=False)), name='question_media_single_owner')]

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.question_id:
            from attempts.models import AttemptQuestion
            Question.objects.select_for_update().get(pk=self.question_id)
            if AttemptQuestion.objects.filter(question_id=self.question_id).exists():
                raise ValidationError('Question media is immutable after an attempt starts.')
        return super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        if self.question_id:
            from attempts.models import AttemptQuestion
            Question.objects.select_for_update().get(pk=self.question_id)
            if AttemptQuestion.objects.filter(question_id=self.question_id).exists():
                raise ValidationError('Question media is immutable after an attempt starts.')
        return super().delete(*args, **kwargs)
