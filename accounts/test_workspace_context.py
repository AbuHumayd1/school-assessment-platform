from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from institutions.models import Institution
from tenants.models import InstitutionMembership


class AuthenticatedWorkspaceContextTests(APITestCase):
    url = "/api/v1/auth/context/"

    def setUp(self):
        self.first = Institution.objects.create(name="North Learning Centre", institution_type="training")
        self.second = Institution.objects.create(name="South Examination Board", institution_type="other")
        self.inactive = Institution.objects.create(name="Closed Workspace", is_active=False)

    def make_user(self, email):
        return User.objects.create_user(email, "workspace-context-test-password")

    def add_membership(self, user, institution, role, *, active=True):
        return InstitutionMembership.objects.create(
            user=user, institution=institution, role=role, is_active=active,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def test_unauthenticated_context_request_is_rejected(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_context_contains_only_request_users_authorized_relationships(self):
        user = self.make_user("teacher@example.test")
        self.add_membership(user, self.first, InstitutionMembership.Role.TEACHER)
        another_user = self.make_user("other@example.test")
        self.add_membership(another_user, self.first, InstitutionMembership.Role.INSTITUTION_ADMIN)
        self.add_membership(another_user, self.second, InstitutionMembership.Role.EXAMINER)
        self.authenticate(user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"], {
            "id": user.pk,
            "email": user.email,
            "first_name": "",
            "last_name": "",
        })
        self.assertEqual(response.data["workspaces"], [{
            "institution": {
                "id": self.first.pk,
                "name": self.first.name,
                "slug": self.first.slug,
                "institution_type": self.first.institution_type,
                "workspace_mode": "full_workspace",
                "can_release_candidate_results": False,
            },
            "role": InstitutionMembership.Role.TEACHER,
        }])
        self.assertNotIn(another_user.email, str(response.data))
        self.assertNotIn(self.second.name, str(response.data))
        self.assertNotIn("password", response.data["user"])
        self.assertNotIn("is_staff", response.data["user"])

    def test_inactive_membership_does_not_grant_workspace_access(self):
        user = self.make_user("inactive-membership@example.test")
        self.add_membership(user, self.first, InstitutionMembership.Role.INSTITUTION_ADMIN, active=False)
        self.authenticate(user)
        self.assertEqual(self.client.get(self.url).data["workspaces"], [])

    def test_membership_in_inactive_institution_does_not_grant_access(self):
        user = self.make_user("inactive-institution@example.test")
        self.add_membership(user, self.inactive, InstitutionMembership.Role.INSTITUTION_ADMIN)
        self.authenticate(user)
        self.assertEqual(self.client.get(self.url).data["workspaces"], [])

    def test_student_only_membership_is_not_a_workspace_membership(self):
        user = self.make_user("student-only@example.test")
        self.add_membership(user, self.first, InstitutionMembership.Role.STUDENT)
        self.authenticate(user)
        self.assertEqual(self.client.get(self.url).data["workspaces"], [])

    def test_institution_admin_role_is_returned(self):
        user = self.make_user("admin@example.test")
        self.add_membership(user, self.first, InstitutionMembership.Role.INSTITUTION_ADMIN)
        self.authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["workspaces"][0]["role"], InstitutionMembership.Role.INSTITUTION_ADMIN)

    def test_teacher_role_is_returned(self):
        user = self.make_user("teacher-role@example.test")
        self.add_membership(user, self.first, InstitutionMembership.Role.TEACHER)
        self.authenticate(user)
        self.assertEqual(self.client.get(self.url).data["workspaces"][0]["role"], InstitutionMembership.Role.TEACHER)

    def test_examiner_role_is_returned(self):
        user = self.make_user("examiner@example.test")
        self.add_membership(user, self.first, InstitutionMembership.Role.EXAMINER)
        self.authenticate(user)
        self.assertEqual(self.client.get(self.url).data["workspaces"][0]["role"], InstitutionMembership.Role.EXAMINER)

    def test_multiple_authorized_institutions_are_returned_without_extra_data(self):
        user = self.make_user("multi@example.test")
        self.add_membership(user, self.first, InstitutionMembership.Role.INSTITUTION_ADMIN)
        self.add_membership(user, self.second, InstitutionMembership.Role.EXAMINER)
        self.authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [(row["institution"]["id"], row["role"]) for row in response.data["workspaces"]],
            [(self.first.pk, InstitutionMembership.Role.INSTITUTION_ADMIN),
             (self.second.pk, InstitutionMembership.Role.EXAMINER)],
        )

    def test_student_relationship_does_not_hide_staff_relationship_in_another_institution(self):
        user = self.make_user("mixed@example.test")
        self.add_membership(user, self.first, InstitutionMembership.Role.STUDENT)
        self.add_membership(user, self.second, InstitutionMembership.Role.TEACHER)
        self.authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(len(response.data["workspaces"]), 1)
        self.assertEqual(response.data["workspaces"][0]["institution"]["id"], self.second.pk)
        self.assertEqual(response.data["workspaces"][0]["role"], InstitutionMembership.Role.TEACHER)

    def test_solo_institution_admin_can_operate_without_other_staff(self):
        user = self.make_user("solo@example.test")
        self.add_membership(user, self.first, InstitutionMembership.Role.INSTITUTION_ADMIN)
        self.authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["workspaces"]), 1)
        self.assertEqual(response.data["workspaces"][0]["role"], InstitutionMembership.Role.INSTITUTION_ADMIN)
        self.assertEqual(self.first.memberships.count(), 1)

    def test_platform_admin_can_select_each_active_institution_using_existing_semantics(self):
        user = self.make_user("platform@example.test")
        self.add_membership(user, self.first, InstitutionMembership.Role.PLATFORM_ADMIN)
        self.authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row["institution"]["id"] for row in response.data["workspaces"]],
            [self.first.pk, self.second.pk],
        )
        self.assertTrue(all(row["role"] == InstitutionMembership.Role.PLATFORM_ADMIN for row in response.data["workspaces"]))
        self.assertNotIn(self.inactive.pk, [row["institution"]["id"] for row in response.data["workspaces"]])

    def test_django_superuser_uses_existing_platform_admin_semantics(self):
        user = User.objects.create_superuser("root@example.test", "workspace-context-test-password")
        self.authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row["institution"]["id"] for row in response.data["workspaces"]],
            [self.first.pk, self.second.pk],
        )

    def test_workspace_discovery_does_not_weaken_admin_only_membership_management(self):
        teacher = self.make_user("management-test@example.test")
        self.add_membership(teacher, self.first, InstitutionMembership.Role.TEACHER)
        self.authenticate(teacher)
        response = self.client.get("/api/v1/memberships/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        create_response = self.client.post(
            "/api/v1/memberships/",
            {"email": "another@example.test", "role": InstitutionMembership.Role.STUDENT},
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)
