from collections.abc import Mapping
from uuid import uuid4

from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers

from audit.models import AuditEvent
from audit.services import record_event
from tenants.models import InstitutionMembership
from .models import Institution
from .serializers import InstitutionSerializer


class WorkspaceCreationSerializer(InstitutionSerializer):
    class Meta:
        model = Institution
        fields = ("id", "name", "institution_type", "email", "phone", "timezone")
        read_only_fields = ("id",)

    def get_fields(self):
        return serializers.ModelSerializer.get_fields(self)

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({"non_field_errors": ["Enter workspace setup fields."]})
        if set(data) - {"name", "institution_type", "email", "phone", "timezone"}:
            raise serializers.ValidationError({"non_field_errors": ["Only workspace setup fields are accepted."]})
        return super().to_internal_value(data)

    @transaction.atomic
    def create(self, validated_data):
        actor = self.context["request"].user
        # Name readability plus a server-generated unique suffix also handles
        # simultaneous identical names and names without Latin characters.
        slug = f"{slugify(validated_data['name'])[:180] or 'workspace'}-{uuid4().hex}"
        institution = Institution.objects.create(slug=slug, **validated_data)
        membership = InstitutionMembership.objects.create(
            institution=institution, user=actor,
            role=InstitutionMembership.Role.INSTITUTION_ADMIN, is_active=True,
        )
        record_event(institution=institution, actor=actor, event_type=AuditEvent.Type.MEMBERSHIP_CHANGED,
                     resource=membership, metadata={"action": "created", "role": membership.role})
        return institution
