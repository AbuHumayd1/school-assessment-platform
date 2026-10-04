from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .models import Question, Topic
from .import_service import import_questions_csv
from .permissions import (
    CanAccessQuestionBank, CanApproveQuestion, CanDeleteQuestion, CanEditQuestion,
    CanManageQuestionBank, CanManageTopics, CanReviewQuestion, CanSubmitQuestion,
)
from .serializers import QuestionSerializer, TopicSerializer
from .tenancy import institution_ids_for_question_bank, write_institution_for_request


class TenantQuestionBankMixin:
    def get_write_institution(self):
        if not hasattr(self, "_write_institution"):
            self._write_institution = write_institution_for_request(self.request)
        return self._write_institution

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == "create":
            context["institution"] = self.get_write_institution()
        elif self.action in {"update", "partial_update"}:
            context["institution"] = self.get_object().institution
        return context


class TopicViewSet(TenantQuestionBankMixin, viewsets.ModelViewSet):
    serializer_class = TopicSerializer
    permission_classes = [CanManageTopics]

    def get_queryset(self):
        queryset = Topic.objects.filter(
            institution_id__in=institution_ids_for_question_bank(self.request.user),
            institution__is_active=True,
        ).select_related("institution", "subject", "parent")
        subject_id = self.request.query_params.get("subject")
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            if is_active.lower() not in {"true", "false", "1", "0"}:
                raise ValidationError({"is_active": "Use true or false."})
            queryset = queryset.filter(is_active=is_active.lower() in {"true", "1"})
        return queryset

    def perform_create(self, serializer):
        serializer.save(institution=self.get_write_institution())


class QuestionViewSet(TenantQuestionBankMixin, viewsets.ModelViewSet):
    serializer_class = QuestionSerializer

    def get_permissions(self):
        permission_by_action = {
            "list": CanAccessQuestionBank,
            "retrieve": CanAccessQuestionBank,
            "create": CanManageQuestionBank,
            "update": CanEditQuestion,
            "partial_update": CanEditQuestion,
            "destroy": CanDeleteQuestion,
            "submit_for_review": CanSubmitQuestion,
            "request_changes": CanReviewQuestion,
            "approve": CanApproveQuestion,
            "archive": CanApproveQuestion,
            "import_csv": CanManageQuestionBank,
        }
        permission_class = permission_by_action.get(self.action, CanAccessQuestionBank)
        return [permission_class()]

    def get_queryset(self):
        queryset = Question.objects.filter(
            institution_id__in=institution_ids_for_question_bank(self.request.user),
            institution__is_active=True,
        ).select_related("institution", "subject", "topic", "created_by", "reviewed_by").prefetch_related("options", "media")
        if self.request.headers.get('X-Institution-ID') or self.request.query_params.get('institution'):
            queryset = queryset.filter(institution=self.get_write_institution())
        for field in ("subject", "topic"):
            value = self.request.query_params.get(field)
            if value:
                try:
                    record_id = int(value)
                    if record_id < 1:
                        raise ValueError
                except (TypeError, ValueError):
                    raise ValidationError({field: "Enter a valid identifier."})
                queryset = queryset.filter(**{f"{field}_id": record_id})

        for field, choices in (
            ("question_type", Question.Type.values),
            ("difficulty", Question.Difficulty.values),
            ("status", Question.Status.values),
        ):
            value = self.request.query_params.get(field)
            if value:
                if value not in choices:
                    return queryset.none()
                queryset = queryset.filter(**{field: value})

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            normalized = is_active.strip().lower()
            if normalized not in {"true", "false", "1", "0"}:
                raise ValidationError({"is_active": "Use true or false."})
            if normalized in {"true", "1"}:
                queryset = queryset.exclude(status=Question.Status.ARCHIVED)
            else:
                queryset = queryset.filter(status=Question.Status.ARCHIVED)

        search = self.request.query_params.get("search", "").strip()
        if len(search) > 200:
            raise ValidationError({"search": "Search text must be 200 characters or fewer."})
        if search:
            queryset = queryset.filter(text__icontains=search)
        return queryset

    def perform_create(self, serializer):
        serializer.save()

    @action(
        detail=False,
        methods=["post"],
        url_path="import",
        parser_classes=[MultiPartParser, FormParser],
        permission_classes=[CanManageQuestionBank],
    )
    def import_csv(self, request, *args, **kwargs):
        institution = self.get_write_institution()
        result = import_questions_csv(
            request.FILES.get("file"), institution=institution, actor=request.user,
        )
        return Response(
            result,
            status=status.HTTP_201_CREATED if not result["errors"] else status.HTTP_400_BAD_REQUEST,
        )

    def _transition(self, question, allowed_from, to_status, set_reviewer=False):
        if question.status not in allowed_from:
            raise ValidationError({"status": f"Cannot transition a {question.status} question to {to_status}."})
        question.status = to_status
        if set_reviewer:
            question.reviewed_by = self.request.user
        question.save(update_fields=("status", "reviewed_by", "updated_at"))
        return Response(self.get_serializer(question).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="submit-for-review")
    def submit_for_review(self, request, pk=None):
        return self._transition(self.get_object(), {Question.Status.DRAFT}, Question.Status.REVIEW)

    @action(detail=True, methods=["post"], url_path="request-changes", permission_classes=[CanReviewQuestion])
    def request_changes(self, request, pk=None):
        return self._transition(self.get_object(), {Question.Status.REVIEW}, Question.Status.DRAFT, set_reviewer=True)

    @action(detail=True, methods=["post"], permission_classes=[CanApproveQuestion])
    def approve(self, request, pk=None):
        return self._transition(self.get_object(), {Question.Status.REVIEW}, Question.Status.APPROVED, set_reviewer=True)

    @action(detail=True, methods=["post"], permission_classes=[CanApproveQuestion])
    def archive(self, request, pk=None):
        return self._transition(self.get_object(), {Question.Status.APPROVED}, Question.Status.ARCHIVED, set_reviewer=True)
