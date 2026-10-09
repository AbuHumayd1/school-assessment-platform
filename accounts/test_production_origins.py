import importlib
import os
import runpy
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from django.http import HttpResponse
from django.test import RequestFactory
from corsheaders.middleware import CorsMiddleware
from config.settings.origins import environment_origins


class ProductionOriginsTests(SimpleTestCase):
    def production(self, **overrides):
        with patch.dict(os.environ, {
            "DJANGO_ALLOWED_HOSTS": "api.example.test", "DJANGO_CORS_ALLOWED_ORIGINS": " https://app.example.test, ,https://other.example.test ",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.example.test, https://other.example.test",
            **overrides,
        }):
            for name in ("DJANGO_SESSION_COOKIE_SAMESITE", "DJANGO_CSRF_COOKIE_SAMESITE", "DJANGO_QUICK_EXAM_COOKIE_SAMESITE", "DJANGO_SECURE_SSL_REDIRECT"):
                if name not in overrides:
                    os.environ.pop(name, None)
            # Reuse loaded base settings without modifying the active Django settings.
            with patch.object(importlib.import_module("config.settings.base"), "SECRET_KEY", "non-secret-test-placeholder"):
                return runpy.run_module("config.settings.production")

    def test_production_defaults_and_explicit_origins(self):
        values = self.production()
        expected = ["https://app.example.test", "https://other.example.test"]
        self.assertEqual(values["CORS_ALLOWED_ORIGINS"], expected)
        self.assertEqual(values["CSRF_TRUSTED_ORIGINS"], expected)
        self.assertTrue(values["CORS_ALLOW_CREDENTIALS"])
        self.assertFalse(values["CORS_ALLOW_ALL_ORIGINS"])
        for name in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY", "QUICK_EXAM_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
            self.assertTrue(values[name])
        for name in ("SESSION_COOKIE_SAMESITE", "CSRF_COOKIE_SAMESITE", "QUICK_EXAM_COOKIE_SAMESITE"):
            self.assertEqual(values[name], "None")
        self.assertEqual(values["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_explicit_overrides(self):
        values = self.production(DJANGO_SESSION_COOKIE_SAMESITE="Lax", DJANGO_CSRF_COOKIE_SAMESITE="Strict", DJANGO_QUICK_EXAM_COOKIE_SAMESITE="Lax", DJANGO_SECURE_SSL_REDIRECT="False")
        self.assertEqual(values["SESSION_COOKIE_SAMESITE"], "Lax")
        self.assertEqual(values["CSRF_COOKIE_SAMESITE"], "Strict")
        self.assertEqual(values["QUICK_EXAM_COOKIE_SAMESITE"], "Lax")
        self.assertFalse(values["SECURE_SSL_REDIRECT"])

    def test_missing_and_invalid_origin_configuration(self):
        with patch.dict(os.environ, {"TEST_ORIGINS": ""}):
            self.assertEqual(environment_origins("TEST_ORIGINS"), [])
        for origin in ("*", "https://*.example.test", "https://example.test/path", "example.test", "https://user@example.test", "https://example.test:invalid"):
            with self.subTest(origin=origin), patch.dict(os.environ, {"TEST_ORIGINS": origin}):
                with self.assertRaises(ImproperlyConfigured):
                    environment_origins("TEST_ORIGINS")

    @override_settings(CORS_ALLOWED_ORIGINS=["https://app.example.test", "https://madaar.pages.dev"], CORS_ALLOWED_ORIGIN_REGEXES=[], CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOW_CREDENTIALS=True)
    def test_credentialed_preflight_allows_csrf_and_institution_headers(self):
        for origin in ("https://app.example.test", "https://madaar.pages.dev"):
            with self.subTest(origin=origin):
                request = RequestFactory().options("/api/v1/assessments/", HTTP_ORIGIN=origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken,x-institution-id")
                response = CorsMiddleware(lambda request: HttpResponse())(request)
                self.assertEqual(response["Access-Control-Allow-Origin"], origin)
                self.assertEqual(response["Access-Control-Allow-Credentials"], "true")
                headers = {header.strip().lower() for header in response["Access-Control-Allow-Headers"].split(",")}
                self.assertTrue({"content-type", "x-csrftoken", "x-institution-id"}.issubset(headers))

    @override_settings(CORS_ALLOWED_ORIGINS=["https://madaar.pages.dev"], CORS_ALLOWED_ORIGIN_REGEXES=[], CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOW_CREDENTIALS=True)
    def test_unconfigured_origin_receives_no_cors_permission(self):
        # Build fresh requests: Django caches request.headers on first access.
        for method in ("options", "get"):
            with self.subTest(method=method):
                request = getattr(RequestFactory(), method)("/api/v1/assessments/", HTTP_ORIGIN="https://evil.example", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-csrftoken,x-institution-id")
                self.assertEqual(request.headers["Origin"], "https://evil.example")
                response = CorsMiddleware(lambda request: HttpResponse())(request)
                self.assertNotIn("Access-Control-Allow-Origin", response)
                self.assertNotIn("Access-Control-Allow-Credentials", response)
