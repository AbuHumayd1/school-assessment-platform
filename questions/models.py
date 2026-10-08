from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from .integrity_querysets import IntegrityQuerySet
from subjects.ownership import OwnedContent, OwnerScope, ownership_constraint, validate_content_owner


class Topic(OwnedContent):
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.CASCADE, related_name="topics")
    subject = models.ForeignKey("subjects.Subject", on_delete=models.CASCADE, related_name="topics")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("subject__name", "name")
        constraints = [models.UniqueConstraint(fields=("institution", "subject", "name"), name="unique_topic_name_per_subject"), ownership_constraint('topic_owner_shape'), models.UniqueConstraint(fields=('subject', 'name'), name='unique_topic_name_per_owner_subject')]

    def clean(self):
        validate_content_owner(self)
        errors = {}
        if self.pk:
            original = type(self).objects.get(pk=self.pk)
            if original.subject_id != self.subject_id and (self.questions.exists() or self.children.exists()):
                errors['subject'] = 'A topic with questions or child topics cannot change subject.'
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
    CONTENT_FIELDS = ('owner_scope', 'institution_id', 'subject_id', 'topic_id', 'question_type', 'text',
        'explanation', 'difficulty', 'marks', 'source', 'source_metadata', 'source_year', 'learning_objective',
        'created_by_id', 'reviewed_by_id')
    objects = IntegrityQuerySet.as_manager()
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

    owner_scope = models.CharField(max_length=16, choices=OwnerScope.choices, default=OwnerScope.INSTITUTION)
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.PROTECT, related_name="questions")
    subject = models.ForeignKey("subjects.Subject", on_delete=models.PROTECT, related_name="questions")
    topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.PROTECT, related_name="questions")
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
    revision_family = models.UUIDField(default=uuid.uuid4, editable=False)
    revision_number = models.PositiveIntegerField(default=1, editable=False)
    content_locked = models.BooleanField(default=False, editable=False)
    available_for_new_assessments = models.BooleanField(default=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_questions")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_questions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            ownership_constraint('question_owner_shape'),
            models.UniqueConstraint(fields=('revision_family', 'revision_number'), name='unique_question_family_revision'),
            models.CheckConstraint(condition=models.Q(revision_number__gte=1), name='question_revision_positive'),
            models.CheckConstraint(condition=(models.Q(content_locked=True) | ~models.Q(status__in=['approved', 'archived'])), name='question_approved_content_locked'),
        ]
        indexes = [
            models.Index(fields=("institution", "status"), name="question_tenant_status_idx"),
            models.Index(fields=("institution", "subject", "difficulty"), name="question_subject_diff_idx"),
        ]

    def clean(self):
        validate_content_owner(self)
        errors = {}
        if self.pk:
            from django.apps import apps
            AttemptQuestion = apps.get_model("attempts", "AttemptQuestion")
            original = type(self).objects.get(pk=self.pk)
            if original.content_locked or AttemptQuestion.objects.filter(question_id=self.pk).exists():
                protected = self.CONTENT_FIELDS
                if any(getattr(original, field) != getattr(self, field) for field in protected):
                    errors["text"] = "Approved question content is immutable. Create a new revision."
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

        if self.status in {self.Status.APPROVED, self.Status.ARCHIVED}:
            self.content_locked = True

    @transaction.atomic
    def save(self, *args, **kwargs):
        family = type(self).objects.filter(pk=self.pk).values_list('revision_family', flat=True).first() if self.pk else self.revision_family
        type(self).objects.select_for_update().filter(revision_family=family, revision_number=1).first()
        original = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if original and kwargs.get('update_fields') is not None and 'status' not in kwargs['update_fields'] and self.status != original.status:
            raise ValidationError('Include status when saving a workflow transition.')
        self.validate_integrity()
        if self.status in {self.Status.APPROVED, self.Status.ARCHIVED}:
            self.content_locked = True
            if self.status == self.Status.APPROVED and original and not original.content_locked:
                self.available_for_new_assessments = not type(self).objects.filter(
                    revision_family=self.revision_family, revision_number__gt=self.revision_number,
                    content_locked=True).exists()
            if self.status == self.Status.ARCHIVED:
                self.available_for_new_assessments = False
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'content_locked', 'available_for_new_assessments'}
        super().save(*args, **kwargs)
        if self.status == self.Status.APPROVED and original and not original.content_locked:
            type(self).objects.filter(revision_family=self.revision_family, content_locked=True,
                revision_number__lt=self.revision_number).update(available_for_new_assessments=False)

    @property
    def is_deliverable_revision(self):
        return self.content_locked and self.status in {self.Status.APPROVED, self.Status.ARCHIVED}

    @property
    def is_content_immutable(self):
        from django.apps import apps
        AttemptQuestion = apps.get_model('attempts', 'AttemptQuestion')
        return self.content_locked or bool(self.pk and AttemptQuestion.objects.filter(question_id=self.pk).exists())

    def validate_integrity(self):
        validate_content_owner(self)
        original = type(self).objects.select_for_update().filter(pk=self.pk).first() if self.pk else None
        if self.owner_scope == OwnerScope.PLATFORM:
            from institutions.permissions import is_platform_administrator
            for field in ('created_by', 'reviewed_by'):
                assigned = original is None or getattr(original, field + '_id') != getattr(self, field + '_id')
                if assigned and getattr(self, field + '_id') and not is_platform_administrator(getattr(self, field)):
                    raise ValidationError({field: 'Platform content requires a platform administrator.'})
        if self.content_locked and self.status not in {self.Status.APPROVED, self.Status.ARCHIVED}:
            raise ValidationError('Only approved content can acquire a permanent revision lock.')
        if original:
            if any(getattr(original, key) != getattr(self, key) for key in ('revision_family', 'revision_number', 'institution_id')):
                raise ValidationError('Question revision identity and ownership cannot change.')
            if original.is_content_immutable and any(
                    getattr(original, key) != getattr(self, key) for key in self.CONTENT_FIELDS):
                raise ValidationError('Approved or participated question content is immutable. Create a new revision.')
            if original.content_locked:
                if not self.content_locked or any(getattr(original, key) != getattr(self, key) for key in self.CONTENT_FIELDS):
                    raise ValidationError('Approved question content is immutable. Create a new revision.')
                if self.status not in {self.Status.APPROVED, self.Status.ARCHIVED}:
                    raise ValidationError('A locked revision cannot return to an editable workflow state.')
                if self.status == self.Status.APPROVED and self.available_for_new_assessments and type(self).objects.filter(
                        revision_family=self.revision_family, revision_number__gt=self.revision_number,
                        content_locked=True).exists():
                    raise ValidationError('A superseded revision cannot become available for new selections.')
        elif self.content_locked or self.status in {self.Status.APPROVED, self.Status.ARCHIVED}:
            raise ValidationError('Create a draft with its options before approving a revision.')
        if not original:
            root = type(self).objects.select_for_update().filter(revision_family=self.revision_family).order_by('revision_number').first()
            if root and ((root.owner_scope, root.institution_id) != (self.owner_scope, self.institution_id) or self.revision_number !=
                    (type(self).objects.filter(revision_family=self.revision_family).aggregate(n=models.Max('revision_number'))['n'] + 1)):
                raise ValidationError('Use the revision creation service for the next revision in this family.')
            if not root and self.revision_number != 1:
                raise ValidationError('A new question family starts at revision 1.')
        if self.status == self.Status.APPROVED and not (original and original.content_locked):
            self.validate_objective_options()
        if self.status == self.Status.ARCHIVED and not (original and original.content_locked):
            raise ValidationError('Only an approved locked revision can be retired.')

    def validate_objective_options(self):
        # Approval must validate current rows, not a prefetch from an earlier read.
        options = list(QuestionOption.objects.filter(question_id=self.pk).order_by('order', 'pk')) if self.pk else []
        correct = sum(option.is_correct for option in options)
        valid = len(options) >= 2 and (
            (self.question_type == self.Type.MULTIPLE_CHOICE and correct == 1) or
            (self.question_type == self.Type.MULTIPLE_SELECT and correct >= 1) or
            (self.question_type == self.Type.TRUE_FALSE and len(options) == 2 and correct == 1))
        if not valid:
            raise ValidationError('A valid objective option set is required before approval.')
        self.full_clean()
        for option in options:
            if option.order < 1:
                raise ValidationError('Objective option order must be positive.')
            option.full_clean()

    def validate_integrity_delete(self):
        original = type(self).objects.select_for_update().get(pk=self.pk)
        if original.is_content_immutable:
            raise ValidationError('An approved or participated question revision cannot be deleted.')

    @transaction.atomic
    def delete(self, *args, **kwargs):
        type(self).objects.select_for_update().get(pk=self.pk)
        self.validate_integrity_delete()
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.subject}: {self.text[:80]}"


class QuestionOption(models.Model):
    objects = IntegrityQuerySet.as_manager()
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
        if self.question_id and (self.question.content_locked or AttemptQuestion.objects.filter(question_id=self.question_id).exists()):
            if not self.pk:
                raise ValidationError({"question": "Options cannot be added after the question has been used in an attempt."})
            original = type(self).objects.get(pk=self.pk)
            protected = ("question_id", "text", "is_correct", "order")
            if any(getattr(original, field) != getattr(self, field) for field in protected):
                raise ValidationError({"text": "Question options cannot be changed after the question has been used in an attempt."})

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.validate_integrity()
        super().save(*args, **kwargs)

    def validate_integrity(self):
        original = type(self).objects.select_for_update().filter(pk=self.pk).first() if self.pk else None
        parents = {self.question_id, original.question_id if original else None} - {None}
        locked = any(q.is_content_immutable for q in Question.objects.select_for_update().filter(pk__in=parents).order_by('pk'))
        if locked and (original is None or any(getattr(original, field) != getattr(self, field)
                for field in ('question_id', 'text', 'is_correct', 'order'))):
            raise ValidationError('Options of an approved or participated question revision are immutable.')

    def validate_integrity_delete(self):
        original = type(self).objects.select_for_update().get(pk=self.pk)
        if Question.objects.select_for_update().get(pk=original.question_id).is_content_immutable:
            raise ValidationError('Options of an approved or participated question revision cannot be deleted.')

    @transaction.atomic
    def delete(self, *args, **kwargs):
        from django.apps import apps
        AttemptQuestion = apps.get_model("attempts", "AttemptQuestion")
        if self.question_id:
            Question.objects.select_for_update().get(pk=self.question_id)
        self.validate_integrity_delete()
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
    objects = IntegrityQuerySet.as_manager()
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
        self.validate_integrity()
        return super().save(*args, **kwargs)

    def validate_integrity(self):
        original = type(self).objects.select_for_update().filter(pk=self.pk).first() if self.pk else None
        parents = {self.question_id, original.question_id if original else None} - {None}
        if any(q.is_content_immutable for q in Question.objects.select_for_update().filter(pk__in=parents).order_by('pk')):
            protected = ('question_id', 'import_session_id', 'parsed_id', 'media_type', 'file', 'alt_text', 'caption', 'order', 'source_metadata')
            if original is None or any(getattr(original, key) != getattr(self, key) for key in protected):
                raise ValidationError('Media of an approved or participated question revision is immutable.')

    def validate_integrity_delete(self):
        original = type(self).objects.select_for_update().get(pk=self.pk)
        if original.question_id and Question.objects.select_for_update().get(pk=original.question_id).is_content_immutable:
            raise ValidationError('Media of an approved or participated question revision cannot be deleted.')

    @transaction.atomic
    def delete(self, *args, **kwargs):
        self.validate_integrity_delete()
        return super().delete(*args, **kwargs)
