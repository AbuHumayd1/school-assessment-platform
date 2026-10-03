import re
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from groups.models import Group
from questions.models import Question
from subjects.models import Subject
from .models import Assessment, AssessmentQuestion
from .tenancy import assessment_institution_ids


class AwareDateTimeField(serializers.DateTimeField):
    """Require an offset in API input rather than silently assuming a timezone."""
    def to_internal_value(self, value):
        if isinstance(value, str) and not re.search(r"(?:Z|[+-]\d{2}:?\d{2})$", value, re.I):
            raise serializers.ValidationError("Provide a timezone-aware datetime with Z or an explicit UTC offset.")
        return super().to_internal_value(value)


class AssessmentQuestionSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source="question.text", read_only=True)
    question = serializers.PrimaryKeyRelatedField(queryset=Question.objects.none())

    class Meta:
        model = AssessmentQuestion
        fields = ("id", "question", "question_text", "order", "marks", "created_at", "updated_at")
        read_only_fields = ("id", "question_text", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        institution = self.context.get("institution")
        assessment = self.context.get("assessment")
        institution_id = institution.pk if institution else getattr(assessment, "institution_id", None)
        if institution_id:
            self.fields["question"].queryset = Question.objects.filter(
                institution_id=institution_id, status=Question.Status.APPROVED
            )

    def validate(self, attrs):
        assessment = self.context.get("assessment") or getattr(self.instance, "assessment", None)
        question = attrs.get("question", getattr(self.instance, "question", None))
        order = attrs.get("order", getattr(self.instance, "order", None))
        marks = attrs.get("marks", getattr(self.instance, "marks", None))
        if assessment and question:
            if question.institution_id != assessment.institution_id:
                raise serializers.ValidationError({"question": "Question must belong to the assessment institution."})
            if question.subject_id != assessment.subject_id:
                raise serializers.ValidationError({"question": "Question must belong to the assessment subject."})
            if question.status != Question.Status.APPROVED:
                raise serializers.ValidationError({"question": "Only approved questions may be selected."})
            duplicates = AssessmentQuestion.objects.filter(assessment=assessment, question=question)
            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError({"question": "This question is already selected."})
            order_matches = AssessmentQuestion.objects.filter(assessment=assessment, order=order)
            if self.instance:
                order_matches = order_matches.exclude(pk=self.instance.pk)
            if order is not None and order_matches.exists():
                raise serializers.ValidationError({"order": "This order is already used in the assessment."})
        if marks is not None and marks <= 0:
            raise serializers.ValidationError({"marks": "Marks must be positive."})
        return attrs


class AssessmentSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True, default=None)
    question_count = serializers.SerializerMethodField()
    quick_access_configured = serializers.SerializerMethodField()
    has_attempt_history = serializers.SerializerMethodField()
    institution = serializers.PrimaryKeyRelatedField(read_only=True)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.none())
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.none(), required=False, allow_null=True)
    total_marks = serializers.DecimalField(max_digits=9, decimal_places=2, read_only=True)
    status = serializers.ChoiceField(choices=Assessment.Status.choices, read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    reviewed_by = serializers.PrimaryKeyRelatedField(read_only=True)
    approved_by = serializers.PrimaryKeyRelatedField(read_only=True)
    start_at = AwareDateTimeField(required=False, allow_null=True)
    end_at = AwareDateTimeField(required=False, allow_null=True)
    questions = AssessmentQuestionSerializer(many=True, required=False, source="assessment_questions")

    class Meta:
        model = Assessment
        fields = (
            "id", "institution", "title", "description", "assessment_type", "subject", "group",
            "duration_minutes", "total_marks", "pass_mark", "start_at", "end_at", "attempt_limit",
            "resume_allowed",
            "randomize_questions", "randomize_options", "security_level", "result_visibility",
            "candidate_access", "review_allowed", "result_release_mode", "status", "created_by",
            "reviewed_by", "approved_by", "questions", "created_at", "updated_at",
            "subject_name", "group_name", "question_count", "quick_access_configured", "has_attempt_history",
        )
        read_only_fields = ("id", "institution", "total_marks", "status", "created_by", "reviewed_by", "approved_by", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        institution = self.context.get("institution") or getattr(self.instance, "institution", None)
        if institution:
            self.fields["subject"].queryset = Subject.objects.filter(institution=institution)
            self.fields["group"].queryset = Group.objects.filter(institution=institution, is_active=True)
            self.fields["questions"].child.context.update({"institution": institution})
            self.fields["questions"].child.fields["question"].queryset = Question.objects.filter(
                institution=institution, status=Question.Status.APPROVED
            )

    def get_quick_access_configured(self, obj):
        from .models import QuickExamConfiguration
        value = getattr(obj, "quick_access_configured", None)
        return value if value is not None else QuickExamConfiguration.objects.filter(assessment=obj).exists()

    def get_has_attempt_history(self, obj):
        from attempts.models import Attempt
        value = getattr(obj, "has_attempt_history", None)
        return value if value is not None else Attempt.objects.filter(assessment=obj).exists()

    def get_question_count(self, obj):
        return obj.assessment_questions.count()

    def validate(self, attrs):
        institution = self.context.get("institution") or getattr(self.instance, "institution", None)
        subject = attrs.get("subject", getattr(self.instance, "subject", None))
        group = attrs.get("group", getattr(self.instance, "group", None))
        if institution and subject and subject.institution_id != institution.pk:
            raise serializers.ValidationError({"subject": "Subject must belong to the selected institution."})
        if group:
            if institution and group.institution_id != institution.pk:
                raise serializers.ValidationError({"group": "Group must belong to the selected institution."})
            if not group.is_active:
                raise serializers.ValidationError({"group": "Group must be active."})
        if "status" in self.initial_data or "institution" in self.initial_data or "total_marks" in self.initial_data:
            raise serializers.ValidationError("institution, total_marks and status are server-controlled fields.")

        start_at = attrs.get("start_at", getattr(self.instance, "start_at", None))
        end_at = attrs.get("end_at", getattr(self.instance, "end_at", None))
        if start_at and end_at and end_at <= start_at:
            raise serializers.ValidationError({"end_at": "End time must be after start time."})
        duration = attrs.get("duration_minutes", getattr(self.instance, "duration_minutes", None))
        attempts = attrs.get("attempt_limit", getattr(self.instance, "attempt_limit", 1))
        if duration is not None and duration < 1:
            raise serializers.ValidationError({"duration_minutes": "Duration must be positive."})
        if attempts is not None and attempts < 1:
            raise serializers.ValidationError({"attempt_limit": "Attempt limit must be positive."})

        question_data = attrs.get("assessment_questions")
        if self.instance and question_data is not None:
            from attempts.models import Attempt
            if Attempt.objects.filter(assessment=self.instance).exists():
                raise serializers.ValidationError({"questions": "Assessment questions cannot be changed after an attempt starts."})
        if question_data is None and self.instance:
            specs = [{"question": row.question, "order": row.order, "marks": row.marks} for row in self.instance.assessment_questions.select_related("question")]
        elif question_data is not None:
            specs = [{"question": row["question"], "order": row["order"], "marks": row["marks"]} for row in question_data]
        else:
            specs = []
        if institution and subject:
            candidate = self.instance or Assessment(institution=institution, created_by=self.context["request"].user)
            candidate.institution = institution
            candidate.subject = subject
            candidate.group = group
            candidate.title = attrs.get("title", getattr(candidate, "title", ""))
            candidate.duration_minutes = duration
            candidate.attempt_limit = attempts
            candidate.pass_mark = attrs.get("pass_mark", getattr(candidate, "pass_mark", Decimal("0.00")))
            candidate.start_at = start_at
            candidate.end_at = end_at
            try:
                candidate.validate_configuration(specs, require_questions=False)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        questions = validated_data.pop("assessment_questions", [])
        assessment = Assessment.objects.create(
            **validated_data, institution=self.context["institution"],
            created_by=self.context["request"].user, status=Assessment.Status.DRAFT,
        )
        AssessmentQuestion.objects.bulk_create([
            AssessmentQuestion(assessment=assessment, **item) for item in questions
        ])
        return assessment

    @transaction.atomic
    def update(self, instance, validated_data):
        questions = validated_data.pop("assessment_questions", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if questions is not None:
            instance.assessment_questions.all().delete()
            AssessmentQuestion.objects.bulk_create([
                AssessmentQuestion(assessment=instance, **item) for item in questions
            ])
        return instance
