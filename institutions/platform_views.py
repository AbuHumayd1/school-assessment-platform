"""Compact operations API. Never impersonates users or grants actor memberships."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from assessments.models import Assessment
from attempts.models import Attempt
from audit.models import AuditEvent
from audit.services import record_event
from candidates.models import Candidate
from tenants.models import InstitutionMembership
from .models import Institution
from .permissions import is_platform_administrator
from .serializers import InstitutionSerializer


class PlatformPermission(BasePermission):
    def has_permission(self, request, view):
        return is_platform_administrator(request.user)


class PlatformPagination(PageNumberPagination):
    page_size = 25


class ClientSerializer(InstitutionSerializer):
    class Meta:
        model = Institution
        fields = ("id", "name", "slug", "institution_type", "timezone", "workspace_mode",
                  "can_release_candidate_results", "is_active")
        read_only_fields = ("id", "is_active", "can_release_candidate_results")
        extra_kwargs = {"slug": {"required": True, "allow_blank": False}}


class AdministratorInput(serializers.Serializer):
    name = serializers.CharField(max_length=300)
    email = serializers.EmailField()
    initial_password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)


class ClientViewSet(viewsets.ModelViewSet):
    permission_classes = (PlatformPermission,)
    serializer_class = ClientSerializer
    pagination_class = PlatformPagination
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        query = Institution.objects.all().order_by("name", "pk")
        search = self.request.query_params.get("search", "").strip()[:200]
        return query.filter(Q(name__icontains=search) | Q(slug__icontains=search)) if search else query

    def perform_create(self, serializer):
        with transaction.atomic():
            institution = serializer.save()
            record_event(institution=institution, actor=self.request.user,
                         event_type=AuditEvent.Type.INSTITUTION_PROFILE_UPDATED, resource=institution,
                         metadata={"action": "client_created"})

    def perform_update(self, serializer):
        with transaction.atomic():
            serializer.instance = Institution.objects.select_for_update().get(pk=serializer.instance.pk)
            institution = serializer.save()
            record_event(institution=institution, actor=self.request.user,
                         event_type=AuditEvent.Type.INSTITUTION_PROFILE_UPDATED, resource=institution,
                         metadata={"fields": sorted(serializer.validated_data)})

    @action(detail=True, methods=["post"], url_path="release-permission")
    @transaction.atomic
    def release_permission(self, request, pk=None):
        institution = Institution.objects.select_for_update().get(pk=self.get_object().pk)
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["enabled"] = serializers.BooleanField(required=True)
        serializer.is_valid(raise_exception=True)
        institution.can_release_candidate_results = serializer.validated_data["enabled"]
        institution.save(update_fields=("can_release_candidate_results", "updated_at"))
        record_event(institution=institution, actor=request.user,
                     event_type=AuditEvent.Type.INSTITUTION_PROFILE_UPDATED, resource=institution,
                     metadata={"fields": ["can_release_candidate_results"], "enabled": institution.can_release_candidate_results})
        return Response(ClientSerializer(institution).data)

    @action(detail=True, methods=["get", "post"])
    def administrators(self, request, pk=None):
        institution = self.get_object()
        if request.method == "GET":
            memberships = institution.memberships.filter(role="institution_admin").select_related("user").order_by("pk")
            return Response([{"id": item.pk, "name": item.user.get_full_name(), "email": item.user.email,
                              "is_active": item.is_active and item.user.is_active} for item in memberships])
        data = AdministratorInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        User = get_user_model()
        try:
            with transaction.atomic():
                # Serialize provisioning for this client; unique email/membership constraints handle other clients.
                Institution.objects.select_for_update().get(pk=institution.pk)
                users = list(User.objects.select_for_update().filter(email__iexact=values["email"])[:2])
                if len(users) > 1 or (users and not users[0].is_active):
                    raise ValidationError({"email": "This account cannot be provisioned."})
                if users:
                    user = users[0]
                    if is_platform_administrator(user):
                        raise ValidationError({"email": "Use a client administrator account."})
                    # Never change an existing account's password or name.
                else:
                    password = values.get("initial_password")
                    if not password:
                        raise ValidationError({"initial_password": "An initial password is required for a new account."})
                    first, _, last = values["name"].partition(" ")
                    if len(first) > 150 or len(last) > 150:
                        raise ValidationError({"name": "Use at most 150 characters for each name."})
                    user = User(email=values["email"].lower(), first_name=first, last_name=last)
                    try:
                        validate_password(password, user)
                    except DjangoValidationError as error:
                        raise ValidationError({"initial_password": error.messages})
                    user.set_password(password)
                    user.save()
                existing = InstitutionMembership.objects.filter(user=user, institution=institution).first()
                if existing:
                    raise ValidationError({"email": "This account already has a relationship with this client."})
                membership = InstitutionMembership.objects.create(user=user, institution=institution, role="institution_admin")
                record_event(institution=institution, actor=request.user, event_type=AuditEvent.Type.MEMBERSHIP_CHANGED,
                             resource=membership, metadata={"action": "administrator_provisioned", "role": "institution_admin"})
        except IntegrityError:
            raise ValidationError({"email": "This account or membership changed. Refresh and try again."})
        return Response({"id": membership.pk, "name": user.get_full_name(), "email": user.email, "is_active": True}, status=201)


class PlatformOverviewView(APIView):
    permission_classes = (PlatformPermission,)

    def get(self, request):
        return Response({"clients": Institution.objects.count(),
                         "active_exams": Assessment.objects.filter(institution__is_active=True, status="scheduled").count(),
                         "candidates": Candidate.objects.filter(institution__is_active=True).count(),
                         "submissions": Attempt.objects.filter(institution__is_active=True, status__in=("submitted", "expired")).count()})


class PlatformExamsView(APIView):
    permission_classes = (PlatformPermission,)

    def get(self, request):
        exams = Assessment.objects.filter(institution__is_active=True).select_related("institution").order_by("-created_at", "-pk")
        pager = PlatformPagination()
        page = pager.paginate_queryset(exams, request, view=self)
        return pager.get_paginated_response([{"id": row.pk, "institution": row.institution_id,
            "client": row.institution.name, "title": row.title, "status": row.status} for row in page])
