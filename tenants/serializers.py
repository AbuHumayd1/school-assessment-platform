from django.contrib.auth import get_user_model
from rest_framework import serializers

from audit.models import AuditEvent
from audit.services import record_event
from .models import InstitutionMembership

User = get_user_model()
MANAGEABLE_ROLES = {
    InstitutionMembership.Role.TEACHER,
    InstitutionMembership.Role.EXAMINER,
    InstitutionMembership.Role.STUDENT,
}


class InstitutionMembershipSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True, required=False)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = InstitutionMembership
        fields = ("id", "institution", "user", "user_email", "email", "role", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "institution", "user", "user_email", "created_at", "updated_at")

    def validate(self, attrs):
        if "institution" in self.initial_data or "user" in self.initial_data:
            raise serializers.ValidationError({"institution": "Institution and user are resolved by the server."})
        request = self.context["request"]
        institution = self.context["institution"]
        actor = request.user
        is_platform = actor.is_superuser or actor.institution_memberships.filter(
            is_active=True, institution__is_active=True, role=InstitutionMembership.Role.PLATFORM_ADMIN,
        ).exists()
        requested_role = attrs.get("role", getattr(self.instance, "role", None))

        if self.instance:
            if self.instance.user_id == actor.pk:
                raise serializers.ValidationError("You cannot modify your own institution membership.")
            if not is_platform:
                if self.instance.role not in MANAGEABLE_ROLES or requested_role not in MANAGEABLE_ROLES:
                    raise serializers.ValidationError({"role": "Institution administrators can manage only teacher, examiner, and student memberships."})
        else:
            email = attrs.get("email")
            if not email:
                raise serializers.ValidationError({"email": "Enter the email address of an existing account."})
            matches = list(User.objects.filter(email__iexact=email, is_active=True).order_by("pk")[:2])
            if len(matches) != 1:
                raise serializers.ValidationError({"email": "No unique active account matches this email address."})
            target_user = matches[0]
            if target_user.pk == actor.pk:
                raise serializers.ValidationError({"email": "You cannot add or change your own membership."})
            if InstitutionMembership.objects.filter(user=target_user, institution=institution).exists():
                raise serializers.ValidationError({"email": "This account already has a membership in the selected institution."})
            target_is_platform = target_user.is_superuser or target_user.institution_memberships.filter(
                is_active=True, institution__is_active=True, role=InstitutionMembership.Role.PLATFORM_ADMIN,
            ).exists()
            if not is_platform and (
                requested_role not in MANAGEABLE_ROLES or target_is_platform
            ):
                raise serializers.ValidationError({"role": "Institution administrators cannot grant or manage platform or institution administrator access."})
            attrs["user"] = target_user
        return attrs

    def create(self, validated_data):
        validated_data.pop("email", None)
        validated_data.pop("institution", None)
        membership = InstitutionMembership.objects.create(
            institution=self.context["institution"],
            **validated_data,
        )
        record_event(
            institution=membership.institution,
            actor=self.context["request"].user,
            event_type=AuditEvent.Type.MEMBERSHIP_CHANGED,
            resource=membership,
            metadata={"action": "created", "role": membership.role},
        )
        return membership

    def update(self, instance, validated_data):
        previous_role = instance.role
        previous_active = instance.is_active
        membership = super().update(instance, validated_data)
        changed = previous_role != membership.role or previous_active != membership.is_active
        if changed:
            action = "role_changed" if previous_role != membership.role else (
                "reactivated" if membership.is_active else "deactivated"
            )
            record_event(
                institution=membership.institution,
                actor=self.context["request"].user,
                event_type=AuditEvent.Type.MEMBERSHIP_CHANGED,
                resource=membership,
                metadata={
                    "action": action,
                    "previous_role": previous_role,
                    "role": membership.role,
                    "was_active": previous_active,
                    "is_active": membership.is_active,
                },
            )
        return membership

