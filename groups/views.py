from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from tenants.permissions import CanManageGroups
from tenants.querysets import institutions_for_user, can_manage_institution
from .models import Group
from .serializers import GroupSerializer
class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer
    permission_classes = [CanManageGroups]
    def get_queryset(self):
        return Group.objects.filter(institution_id__in=institutions_for_user(self.request.user), institution__is_active=True)
    def perform_create(self, serializer):
        institution_id = self.request.data.get("institution")
        if not institution_id or not can_manage_institution(self.request.user, institution_id, ["institution_admin", "teacher", "examiner"]):
            raise ValidationError({"institution": "Choose an institution you are authorized to manage."})
        serializer.save(institution_id=institution_id)
    def perform_update(self, serializer):
        if "institution" in self.request.data and str(self.request.data["institution"]) != str(serializer.instance.institution_id):
            raise ValidationError({"institution": "Groups cannot be moved between institutions through this API."})
        serializer.save()
