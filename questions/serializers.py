from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from subjects.models import Subject
from .models import Question, QuestionOption, Topic
from .tenancy import institution_ids_for_question_bank


def _visible_institution_ids(context):
    institution = context.get("institution")
    if institution:
        return (institution.pk,)
    request = context.get("request")
    if request and request.user.is_authenticated:
        return institution_ids_for_question_bank(request.user)
    return ()


class TopicSerializer(serializers.ModelSerializer):
    institution = serializers.PrimaryKeyRelatedField(read_only=True)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.none())
    parent = serializers.PrimaryKeyRelatedField(queryset=Topic.objects.none(), required=False, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        institutions = _visible_institution_ids(self.context)
        self.fields["subject"].queryset = Subject.objects.filter(institution_id__in=institutions)
        self.fields["parent"].queryset = Topic.objects.filter(institution_id__in=institutions)

    class Meta:
        model = Topic
        fields = ("id", "institution", "subject", "parent", "name", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "institution", "created_at", "updated_at")

    def validate(self, attrs):
        institution = self.context.get("institution") or getattr(self.instance, "institution", None)
        subject = attrs.get("subject", getattr(self.instance, "subject", None))
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        if institution and subject and subject.institution_id != institution.pk:
            raise serializers.ValidationError({"subject": "The subject must belong to the selected institution."})
        if parent:
            if institution and parent.institution_id != institution.pk:
                raise serializers.ValidationError({"parent": "The parent topic must belong to the selected institution."})
            if subject and parent.subject_id != subject.pk:
                raise serializers.ValidationError({"parent": "The parent topic must belong to the selected subject."})
            if self.instance and parent.pk == self.instance.pk:
                raise serializers.ValidationError({"parent": "A topic cannot be its own parent."})
            ancestor = parent
            while ancestor is not None:
                if self.instance and ancestor.pk == self.instance.pk:
                    raise serializers.ValidationError({"parent": "A topic cannot be its own ancestor."})
                ancestor = ancestor.parent
        return attrs


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = ("id", "text", "is_correct", "order", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class CandidateQuestionOptionSerializer(serializers.ModelSerializer):
    """Safe future-facing shape; correct-answer flags are intentionally absent."""
    class Meta:
        model = QuestionOption
        fields = ("id", "text", "order")
        read_only_fields = fields


class QuestionSerializer(serializers.ModelSerializer):
    institution = serializers.PrimaryKeyRelatedField(read_only=True)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.none())
    topic = serializers.PrimaryKeyRelatedField(queryset=Topic.objects.none(), required=False, allow_null=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    reviewed_by = serializers.PrimaryKeyRelatedField(read_only=True)
    status = serializers.ChoiceField(choices=Question.Status.choices, read_only=True)
    options = QuestionOptionSerializer(many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        institutions = _visible_institution_ids(self.context)
        self.fields["subject"].queryset = Subject.objects.filter(institution_id__in=institutions)
        self.fields["topic"].queryset = Topic.objects.filter(institution_id__in=institutions)

    class Meta:
        model = Question
        fields = (
            "id", "institution", "subject", "topic", "question_type", "difficulty", "text", "explanation",
            "marks", "source", "source_year", "learning_objective", "status", "created_by", "reviewed_by",
            "options", "created_at", "updated_at",
        )
        read_only_fields = ("id", "institution", "status", "created_by", "reviewed_by", "created_at", "updated_at")

    def validate(self, attrs):
        institution = self.context.get("institution") or getattr(self.instance, "institution", None)
        subject = attrs.get("subject", getattr(self.instance, "subject", None))
        topic = attrs.get("topic", getattr(self.instance, "topic", None))
        question_type = attrs.get("question_type", getattr(self.instance, "question_type", None))
        options = attrs.get("options")
        if options is None and self.instance:
            options = list(self.instance.options.values("text", "is_correct", "order"))

        if institution and subject and subject.institution_id != institution.pk:
            raise serializers.ValidationError({"subject": "The subject must belong to the selected institution."})
        if topic:
            if institution and topic.institution_id != institution.pk:
                raise serializers.ValidationError({"topic": "The topic must belong to the selected institution."})
            if subject and topic.subject_id != subject.pk:
                raise serializers.ValidationError({"topic": "The topic must belong to the selected subject."})
        if attrs.get("source_year") is not None and attrs["source_year"] > timezone.localdate().year + 1:
            raise serializers.ValidationError({"source_year": "The source year cannot be more than one year in the future."})
        if options is None:
            return attrs
        if len(options) < 2:
            raise serializers.ValidationError({"options": "Objective questions must have at least two options."})
        option_orders = [option["order"] for option in options]
        if len(option_orders) != len(set(option_orders)):
            raise serializers.ValidationError({"options": "Option order values must be unique within a question."})
        correct_count = sum(bool(option["is_correct"]) for option in options)
        if question_type == Question.Type.MULTIPLE_CHOICE and correct_count != 1:
            raise serializers.ValidationError({"options": "Multiple-choice questions require exactly one correct option."})
        if question_type == Question.Type.MULTIPLE_SELECT and correct_count < 1:
            raise serializers.ValidationError({"options": "Multiple-select questions require at least one correct option."})
        if question_type == Question.Type.TRUE_FALSE and (len(options) != 2 or correct_count != 1):
            raise serializers.ValidationError({"options": "True/false questions require exactly two options and one correct option."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        options = validated_data.pop("options")
        question = Question.objects.create(
            **validated_data,
            institution=self.context["institution"],
            created_by=self.context["request"].user,
            status=Question.Status.DRAFT,
        )
        QuestionOption.objects.bulk_create([QuestionOption(question=question, **option) for option in options])
        return question

    @transaction.atomic
    def update(self, instance, validated_data):
        options = validated_data.pop("options", None)
        if options is not None:
            from attempts.models import AttemptQuestion
            if AttemptQuestion.objects.filter(question=instance).exists():
                raise serializers.ValidationError({"options": "Question options cannot be changed after an attempt starts."})
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if options is not None:
            instance.options.all().delete()
            QuestionOption.objects.bulk_create([QuestionOption(question=instance, **option) for option in options])
        return instance
