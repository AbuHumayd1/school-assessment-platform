from django.db import models
from .ownership import OwnedContent, ownership_constraint, validate_content_owner

class Subject(OwnedContent):
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=64)
    # Nullable unique key gives MySQL platform-code uniqueness without partial indexes.
    platform_code = models.CharField(max_length=64, null=True, blank=True, unique=True, editable=False)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["institution", "code"], name="unique_subject_code_per_institution"), ownership_constraint('subject_owner_shape'), models.CheckConstraint(condition=(models.Q(owner_scope='institution', platform_code__isnull=True) | models.Q(owner_scope='platform', platform_code__isnull=False, platform_code=models.F('code'))), name='subject_platform_code_shape')]
    def save(self, *args, **kwargs):
        self.platform_code = self.code if self.owner_scope == 'platform' else None
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'platform_code'}
        return super().save(*args, **kwargs)
    def clean(self):
        validate_content_owner(self)
        self.platform_code = self.code if self.owner_scope == 'platform' else None
    def __str__(self):
        return f"{self.name} ({self.code})"
