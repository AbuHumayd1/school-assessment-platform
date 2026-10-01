from django.urls import path

from .views import CandidateExamListView, CandidateMeView

urlpatterns = [
    path("me/", CandidateMeView.as_view(), name="candidate-me"),
    path("me/exams/", CandidateExamListView.as_view(), name="candidate-me-exams"),
]
