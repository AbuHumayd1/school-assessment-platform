from django.urls import path

from .views import (AttemptMarkView, MyResultsView, ResultDetailView,
                    ResultListView, ResultPublishView, ResultWithholdView)

urlpatterns = [
    path("my/", MyResultsView.as_view(), name="my-results"),
    path("attempts/<int:attempt_id>/mark/", AttemptMarkView.as_view(), name="result-mark-attempt"),
    path("<int:result_id>/publish/", ResultPublishView.as_view(), name="result-publish"),
    path("<int:result_id>/withhold/", ResultWithholdView.as_view(), name="result-withhold"),
    path("<int:result_id>/", ResultDetailView.as_view(), name="result-detail"),
    path("", ResultListView.as_view(), name="result-list"),
]
