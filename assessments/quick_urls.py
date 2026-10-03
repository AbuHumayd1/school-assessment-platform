from django.urls import path

from .quick_public_views import (
    QuickAnswerView, QuickAttemptDetailView, QuickCurrentAttemptView, QuickIntegrityView,
    QuickLogoutView, QuickQuestionDetailView, QuickQuestionListView, QuickReviewView,
    QuickSessionView, QuickStartView, QuickSubmitView, QuickVerifyView,
)


urlpatterns = [
    path("verify/", QuickVerifyView.as_view(), name="quick-verify"),
    path("session/", QuickSessionView.as_view(), name="quick-session"),
    path("logout/", QuickLogoutView.as_view(), name="quick-logout"),
    path("start/", QuickStartView.as_view(), name="quick-start"),
    path("attempt/", QuickCurrentAttemptView.as_view(), name="quick-current-attempt"),
    path("attempt/<int:attempt_id>/", QuickAttemptDetailView.as_view(), name="quick-attempt-detail"),
    path("attempt/<int:attempt_id>/questions/", QuickQuestionListView.as_view(), name="quick-questions"),
    path("attempt/<int:attempt_id>/questions/<int:question_id>/", QuickQuestionDetailView.as_view(), name="quick-question"),
    path("attempt/<int:attempt_id>/questions/<int:question_id>/answer/", QuickAnswerView.as_view(), name="quick-answer"),
    path("attempt/<int:attempt_id>/questions/<int:question_id>/review/", QuickReviewView.as_view(), name="quick-review"),
    path("attempt/<int:attempt_id>/integrity/", QuickIntegrityView.as_view(), name="quick-integrity"),
    path("attempt/<int:attempt_id>/submit/", QuickSubmitView.as_view(), name="quick-submit"),
]
