from rest_framework import serializers
from questions.models import Question, QuestionOption
from .models import AssessmentQuestion


class InspectionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = ("id", "text", "order", "is_correct")
        read_only_fields = fields


class InspectionQuestionSerializer(serializers.ModelSerializer):
    options = InspectionOptionSerializer(many=True, read_only=True)
    topic_name = serializers.CharField(source="topic.name", read_only=True, default=None)

    class Meta:
        model = Question
        fields = ("id", "text", "question_type", "options", "explanation", "topic", "topic_name", "difficulty", "status")
        read_only_fields = fields


class QuestionInspectionSerializer(serializers.ModelSerializer):
    question = InspectionQuestionSerializer(read_only=True)

    class Meta:
        model = AssessmentQuestion
        fields = ("id", "order", "marks", "question")
        read_only_fields = fields


class PreviewOptionSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="text", read_only=True)

    class Meta:
        model = QuestionOption
        fields = ("id", "label", "order")
        read_only_fields = fields


class PreviewQuestionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="question.id", read_only=True)
    prompt = serializers.CharField(source="question.text", read_only=True)
    type = serializers.CharField(source="question.question_type", read_only=True)
    options = PreviewOptionSerializer(source="question.options", many=True, read_only=True)

    class Meta:
        model = AssessmentQuestion
        fields = ("id", "prompt", "type", "options", "order", "marks")
        read_only_fields = fields
