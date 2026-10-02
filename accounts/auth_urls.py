from django.urls import path

from .auth_views import CsrfTokenView, CurrentUserView, LoginView, LogoutView, WorkspaceContextView

urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("me/", CurrentUserView.as_view(), name="auth-me"),
    path("context/", WorkspaceContextView.as_view(), name="auth-context"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
]
