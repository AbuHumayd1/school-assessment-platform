from django.urls import path

from .views import (
    AttemptAnswerView, AttemptDetailView, AttemptListView, AttemptQuestionDetailView,
    AttemptQuestionListView, AttemptReviewFlagView, AttemptStartView, AttemptSubmitView,
    AttemptIntegrityView,
)

urlpatterns = [
    path("", AttemptListView.as_view(), name="attempt-list"),
    path("start/", AttemptStartView.as_view(), name="attempt-start"),
    path("<int:attempt_id>/", AttemptDetailView.as_view(), name="attempt-detail"),
    path("<int:attempt_id>/submit/", AttemptSubmitView.as_view(), name="attempt-submit"),
    path("<int:attempt_id>/integrity/", AttemptIntegrityView.as_view(), name="attempt-integrity"),
    path("<int:attempt_id>/questions/", AttemptQuestionListView.as_view(), name="attempt-question-list"),
    path("<int:attempt_id>/questions/<int:question_id>/", AttemptQuestionDetailView.as_view(), name="attempt-question-detail"),
    path("<int:attempt_id>/questions/<int:question_id>/answer/", AttemptAnswerView.as_view(), name="attempt-answer"),
    path("<int:attempt_id>/questions/<int:question_id>/review/", AttemptReviewFlagView.as_view(), name="attempt-review-flag"),
]
