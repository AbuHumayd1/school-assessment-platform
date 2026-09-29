from django.conf import settings
from django.db import models

class InstitutionMembership(models.Model):
    class Role(models.TextChoices):
        PLATFORM_ADMIN = "platform_admin", "Platform admin"
        INSTITUTION_ADMIN = "institution_admin", "Institution admin"
        TEACHER = "teacher", "Teacher"
        EXAMINER = "examiner", "Examiner"
        STUDENT = "student", "Student"
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="institution_memberships")
    institution = models.ForeignKey("institutions.Institution", on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=32, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "institution"], name="unique_user_institution_membership")]
    def __str__(self):
        return f"{self.user} — {self.institution} ({self.role})"
