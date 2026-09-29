from rest_framework import serializers
from .models import Candidate
class CandidateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = ("id", "institution", "user", "candidate_id", "first_name", "last_name", "email", "phone", "date_of_birth", "status", "created_at", "updated_at")
        read_only_fields = ("institution", "created_at", "updated_at")
