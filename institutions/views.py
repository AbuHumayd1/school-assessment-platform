from rest_framework import viewsets
from tenants.permissions import CanManageInstitution
from tenants.querysets import institutions_for_user
from .models import Institution
from .serializers import InstitutionSerializer
class InstitutionViewSet(viewsets.ModelViewSet):
    serializer_class = InstitutionSerializer
    permission_classes = [CanManageInstitution]
    def get_queryset(self):
        return Institution.objects.filter(pk__in=institutions_for_user(self.request.user), is_active=True)
    def perform_create(self, serializer):
        if not (self.request.user.is_superuser or self.request.user.institution_memberships.filter(is_active=True, role="platform_admin").exists()):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only platform administrators can create institutions.")
        institution = serializer.save()
        from tenants.models import InstitutionMembership
        InstitutionMembership.objects.get_or_create(user=self.request.user, institution=institution,
            defaults={"role": InstitutionMembership.Role.INSTITUTION_ADMIN, "is_active": True})
