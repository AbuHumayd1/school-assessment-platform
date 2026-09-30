from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from tenants.models import InstitutionMembership
from .models import Institution


class InstitutionSerializer(serializers.ModelSerializer):
    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError("Enter a valid IANA timezone name.")
        return value

    class Meta:
        model = Institution
        fields = (
            "id", "name", "slug", "institution_type", "logo", "email", "phone",
            "address", "timezone", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "slug", "created_at", "updated_at")

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and not (
            request.user.is_superuser or request.user.institution_memberships.filter(
                is_active=True, institution__is_active=True,
                role=InstitutionMembership.Role.PLATFORM_ADMIN,
            ).exists()
        ):
            fields["is_active"].read_only = True
        return fields
