from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework.urlpatterns import format_suffix_patterns

from .views import AssessmentQuestionDetailView, AssessmentQuestionListCreateView, AssessmentViewSet

router = DefaultRouter()
router.register("", AssessmentViewSet, basename="assessment")

question_list = AssessmentQuestionListCreateView.as_view({"get": "list", "post": "create"})
question_detail = AssessmentQuestionDetailView.as_view({"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"})

urlpatterns = [
    path("", include(router.urls)),
    path("<int:assessment_pk>/questions/", question_list, name="assessment-question-list"),
    path("<int:assessment_pk>/questions/<int:pk>/", question_detail, name="assessment-question-detail"),
]
