from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .models import Assessment, AssessmentQuestion
from .permissions import CanAccessAssessments, CanApproveAssessment, CanDeleteAssessment, CanManageAssessment, CanReviewAssessment
from .serializers import AssessmentQuestionSerializer, AssessmentSerializer
from .tenancy import assessment_institution_for_request
from .assessment_events import audit_assessment
from .owner_serializers import QuestionInspectionSerializer, PreviewQuestionSerializer, InspectionQuestionSerializer


class OwnerPagination(PageNumberPagination):
    page_size = 25


class AssessmentViewSet(viewsets.ModelViewSet):
    pagination_class = OwnerPagination

    def institution(self):
        if not hasattr(self, "_assessment_institution"):
            self._assessment_institution = assessment_institution_for_request(self.request)
        return self._assessment_institution
    serializer_class = AssessmentSerializer

    def get_permissions(self):
        classes = {
            "list": CanAccessAssessments, "retrieve": CanAccessAssessments,
            "create": CanManageAssessment, "update": CanManageAssessment,
            "partial_update": CanManageAssessment, "destroy": CanDeleteAssessment,
            "submit_review": CanManageAssessment, "request_changes": CanReviewAssessment,
            "approve": CanApproveAssessment, "schedule": CanApproveAssessment,
            "reopen": CanApproveAssessment, "archive": CanApproveAssessment,
        }
        return [classes.get(self.action, CanAccessAssessments)()]

    def get_queryset(self):
        qs = Assessment.objects.filter(
            institution=self.institution(),
        ).select_related("institution", "subject", "group", "created_by", "reviewed_by", "approved_by").prefetch_related(
            "assessment_questions__question"
        )
        from attempts.models import Attempt
        from .models import QuickExamConfiguration
        qs = qs.annotate(
            quick_access_configured=Exists(QuickExamConfiguration.objects.filter(assessment_id=OuterRef("pk"))),
            has_attempt_history=Exists(Attempt.objects.filter(assessment_id=OuterRef("pk"))),
        )
        search = self.request.query_params.get("search", "").strip()[:200]
        if search:
            qs = qs.filter(title__icontains=search)
        for field in ("assessment_type", "subject", "group", "status", "created_by"):
            value = self.request.query_params.get(field)
            if value:
                if field in {"subject", "group", "created_by"} and (not value.isdecimal() or int(value) < 1):
                    raise ValidationError({field: "Select a valid identifier."})
                qs = qs.filter(**{f"{field}_id" if field in {"subject", "group", "created_by"} else field: value})
        if self.action in {"update", "partial_update", "destroy"}:
            qs = qs.select_for_update()
        return qs

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["institution"] = self.institution()
        return context

    @transaction.atomic
    def perform_create(self, serializer):
        assessment = serializer.save()
        audit_assessment(assessment, self.request.user, "assessment_created")
        for row in assessment.assessment_questions.all():
            audit_assessment(row, self.request.user, "assessment_question_attached", question_id=row.question_id)

    @transaction.atomic
    def perform_update(self, serializer):
        replaced = "assessment_questions" in serializer.validated_data
        previous = list(serializer.instance.assessment_questions.all()) if replaced else []
        try:
            assessment = serializer.save()
        except DjangoValidationError as error:
            raise ValidationError(error.message_dict if hasattr(error, "message_dict") else error.messages)
        audit_assessment(assessment, self.request.user, "assessment_edited", fields=sorted(serializer.validated_data))
        for row in previous:
            audit_assessment(row, self.request.user, "assessment_question_removed", question_id=row.question_id)
        if replaced:
            for row in assessment.assessment_questions.all():
                audit_assessment(row, self.request.user, "assessment_question_attached", question_id=row.question_id)

    @transaction.atomic
    def perform_destroy(self, instance):
        audit_assessment(instance, self.request.user, "assessment_deleted")
        instance.delete()

    def paper(self, assessment):
        return assessment.assessment_questions.select_related("question__topic").prefetch_related("question__options").order_by("order", "id")

    @action(detail=True, methods=["get"], url_path="question-inspection")
    def question_inspection(self, request, pk=None):
        return Response(QuestionInspectionSerializer(self.paper(self.get_object()), many=True).data)

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        assessment = self.get_object()
        return Response({
            "title": assessment.title, "duration_minutes": assessment.duration_minutes,
            "randomize_questions": assessment.randomize_questions,
            "randomize_options": assessment.randomize_options,
            "questions": PreviewQuestionSerializer(self.paper(assessment), many=True).data,
        })

    @action(detail=False, methods=["get"], url_path="form-options")
    def form_options(self, request):
        from subjects.models import Subject
        from groups.models import Group
        institution = self.institution()
        choices = {}
        for name, enum in (("assessment_type", Assessment.Type), ("security_level", Assessment.SecurityLevel),
                           ("result_visibility", Assessment.ResultVisibility), ("result_release_mode", Assessment.ResultReleaseMode)):
            choices[name] = [{"value": value, "label": label} for value, label in enum.choices]
        choices["candidate_access"] = [{"value": value, "label": label} for value, label in Assessment.CandidateAccess.choices if value != "specific_candidates"]
        return Response({"subjects": list(Subject.objects.filter(institution=institution).order_by("name", "pk").values("id", "name")),
                         "groups": list(Group.objects.filter(institution=institution, is_active=True).order_by("name", "pk").values("id", "name")), "choices": choices})

    @action(detail=False, methods=["get"], url_path="question-options")
    def question_options(self, request):
        from subjects.models import Subject
        from questions.models import Question
        subject = request.query_params.get("subject", "")
        if not subject.isdecimal() or int(subject) < 1:
            raise ValidationError({"subject": "Select a valid subject."})
        subject = get_object_or_404(Subject, pk=subject, institution=self.institution())
        questions = Question.objects.filter(institution=self.institution(), subject=subject, status=Question.Status.APPROVED).select_related("topic").prefetch_related("options").order_by("pk")
        search = request.query_params.get("search", "").strip()[:200]
        if search:
            questions = questions.filter(text__icontains=search)
        return self.get_paginated_response(InspectionQuestionSerializer(self.paginate_queryset(questions), many=True).data)

    @action(detail=True, methods=["get"])
    def eligibility(self, request, pk=None):
        from candidates.models import Candidate
        from attempts.tenancy import active_local_date, assessment_window_state
        from django.utils import timezone
        assessment = self.get_object()
        candidates = Candidate.objects.filter(institution=assessment.institution)
        mode = assessment.candidate_access
        if mode == "assigned_group" and assessment.group_id and assessment.group.is_active:
            today = active_local_date(assessment.institution)
            candidates = candidates.filter(
                Q(group_memberships__start_date__isnull=True) | Q(group_memberships__start_date__lte=today),
                Q(group_memberships__end_date__isnull=True) | Q(group_memberships__end_date__gte=today),
                status=Candidate.Status.ACTIVE, group_memberships__group=assessment.group,
                group_memberships__is_active=True,
            )
        elif mode == "access_code":
            candidates = candidates.filter(quick_credentials__configuration__assessment=assessment)
        else:
            candidates = candidates.none()
        rows = self.paginate_queryset(candidates.distinct().order_by("first_name", "last_name", "pk"))
        data = [{"id": row.pk, "candidate_id": row.candidate_id, "name": f"{row.first_name} {row.last_name}".strip(), "status": row.status} for row in rows]
        response = self.get_paginated_response(data)
        response.data.update(mode=mode, delivery_supported=mode != "specific_candidates",
                             workflow_status=assessment.status, window=assessment_window_state(assessment, timezone.now()))
        return response

    @transaction.atomic
    def _transition(self, assessment, allowed, target, *, reviewer=False, approver=False, schedule=False):
        assessment = Assessment.objects.select_for_update().get(pk=assessment.pk, institution=self.institution())
        if assessment.status not in allowed:
            raise ValidationError({"status": f"Cannot transition {assessment.status} to {target}."})
        if target == Assessment.Status.DRAFT:
            from attempts.models import Attempt
            if Attempt.objects.filter(assessment=assessment).exists():
                raise ValidationError({"status": "Assessments with attempt history cannot be reopened."})
        if schedule or target in {Assessment.Status.REVIEW, Assessment.Status.APPROVED}:
            try:
                assessment.validate_configuration(require_questions=True, require_schedule=schedule)
            except DjangoValidationError as exc:
                raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        previous_status = assessment.status
        assessment.status = target
        fields = ["status", "updated_at"]
        if reviewer:
            assessment.reviewed_by = self.request.user
            fields.append("reviewed_by")
        if approver:
            assessment.approved_by = self.request.user
            fields.append("approved_by")
        assessment.save(update_fields=fields)
        event_type = {"approved": "assessment_approved", "scheduled": "assessment_scheduled"}.get(target)
        event_type = event_type or {"submit_review": "assessment_review_submitted", "request_changes": "assessment_changes_requested",
                                    "reopen": "assessment_reopened", "archive": "assessment_archived"}[self.action]
        audit_assessment(assessment, self.request.user, event_type, previous_status=previous_status, status=target)
        return Response(self.get_serializer(assessment).data)

    @action(detail=True, methods=["post"], url_path="submit-review")
    def submit_review(self, request, pk=None):
        return self._transition(self.get_object(), {Assessment.Status.DRAFT}, Assessment.Status.REVIEW)

    @action(detail=True, methods=["post"], url_path="request-changes", permission_classes=[CanReviewAssessment])
    def request_changes(self, request, pk=None):
        return self._transition(self.get_object(), {Assessment.Status.REVIEW}, Assessment.Status.DRAFT, reviewer=True)

    @action(detail=True, methods=["post"], permission_classes=[CanApproveAssessment])
    def approve(self, request, pk=None):
        assessment = self.get_object()
        return self._transition(assessment, {Assessment.Status.REVIEW}, Assessment.Status.APPROVED, reviewer=True, approver=True)

    @action(detail=True, methods=["post"], permission_classes=[CanApproveAssessment])
    def schedule(self, request, pk=None):
        return self._transition(self.get_object(), {Assessment.Status.APPROVED}, Assessment.Status.SCHEDULED, schedule=True)

    @action(detail=True, methods=["post"], permission_classes=[CanApproveAssessment])
    def reopen(self, request, pk=None):
        return self._transition(self.get_object(), {Assessment.Status.APPROVED}, Assessment.Status.DRAFT)

    @action(detail=True, methods=["post"], permission_classes=[CanApproveAssessment])
    def archive(self, request, pk=None):
        return self._transition(self.get_object(), {Assessment.Status.APPROVED, Assessment.Status.SCHEDULED}, Assessment.Status.ARCHIVED)


class AssessmentQuestionListCreateView(viewsets.ViewSet):
    permission_classes = [CanAccessAssessments]
    """Dedicated staff endpoint for selecting questions into one assessment."""
    def _assessment(self, request, pk):
        try:
            assessments = Assessment.objects.all()
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                assessments = assessments.select_for_update()
            return assessments.get(pk=pk, institution=assessment_institution_for_request(request))
        except Assessment.DoesNotExist:
            raise NotFound()

    def list(self, request, assessment_pk=None):
        assessment = self._assessment(request, assessment_pk)
        if not CanAccessAssessments().has_object_permission(request, self, assessment):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        return Response(AssessmentQuestionSerializer(assessment.assessment_questions.select_related("question"), many=True, context={"assessment": assessment}).data)

    @transaction.atomic
    def create(self, request, assessment_pk=None):
        assessment = self._assessment(request, assessment_pk)
        if assessment.status != Assessment.Status.DRAFT or not CanManageAssessment().has_object_permission(request, self, assessment):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        serializer = AssessmentQuestionSerializer(data=request.data, context={"assessment": assessment})
        serializer.is_valid(raise_exception=True)
        row = serializer.save(assessment=assessment)
        audit_assessment(row, request.user, "assessment_question_attached", question_id=row.question_id)
        try:
            assessment.validate_configuration(require_questions=False)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return Response(AssessmentQuestionSerializer(row, context={"assessment": assessment}).data, status=status.HTTP_201_CREATED)


class AssessmentQuestionDetailView(viewsets.ViewSet):
    permission_classes = [CanAccessAssessments]
    def _row(self, request, assessment_pk, pk, write=False):
        try:
            assessments = Assessment.objects.select_for_update() if write else Assessment.objects.all()
            assessment = assessments.get(pk=assessment_pk, institution=assessment_institution_for_request(request))
        except Assessment.DoesNotExist:
            raise NotFound()
        if write:
            allowed = assessment.status == Assessment.Status.DRAFT and CanManageAssessment().has_object_permission(request, self, assessment)
        else:
            allowed = CanAccessAssessments().has_object_permission(request, self, assessment)
        if not allowed:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        try:
            return assessment.assessment_questions.select_related("question").get(pk=pk)
        except AssessmentQuestion.DoesNotExist:
            raise NotFound()

    def retrieve(self, request, assessment_pk=None, pk=None):
        row = self._row(request, assessment_pk, pk)
        return Response(AssessmentQuestionSerializer(row, context={"assessment": row.assessment}).data)

    @transaction.atomic
    def update(self, request, assessment_pk=None, pk=None):
        row = self._row(request, assessment_pk, pk, write=True)
        serializer = AssessmentQuestionSerializer(row, data=request.data, partial=request.method == "PATCH", context={"assessment": row.assessment})
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        audit_assessment(updated, request.user, "assessment_question_edited", fields=sorted(serializer.validated_data))
        try:
            row.assessment.validate_configuration(require_questions=False)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return Response(AssessmentQuestionSerializer(updated, context={"assessment": row.assessment}).data)

    def partial_update(self, request, assessment_pk=None, pk=None):
        return self.update(request, assessment_pk, pk)

    @transaction.atomic
    def destroy(self, request, assessment_pk=None, pk=None):
        row = self._row(request, assessment_pk, pk, write=True)
        audit_assessment(row, request.user, "assessment_question_removed", question_id=row.question_id)
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
