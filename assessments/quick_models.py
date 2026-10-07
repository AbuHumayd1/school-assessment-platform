import re

from django.conf import settings
from django.contrib.auth.hashers import identify_hasher
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


def normalize_exam_code(value):
    if not isinstance(value, str):
        raise ValidationError({"exam_code": "Enter an exam code."})
    value = value.strip()
    if not value.isascii():
        raise ValidationError({"exam_code": "Use ASCII letters, digits and hyphens only."})
    value = value.upper()
    if len(value) > 32 or not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", value, flags=re.ASCII):
        raise ValidationError({"exam_code": "Use at most 32 ASCII letters, digits and single separating hyphens."})
    return value


class QuickExamConfiguration(models.Model):
    assessment = models.OneToOneField("assessments.Assessment", on_delete=models.CASCADE, related_name="quick_configuration")
    exam_code = models.CharField(max_length=32, unique=True)
    enabled = models.BooleanField(default=False)
    session_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(session_version__gte=1), name="quick_config_version_positive")]

    def clean(self):
        self.exam_code = normalize_exam_code(self.exam_code)
        if self.assessment_id and self.assessment.candidate_access not in {"access_code", "specific_candidates"}:
            raise ValidationError({"assessment": "Quick Exam supports Specific Candidates eligibility. Choose Specific Candidates first."})
        if self.assessment_id and self.assessment.group_id:
            raise ValidationError({"assessment": "Specific Candidates eligibility does not use a group."})
        if self.assessment_id and not self.pk and self.assessment.candidate_access != "access_code":
            raise ValidationError({"assessment": "Delivery method is fixed when the exam is created."})
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).first()
            if original and original.assessment_id != self.assessment_id:
                raise ValidationError({"assessment": "Quick Exam configuration cannot be reassigned."})

    def save(self, *args, **kwargs):
        self.exam_code = normalize_exam_code(self.exam_code)
        self.full_clean()
        return super().save(*args, **kwargs)


class QuickExamCredential(models.Model):
    configuration = models.ForeignKey(QuickExamConfiguration, on_delete=models.CASCADE, related_name="credentials")
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.CASCADE, related_name="quick_credentials")
    pin_hash = models.CharField(max_length=256)
    active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    generated_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="issued_quick_credentials")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("configuration", "candidate"), name="unique_quick_candidate_cred"),
            models.CheckConstraint(condition=models.Q(version__gte=1), name="quick_credential_version_pos"),
        ]
        indexes = [models.Index(fields=("configuration", "active"), name="quick_credential_active_idx")]

    def clean(self):
        if self.configuration_id and self.candidate_id and self.candidate.institution_id != self.configuration.assessment.institution_id:
            raise ValidationError({"candidate": "Candidate and assessment must belong to the same institution."})
        try:
            identify_hasher(self.pin_hash)
        except ValueError:
            raise ValidationError({"pin_hash": "A Django password hash is required."})
        if self.expires_at and timezone.is_naive(self.expires_at):
            raise ValidationError({"expires_at": "Expiry must be timezone-aware."})
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).first()
            if original and (original.configuration_id != self.configuration_id or original.candidate_id != self.candidate_id):
                raise ValidationError("Credential ownership cannot be reassigned.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class QuickExamSession(models.Model):
    credential = models.ForeignKey(QuickExamCredential, on_delete=models.CASCADE, related_name="sessions")
    token_digest = models.CharField(max_length=64, unique=True, validators=[RegexValidator(r"\A[0-9a-f]{64}\Z", "Store a SHA-256 token digest only.")])
    credential_version = models.PositiveIntegerField()
    configuration_version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(credential_version__gte=1), name="quick_session_cred_version_pos"),
            models.CheckConstraint(condition=models.Q(configuration_version__gte=1), name="quick_session_config_ver_pos"),
        ]

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
