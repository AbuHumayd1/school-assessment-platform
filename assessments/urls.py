from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework.urlpatterns import format_suffix_patterns

from .views import AssessmentQuestionDetailView, AssessmentQuestionListCreateView, AssessmentViewSet
from .quick_views import QuickConfigurationView, QuickCredentialView, QuickCredentialResetView, QuickCredentialRevokeView

router = DefaultRouter()
router.register("", AssessmentViewSet, basename="assessment")

question_list = AssessmentQuestionListCreateView.as_view({"get": "list", "post": "create"})
question_detail = AssessmentQuestionDetailView.as_view({"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"})

urlpatterns = [
    path("<int:assessment_pk>/quick-access/", QuickConfigurationView.as_view(), name="quick-configuration"),
    path("<int:assessment_pk>/quick-access/credentials/", QuickCredentialView.as_view(), name="quick-credentials"),
    path("<int:assessment_pk>/quick-access/credentials/<int:candidate_pk>/reset/", QuickCredentialResetView.as_view(), name="quick-credential-reset"),
    path("<int:assessment_pk>/quick-access/credentials/<int:candidate_pk>/revoke/", QuickCredentialRevokeView.as_view(), name="quick-credential-revoke"),
    path("", include(router.urls)),
    path("<int:assessment_pk>/questions/", question_list, name="assessment-question-list"),
    path("<int:assessment_pk>/questions/<int:pk>/", question_detail, name="assessment-question-detail"),
]
