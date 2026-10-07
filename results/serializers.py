from rest_framework import serializers

from .models import Result, ResultQuestion


class ResultQuestionStaffSerializer(serializers.ModelSerializer):
    question_id = serializers.IntegerField(source="attempt_question.question_id", read_only=True)
    question_order = serializers.IntegerField(source="attempt_question.order", read_only=True)

    class Meta:
        model = ResultQuestion
        fields = ("id", "question_id", "question_order", "marks_available", "marks_obtained", "status", "validation_note")


class StaffResultSerializer(serializers.ModelSerializer):
    attempt_id = serializers.IntegerField(read_only=True)
    candidate_id = serializers.IntegerField(read_only=True)
    assessment_id = serializers.IntegerField(read_only=True)
    candidate_name = serializers.CharField(source="candidate.candidate_id", read_only=True)
    assessment_title = serializers.CharField(source="assessment.title", read_only=True)
    questions = ResultQuestionStaffSerializer(many=True, read_only=True)

    class Meta:
        model = Result
        fields = ("id", "attempt_id", "candidate_id", "candidate_name", "assessment_id", "assessment_title",
                  "total_marks", "marks_obtained", "pass_mark", "percentage", "grade", "passed", "status",
                  "marked_at", "published_at", "questions")
        read_only_fields = fields


class CandidateResultSerializer(serializers.ModelSerializer):
    assessment_title = serializers.CharField(source="assessment.title", read_only=True)
    assessment_type = serializers.CharField(source="assessment.assessment_type", read_only=True)
    submitted_at = serializers.DateTimeField(source="attempt.submitted_at", read_only=True)

    class Meta:
        model = Result
        fields = ("id", "assessment_title", "assessment_type", "marks_obtained", "total_marks", "percentage",
                  "grade", "passed", "published_at", "submitted_at")
        read_only_fields = fields
