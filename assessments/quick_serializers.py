from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import QuickExamConfiguration, QuickExamCredential
from .quick_models import normalize_exam_code


class StrictInputSerializer(serializers.Serializer):
    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "This field is not accepted." for key in unknown})
        return attrs


class ConfigurationWriteSerializer(StrictInputSerializer):
    exam_code = serializers.CharField(required=False, max_length=32)
    enabled = serializers.BooleanField(required=False)

    def validate_exam_code(self, value):
        try:
            return normalize_exam_code(value)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict["exam_code"])


class CredentialWriteSerializer(StrictInputSerializer):
    candidate = serializers.IntegerField(min_value=1)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class CredentialResetSerializer(StrictInputSerializer):
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class ConfigurationReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuickExamConfiguration
        fields = ("id", "assessment", "exam_code", "enabled", "session_version", "created_at", "updated_at")
        read_only_fields = fields


class CredentialReadSerializer(serializers.ModelSerializer):
    candidate_identifier = serializers.CharField(source="candidate.candidate_id", read_only=True)
    candidate_name = serializers.SerializerMethodField()
    candidate_status = serializers.CharField(source="candidate.status", read_only=True)

    def get_candidate_name(self, obj):
        return f"{obj.candidate.first_name} {obj.candidate.last_name}".strip()

    class Meta:
        model = QuickExamCredential
        fields = ("id", "configuration", "candidate", "candidate_identifier", "candidate_name", "candidate_status", "active", "version", "expires_at", "created_at", "generated_at", "revoked_at")
        read_only_fields = fields
