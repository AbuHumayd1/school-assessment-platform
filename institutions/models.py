from django.conf import settings
from django.db import models
from django.utils.text import slugify

class Institution(models.Model):
    class WorkspaceMode(models.TextChoices):
        FULL_WORKSPACE = "full_workspace", "Full Workspace"
        MANAGED_EXAM = "managed_exam", "Managed Exam"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    institution_type = models.CharField(max_length=40, default="other")
    logo = models.FileField(upload_to="institution-logos/", blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    timezone = models.CharField(max_length=64, default="Africa/Lagos")
    workspace_mode = models.CharField(max_length=20, choices=WorkspaceMode.choices, default=WorkspaceMode.FULL_WORKSPACE)
    can_release_candidate_results = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    def __str__(self):
        return self.name
