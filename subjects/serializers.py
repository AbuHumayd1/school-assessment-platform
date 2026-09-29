from rest_framework import serializers
from .models import Subject
class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ("id", "institution", "name", "code", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("institution", "created_at", "updated_at")
