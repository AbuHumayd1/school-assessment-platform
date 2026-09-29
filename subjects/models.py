from django.db import models

class Subject(models.Model):
    institution = models.ForeignKey("institutions.Institution", on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["institution", "code"], name="unique_subject_code_per_institution")]
    def __str__(self):
        return f"{self.name} ({self.code})"
