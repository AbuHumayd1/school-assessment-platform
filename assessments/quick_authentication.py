from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication

from .quick_sessions import COOKIE_NAME, resolve_session


class QuickExamAuthentication(BaseAuthentication):
    """Used only by the Quick API; never authenticates a persistent Django User."""

    def authenticate(self, request):
        context = resolve_session(token=request.COOKIES.get(COOKIE_NAME, ""))
        return AnonymousUser(), context

    def authenticate_header(self, request):
        return "QuickExam"
