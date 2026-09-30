from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Result(models.Model):
    class Status(models.TextChoices):
        PROVISIONAL = "provisional", "Provisional"
        PUBLISHED = "published", "Published"
        WITHHELD = "withheld", "Withheld"

    institution = models.ForeignKey("institutions.Institution", on_delete=models.PROTECT, related_name="results")
    attempt = models.OneToOneField("attempts.Attempt", on_delete=models.PROTECT, related_name="result")
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.PROTECT, related_name="results")
    assessment = models.ForeignKey("assessments.Assessment", on_delete=models.PROTECT, related_name="results")
    total_marks = models.DecimalField(max_digits=9, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    marks_obtained = models.DecimalField(max_digits=9, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    pass_mark = models.DecimalField(max_digits=9, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    grade = models.CharField(max_length=2, default="F")
    passed = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROVISIONAL, db_index=True)
    marked_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-marked_at", "-id")
        indexes = [
            models.Index(fields=("institution", "status"), name="result_tenant_status_idx"),
            models.Index(fields=("candidate", "assessment"), name="result_candidate_assess_idx"),
            models.Index(fields=("published_at",), name="result_published_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(total_marks__gte=0), name="result_total_nonnegative"),
            models.CheckConstraint(condition=models.Q(marks_obtained__gte=0), name="result_obtained_nonnegative"),
            models.CheckConstraint(condition=models.Q(marks_obtained__lte=models.F("total_marks")), name="result_obtained_lte_total"),
            models.CheckConstraint(condition=models.Q(pass_mark__gte=0), name="result_passmark_nonnegative"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.attempt_id and (self.attempt.institution_id != self.institution_id or self.attempt.candidate_id != self.candidate_id or self.attempt.assessment_id != self.assessment_id):
            raise ValidationError("Result ownership must match its historical attempt.")


class ResultQuestion(models.Model):
    class Status(models.TextChoices):
        CORRECT = "correct", "Correct"
        INCORRECT = "incorrect", "Incorrect"
        UNANSWERED = "unanswered", "Unanswered"
        INVALID = "invalid", "Invalid stored answer"

    result = models.ForeignKey(Result, on_delete=models.CASCADE, related_name="questions")
    attempt_question = models.ForeignKey("attempts.AttemptQuestion", on_delete=models.PROTECT, related_name="result_rows")
    marks_available = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    marks_obtained = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    status = models.CharField(max_length=16, choices=Status.choices)
    validation_note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("attempt_question__order", "id")
        constraints = [
            models.UniqueConstraint(fields=("result", "attempt_question"), name="unique_result_attempt_question"),
            models.CheckConstraint(condition=models.Q(marks_available__gte=0), name="result_q_available_nonnegative"),
            models.CheckConstraint(condition=models.Q(marks_obtained__gte=0), name="result_q_obtained_nonnegative"),
            models.CheckConstraint(condition=models.Q(marks_obtained__lte=models.F("marks_available")), name="result_q_obtained_lte_available"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.result_id and self.attempt_question_id and self.result.attempt_id != self.attempt_question.attempt_id:
            raise ValidationError("Result question must belong to the result attempt.")
