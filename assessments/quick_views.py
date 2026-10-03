from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from candidates.models import Candidate
from tenants.permissions import CanManageInstitution
from tenants.querysets import resolve_institution_context
from .models import Assessment, QuickExamConfiguration, QuickExamCredential
from .quick_serializers import (
    ConfigurationReadSerializer, ConfigurationWriteSerializer, CredentialReadSerializer,
    CredentialResetSerializer, CredentialWriteSerializer, StrictInputSerializer,
)
from .quick_services import configure_quick_access, generate_credential, reset_credential, revoke_credential


class QuickStaffView(APIView):
    permission_classes = (CanManageInstitution,)
    throttle_classes = (ScopedRateThrottle,)

    def get_throttles(self):
        self.throttle_scope = "quick_exam_admin" if self.request.method not in {"GET", "HEAD", "OPTIONS"} else None
        return super().get_throttles()

    def assessment(self, request, assessment_pk):
        institution = resolve_institution_context(request, {"institution_admin"})
        return get_object_or_404(Assessment.objects.select_related("institution"), pk=assessment_pk, institution=institution)

    def configuration(self, assessment):
        return get_object_or_404(QuickExamConfiguration.objects.select_related("assessment__institution"), assessment=assessment)

    def candidate(self, assessment, candidate_pk):
        return get_object_or_404(Candidate, pk=candidate_pk, institution_id=assessment.institution_id)


class QuickConfigurationView(QuickStaffView):
    def get(self, request, assessment_pk):
        assessment = self.assessment(request, assessment_pk)
        return Response(ConfigurationReadSerializer(self.configuration(assessment)).data)

    def put(self, request, assessment_pk):
        assessment = self.assessment(request, assessment_pk)
        serializer = ConfigurationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        configuration, created = configure_quick_access(assessment, request.user, **serializer.validated_data)
        return Response(ConfigurationReadSerializer(configuration).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def patch(self, request, assessment_pk):
        assessment = self.assessment(request, assessment_pk)
        self.configuration(assessment)
        serializer = ConfigurationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        configuration, _ = configure_quick_access(assessment, request.user, **serializer.validated_data)
        return Response(ConfigurationReadSerializer(configuration).data)


class QuickCredentialView(QuickStaffView):
    def get(self, request, assessment_pk):
        configuration = self.configuration(self.assessment(request, assessment_pk))
        credentials = QuickExamCredential.objects.filter(configuration=configuration).select_related("candidate").order_by("candidate__candidate_id", "pk")
        pagination = PageNumberPagination()
        pagination.page_size = 25
        rows = pagination.paginate_queryset(credentials, request, view=self)
        return pagination.get_paginated_response(CredentialReadSerializer(rows, many=True).data)

    def post(self, request, assessment_pk):
        assessment = self.assessment(request, assessment_pk)
        configuration = self.configuration(assessment)
        serializer = CredentialWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        candidate = self.candidate(assessment, data.pop("candidate"))
        credential, pin = generate_credential(configuration, candidate, request.user, **data)
        return credential_response(credential, pin, status.HTTP_201_CREATED)


def credential_response(credential, pin, response_status=status.HTTP_200_OK):
    response = Response({"credential": CredentialReadSerializer(credential).data, "initial_pin": pin}, status=response_status)
    response["Cache-Control"] = "no-store, private"
    return response


class QuickCredentialResetView(QuickStaffView):
    def post(self, request, assessment_pk, candidate_pk):
        assessment = self.assessment(request, assessment_pk)
        configuration = self.configuration(assessment)
        candidate = self.candidate(assessment, candidate_pk)
        serializer = CredentialResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credential, pin = reset_credential(configuration, candidate, request.user, **serializer.validated_data)
        return credential_response(credential, pin)


class QuickCredentialRevokeView(QuickStaffView):
    def post(self, request, assessment_pk, candidate_pk):
        assessment = self.assessment(request, assessment_pk)
        configuration = self.configuration(assessment)
        candidate = self.candidate(assessment, candidate_pk)
        serializer = StrictInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credential = revoke_credential(configuration, candidate, request.user)
        return Response(CredentialReadSerializer(credential).data)
