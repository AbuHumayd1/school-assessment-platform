from rest_framework import serializers

from .models import Answer, AnswerSelection, Attempt, AttemptQuestion


class StartAttemptSerializer(serializers.Serializer):
    assessment = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        unknown = set(self.initial_data) - {"assessment"}
        if unknown:
            raise serializers.ValidationError({key: "This field is not accepted." for key in unknown})
        return attrs


class AnswerWriteSerializer(serializers.Serializer):
    selected_options = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=True)

    def validate(self, attrs):
        unknown = set(self.initial_data) - {"selected_options"}
        if unknown:
            raise serializers.ValidationError({key: "This field is server-controlled or unsupported." for key in unknown})
        ids = attrs["selected_options"]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError({"selected_options": "An option cannot be selected more than once."})
        return attrs


class ReviewFlagSerializer(serializers.Serializer):
    marked_for_review = serializers.BooleanField()

    def validate(self, attrs):
        unknown = set(self.initial_data) - {"marked_for_review"}
        if unknown:
            raise serializers.ValidationError({key: "This field is not accepted." for key in unknown})
        return attrs


class CandidateOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="option_id", read_only=True)
    text = serializers.CharField(source="option.text", read_only=True)


class CandidateExamQuestionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="question_id", read_only=True)
    attempt_question_id = serializers.IntegerField(source="pk", read_only=True)
    question = serializers.SerializerMethodField()
    options = CandidateOptionSerializer(source="ordered_options", many=True, read_only=True)
    marks = serializers.SerializerMethodField()
    selected_options = serializers.SerializerMethodField()

    class Meta:
        model = AttemptQuestion
        fields = ("id", "attempt_question_id", "order", "question", "options", "marks", "marked_for_review", "selected_options")

    def get_question(self, obj):
        # Explicit allowlist: no explanation, correctness, difficulty, status, tenant, or author fields.
        return {"id": obj.question_id, "text": obj.question.text}

    def get_marks(self, obj):
        return obj.marks_available

    def get_selected_options(self, obj):
        answer = Answer.objects.filter(attempt=obj.attempt, question_id=obj.question_id).first()
        if answer is None:
            return []
        return list(answer.selections.order_by("option_id").values_list("option_id", flat=True))


class CandidateNavigationSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="question_id", read_only=True)
    answered = serializers.SerializerMethodField()

    class Meta:
        model = AttemptQuestion
        fields = ("id", "order", "answered", "marked_for_review")

    def get_answered(self, obj):
        return AnswerSelection.objects.filter(answer__attempt=obj.attempt, answer__question_id=obj.question_id).exists()


class CandidateAttemptSerializer(serializers.ModelSerializer):
    assessment_title = serializers.CharField(source="assessment.title", read_only=True)
    assessment_type = serializers.CharField(source="assessment.assessment_type", read_only=True)
    duration_minutes = serializers.IntegerField(source="assessment.duration_minutes", read_only=True)
    total_questions = serializers.SerializerMethodField()
    answered_count = serializers.SerializerMethodField()
    unanswered_count = serializers.SerializerMethodField()
    marked_for_review_count = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    server_time = serializers.SerializerMethodField()

    class Meta:
        model = Attempt
        fields = (
            "id", "assessment_title", "assessment_type", "duration_minutes", "attempt_number", "status",
            "started_at", "expires_at", "submitted_at", "total_questions", "answered_count",
            "unanswered_count", "marked_for_review_count", "remaining_seconds", "server_time",
        )

    def get_total_questions(self, obj):
        return obj.attempt_questions.count()

    def get_answered_count(self, obj):
        return AnswerSelection.objects.filter(answer__attempt=obj).values("answer_id").distinct().count()

    def get_unanswered_count(self, obj):
        return self.get_total_questions(obj) - self.get_answered_count(obj)

    def get_marked_for_review_count(self, obj):
        return obj.attempt_questions.filter(marked_for_review=True).count()

    def get_server_time(self, obj):
        from django.utils import timezone
        return timezone.now()

    def get_remaining_seconds(self, obj):
        from django.utils import timezone
        if obj.status != Attempt.Status.IN_PROGRESS:
            return 0
        return max(int((obj.expires_at - timezone.now()).total_seconds()), 0)


class StartAttemptResponseSerializer(serializers.ModelSerializer):
    assessment_title = serializers.CharField(source="assessment.title", read_only=True)
    assessment_type = serializers.CharField(source="assessment.assessment_type", read_only=True)
    duration_minutes = serializers.IntegerField(source="assessment.duration_minutes", read_only=True)
    total_questions = serializers.SerializerMethodField()

    class Meta:
        model = Attempt
        fields = ("id", "assessment_title", "assessment_type", "duration_minutes", "started_at", "expires_at", "status", "total_questions")

    def get_total_questions(self, obj):
        return obj.attempt_questions.count()


class StaffAttemptSerializer(serializers.ModelSerializer):
    candidate_name = serializers.SerializerMethodField()
    assessment_title = serializers.CharField(source="assessment.title", read_only=True)

    class Meta:
        model = Attempt
        fields = ("id", "candidate_id", "candidate_name", "assessment_id", "assessment_title", "attempt_number", "status", "started_at", "expires_at", "submitted_at", "last_activity_at")

    def get_candidate_name(self, obj):
        return f"{obj.candidate.first_name} {obj.candidate.last_name}".strip()
