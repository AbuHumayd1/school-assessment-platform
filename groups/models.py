from django.db import models

class Group(models.Model):
    institution = models.ForeignKey("institutions.Institution", on_delete=models.CASCADE, related_name="groups")
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=64)
    group_type = models.CharField(max_length=64, blank=True)
    academic_session = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["institution", "code"], name="unique_group_code_per_institution")]
    def __str__(self):
        return f"{self.name} ({self.code})"

class GroupMembership(models.Model):
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.CASCADE, related_name="group_memberships")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="memberships")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["candidate", "group"], name="unique_candidate_group_membership")]
