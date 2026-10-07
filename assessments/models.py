from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone
from questions.integrity_querysets import IntegrityQuerySet


class Assessment(models.Model):
    objects = IntegrityQuerySet.as_manager()
    class Type(models.TextChoices):
        QUIZ = "quiz", "Quiz"
        ASSIGNMENT = "assignment", "Assignment"
        CLASS_TEST = "class_test", "Class test"
        CONTINUOUS_ASSESSMENT = "continuous_assessment", "Continuous assessment"
        TEST = "test", "Test"
        MOCK_EXAM = "mock_exam", "Mock exam"
        TERM_EXAM = "term_exam", "Term exam"
        ENTRANCE_EXAM = "entrance_exam", "Entrance exam"
        PLACEMENT_TEST = "placement_test", "Placement test"
        COMPETITION = "competition", "Competition"
        CERTIFICATION_EXAM = "certification_exam", "Certification exam"
        TRAINING_ASSESSMENT = "training_assessment", "Training assessment"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "In review"
        APPROVED = "approved", "Approved"
        SCHEDULED = "scheduled", "Scheduled"
        ARCHIVED = "archived", "Archived"

    class SecurityLevel(models.TextChoices):
        STANDARD = "standard", "Standard"
        ENHANCED = "enhanced", "Enhanced"

    class ResultVisibility(models.TextChoices):
        HIDDEN = "hidden", "Hidden"
        AFTER_SUBMISSION = "after_submission", "After submission"
        SCHEDULED_RELEASE = "scheduled_release", "Scheduled release"

    class CandidateAccess(models.TextChoices):
        ASSIGNED_GROUP = "assigned_group", "Assigned group"
        SPECIFIC_CANDIDATES = "specific_candidates", "Specific candidates"
        ACCESS_CODE = "access_code", "Access code"

    class ResultReleaseMode(models.TextChoices):
        IMMEDIATE = "immediate", "Immediate"
        APPROVAL_REQUIRED = "approval_required", "Approval required"
        MANUAL_RELEASE = "manual_release", "Manual release"

    institution = models.ForeignKey("institutions.Institution", on_delete=models.CASCADE, related_name="assessments")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assessment_type = models.CharField(max_length=32, choices=Type.choices)
    subject = models.ForeignKey("subjects.Subject", on_delete=models.PROTECT, related_name="assessments")
    group = models.ForeignKey("groups.Group", null=True, blank=True, on_delete=models.SET_NULL, related_name="assessments")
    duration_minutes = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    pass_mark = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))])
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    attempt_limit = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    resume_allowed = models.BooleanField(default=True)
    randomize_questions = models.BooleanField(default=False)
    randomize_options = models.BooleanField(default=False)
    security_level = models.CharField(max_length=16, choices=SecurityLevel.choices, default=SecurityLevel.STANDARD)
    result_visibility = models.CharField(max_length=24, choices=ResultVisibility.choices, default=ResultVisibility.HIDDEN)
    show_score_immediately = models.BooleanField(default=False)
    candidate_access = models.CharField(max_length=24, choices=CandidateAccess.choices, default=CandidateAccess.ASSIGNED_GROUP)
    review_allowed = models.BooleanField(default=False)
    result_release_mode = models.CharField(max_length=24, choices=ResultReleaseMode.choices, default=ResultReleaseMode.APPROVAL_REQUIRED)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_assessments")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_assessments")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_assessments")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "id")
        indexes = [
            models.Index(fields=("institution", "status"), name="assessment_tenant_status_idx"),
            models.Index(fields=("institution", "subject"), name="assessment_tenant_subject_idx"),
            models.Index(fields=("institution", "group"), name="assessment_tenant_group_idx"),
        ]

    @property
    def uses_quick_delivery(self):
        # Existing Quick configurations select delivery; retain the legacy marker.
        return self.candidate_access == self.CandidateAccess.ACCESS_CODE or bool(
            self.pk and QuickExamConfiguration.objects.filter(assessment_id=self.pk).exists())

    @property
    def total_marks(self):
        if not self.pk:
            return Decimal("0.00")
        return self.assessment_questions.aggregate(total=Sum("marks"))["total"] or Decimal("0.00")

    def clean(self):
        errors = {}
        if self.subject_id and self.institution_id and self.subject.institution_id != self.institution_id:
            errors["subject"] = "The subject must belong to the assessment institution."
        if self.group_id:
            if self.group.institution_id != self.institution_id:
                errors["group"] = "The group must belong to the assessment institution."
            elif not self.group.is_active:
                errors["group"] = "The selected group must be active."
        if self.duration_minutes is not None and self.duration_minutes < 1:
            errors["duration_minutes"] = "Duration must be a positive number of minutes."
        if self.attempt_limit is not None and self.attempt_limit < 1:
            errors["attempt_limit"] = "Attempt limit must be positive."
        if self.start_at and self.end_at:
            if timezone.is_naive(self.start_at) or timezone.is_naive(self.end_at):
                errors["start_at"] = "Availability dates must be timezone-aware."
            elif self.end_at <= self.start_at:
                errors["end_at"] = "End time must be after start time."
        if self.institution_id and self.created_by_id:
            from questions.tenancy import has_question_role, is_platform_admin
            if not has_question_role(self.created_by, self.institution_id, {"institution_admin", "teacher", "examiner"}) and not is_platform_admin(self.created_by):
                errors["created_by"] = "The creator must have an active assessment-management role in this institution."
        for field in ("reviewed_by", "approved_by"):
            actor_id = getattr(self, f"{field}_id")
            actor = getattr(self, field, None)
            if self.institution_id and actor_id and actor:
                from questions.tenancy import has_question_role, is_platform_admin
                if not has_question_role(actor, self.institution_id, {"institution_admin", "examiner"}) and not is_platform_admin(actor):
                    errors[field] = "The workflow actor must belong to the assessment institution."
        if errors:
            raise ValidationError(errors)

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.validate_integrity()
        if self.pk:
            original = type(self).objects.select_for_update().filter(pk=self.pk).first()
            if original:
                configured = QuickExamConfiguration.objects.filter(assessment_id=self.pk).exists()
                if not configured and (
                    (original.candidate_access == self.CandidateAccess.ACCESS_CODE) !=
                    (self.candidate_access == self.CandidateAccess.ACCESS_CODE)
                ):
                    raise ValidationError({"candidate_access": "Delivery method is fixed when the exam is created."})
                if configured:
                    if self.candidate_access not in {self.CandidateAccess.ACCESS_CODE, self.CandidateAccess.SPECIFIC_CANDIDATES}:
                        raise ValidationError({"candidate_access": "Quick Exam supports Specific Candidates eligibility."})
                    if self.candidate_access != original.candidate_access:
                        raise ValidationError({"candidate_access": "Candidate eligibility cannot change after Quick access is configured."})
                    if original.institution_id != self.institution_id:
                        raise ValidationError({"institution": "An assessment with Quick Exam configuration cannot change institution."})
                from attempts.models import Attempt
                has_attempts = Attempt.objects.filter(assessment_id=self.pk).exists()
                protected = (
                    "institution_id", "title", "description", "assessment_type", "subject_id", "group_id",
                    "duration_minutes", "pass_mark", "start_at", "end_at", "attempt_limit", "resume_allowed",
                    "randomize_questions", "randomize_options", "security_level", "result_visibility",
                    "candidate_access", "review_allowed", "result_release_mode", "show_score_immediately",
                )
                if has_attempts and any(getattr(original, field) != getattr(self, field) for field in protected):
                    raise ValidationError("Assessment configuration cannot be changed after an attempt has started.")
                if has_attempts and original.status != self.status and self.status == self.Status.DRAFT:
                    raise ValidationError("An assessment with attempt history cannot be reopened as a draft.")
        super().save(*args, **kwargs)

    def validate_integrity(self):
        original = type(self).objects.select_for_update().filter(pk=self.pk).first() if self.pk else None
        if not original and self.status != self.Status.DRAFT:
            raise ValidationError('Create a draft, attach its revisions, then approve the assessment.')
        if original:
            from attempts.models import Attempt
            protected = ('institution_id', 'title', 'description', 'assessment_type', 'subject_id', 'group_id',
                'duration_minutes', 'pass_mark', 'start_at', 'end_at', 'attempt_limit', 'resume_allowed',
                'randomize_questions', 'randomize_options', 'security_level', 'result_visibility',
                'candidate_access', 'review_allowed', 'result_release_mode', 'show_score_immediately')
            if (original.status != self.Status.DRAFT or Attempt.objects.filter(assessment=self).exists()) and any(getattr(original, key) != getattr(self, key) for key in protected):
                raise ValidationError('Approved/reviewed exam preparation is frozen. Reopen before making changes.')
            if self.status == self.Status.DRAFT and original.status != self.status and Attempt.objects.filter(assessment=self).exists():
                raise ValidationError('An exam with participation cannot be reopened.')
            if self.status in {self.Status.APPROVED, self.Status.SCHEDULED} and self.status != original.status:
                rows = list(self.assessment_questions.select_related('question').order_by('question_id'))
                # Approval serializes with revision publication/content writes.
                from questions.models import Question
                list(Question.objects.select_for_update()
                    .filter(pk__in=[row.question_id for row in rows]).order_by('pk'))
                for row in rows:
                    row.question = Question.objects.get(pk=row.question_id)
                    row.question.validate_objective_options()
                self.validate_configuration(require_questions=True, require_schedule=self.status == self.Status.SCHEDULED)

    def validate_integrity_delete(self):
        from attempts.models import Attempt
        original = type(self).objects.select_for_update().get(pk=self.pk)
        if original.status != self.Status.DRAFT or Attempt.objects.filter(assessment=original).exists():
            raise ValidationError('Only a draft without participation can be deleted.')

    @transaction.atomic
    def delete(self, *args, **kwargs):
        original = type(self).objects.select_for_update().get(pk=self.pk)
        original.validate_integrity_delete()
        return super().delete(*args, **kwargs)

    def validate_configuration(self, question_specs=None, *, require_questions=False, require_schedule=False):
        """Validate persisted or prospective question rows before review and scheduling."""
        errors = {}
        if not self.title.strip():
            errors["title"] = "Title is required."
        if not self.institution_id:
            errors["institution"] = "An institution is required."
        if not self.subject_id:
            errors["subject"] = "A subject is required."
        elif self.institution_id and self.subject.institution_id != self.institution_id:
            errors["subject"] = "The subject must belong to the assessment institution."
        if self.duration_minutes is None or self.duration_minutes < 1:
            errors["duration_minutes"] = "Duration must be a positive number of minutes."
        if self.attempt_limit is None or self.attempt_limit < 1:
            errors["attempt_limit"] = "Attempt limit must be positive."
        if self.group_id:
            if self.group.institution_id != self.institution_id:
                errors["group"] = "The group must belong to the assessment institution."
            elif not self.group.is_active:
                errors["group"] = "The selected group must be active."
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            errors["end_at"] = "End time must be after start time."
        if require_schedule:
            if not self.start_at or not self.end_at:
                errors["start_at"] = "Both start_at and end_at are required before scheduling."
            if self.candidate_access in {self.CandidateAccess.SPECIFIC_CANDIDATES, self.CandidateAccess.ACCESS_CODE} and (not self.pk or not self.candidate_assignments.exists()):
                errors["candidates"] = "Assign at least one candidate before scheduling this exam."
            if self.candidate_access == self.CandidateAccess.ASSIGNED_GROUP and not self.group_id:
                errors["group"] = "An active target group is required for assigned-group access."

        if question_specs is None:
            specs = list(self.assessment_questions.select_related("question").all()) if self.pk else []
            specs = [{"question": row.question, "order": row.order, "marks": row.marks} for row in specs]
        else:
            specs = list(question_specs)

        if require_questions and not specs:
            errors["questions"] = "At least one approved question is required."
        seen_questions = set()
        seen_orders = set()
        total = Decimal("0.00")
        for index, spec in enumerate(specs):
            question = spec["question"]
            order = spec["order"]
            marks = spec["marks"]
            if question.pk in seen_questions:
                errors["questions"] = f"Question {question.pk} is selected more than once."
            if order in seen_orders:
                errors["questions"] = f"Question order {order} is duplicated."
            seen_questions.add(question.pk)
            seen_orders.add(order)
            if question.institution_id != self.institution_id:
                errors["questions"] = f"Question {question.pk} belongs to another institution."
            if self.subject_id and question.subject_id != self.subject_id:
                errors["questions"] = f"Question {question.pk} belongs to another subject."
            if not question.is_deliverable_revision:
                errors["questions"] = f"Question {question.pk} is not an approved immutable revision."
            if order < 1:
                errors["questions"] = f"Question order at position {index + 1} must be positive."
            if marks <= 0:
                errors["questions"] = f"Marks for question {question.pk} must be positive."
            total += marks
        if total <= 0 and require_questions:
            errors["total_marks"] = "The assessment must have total marks greater than zero."
        if self.pass_mark < 0:
            errors["pass_mark"] = "Pass mark cannot be negative."
        elif specs and self.pass_mark > total:
            errors["pass_mark"] = "Pass mark cannot exceed total marks."
        if errors:
            raise ValidationError(errors)
        return total

    def __str__(self):
        return self.title


class AssessmentCandidate(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="candidate_assignments")
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.PROTECT, related_name="assessment_assignments")
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assessment_candidate_assignments")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("assessment", "candidate"), name="unique_assessment_candidate")]

    def clean(self):
        if self.assessment_id and self.candidate_id and self.assessment.institution_id != self.candidate.institution_id:
            raise ValidationError({"candidate": "The candidate must belong to the exam institution."})
        if self.assessment_id and self.assigned_by_id:
            from questions.tenancy import has_question_role, is_platform_admin
            if not has_question_role(self.assigned_by, self.assessment.institution_id, {"institution_admin", "teacher", "examiner"}) and not is_platform_admin(self.assigned_by):
                raise ValidationError({"assigned_by": "The assigning user must have an active exam-management role in this institution."})

    @transaction.atomic
    def save(self, *args, **kwargs):
        Assessment.objects.select_for_update().get(pk=self.assessment_id)
        self.clean()
        from attempts.models import Attempt
        if not self.pk and Attempt.objects.filter(assessment_id=self.assessment_id).exists():
            raise ValidationError("Candidates cannot be assigned after participation starts.")
        if self.pk:
            original = type(self).objects.get(pk=self.pk)
            if (original.assessment_id, original.candidate_id, original.assigned_by_id) != (self.assessment_id, self.candidate_id, self.assigned_by_id):
                raise ValidationError("An assignment cannot be reassigned. Remove it safely and create another.")
        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        Assessment.objects.select_for_update().get(pk=self.assessment_id)
        from attempts.models import Attempt
        from results.models import Result
        if Attempt.objects.filter(assessment_id=self.assessment_id, candidate_id=self.candidate_id).exists() or Result.objects.filter(assessment_id=self.assessment_id, candidate_id=self.candidate_id).exists():
            raise ValidationError("This candidate has participated and cannot be removed from the exam.")
        return super().delete(*args, **kwargs)


class AssessmentQuestion(models.Model):
    objects = IntegrityQuerySet.as_manager()
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="assessment_questions")
    question = models.ForeignKey("questions.Question", on_delete=models.PROTECT, related_name="assessment_links")
    order = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    marks = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "id")
        constraints = [
            models.UniqueConstraint(fields=("assessment", "question"), name="unique_question_per_assessment"),
            models.UniqueConstraint(fields=("assessment", "order"), name="unique_assessment_question_order"),
        ]

    def clean(self):
        errors = {}
        if self.assessment_id and self.question_id:
            from questions.models import Question
            self.question = Question.objects.get(pk=self.question_id)
            assessment = self.assessment
            question = self.question
            if assessment.institution_id != question.institution_id:
                errors["question"] = "The question must belong to the assessment institution."
            elif assessment.subject_id != question.subject_id:
                errors["question"] = "The question must belong to the assessment subject."
            elif not question.is_deliverable_revision:
                errors["question"] = "Only approved immutable revisions may be attached."
            elif (not self.pk or type(self).objects.filter(pk=self.pk).exclude(
                    question_id=self.question_id, assessment_id=self.assessment_id).exists()) and (
                    question.status != question.Status.APPROVED or not question.available_for_new_assessments):
                errors["question"] = "This revision is unavailable for new assessment selections."
        if self.order is not None and self.order < 1:
            errors["order"] = "Order must be positive."
        try:
            self.marks = self._meta.get_field('marks').clean(self.marks, self)
        except ValidationError as error:
            errors['marks'] = error.messages
        if errors:
            raise ValidationError(errors)

    def _assessment_has_attempts(self, assessment_id=None):
        from attempts.models import Attempt
        assessment_id = assessment_id or self.assessment_id
        return bool(assessment_id and Attempt.objects.filter(assessment_id=assessment_id).exists())

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.validate_integrity()
        if self.pk:
            original = type(self).objects.get(pk=self.pk)
            from assessments.models import Assessment
            Assessment.objects.select_for_update().get(pk=original.assessment_id)
            if self.assessment_id != original.assessment_id:
                Assessment.objects.select_for_update().get(pk=self.assessment_id)
            if self._assessment_has_attempts(original.assessment_id) or self._assessment_has_attempts():
                protected = ("assessment_id", "question_id", "order", "marks")
                if any(getattr(original, field) != getattr(self, field) for field in protected):
                    raise ValidationError("Assessment question configuration is frozen after an attempt starts.")
        elif not self.pk and self._assessment_has_attempts():
            raise ValidationError("Questions cannot be added after an attempt starts.")
        super().save(*args, **kwargs)

    def validate_integrity(self):
        original = type(self).objects.select_for_update().filter(pk=self.pk).first() if self.pk else None
        ids = {self.assessment_id, original.assessment_id if original else None} - {None}
        for assessment in Assessment.objects.select_for_update().filter(pk__in=ids).order_by('pk'):
            if assessment.pk == self.assessment_id:
                self.assessment = assessment
            changed = original is None or any(getattr(original, key) != getattr(self, key)
                for key in ('assessment_id', 'question_id', 'order', 'marks'))
            if changed and (assessment.status != Assessment.Status.DRAFT or self._assessment_has_attempts(assessment.pk)):
                raise ValidationError('Question preparation is allowed only in drafts without participation.')
        from questions.models import Question
        Question.objects.select_for_update().get(pk=self.question_id)
        self.clean()

    def validate_integrity_delete(self):
        original = type(self).objects.select_for_update().get(pk=self.pk)
        assessment = Assessment.objects.select_for_update().get(pk=original.assessment_id)
        if assessment.status != Assessment.Status.DRAFT or self._assessment_has_attempts(original.assessment_id):
            raise ValidationError('Question preparation is allowed only in drafts without participation.')

    @transaction.atomic
    def delete(self, *args, **kwargs):
        self.validate_integrity_delete()
        from assessments.models import Assessment
        Assessment.objects.select_for_update().get(pk=self.assessment_id)
        if self._assessment_has_attempts():
            raise ValidationError("Assessment questions cannot be removed after an attempt starts.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.assessment}: question {self.question_id}"


from .quick_models import QuickExamConfiguration, QuickExamCredential, QuickExamSession
