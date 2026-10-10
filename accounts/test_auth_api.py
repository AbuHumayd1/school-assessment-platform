from django.test import TestCase
from rest_framework.test import APIClient

from candidates.models import Candidate
from institutions.models import Institution
from .models import User


class SessionAuthenticationApiTests(TestCase):
    def setUp(self):
        self.email = "candidate@example.com"
        self.password = "local-test-password-934!"
        self.user = User.objects.create_user(
            self.email,
            self.password,
            first_name="Casey",
            last_name="Candidate",
        )
        institution = Institution.objects.create(name="Authentication Test School")
        Candidate.objects.create(
            institution=institution,
            candidate_id="AUTH-001",
            first_name="Casey",
            last_name="Candidate",
            user=self.user,
        )
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf_token(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", self.client.cookies)
        return response.data["csrfToken"]

    def test_anonymous_csrf_bootstrap_sets_cookie_and_is_not_cacheable(self):
        response = self.client.get('/api/v1/auth/csrf/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['csrfToken'])
        self.assertIn('csrftoken', response.cookies)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('private', response['Cache-Control'])
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_establishes_session_and_returns_only_safe_user_fields(self):
        token = self.csrf_token()
        response = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["user"], {
            "id": self.user.pk,
            "email": self.email,
            "first_name": "Casey",
            "last_name": "Candidate",
            "is_candidate": True,
        })
        self.assertIn("sessionid", self.client.cookies)
        self.assertNotIn("password", response.data)
        self.assertNotIn("sessionid", response.data)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)

    def test_invalid_password_and_unknown_email_have_the_same_safe_error(self):
        token = self.csrf_token()
        responses = [
            self.client.post(
                "/api/v1/auth/login/",
                {"email": email, "password": password},
                format="json",
                HTTP_X_CSRFTOKEN=token,
            )
            for email, password in (
                (self.email, "incorrect-password"),
                ("unknown@example.com", "incorrect-password"),
            )
        ]
        self.assertEqual([response.status_code for response in responses], [400, 400])
        self.assertEqual(responses[0].data, responses[1].data)
        self.assertEqual(responses[0].data["detail"], "Email or password is incorrect.")

    def test_inactive_account_cannot_sign_in(self):
        inactive = User.objects.create_user("inactive@example.com", self.password, is_active=False)
        token = self.csrf_token()
        response = self.client.post(
            "/api/v1/auth/login/",
            {"email": inactive.email, "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Email or password is incorrect.")
        self.assertNotIn("sessionid", self.client.cookies)

    def test_current_user_returns_unauthenticated_then_safe_session_identity(self):
        anonymous = self.client.get("/api/v1/auth/me/")
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(anonymous.data, {"authenticated": False})

        self.client.force_login(self.user)
        authenticated = self.client.get("/api/v1/auth/me/")
        self.assertEqual(authenticated.status_code, 200)
        self.assertEqual(authenticated.data["email"], self.email)
        self.assertNotIn("password", authenticated.data)
        self.assertNotIn("is_staff", authenticated.data)

    def test_logout_terminates_server_session(self):
        token = self.csrf_token()
        login_response = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(login_response.status_code, 200, login_response.data)
        logout_response = self.client.post(
            "/api/v1/auth/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=login_response.data["csrfToken"],
        )
        self.assertEqual(logout_response.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_login_and_logout_reject_requests_without_csrf(self):
        login_response = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )
        self.assertEqual(login_response.status_code, 403)

        self.client.force_login(self.user)
        logout_response = self.client.post("/api/v1/auth/logout/", format="json")
        self.assertEqual(logout_response.status_code, 403)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)
