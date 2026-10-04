from django.urls import path
from .docx_views import DocxPreviewView, DocxReviewView, DocxConfirmView, QuestionMediaView, QuickQuestionMediaView

urlpatterns = [
    path('questions/import/docx/preview/', DocxPreviewView.as_view()),
    path('questions/import/docx/<uuid:session_id>/', DocxReviewView.as_view()),
    path('questions/import/docx/<uuid:session_id>/confirm/', DocxConfirmView.as_view()),
    path('questions/media/<uuid:media_id>/', QuestionMediaView.as_view()),
    path('quick-exam/media/<uuid:media_id>/', QuickQuestionMediaView.as_view()),
]
