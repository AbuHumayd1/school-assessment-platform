from rest_framework import serializers
from .models import Subject
class SubjectSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        if 'owner_scope' in self.initial_data:
            raise serializers.ValidationError({'owner_scope': 'Ownership is assigned by this endpoint.'})
        return attrs
    class Meta:
        model = Subject
        fields = ("id", "institution", "name", "code", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("institution", "created_at", "updated_at")
