from django.contrib.auth import authenticate
from django.test import TestCase
from .models import User

class UserTests(TestCase):
    def test_email_is_authentication_identity(self):
        user = User.objects.create_user("person@example.com", "long-test-password")
        self.assertEqual(user.email, "person@example.com")
        self.assertIsNone(user.username)
        self.assertEqual(authenticate(email="person@example.com", password="long-test-password"), user)

    def test_superuser_creation(self):
        user = User.objects.create_superuser("admin@example.com", "long-test-password")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
