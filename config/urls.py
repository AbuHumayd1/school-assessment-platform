from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from institutions.views import InstitutionViewSet
from candidates.views import CandidateViewSet
from groups.views import GroupViewSet
from subjects.views import SubjectViewSet
from questions.views import TopicViewSet, QuestionViewSet
from tenants.views import InstitutionMembershipViewSet, InstitutionDashboardView

router = DefaultRouter()
router.register("institutions", InstitutionViewSet, basename="institution")
router.register("memberships", InstitutionMembershipViewSet, basename="membership")
router.register("candidates", CandidateViewSet, basename="candidate")
router.register("groups", GroupViewSet, basename="group")
router.register("subjects", SubjectViewSet, basename="subject")
router.register("topics", TopicViewSet, basename="topic")
router.register("questions", QuestionViewSet, basename="question")

urlpatterns = [path("admin/", admin.site.urls), path("api/v1/", include(router.urls)),
               path("api/v1/institution/dashboard/", InstitutionDashboardView.as_view(), name="institution-dashboard"),
               path("api/v1/auth/", include("accounts.auth_urls")),
               path("api/v1/candidate/", include("candidates.candidate_urls")),
               path("api/v1/users/", include("accounts.urls")),
               path("api/v1/assessments/", include("assessments.urls")),
               path("api/v1/attempts/", include("attempts.urls"))]
urlpatterns += [path("api/v1/results/", include("results.urls"))]
