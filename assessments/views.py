from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .models import Assessment, AssessmentQuestion
from .permissions import CanAccessAssessments, CanApproveAssessment, CanDeleteAssessment, CanManageAssessment, CanReviewAssessment
from .serializers import AssessmentQuestionSerializer, AssessmentSerializer
from .tenancy import assessment_institution_for_request, assessment_institution_ids


class AssessmentViewSet(viewsets.ModelViewSet):
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
            institution_id__in=assessment_institution_ids(self.request.user), institution__is_active=True,
        ).select_related("institution", "subject", "group", "created_by", "reviewed_by", "approved_by").prefetch_related(
            "assessment_questions__question"
        )
        for field in ("assessment_type", "subject", "group", "status", "created_by"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{f"{field}_id" if field in {"subject", "group", "created_by"} else field: value})
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == "create":
            if not hasattr(self, "_assessment_institution"):
                self._assessment_institution = assessment_institution_for_request(self.request)
            context["institution"] = self._assessment_institution
        return context

    def perform_create(self, serializer):
        if not hasattr(self, "_assessment_institution"):
            self._assessment_institution = assessment_institution_for_request(self.request)
        serializer.save()

    @transaction.atomic
    def _transition(self, assessment, allowed, target, *, reviewer=False, approver=False, schedule=False):
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
        assessment.status = target
        fields = ["status", "updated_at"]
        if reviewer:
            assessment.reviewed_by = self.request.user
            fields.append("reviewed_by")
        if approver:
            assessment.approved_by = self.request.user
            fields.append("approved_by")
        assessment.save(update_fields=fields)
        from audit.models import AuditEvent
        from audit.services import record_event
        event_type = {
            Assessment.Status.APPROVED: AuditEvent.Type.ASSESSMENT_APPROVED,
            Assessment.Status.SCHEDULED: AuditEvent.Type.ASSESSMENT_SCHEDULED,
        }.get(target)
        if event_type:
            record_event(institution=assessment.institution, actor=self.request.user, event_type=event_type,
                         resource=assessment, metadata={"status": target})
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
    """Dedicated staff endpoint for selecting questions into one assessment."""
    def _assessment(self, request, pk):
        try:
            return Assessment.objects.get(pk=pk, institution_id__in=assessment_institution_ids(request.user), institution__is_active=True)
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
        try:
            assessment.validate_configuration(require_questions=False)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return Response(AssessmentQuestionSerializer(row, context={"assessment": assessment}).data, status=status.HTTP_201_CREATED)


class AssessmentQuestionDetailView(viewsets.ViewSet):
    def _row(self, request, assessment_pk, pk, write=False):
        try:
            assessment = Assessment.objects.get(pk=assessment_pk, institution_id__in=assessment_institution_ids(request.user), institution__is_active=True)
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
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
