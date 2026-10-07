from django.db import transaction
from django.utils import timezone
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle

from institutions.permissions import is_platform_administrator
from institutions.workspace_access import require_result_release, can_release_results
from assessments.models import Assessment
from assessments.tenancy import assessment_institution_for_request
from .models import Result
from .reporting import build_assessment_report, attempt_queryset, submission_detail, releasable_results
from .services import publish_result
from .views import _require_role
from .permissions import ADMIN_ROLES


class OwnerReportView(APIView):
    """Explicit selected-workspace guard before every collection/detail/export."""
    def assessment(self, request, assessment_pk):
        institution = assessment_institution_for_request(request)
        return get_object_or_404(Assessment.objects.select_related("institution", "group"),
                                 pk=assessment_pk, institution=institution)

    def get(self, request, assessment_pk, kind="summary", attempt_pk=None, export_format=None):
        assessment = self.assessment(request, assessment_pk)
        if kind == "detail":
            attempt = get_object_or_404(attempt_queryset(assessment), pk=attempt_pk,
                                       status__in=("submitted", "expired"))
            data = submission_detail(assessment, attempt)
            if assessment.institution.workspace_mode == "managed_exam" and not is_platform_administrator(request.user):
                for row in data["questions"]:
                    row["question"].pop("explanation", None)
                    row["question"].pop("options", None)
                    for option in row["options"]:
                        option.pop("is_correct", None)
            return Response(data)
        report = build_assessment_report(assessment, assessment.institution)
        report["summary"]["can_release_results"] = can_release_results(request.user, assessment.institution_id)
        if kind in {"summary", "results"}:
            report["summary"]["release_pending_count"] = releasable_results(assessment).exclude(
                status=Result.Status.PUBLISHED, published_at__isnull=False,
            ).count()
        if kind == "export":
            from .report_exports import render_report, CONTENT_TYPES
            if export_format not in CONTENT_TYPES:
                raise ValidationError("Choose CSV, PDF or DOCX.")
            response = HttpResponse(render_report(report, export_format), content_type=CONTENT_TYPES[export_format])
            title = slugify(assessment.title)[:80] or "exam"
            response["Content-Disposition"] = f'attachment; filename="{title}-results-{report["generated_at"]:%Y-%m-%d}.{export_format}"'
            response["Cache-Control"] = "private, no-store"
            return response
        if kind == "summary":
            return Response({"summary": report["summary"], "delivery_supported": report["assessment"]["delivery_supported"]})
        rows = report["rows"]
        search = request.query_params.get("search", "").strip().casefold()[:200]
        if search:
            rows = [row for row in rows if search in f'{row["name"]} {row["candidate_id"]}'.casefold()]
        status = request.query_params.get("status", "all")
        allowed = {"all", "not_started", "in_progress", "submitted", "auto_submitted", "not_submitted", "cancelled", "passed", "failed", "released", "not_released"}
        if status not in allowed:
            raise ValidationError({"status": "Choose a supported filter."})
        if status in {"passed", "failed"}:
            rows = [row for row in rows if row["passed"] is (status == "passed")]
        elif status in {"released", "not_released"}:
            rows = [row for row in rows if row["result"] is not None and row["publication"] == status]
        elif status != "all":
            rows = [row for row in rows if row["submission_status"] == status]
        sort = request.query_params.get("sort", "name")
        field = sort.lstrip("-")
        if field not in {"name", "percentage", "score", "submitted_at"}:
            raise ValidationError({"sort": "Choose a supported sort."})
        # Nulls last in both directions, deterministic candidate-ID tie breaking.
        populated = [row for row in rows if row[field] is not None]
        missing = [row for row in rows if row[field] is None]
        populated.sort(key=lambda row: (row[field].casefold() if field == "name" else row[field], row["candidate"]), reverse=sort.startswith("-"))
        pager = PageNumberPagination()
        pager.page_size = 25
        response = pager.get_paginated_response(pager.paginate_queryset(populated + missing, request, view=self))
        response.data.update(summary=report["summary"], delivery_supported=report["assessment"]["delivery_supported"])
        return response


class OwnerReleaseView(OwnerReportView):
    http_method_names = ["post", "options"]
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "result_publish"

    @transaction.atomic
    def post(self, request, assessment_pk, result_pk):
        assessment = self.assessment(request, assessment_pk)
        _require_role(request.user, ADMIN_ROLES, assessment.institution_id)
        require_result_release(request.user, assessment.institution_id)
        result = get_object_or_404(Result, pk=result_pk, assessment=assessment, institution=assessment.institution)
        publish_result(result.pk, actor=request.user)
        return Response({"released": True})


class OwnerOutcomesIndexView(APIView):
    """Assessment-first centres; paginate assessments before loading their reports."""
    def get(self, request, kind):
        if kind not in {"results", "reports", "submissions"}:
            raise ValidationError("Choose Results, Reports or Submissions.")
        institution = assessment_institution_for_request(request)
        assessments = Assessment.objects.filter(institution=institution).select_related("institution", "group", "subject")
        search = request.query_params.get("search", "").strip()[:200]
        if search:
            assessments = assessments.filter(title__icontains=search)
        assessments = assessments.order_by("-created_at", "-pk")
        pager = PageNumberPagination()
        pager.page_size = 25
        page = pager.paginate_queryset(assessments, request, view=self)
        now = timezone.now()
        rows = []
        for assessment in page:
            report = build_assessment_report(assessment, institution, now=now)
            rows.append({
                "id": assessment.pk, "institution": institution.pk, "title": assessment.title,
                "subject_name": assessment.subject.name if assessment.subject.institution_id == institution.pk else None,
                "status": assessment.status, "start_at": assessment.start_at, "end_at": assessment.end_at,
                "summary": report["summary"], "report_available": report["summary"]["results_count"] > 0,
                "delivery_supported": report["assessment"]["delivery_supported"],
            })
        return pager.get_paginated_response(rows)


class OwnerBulkReleaseView(OwnerReleaseView):
    @transaction.atomic
    def post(self, request, assessment_pk):
        assessment = self.assessment(request, assessment_pk)
        _require_role(request.user, ADMIN_ROLES, assessment.institution_id)
        require_result_release(request.user, assessment.institution_id)
        # Serialize exam-level requests; the publication service locks each result too.
        Assessment.objects.select_for_update().get(pk=assessment.pk, institution=assessment.institution)
        results = list(releasable_results(assessment).select_for_update().order_by("pk"))
        already = sum(result.status == Result.Status.PUBLISHED and result.published_at is not None for result in results)
        released = 0
        now = timezone.now()
        for result in results:
            if result.status == Result.Status.PUBLISHED and result.published_at is not None:
                continue
            publish_result(result.pk, actor=request.user, now=now)
            released += 1
        summary = build_assessment_report(assessment, assessment.institution, now=now)["summary"]
        return Response({"released_count": released, "already_released_count": already,
                         "results_available": len(results), "release_state": summary["release_state"],
                         "summary": summary})
