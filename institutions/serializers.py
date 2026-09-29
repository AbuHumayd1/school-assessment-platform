from rest_framework import serializers
from .models import Institution
class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = ("id", "name", "slug", "institution_type", "logo", "email", "phone", "address", "timezone", "is_active", "created_at", "updated_at")
        read_only_fields = ("slug", "created_at", "updated_at")
