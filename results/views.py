from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from attempts.models import Attempt
from candidates.models import Candidate
from .models import Result
from .permissions import ADMIN_ROLES, MARKER_ROLES, institution_ids, is_platform_admin
from .serializers import CandidateResultSerializer, StaffResultSerializer
from .services import mark_attempt, publish_result, withhold_result


def _require_role(user, roles, institution_id=None):
    if user.is_superuser or is_platform_admin(user):
        return
    memberships = user.institution_memberships.filter(is_active=True, institution__is_active=True)
    if institution_id is not None:
        memberships = memberships.filter(institution_id=institution_id)
    if memberships.filter(role__in=roles).exists():
        return
    raise PermissionDenied("You do not have permission to perform this result action.")


def _candidate_visible(result, now=None):
    now = now or timezone.now()
    assessment = result.assessment
    if result.status != Result.Status.PUBLISHED or not result.published_at or not result.institution.is_active:
        return False
    if assessment.result_visibility == assessment.ResultVisibility.HIDDEN:
        return False
    if assessment.result_visibility == assessment.ResultVisibility.SCHEDULED_RELEASE:
        return bool(assessment.end_at and now >= assessment.end_at)
    return assessment.result_visibility == assessment.ResultVisibility.AFTER_SUBMISSION


class ResultListView(APIView):
    def get(self, request):
        _require_role(request.user, {"platform_admin", "institution_admin", "examiner", "teacher"})
        queryset = Result.objects.filter(institution_id__in=institution_ids(request.user)).select_related("candidate", "assessment", "institution").prefetch_related("questions")
        status_filter = request.query_params.get("status")
        if status_filter in Result.Status.values:
            queryset = queryset.filter(status=status_filter)
        return Response(StaffResultSerializer(queryset, many=True).data)


class ResultDetailView(APIView):
    def get(self, request, result_id):
        candidate_result = Result.objects.filter(pk=result_id, candidate__user=request.user,
                                                 candidate__status=Candidate.Status.ACTIVE,
                                                 institution__is_active=True).select_related("assessment", "institution").first()
        if candidate_result is not None:
            if not _candidate_visible(candidate_result):
                raise NotFound()
            return Response(CandidateResultSerializer(candidate_result).data)
        if Candidate.objects.filter(user=request.user).exists():
            raise NotFound()
        _require_role(request.user, {"platform_admin", "institution_admin", "examiner", "teacher"})
        result = get_object_or_404(Result.objects.select_related("candidate", "assessment", "institution").prefetch_related("questions__attempt_question"),
                                   pk=result_id, institution_id__in=institution_ids(request.user))
        return Response(StaffResultSerializer(result).data)


class MyResultsView(APIView):
    def get(self, request):
        results = Result.objects.filter(candidate__user=request.user, candidate__status=Candidate.Status.ACTIVE,
                                        institution__is_active=True).select_related("assessment", "institution")
        visible = [result for result in results if _candidate_visible(result)]
        return Response(CandidateResultSerializer(visible, many=True).data)


class AttemptMarkView(APIView):
    @transaction.atomic
    def post(self, request, attempt_id):
        _require_role(request.user, MARKER_ROLES)
        attempt = get_object_or_404(Attempt.objects.select_related("institution"), pk=attempt_id,
                                    institution_id__in=institution_ids(request.user, MARKER_ROLES))
        _require_role(request.user, MARKER_ROLES, attempt.institution_id)
        result = mark_attempt(attempt.pk)
        result = Result.objects.select_related("candidate", "assessment").prefetch_related("questions__attempt_question").get(pk=result.pk)
        return Response(StaffResultSerializer(result).data)


class ResultPublishView(APIView):
    @transaction.atomic
    def post(self, request, result_id):
        _require_role(request.user, ADMIN_ROLES)
        result = get_object_or_404(Result.objects.select_related("institution"), pk=result_id,
                                   institution_id__in=institution_ids(request.user, ADMIN_ROLES))
        _require_role(request.user, ADMIN_ROLES, result.institution_id)
        result = publish_result(result.pk)
        return Response(StaffResultSerializer(Result.objects.select_related("candidate", "assessment").prefetch_related("questions__attempt_question").get(pk=result.pk)).data)


class ResultWithholdView(APIView):
    @transaction.atomic
    def post(self, request, result_id):
        _require_role(request.user, ADMIN_ROLES)
        result = get_object_or_404(Result.objects.select_related("institution"), pk=result_id,
                                   institution_id__in=institution_ids(request.user, ADMIN_ROLES))
        _require_role(request.user, ADMIN_ROLES, result.institution_id)
        result = withhold_result(result.pk)
        return Response(StaffResultSerializer(Result.objects.select_related("candidate", "assessment").prefetch_related("questions__attempt_question").get(pk=result.pk)).data)
