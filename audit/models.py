from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AuditEvent(models.Model):
    class Type(models.TextChoices):
        ASSESSMENT_APPROVED = "assessment_approved", "Assessment approved"
        ASSESSMENT_SCHEDULED = "assessment_scheduled", "Assessment scheduled"
        ATTEMPT_STARTED = "attempt_started", "Attempt started"
        ATTEMPT_SUBMITTED = "attempt_submitted", "Attempt submitted"
        ATTEMPT_EXPIRED = "attempt_expired", "Attempt expired"
        RESULT_MARKED = "result_marked", "Result marked"
        RESULT_PUBLISHED = "result_published", "Result published"
        RESULT_WITHHELD = "result_withheld", "Result withheld"
        INSTITUTION_PROFILE_UPDATED = "institution_profile_updated", "Institution profile updated"
        MEMBERSHIP_CHANGED = "membership_changed", "Institution membership changed"
        QUESTION_IMPORT = "question_import", "Question bank CSV import"

    institution = models.ForeignKey("institutions.Institution", on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events")
    event_type = models.CharField(max_length=32, choices=Type.choices)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=100)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-occurred_at", "-id")
        indexes = [models.Index(fields=("institution", "occurred_at"), name="audit_tenant_time_idx")]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit events are append-only.")
        if not isinstance(self.metadata, dict):
            raise ValidationError({"metadata": "Audit metadata must be an object."})
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events cannot be deleted.")
