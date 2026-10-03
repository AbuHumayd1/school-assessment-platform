from unittest.mock import patch

from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from candidates.models import Candidate
from institutions.models import Institution
from tenants.models import InstitutionMembership
from .models import User


class RegistrationTests(TestCase):
    url = "/api/v1/auth/register/"

    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/v1/auth/csrf/").data["csrfToken"]
        self.fields = dict(first_name="Robin", last_name="Organizer", email="robin@EXAMPLE.com",
                           password="A-long-uncommon-passphrase-793!", password_confirmation="A-long-uncommon-passphrase-793!")

    def register(self, **changes):
        return self.client.post(self.url, {**self.fields, **changes}, format="json", HTTP_X_CSRFTOKEN=self.token)

    def test_registration_creates_safe_normalized_user_and_live_session_only(self):
        response = self.register()
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="robin@example.com")
        self.assertTrue(user.check_password(self.fields["password"]))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(set(response.data["user"]), {"id", "email", "first_name", "last_name", "is_candidate"})
        self.assertEqual(self.client.get("/api/v1/auth/me/").data["id"], user.pk)
        self.assertIn("csrfToken", response.data)
        self.assertNotEqual(response.data["csrfToken"], self.token)
        self.assertFalse(Candidate.objects.exists())
        self.assertFalse(Institution.objects.exists())
        self.assertFalse(InstitutionMembership.objects.exists())

    def test_duplicate_email_including_case_variant_is_rejected(self):
        User.objects.create_user("ROBIN@example.com", "existing-password")
        response = self.register()
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_required_names_email_and_password_fields(self):
        for field in self.fields:
            with self.subTest(field=field):
                response = self.register(**{field: ""})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
        self.assertFalse(User.objects.exists())

    def test_password_validators_and_confirmation(self):
        for password in ("12345678", "password", "short", "robin@example.com"):
            with self.subTest(password=password):
                response = self.register(password=password, password_confirmation=password)
                self.assertEqual(response.status_code, 400)
                self.assertIn("password", response.data)
        response = self.register(password_confirmation="different")
        self.assertEqual(response.status_code, 400)
        self.assertIn("password_confirmation", response.data)
        self.assertFalse(User.objects.exists())

    def test_privilege_and_tenant_fields_are_rejected(self):
        for field, value in (("is_staff", True), ("is_superuser", True), ("role", "platform_admin"),
                             ("institution_id", 1), ("is_active", False)):
            with self.subTest(field=field):
                self.assertEqual(self.register(**{field: value}).status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_csrf_is_required_for_anonymous_registration(self):
        response = self.client.post(self.url, self.fields, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.exists())

    def test_logged_in_user_cannot_replace_session_with_new_registration(self):
        user = User.objects.create_user("existing@example.com", "existing-password")
        self.client.force_login(user)
        self.assertEqual(self.register().status_code, 400)
        self.assertEqual(self.client.get("/api/v1/auth/me/").data["id"], user.pk)
        self.assertEqual(User.objects.count(), 1)

    def test_registration_is_throttled(self):
        for _ in range(10):
            self.assertEqual(self.register(email="invalid").status_code, 400)
        self.assertEqual(self.register(email="invalid").status_code, 429)

    def test_database_duplicate_race_is_a_safe_validation_failure(self):
        with patch("accounts.registration.User.objects.create_user", side_effect=IntegrityError("duplicate")):
            response = self.register()
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)
        self.assertFalse(User.objects.exists())
