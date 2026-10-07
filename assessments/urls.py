from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework.urlpatterns import format_suffix_patterns

from .views import AssessmentQuestionDetailView, AssessmentQuestionListCreateView, AssessmentViewSet
from .quick_views import QuickConfigurationView, QuickCredentialView, QuickCredentialResetView, QuickCredentialRevokeView, QuickCredentialBatchView
from results.owner_views import OwnerReportView, OwnerReleaseView, OwnerBulkReleaseView, OwnerOutcomesIndexView

from .setup_views import AssessmentCandidatesView, AssessmentCandidateRemoveView, AssessmentQuestionBatchView, AssessmentQuestionRemoveView

router = DefaultRouter()
router.register("", AssessmentViewSet, basename="assessment")

question_list = AssessmentQuestionListCreateView.as_view({"get": "list", "post": "create"})
question_detail = AssessmentQuestionDetailView.as_view({"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"})

urlpatterns = [
    path("<int:assessment_pk>/candidate-assignments/", AssessmentCandidatesView.as_view()),
    path("<int:assessment_pk>/candidate-assignments/<int:candidate_pk>/", AssessmentCandidateRemoveView.as_view()),
    path("<int:assessment_pk>/questions/add/", AssessmentQuestionBatchView.as_view()),
    path("<int:assessment_pk>/questions/remove/", AssessmentQuestionRemoveView.as_view()),
    path("outcomes/<str:kind>/", OwnerOutcomesIndexView.as_view(), name="assessment-outcomes-index"),
    path("<int:assessment_pk>/outcomes/", OwnerReportView.as_view(), name="assessment-outcomes"),
    path("<int:assessment_pk>/submissions/", OwnerReportView.as_view(), {"kind": "submissions"}, name="assessment-submissions"),
    path("<int:assessment_pk>/submissions/<int:attempt_pk>/", OwnerReportView.as_view(), {"kind": "detail"}, name="assessment-submission-detail"),
    path("<int:assessment_pk>/results/", OwnerReportView.as_view(), {"kind": "results"}, name="assessment-results"),
    path("<int:assessment_pk>/results/release/", OwnerBulkReleaseView.as_view(), name="assessment-results-release"),
    path("<int:assessment_pk>/results/<int:result_pk>/release/", OwnerReleaseView.as_view(), name="assessment-result-release"),
    path("<int:assessment_pk>/reports/<str:export_format>/", OwnerReportView.as_view(), {"kind": "export"}, name="assessment-report"),
    path("<int:assessment_pk>/quick-access/", QuickConfigurationView.as_view(), name="quick-configuration"),
    path("<int:assessment_pk>/quick-access/credentials/", QuickCredentialView.as_view(), name="quick-credentials"),
    path("<int:assessment_pk>/quick-access/credentials/generate-sheet/", QuickCredentialBatchView.as_view(), name="quick-credential-sheet"),
    path("<int:assessment_pk>/quick-access/credentials/<int:candidate_pk>/reset/", QuickCredentialResetView.as_view(), name="quick-credential-reset"),
    path("<int:assessment_pk>/quick-access/credentials/<int:candidate_pk>/revoke/", QuickCredentialRevokeView.as_view(), name="quick-credential-revoke"),
    path("", include(router.urls)),
    path("<int:assessment_pk>/questions/", question_list, name="assessment-question-list"),
    path("<int:assessment_pk>/questions/<int:pk>/", question_detail, name="assessment-question-detail"),
]
