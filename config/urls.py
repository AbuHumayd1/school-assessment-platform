from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from institutions.views import InstitutionViewSet
from candidates.views import CandidateViewSet
from groups.views import GroupViewSet
from subjects.views import SubjectViewSet
from questions.views import TopicViewSet, QuestionViewSet

router = DefaultRouter()
router.register("institutions", InstitutionViewSet, basename="institution")
router.register("candidates", CandidateViewSet, basename="candidate")
router.register("groups", GroupViewSet, basename="group")
router.register("subjects", SubjectViewSet, basename="subject")
router.register("topics", TopicViewSet, basename="topic")
router.register("questions", QuestionViewSet, basename="question")

urlpatterns = [path("admin/", admin.site.urls), path("api/v1/", include(router.urls)),
               path("api/v1/auth/", include("rest_framework.urls")),
               path("api/v1/users/", include("accounts.urls"))]
