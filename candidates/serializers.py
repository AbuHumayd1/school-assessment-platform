from rest_framework import serializers

from accounts.models import User
from .models import Candidate


class CandidateSerializer(serializers.ModelSerializer):
    institution = serializers.PrimaryKeyRelatedField(read_only=True)
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.none(), required=False, allow_null=True)

    class Meta:
        model = Candidate
        fields = ("id", "institution", "user", "candidate_id", "first_name", "last_name", "email", "phone", "date_of_birth", "status", "created_at", "updated_at")
        read_only_fields = ("id", "institution", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        institution_id = getattr(self.instance, "institution_id", None)
        if institution_id is None:
            institution_id = self.initial_data.get("institution") if hasattr(self, "initial_data") else None
        try:
            institution_id = int(institution_id) if institution_id is not None else None
        except (TypeError, ValueError):
            institution_id = None
        if institution_id:
            self.fields["user"].queryset = User.objects.filter(
                is_active=True,
                institution_memberships__institution_id=institution_id,
                institution_memberships__institution__is_active=True,
                institution_memberships__is_active=True,
            ).distinct()

    def validate(self, attrs):
        if not self.instance:
            return attrs
        request = self.context.get("request")
        if request and request.user.pk == self.instance.user_id:
            protected = {"candidate_id", "status", "user"}
            if any(key in attrs and attrs[key] != getattr(self.instance, key) for key in protected):
                raise serializers.ValidationError("Candidate-owned identity and status fields cannot be changed through this API.")
        request = self.context.get("request")
        if request and any(key in attrs for key in ("candidate_id", "status", "user")):
            user = request.user
            manager = user.is_superuser or user.institution_memberships.filter(
                institution_id=self.instance.institution_id, institution__is_active=True,
                is_active=True, role__in=("platform_admin", "institution_admin"),
            ).exists()
            if not manager and any(key in attrs for key in ("candidate_id", "status", "user")):
                raise serializers.ValidationError("Only an institution administrator can change candidate identity, status, or account linkage.")
        return attrs
