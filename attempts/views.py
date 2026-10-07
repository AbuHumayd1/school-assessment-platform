from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from assessments.models import Assessment
from institutions.models import Institution
from questions.models import Question
from tenants.models import InstitutionMembership
from .models import Answer, AnswerSelection, Attempt, AttemptQuestion, AttemptQuestionOption
from .permissions import IsCandidateUser
from .serializers import (
    AnswerWriteSerializer, CandidateAttemptSerializer, CandidateExamQuestionSerializer,
    CandidateNavigationSerializer, ReviewFlagSerializer, StaffAttemptSerializer,
    IntegrityEventSerializer, StartAttemptResponseSerializer, StartAttemptSerializer,
)
from .integrity import ClosedAttemptIntegrityEvent, integrity_state, record_integrity_signal
from .services import (
    AttemptConflict, CompletionReason, expire_attempt, finalize_attempt,
    lock_candidate_attempt, lock_access_attempt, start_attempt,
)
from .tenancy import candidates_for_user, is_attempt_staff
from .access import ExamAccessContext


def _linked_assessment_institutions(user):
    if user.is_superuser or user.institution_memberships.filter(is_active=True, role="platform_admin").exists():
        return Institution.objects.filter(is_active=True).values_list("id", flat=True)
    return InstitutionMembership.objects.filter(
        user=user, is_active=True, institution__is_active=True,
        role__in={"institution_admin", "examiner"},
    ).values_list("institution_id", flat=True)


class AttemptStartView(APIView):
    permission_classes = (IsCandidateUser,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "attempt_start"

    def post(self, request):
        serializer = StartAttemptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        institution_header = request.headers.get("X-Institution-ID")
        if institution_header:
            try:
                institution_header = int(institution_header)
            except (TypeError, ValueError):
                raise ValidationError({"institution": "Select a valid institution."})
        attempt, created = start_attempt(
            request.user, serializer.validated_data["assessment"], institution_id=institution_header,
        )
        if attempt is None:
            return Response({"detail": "The assessment attempt limit has been reached."}, status=status.HTTP_403_FORBIDDEN)
        return Response(
            StartAttemptResponseSerializer(attempt).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class AttemptListView(APIView):
    permission_classes = (IsCandidateUser,)

    def get(self, request):
        owned = Q(candidate__user=request.user, assessment__candidate_access__in=(Assessment.CandidateAccess.ASSIGNED_GROUP, Assessment.CandidateAccess.SPECIFIC_CANDIDATES), assessment__quick_configuration__isnull=True)
        staff_ids = _linked_assessment_institutions(request.user)
        queryset = Attempt.objects.filter(
            owned | Q(institution_id__in=staff_ids), institution__is_active=True,
        ).select_related("assessment", "candidate", "institution").distinct()
        attempt_status = request.query_params.get("status")
        if attempt_status:
            queryset = queryset.filter(status=attempt_status)
        data = []
        now = timezone.now()
        for attempt in queryset:
            if expire_attempt(attempt, now, actor=request.user):
                attempt.refresh_from_db()
            serializer_class = CandidateAttemptSerializer if attempt.candidate.user_id == request.user.pk and not attempt.assessment.uses_quick_delivery else StaffAttemptSerializer
            data.append(serializer_class(attempt, context={"request": request}).data)
        return Response(data)


class AttemptDetailView(APIView):
    permission_classes = (IsCandidateUser,)

    @transaction.atomic
    def get(self, request, attempt_id):
        try:
            attempt = Attempt.objects.select_for_update().select_related("assessment", "candidate", "institution").get(
                Q(candidate__user=request.user, assessment__candidate_access__in=(Assessment.CandidateAccess.ASSIGNED_GROUP, Assessment.CandidateAccess.SPECIFIC_CANDIDATES), assessment__quick_configuration__isnull=True) | Q(institution_id__in=_linked_assessment_institutions(request.user)),
                pk=attempt_id, institution__is_active=True,
            )
        except Attempt.DoesNotExist:
            raise NotFound()
        expire_attempt(attempt, actor=request.user)
        if attempt.candidate.user_id == request.user.pk and not attempt.assessment.uses_quick_delivery:
            return Response(CandidateAttemptSerializer(attempt, context={"request": request}).data)
        return Response(StaffAttemptSerializer(attempt).data)


class CandidateAttemptAccessMixin:
    def access_context(self, request):
        return request.auth if isinstance(request.auth, ExamAccessContext) else None

    def actor(self, request):
        context = self.access_context(request)
        return context.user if context else request.user

    def lock_attempt(self, request, attempt_id):
        context = self.access_context(request)
        return lock_access_attempt(context, attempt_id) if context else lock_candidate_attempt(request.user, attempt_id)


class AttemptSubmitView(CandidateAttemptAccessMixin, APIView):
    permission_classes = (IsCandidateUser,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "attempt_submit"

    @transaction.atomic
    def post(self, request, attempt_id):
        attempt = self.lock_attempt(request, attempt_id)
        attempt, newly_finalized = finalize_attempt(
            attempt, reason=CompletionReason.MANUAL, actor=self.actor(request),
        )
        if attempt.status == Attempt.Status.EXPIRED:
            return Response({"detail": "Attempt has expired."}, status=status.HTTP_409_CONFLICT)
        return Response({
            "id": attempt.pk, "status": attempt.status, "submitted_at": attempt.submitted_at,
            "immediate_score": CandidateAttemptSerializer(attempt, context={"request": request}).data["immediate_score"],
            "detail": "Attempt submitted." if newly_finalized else "Attempt was already submitted.",
        })


class AttemptIntegrityView(CandidateAttemptAccessMixin, APIView):
    permission_classes = (IsCandidateUser,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "attempt_integrity"

    @transaction.atomic
    def get(self, request, attempt_id):
        attempt = self.lock_attempt(request, attempt_id)
        expire_attempt(attempt, actor=self.actor(request))
        attempt.refresh_from_db(fields=("status", "submitted_at", "updated_at"))
        return Response(integrity_state(attempt))

    @transaction.atomic
    def post(self, request, attempt_id):
        serializer = IntegrityEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = record_integrity_signal(self.access_context(request) or request.user, attempt_id, serializer.validated_data["signal"])
        except ClosedAttemptIntegrityEvent as error:
            return Response({"detail": error.detail}, status=status.HTTP_409_CONFLICT)
        if result.get("event_rejected"):
            return Response({"detail": "The attempt has expired."}, status=status.HTTP_409_CONFLICT)
        return Response(result)


class AttemptQuestionListView(CandidateAttemptAccessMixin, APIView):
    permission_classes = (IsCandidateUser,)

    @transaction.atomic
    def get(self, request, attempt_id):
        attempt = self.lock_attempt(request, attempt_id)
        expire_attempt(attempt, actor=self.actor(request))
        queryset = attempt.attempt_questions.select_related("question").prefetch_related("ordered_options__option").order_by("order")
        return Response(CandidateNavigationSerializer(queryset, many=True).data)


class AttemptQuestionDetailView(CandidateAttemptAccessMixin, APIView):
    permission_classes = (IsCandidateUser,)

    @transaction.atomic
    def get(self, request, attempt_id, question_id):
        attempt = self.lock_attempt(request, attempt_id)
        expire_attempt(attempt, actor=self.actor(request))
        row = get_object_or_404(
            AttemptQuestion.objects.select_related("question", "attempt__assessment").prefetch_related("ordered_options__option"),
            attempt=attempt, question_id=question_id,
        )
        return Response(CandidateExamQuestionSerializer(row).data)


class AttemptAnswerView(CandidateAttemptAccessMixin, APIView):
    permission_classes = (IsCandidateUser,)

    @transaction.atomic
    def put(self, request, attempt_id, question_id):
        return self._save(request, attempt_id, question_id)

    @transaction.atomic
    def patch(self, request, attempt_id, question_id):
        return self._save(request, attempt_id, question_id)

    def _save(self, request, attempt_id, question_id):
        attempt = self.lock_attempt(request, attempt_id)
        if expire_attempt(attempt, actor=self.actor(request)):
            return Response({"detail": "Attempt has expired; answers are locked."}, status=status.HTTP_409_CONFLICT)
        if attempt.status != Attempt.Status.IN_PROGRESS:
            raise AttemptConflict("Answers can only be changed during an in-progress attempt.")
        attempt_question = get_object_or_404(AttemptQuestion, attempt=attempt, question_id=question_id)
        serializer = AnswerWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        option_ids = serializer.validated_data["selected_options"]
        question = attempt_question.question
        if question.question_type in {Question.Type.MULTIPLE_CHOICE, Question.Type.TRUE_FALSE} and len(option_ids) > 1:
            raise ValidationError({"selected_options": "This question accepts only one selected option."})
        available = set(AttemptQuestionOption.objects.filter(
            attempt_question=attempt_question, option_id__in=option_ids, option__question_id=question_id,
        ).values_list("option_id", flat=True))
        if available != set(option_ids):
            raise ValidationError({"selected_options": "Every selected option must belong to this question and attempt."})
        now = timezone.now()
        answer = Answer.objects.filter(attempt=attempt, question_id=question_id).first()
        if not option_ids:
            if answer:
                answer.delete()
        else:
            if answer is None:
                answer = Answer.objects.create(attempt=attempt, question_id=question_id, answered_at=now)
            else:
                answer.answered_at = now
                answer.save(update_fields=("answered_at", "updated_at"))
            answer.selections.all().delete()
            AnswerSelection.objects.bulk_create([
                AnswerSelection(answer=answer, option_id=option_id) for option_id in option_ids
            ])
        attempt.last_activity_at = now
        attempt.save(update_fields=("last_activity_at", "updated_at"))
        return Response({"question": question_id, "selected_options": option_ids, "answered": bool(option_ids)})


class AttemptReviewFlagView(CandidateAttemptAccessMixin, APIView):
    permission_classes = (IsCandidateUser,)

    @transaction.atomic
    def patch(self, request, attempt_id, question_id):
        attempt = self.lock_attempt(request, attempt_id)
        if expire_attempt(attempt, actor=self.actor(request)):
            return Response({"detail": "Attempt has expired; review state is locked."}, status=status.HTTP_409_CONFLICT)
        if attempt.status != Attempt.Status.IN_PROGRESS:
            raise AttemptConflict("Review state can only change during an in-progress attempt.")
        serializer = ReviewFlagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempt_question = get_object_or_404(AttemptQuestion, attempt=attempt, question_id=question_id)
        attempt_question.marked_for_review = serializer.validated_data["marked_for_review"]
        attempt_question.save(update_fields=("marked_for_review", "updated_at"))
        now = timezone.now()
        attempt.last_activity_at = now
        attempt.save(update_fields=("last_activity_at", "updated_at"))
        return Response({"question": question_id, "marked_for_review": attempt_question.marked_for_review})
