import re
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from rest_framework import serializers

from groups.models import Group
from questions.models import Question
from subjects.models import Subject
from .models import Assessment, AssessmentQuestion
from .tenancy import assessment_institution_ids


def selectable_revisions(institution_id, pinned_ids=()):
    return Question.objects.filter(institution_id=institution_id, content_locked=True).filter(
        Q(status=Question.Status.APPROVED, available_for_new_assessments=True) |
        Q(pk__in=pinned_ids, status__in=[Question.Status.APPROVED, Question.Status.ARCHIVED]))


def pinned_question_ids(instance):
    """Keep pin lookup lazy and batch collection lookups for many=True."""
    if isinstance(instance, AssessmentQuestion):
        return [instance.question_id]
    if isinstance(instance, Assessment):
        return instance.assessment_questions.values_list('question_id', flat=True)
    if isinstance(instance, QuerySet):
        if instance.model is AssessmentQuestion:
            return instance.values_list('question_id', flat=True)
        if instance.model is Assessment:
            return AssessmentQuestion.objects.filter(
                assessment_id__in=instance.values('pk')).values_list('question_id', flat=True)
    if isinstance(instance, (list, tuple)):
        if instance and isinstance(instance[0], AssessmentQuestion):
            return [row.question_id for row in instance]
        return AssessmentQuestion.objects.filter(
            assessment_id__in=[row.pk for row in instance]).values_list('question_id', flat=True)
    return []


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
            pinned_ids = pinned_question_ids(self.instance)
            self.fields["question"].queryset = selectable_revisions(institution_id, pinned_ids)

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
            pinned = self.instance and self.instance.question_id == question.pk
            if not question.is_deliverable_revision or (not pinned and (
                    question.status != Question.Status.APPROVED or not question.available_for_new_assessments)):
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
    delivery_mode = serializers.ChoiceField(choices=("quick_exam", "account_login"), required=False)
    eligibility_strategy = serializers.SerializerMethodField()
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
            "candidate_access", "review_allowed", "result_release_mode", "show_score_immediately", "status", "created_by",
            "reviewed_by", "approved_by", "questions", "created_at", "updated_at",
            "subject_name", "group_name", "question_count", "quick_access_configured", "has_attempt_history", "delivery_mode", "eligibility_strategy",
        )
        read_only_fields = ("id", "institution", "total_marks", "status", "created_by", "reviewed_by", "approved_by", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        institution = self.context.get("institution") or getattr(self.instance, "institution", None)
        if institution:
            self.fields["subject"].queryset = Subject.objects.filter(institution=institution)
            self.fields["group"].queryset = Group.objects.filter(institution=institution, is_active=True)
            self.fields["questions"].child.context.update({"institution": institution})
            pinned_ids = pinned_question_ids(self.instance)
            self.fields["questions"].child.fields["question"].queryset = selectable_revisions(institution.pk, pinned_ids)

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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["delivery_mode"] = "quick_exam" if instance.uses_quick_delivery else "account_login"
        return data

    def get_eligibility_strategy(self, obj):
        return "specific_candidates" if obj.candidate_access == Assessment.CandidateAccess.ACCESS_CODE else obj.candidate_access

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

        delivery = attrs.pop("delivery_mode", None)
        if self.instance:
            current = "quick_exam" if self.instance.uses_quick_delivery else "account_login"
            if delivery is not None and delivery != current:
                raise serializers.ValidationError({"delivery_mode": "Delivery method is fixed when the exam is created."})
            proposed = attrs.get("candidate_access", self.instance.candidate_access)
            if not self.get_quick_access_configured(self.instance) and ((proposed == Assessment.CandidateAccess.ACCESS_CODE) != (current == "quick_exam")):
                raise serializers.ValidationError({"candidate_access": "Delivery method is fixed when the exam is created."})
        elif delivery is not None:
            if delivery == "quick_exam":
                if attrs.get("candidate_access") not in {None, Assessment.CandidateAccess.ACCESS_CODE, Assessment.CandidateAccess.SPECIFIC_CANDIDATES} or group:
                    raise serializers.ValidationError({"candidate_access": "Quick Exam supports Specific Candidates eligibility."})
                attrs["candidate_access"] = Assessment.CandidateAccess.ACCESS_CODE
            elif attrs.get("candidate_access") == Assessment.CandidateAccess.ACCESS_CODE:
                raise serializers.ValidationError({"candidate_access": "Account delivery cannot use Quick Exam access."})

        mode = attrs.get("candidate_access", getattr(self.instance, "candidate_access", Assessment.CandidateAccess.ASSIGNED_GROUP))
        if mode == Assessment.CandidateAccess.ASSIGNED_GROUP and not group and ("candidate_access" in attrs or "group" in attrs) and self.instance:
            raise serializers.ValidationError({"group": "Assign a group before saving group eligibility."})
        if self.instance and mode == Assessment.CandidateAccess.ASSIGNED_GROUP and mode != self.instance.candidate_access and self.instance.candidate_assignments.exists():
            raise serializers.ValidationError({"candidate_access": "Remove direct candidate assignments before changing eligibility strategy."})
        if mode in {Assessment.CandidateAccess.SPECIFIC_CANDIDATES, Assessment.CandidateAccess.ACCESS_CODE} and group:
            raise serializers.ValidationError({"group": "Specific candidate eligibility does not use a group."})
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
            existing = {row.question_id: row for row in instance.assessment_questions.select_for_update()}
            wanted = {item['question'].pk for item in questions}
            instance.assessment_questions.exclude(question_id__in=wanted).delete()
            # Preserve concrete pins and row IDs, including retired revisions. Move
            # retained orders temporarily to allow swaps under the unique constraint.
            offset = max([row.order for row in existing.values()] + [item['order'] for item in questions] + [0]) + 1
            for position, row in enumerate(existing.values()):
                if row.question_id in wanted:
                    row.order = offset + position
                    row.save(update_fields=['order'])
            for item in questions:
                row = existing.get(item['question'].pk)
                if row is None:
                    AssessmentQuestion.objects.create(assessment=instance, **item)
                else:
                    row.order, row.marks = item['order'], item['marks']
                    row.save(update_fields=['order', 'marks'])
        return instance
