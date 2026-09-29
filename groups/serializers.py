from rest_framework import serializers
from .models import Group
class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ("id", "institution", "name", "code", "group_type", "academic_session", "is_active", "created_at", "updated_at")
        read_only_fields = ("institution", "created_at", "updated_at")
