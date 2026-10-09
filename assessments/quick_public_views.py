from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from attempts.models import Attempt
from attempts.serializers import CandidateAttemptSerializer, StartAttemptResponseSerializer
from attempts.services import (
    AVAILABILITY_MESSAGES, _validate_assessment_for_candidate, assessment_unavailability_reason,
    expire_attempt, start_access_attempt,
)
from attempts.views import (
    CandidateAttemptAccessMixin, AttemptAnswerView, AttemptIntegrityView,
    AttemptQuestionDetailView, AttemptQuestionListView, AttemptReviewFlagView, AttemptSubmitView,
)
from .quick_authentication import QuickExamAuthentication
from .quick_serializers import StrictInputSerializer
from .quick_sessions import COOKIE_NAME, COOKIE_PATH, INVALID_DETAILS, dummy_password_hash, logout_session, verify_and_create_session
from .quick_throttles import QuickSessionThrottle, QuickVerifyIdentifierThrottle, QuickVerifyIPThrottle


class VerificationSerializer(StrictInputSerializer):
    exam_code = serializers.CharField(max_length=32)
    candidate_id = serializers.CharField(max_length=64)
    pin = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


@method_decorator(csrf_protect, name="dispatch")
class QuickPublicView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get_authenticate_header(self, request):
        return "QuickExam"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store, private"
        return response


class QuickVerifyView(QuickPublicView):
    throttle_classes = (QuickVerifyIPThrottle, QuickVerifyIdentifierThrottle)

    def post(self, request):
        serializer = VerificationSerializer(data=request.data)
        if not serializer.is_valid():
            check_password("", dummy_password_hash())
            return Response({"detail": INVALID_DETAILS}, status=status.HTTP_401_UNAUTHORIZED)
        session, token = verify_and_create_session(**serializer.validated_data)
        response = Response({"verified": True})
        response.set_cookie(COOKIE_NAME, token, max_age=max(1, int((session.expires_at - timezone.now()).total_seconds())),
                            path=COOKIE_PATH, secure=settings.QUICK_EXAM_COOKIE_SECURE,
                            httponly=True, samesite=settings.QUICK_EXAM_COOKIE_SAMESITE)
        return response


class QuickLogoutView(QuickPublicView):
    def post(self, request):
        serializer = StrictInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        logout_session(request.COOKIES.get(COOKIE_NAME, ""))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, samesite=settings.QUICK_EXAM_COOKIE_SAMESITE)
        response.cookies[COOKIE_NAME]["secure"] = settings.QUICK_EXAM_COOKIE_SECURE
        response.cookies[COOKIE_NAME]["httponly"] = True
        return response


class QuickProtectedView(QuickPublicView):
    authentication_classes = (QuickExamAuthentication,)
    throttle_classes = (QuickSessionThrottle,)
    throttle_scope = "quick_exam_requests"


def session_summary(context):
    assessment, candidate = context.assessment, context.candidate
    now = timezone.now()
    attempts = Attempt.objects.filter(candidate=candidate, assessment=assessment)
    active = attempts.filter(status=Attempt.Status.IN_PROGRESS, expires_at__gt=now).first()
    used = attempts.count()
    available = False
    reason = None
    try:
        _validate_assessment_for_candidate(assessment, candidate, now, access_mode="quick")
        available = True
    except APIException as error:
        reason = assessment_unavailability_reason(error)
    state = "unavailable"
    if active:
        state = "in_progress"
        # Existing attempts retain resume-before-window/workflow semantics.
        reason = None if assessment.resume_allowed else "resume_disabled"
    elif reason in {"upcoming", "ended"}:
        state = reason
    elif available:
        state = "attempt_limit_reached" if used >= assessment.attempt_limit else "available"
        reason = "attempt_limit_reached" if used >= assessment.attempt_limit else None
    return {
        "candidate": {"candidate_id": candidate.candidate_id, "first_name": candidate.first_name, "last_name": candidate.last_name},
        "assessment": {"id": assessment.pk, "title": assessment.title, "description": assessment.description,
                       "duration_minutes": assessment.duration_minutes, "start_at": assessment.start_at,
                       "end_at": assessment.end_at, "attempt_limit": assessment.attempt_limit,
                       "question_count": assessment.assessment_questions.count(),
                       "timezone": assessment.institution.timezone},
        "availability": {"state": state, "attempts_remaining": max(assessment.attempt_limit - used, 0),
                         "reason": reason, "message": AVAILABILITY_MESSAGES.get(reason),
                         "can_start": available and not active and used < assessment.attempt_limit,
                         "can_resume": bool(active and assessment.resume_allowed),
                         "active_attempt_id": active.pk if active else None},
    }


class QuickSessionView(QuickProtectedView):
    def get(self, request):
        return Response(session_summary(request.auth))


class QuickStartView(QuickProtectedView):
    throttle_scope = "attempt_start"

    def post(self, request):
        serializer = StrictInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            attempt, created = start_access_attempt(request.auth)
        except (PermissionDenied, ValidationError, NotFound) as error:
            reason = assessment_unavailability_reason(error)
            return Response({"detail": AVAILABILITY_MESSAGES[reason], "reason": reason}, status=error.status_code)
        if attempt is None:
            return Response({"detail": AVAILABILITY_MESSAGES["attempt_limit_reached"], "reason": "attempt_limit_reached"}, status=status.HTTP_403_FORBIDDEN)
        return Response(StartAttemptResponseSerializer(attempt).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class QuickAttemptDetailView(QuickProtectedView, CandidateAttemptAccessMixin):
    @transaction.atomic
    def get(self, request, attempt_id):
        attempt = self.lock_attempt(request, attempt_id)
        expire_attempt(attempt, actor=self.actor(request))
        return Response(CandidateAttemptSerializer(attempt, context={"request": request}).data)


class QuickCurrentAttemptView(QuickAttemptDetailView):
    def get(self, request):
        attempt_id = Attempt.objects.filter(candidate=request.auth.candidate, assessment=request.auth.assessment).order_by("-attempt_number").values_list("pk", flat=True).first()
        if not attempt_id:
            raise NotFound()
        return super().get(request, attempt_id)


# The existing runner views contain the sole implementations of these operations.
class QuickAnswerView(QuickProtectedView, AttemptAnswerView):
    pass


class QuickQuestionListView(QuickProtectedView, AttemptQuestionListView):
    pass


class QuickQuestionDetailView(QuickProtectedView, AttemptQuestionDetailView):
    pass


class QuickReviewView(QuickProtectedView, AttemptReviewFlagView):
    pass


class QuickIntegrityView(QuickProtectedView, AttemptIntegrityView):
    throttle_scope = "attempt_integrity"


class QuickSubmitView(QuickProtectedView, AttemptSubmitView):
    throttle_scope = "attempt_submit"
