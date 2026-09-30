from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

class Candidate(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"
    institution = models.ForeignKey("institutions.Institution", on_delete=models.CASCADE, related_name="candidates")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="candidate_profiles")
    candidate_id = models.CharField(max_length=64)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["institution", "candidate_id"], name="unique_candidate_id_per_institution")]

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.select_for_update().filter(pk=self.pk).first()
            if original:
                from attempts.models import Attempt
                if Attempt.objects.filter(candidate_id=self.pk).exists():
                    protected = ("institution_id", "candidate_id", "user_id")
                    if any(getattr(original, field) != getattr(self, field) for field in protected):
                        raise ValidationError("Candidate identity and account linkage cannot change after an attempt starts.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.candidate_id} — {self.first_name} {self.last_name}"
