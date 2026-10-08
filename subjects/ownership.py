"""Explicit content ownership shared by the existing question hierarchy."""
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models, transaction

from questions.integrity_querysets import IntegrityQuerySet


class OwnerScope(models.TextChoices):
    INSTITUTION = 'institution', 'Institution'
    PLATFORM = 'platform', 'Platform'


def ownership_constraint(name):
    return models.CheckConstraint(condition=(
        models.Q(owner_scope='institution', institution__isnull=False) |
        models.Q(owner_scope='platform', institution__isnull=True)), name=name)


def validate_content_owner(instance):
    errors = {}
    if not ((instance.owner_scope == OwnerScope.INSTITUTION and instance.institution_id is not None)
            or (instance.owner_scope == OwnerScope.PLATFORM and instance.institution_id is None)):
        errors['institution'] = 'Choose an institution for institution content; platform content has no institution.'
    if instance.pk:
        original = type(instance).objects.using(instance._state.db or 'default').filter(pk=instance.pk).first()
        if original and (original.owner_scope, original.institution_id) != (instance.owner_scope, instance.institution_id):
            errors[NON_FIELD_ERRORS] = 'Content ownership cannot be transferred.'
    for field in ('subject', 'topic', 'parent'):
        if hasattr(instance, field + '_id') and getattr(instance, field + '_id'):
            related_model = instance._meta.get_field(field).remote_field.model
            fields = ['owner_scope', 'institution_id'] + (['subject_id'] if field != 'subject' else [])
            related = related_model.objects.using(instance._state.db or 'default').filter(
                pk=getattr(instance, field + '_id')).values(*fields).first()
            if related is None or (related['owner_scope'], related['institution_id']) != (instance.owner_scope, instance.institution_id):
                errors[field] = 'Related content must have the same owner.'
            elif field != 'subject' and related['subject_id'] != instance.subject_id:
                errors[field] = 'Related topics must belong to the selected subject.'
    if errors:
        raise ValidationError(errors)


class OwnedContent(models.Model):
    owner_scope = models.CharField(max_length=16, choices=OwnerScope.choices, default=OwnerScope.INSTITUTION)
    objects = IntegrityQuerySet.as_manager()

    class Meta:
        abstract = True

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.pk:
            type(self).objects.select_for_update().filter(pk=self.pk).first()
        validate_content_owner(self)
        self.clean()
        return super().save(*args, **kwargs)

    def validate_integrity_delete(self):
        # Existing cascade/PROTECT semantics remain authoritative for these parents.
        pass
