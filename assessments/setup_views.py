from institutions.workspace_access import WorkspaceAccessMixin
"""Draft setup operations, authorized and locked in the selected workspace."""
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers

from candidates.models import Candidate
from .models import Assessment, AssessmentCandidate
from .permissions import CanAccessAssessments, CanManageAssessment
from .tenancy import assessment_institution_for_request
from .views import OwnerPagination
from .serializers import AssessmentQuestionSerializer
from .owner_serializers import QuestionInspectionSerializer
from .assessment_events import audit_assessment
from .eligibility import eligible_subject_questions, question_document_order, institution_candidates


class SetupView(WorkspaceAccessMixin, APIView):
    workspace_module = "preparation"
    permission_classes = [CanAccessAssessments]

    def assessment(self, request, pk, write=False):
        qs = Assessment.objects.select_for_update() if write else Assessment.objects.all()
        exam = get_object_or_404(qs, pk=pk, institution=assessment_institution_for_request(request))
        permission = CanManageAssessment() if write else CanAccessAssessments()
        if not permission.has_object_permission(request, self, exam):
            raise PermissionDenied()
        if write and exam.attempts.exists():
            raise ValidationError({"detail": "Exam setup is frozen after participation starts."})
        return exam


class AssignmentInput(serializers.Serializer):
    candidates = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=1000, required=False)
    select_all = serializers.BooleanField(default=False)
    search = serializers.CharField(max_length=200, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=[Candidate.Status.ACTIVE], default=Candidate.Status.ACTIVE)
    expected_count = serializers.IntegerField(min_value=0, max_value=1000, required=False)

    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise ValidationError({"candidates": "Use only candidate selection fields."})
        if attrs["select_all"]:
            if "candidates" in attrs:
                raise ValidationError({"candidates": "Choose either Select all or explicit candidates."})
        elif not attrs.get("candidates") or attrs["search"] or "expected_count" in attrs:
            raise ValidationError({"candidates": "Select candidates or use Select all."})
        return attrs


class AssessmentCandidatesView(SetupView):
    def get(self, request, assessment_pk):
        exam = self.assessment(request, assessment_pk)
        search = request.query_params.get("search", "").strip()[:200]
        candidate_status = request.query_params.get("status", Candidate.Status.ACTIVE)
        if candidate_status != Candidate.Status.ACTIVE:
            raise ValidationError({"status": "Only active candidates can be assigned."})
        qs = institution_candidates(exam.institution, search, candidate_status)
        pagination = OwnerPagination()
        rows = pagination.paginate_queryset(qs.order_by("first_name", "last_name", "pk"), request)
        assigned = set(exam.candidate_assignments.values_list("candidate_id", flat=True))
        response = pagination.get_paginated_response([{
            "id": c.pk, "candidate_id": c.candidate_id, "name": f"{c.first_name} {c.last_name}".strip(),
            "email": c.email, "assigned": c.pk in assigned,
        } for c in rows])
        response.data["available_count"] = qs.exclude(pk__in=assigned).count()
        return response

    @transaction.atomic
    def post(self, request, assessment_pk):
        exam = self.assessment(request, assessment_pk)
        if not CanManageAssessment().has_object_permission(request, self, exam):
            raise PermissionDenied()
        if exam.candidate_access not in {Assessment.CandidateAccess.SPECIFIC_CANDIDATES, Assessment.CandidateAccess.ACCESS_CODE}:
            raise ValidationError({"detail": "Choose Specific Candidates before adding candidates."})
        serializer = AssignmentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        selection = serializer.validated_data
        assigned = set(exam.candidate_assignments.values_list("candidate_id", flat=True))
        eligible = institution_candidates(exam.institution, selection["search"], selection["status"])
        if selection["select_all"]:
            candidates = list(eligible.exclude(pk__in=assigned).select_for_update().order_by("pk")[:1001])
            if len(candidates) > 1000:
                raise ValidationError({"candidates": "Assign at most 1000 candidates in one operation. Narrow the search."})
        else:
            ids = set(selection["candidates"])
            candidates = list(eligible.filter(pk__in=ids).select_for_update().order_by("pk"))
            if len(candidates) != len(ids):
                raise ValidationError({"candidates": "Select active candidates from the current workspace."})
        # Match Quick access: lock candidates before the assessment, then recheck the selection.
        exam = self.assessment(request, assessment_pk, True)
        if exam.candidate_access not in {Assessment.CandidateAccess.SPECIFIC_CANDIDATES, Assessment.CandidateAccess.ACCESS_CODE}:
            raise ValidationError({"detail": "Choose Specific Candidates before adding candidates."})
        if selection["select_all"]:
            assigned = set(exam.candidate_assignments.values_list("candidate_id", flat=True))
            pending_ids = set(eligible.exclude(pk__in=assigned).values_list("pk", flat=True))
            candidates = [candidate for candidate in candidates if candidate.pk in pending_ids]
            if pending_ids != {candidate.pk for candidate in candidates} or ("expected_count" in selection and selection["expected_count"] != len(candidates)):
                raise ValidationError({"candidates": "Available candidates changed. Refresh the picker and select again."})
        added = 0
        for candidate in sorted(candidates, key=lambda c: (c.candidate_id, c.pk)):
            row, created = AssessmentCandidate.objects.get_or_create(assessment=exam, candidate=candidate, defaults={"assigned_by": request.user})
            if created:
                added += 1
                audit_assessment(row, request.user, "assessment_candidate_assigned", candidate_id=candidate.pk)
        return Response({"assigned": len(candidates), "added_count": added, "assigned_count": exam.candidate_assignments.count()})


class AssessmentCandidateRemoveView(SetupView):
    @transaction.atomic
    def delete(self, request, assessment_pk, candidate_pk):
        exam = self.assessment(request, assessment_pk)
        # Existing draft permissions apply; historical participation is checked per candidate below.
        exam = Assessment.objects.select_for_update().get(pk=exam.pk)
        if not CanManageAssessment().has_object_permission(request, self, exam):
            raise PermissionDenied()
        row = get_object_or_404(AssessmentCandidate, assessment=exam, candidate_id=candidate_pk)
        try:
            row.delete()
        except ModelValidationError as error:
            raise ValidationError({"detail": error.messages})
        audit_assessment(exam, request.user, "assessment_candidate_removed", candidate_id=candidate_pk)
        return Response(status=204)


class QuestionBatchInput(serializers.Serializer):
    questions = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=1000, required=False)
    select_all = serializers.BooleanField(default=False)
    search = serializers.CharField(max_length=200, allow_blank=True, default="")
    expected_count = serializers.IntegerField(min_value=0, max_value=1000, required=False)

    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise ValidationError({"questions": "Use only question selection fields."})
        if attrs["select_all"]:
            if "questions" in attrs:
                raise ValidationError({"questions": "Choose either Select all or explicit questions."})
        elif not attrs.get("questions") or attrs["search"] or "expected_count" in attrs:
            raise ValidationError({"questions": "Select questions or use Select all with a search."})
        return attrs


class AssessmentQuestionBatchView(SetupView):
    @transaction.atomic
    def post(self, request, assessment_pk):
        exam = self.assessment(request, assessment_pk, True)
        serializer = QuestionBatchInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        attached = set(exam.assessment_questions.values_list("question_id", flat=True))
        selection = serializer.validated_data
        eligible = eligible_subject_questions(exam.institution, exam.subject, selection["search"])
        if selection["select_all"]:
            questions = list(eligible.exclude(pk__in=attached).order_by("pk")[:1001])
            if len(questions) > 1000:
                raise ValidationError({"questions": "Add at most 1000 questions in one operation. Narrow the search."})
            if "expected_count" in selection and selection["expected_count"] != len(questions):
                raise ValidationError({"questions": "Available questions changed. Refresh the picker and select again."})
            questions.sort(key=question_document_order)
        else:
            ids = list(dict.fromkeys(selection["questions"]))
            by_id = {q.pk: q for q in eligible.filter(pk__in=ids)}
            if len(by_id) != len(ids):
                raise ValidationError({"questions": "Select approved questions from the exam subject and workspace."})
            questions = [by_id[pk] for pk in ids if pk not in attached]
        order = max(exam.assessment_questions.values_list("order", flat=True), default=0)
        for question in questions:
            order += 1
            question_id = question.pk
            item = AssessmentQuestionSerializer(data={"question": question_id, "order": order, "marks": str(question.marks)}, context={"assessment": exam})
            item.is_valid(raise_exception=True)
            row = item.save(assessment=exam)
            audit_assessment(row, request.user, "assessment_question_attached", question_id=question_id)
        try:
            exam.validate_configuration()
        except ModelValidationError as error:
            raise ValidationError(error.message_dict)
        return Response({"question_count": exam.assessment_questions.count(), "added_count": len(questions), "total_marks": str(exam.total_marks)})


class QuestionRemovalInput(serializers.Serializer):
    attachments = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=1000, required=False)
    select_all = serializers.BooleanField(default=False)
    search = serializers.CharField(max_length=200, allow_blank=True, default="")
    expected_count = serializers.IntegerField(min_value=0, max_value=1000, required=False)

    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise ValidationError({"questions": "Use only attached-question selection fields."})
        if attrs["select_all"]:
            if "attachments" in attrs or "expected_count" not in attrs:
                raise ValidationError({"questions": "Select all requires the matching count and no explicit attachments."})
        elif not attrs.get("attachments") or attrs["search"] or "expected_count" in attrs:
            raise ValidationError({"questions": "Select attachments or use Select all with the matching count."})
        return attrs


class AssessmentQuestionRemoveView(SetupView):
    def matching(self, exam, search):
        rows = exam.assessment_questions.filter(question__institution_id=exam.institution_id)
        if search:
            rows = rows.filter(question__text__icontains=search)
        return rows.order_by("order", "pk")

    def get(self, request, assessment_pk):
        exam = self.assessment(request, assessment_pk)
        search = request.query_params.get("search", "").strip()[:200]
        rows = self.matching(exam, search).select_related("question__topic").prefetch_related("question__options", "question__media")
        pagination = OwnerPagination()
        page = pagination.paginate_queryset(rows, request, view=self)
        return pagination.get_paginated_response(QuestionInspectionSerializer(page, many=True).data)

    @transaction.atomic
    def post(self, request, assessment_pk):
        # Serialize with question attachment/editing and candidate attempt start.
        exam = self.assessment(request, assessment_pk, True)
        if exam.results.exists():
            raise ValidationError({"detail": "Questions cannot be removed from an exam with result history."})
        serializer = QuestionRemovalInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        selection = serializer.validated_data
        matching = self.matching(exam, selection["search"])
        if selection["select_all"]:
            rows = list(matching.select_for_update()[:1001])
            if len(rows) > 1000:
                raise ValidationError({"questions": "Remove at most 1000 questions in one operation. Narrow the search."})
            if selection["expected_count"] != len(rows):
                raise ValidationError({"questions": "Attached questions changed. Refresh the list and select again."})
        else:
            ids = set(selection["attachments"])
            rows = list(matching.filter(pk__in=ids).select_for_update())
            if len(rows) != len(ids):
                raise ValidationError({"questions": "Select questions attached to this exam in the current workspace."})
        for row in rows:
            question_id = row.question_id
            # Keep the model's participation protection as well as the exam lock.
            try:
                row.delete()
            except ModelValidationError as error:
                raise ValidationError({"questions": error.messages})
            audit_assessment(exam, request.user, "assessment_question_removed", question_id=question_id)
        return Response({"removed_count": len(rows), "question_count": exam.assessment_questions.count(), "total_marks": str(exam.total_marks)})
