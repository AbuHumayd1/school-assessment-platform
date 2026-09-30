from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Attempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    institution = models.ForeignKey("institutions.Institution", on_delete=models.PROTECT, related_name="attempts")
    assessment = models.ForeignKey("assessments.Assessment", on_delete=models.PROTECT, related_name="attempts")
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.PROTECT, related_name="attempts")
    attempt_number = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-started_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("candidate", "assessment", "attempt_number"), name="unique_candidate_assessment_attempt_no"),
        ]
        indexes = [
            models.Index(fields=("institution", "status"), name="attempt_tenant_status_idx"),
            models.Index(fields=("candidate", "assessment", "status"), name="attempt_candidate_assess_idx"),
            models.Index(fields=("expires_at", "status"), name="attempt_expiry_status_idx"),
        ]

    def clean(self):
        errors = {}
        if self.assessment_id and self.institution_id and self.assessment.institution_id != self.institution_id:
            errors["assessment"] = "Assessment and attempt must belong to the same institution."
        if self.candidate_id and self.institution_id and self.candidate.institution_id != self.institution_id:
            errors["candidate"] = "Candidate and attempt must belong to the same institution."
        if self.attempt_number is not None and self.attempt_number < 1:
            errors["attempt_number"] = "Attempt number must be positive."
        if self.started_at and self.expires_at and self.expires_at <= self.started_at:
            errors["expires_at"] = "Expiry must be after the server start time."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.candidate} — {self.assessment} (attempt {self.attempt_number})"


class AttemptQuestion(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="attempt_questions")
    question = models.ForeignKey("questions.Question", on_delete=models.PROTECT, related_name="attempt_links")
    order = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    marked_for_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "id")
        constraints = [
            models.UniqueConstraint(fields=("attempt", "question"), name="unique_question_per_attempt"),
            models.UniqueConstraint(fields=("attempt", "order"), name="unique_attempt_question_order"),
        ]

    def clean(self):
        if self.attempt_id and self.question_id:
            if self.question.institution_id != self.attempt.institution_id:
                raise ValidationError({"question": "Question must belong to the attempt institution."})
            if not self.attempt.assessment.assessment_questions.filter(question_id=self.question_id).exists():
                raise ValidationError({"question": "Question must be selected for this assessment."})

    def __str__(self):
        return f"{self.attempt}: question {self.order}"


class AttemptQuestionOption(models.Model):
    """Persist option order per attempt question so refreshes never reshuffle."""
    attempt_question = models.ForeignKey(AttemptQuestion, on_delete=models.CASCADE, related_name="ordered_options")
    option = models.ForeignKey("questions.QuestionOption", on_delete=models.PROTECT, related_name="attempt_orders")
    order = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ("order", "id")
        constraints = [
            models.UniqueConstraint(fields=("attempt_question", "option"), name="unique_option_per_attempt_question"),
            models.UniqueConstraint(fields=("attempt_question", "order"), name="unique_attempt_option_order"),
        ]


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey("questions.Question", on_delete=models.PROTECT, related_name="candidate_answers")
    answered_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("attempt", "question"), name="unique_answer_per_attempt_question")]
        indexes = [models.Index(fields=("attempt", "question"), name="answer_attempt_question_idx")]

    def clean(self):
        if self.attempt_id and self.question_id and not self.attempt.attempt_questions.filter(question_id=self.question_id).exists():
            raise ValidationError({"question": "Question is not part of this attempt."})


class AnswerSelection(models.Model):
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="selections")
    option = models.ForeignKey("questions.QuestionOption", on_delete=models.PROTECT, related_name="answer_selections")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("answer", "option"), name="unique_option_per_answer")]

    def clean(self):
        if self.answer_id and self.option_id and self.option.question_id != self.answer.question_id:
            raise ValidationError({"option": "Selected option must belong to the answered question."})
