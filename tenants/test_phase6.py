from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from assessments.models import Assessment
from attempts.models import Attempt
from audit.models import AuditEvent
from candidates.models import Candidate
from groups.models import Group
from institutions.models import Institution
from results.models import Result
from subjects.models import Subject
from .models import InstitutionMembership


class Phase6APITestCase(APITestCase):
    password = "Safe-phase6-password-184"

    def make_user(self, email, institution=None, role=None):
        user = User.objects.create_user(email, self.password)
        if institution and role:
            InstitutionMembership.objects.create(user=user, institution=institution, role=role)
        return user

    def authenticate_as(self, user):
        self.client.force_authenticate(user)

    def institution_context(self, institution):
        return {"HTTP_X_INSTITUTION_ID": str(institution.pk)}


class InstitutionManagementAPITests(Phase6APITestCase):
    def setUp(self):
        self.school_a = Institution.objects.create(name="North Academy")
        self.school_b = Institution.objects.create(name="South Academy")
        self.admin_a = self.make_user("admin-a@example.test", self.school_a, "institution_admin")
        self.admin_b = self.make_user("admin-b@example.test", self.school_b, "institution_admin")
        self.teacher = self.make_user("teacher@example.test", self.school_a, "teacher")
        self.platform = self.make_user("platform@example.test", self.school_a, "platform_admin")
        self.url = "/api/v1/institutions/"

    def test_admin_lists_only_managed_institutions(self):
        self.authenticate_as(self.admin_a)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in response.data], [self.school_a.pk])

    def test_admin_can_retrieve_own_institution(self):
        self.authenticate_as(self.admin_a)
        self.assertEqual(self.client.get(f"{self.url}{self.school_a.pk}/").status_code, 200)

    def test_admin_gets_404_for_another_institution(self):
        self.authenticate_as(self.admin_a)
        self.assertEqual(self.client.get(f"{self.url}{self.school_b.pk}/").status_code, 404)

    def test_admin_can_update_profile_contact_and_address(self):
        self.authenticate_as(self.admin_a)
        response = self.client.patch(f"{self.url}{self.school_a.pk}/", {
            "name": "North Academy Updated", "email": "office@north.example", "phone": "+2348000000000",
            "address": "1 School Road", "timezone": "Africa/Accra", "institution_type": "school",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.email, "office@north.example")
        self.assertEqual(self.school_a.address, "1 School Road")
        self.assertEqual(self.school_a.timezone, "Africa/Accra")

    def test_profile_update_writes_audit_event(self):
        self.authenticate_as(self.admin_a)
        self.client.patch(f"{self.url}{self.school_a.pk}/", {"phone": "12345"}, format="json")
        event = AuditEvent.objects.get(event_type=AuditEvent.Type.INSTITUTION_PROFILE_UPDATED)
        self.assertEqual(event.institution, self.school_a)
        self.assertEqual(event.actor, self.admin_a)
        self.assertEqual(event.metadata, {"fields": ["phone"]})

    def test_admin_cannot_change_slug(self):
        self.authenticate_as(self.admin_a)
        old_slug = self.school_a.slug
        response = self.client.patch(f"{self.url}{self.school_a.pk}/", {"slug": "tenant-takeover"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.slug, old_slug)

    def test_admin_cannot_deactivate_institution(self):
        self.authenticate_as(self.admin_a)
        response = self.client.patch(f"{self.url}{self.school_a.pk}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.school_a.refresh_from_db()
        self.assertTrue(self.school_a.is_active)

    def test_institution_deletion_is_not_exposed(self):
        self.authenticate_as(self.admin_a)
        self.assertEqual(self.client.delete(f"{self.url}{self.school_a.pk}/").status_code, 405)

    def test_invalid_timezone_is_rejected(self):
        self.authenticate_as(self.admin_a)
        response = self.client.patch(f"{self.url}{self.school_a.pk}/", {"timezone": "not/a-timezone"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_admin_cannot_create_institution(self):
        self.authenticate_as(self.admin_a)
        self.assertEqual(self.client.post(self.url, {"name": "Attempted Tenant"}, format="json").status_code, 403)

    def test_teacher_cannot_manage_institution_profiles(self):
        self.authenticate_as(self.teacher)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_unauthenticated_user_cannot_manage_institutions(self):
        self.assertIn(self.client.get(self.url).status_code, (401, 403))

    def test_admin_cannot_view_institution_after_membership_deactivation(self):
        self.authenticate_as(self.admin_a)
        InstitutionMembership.objects.filter(user=self.admin_a, institution=self.school_a).update(is_active=False)
        self.assertEqual(self.client.get(f"{self.url}{self.school_a.pk}/").status_code, 403)

    def test_platform_admin_can_deactivate_institution(self):
        self.authenticate_as(self.platform)
        response = self.client.patch(f"{self.url}{self.school_b.pk}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.school_b.refresh_from_db()
        self.assertFalse(self.school_b.is_active)

    def test_platform_admin_can_reactivate_inactive_institution(self):
        self.school_b.is_active = False
        self.school_b.save(update_fields=("is_active",))
        self.authenticate_as(self.platform)
        response = self.client.patch(f"{self.url}{self.school_b.pk}/", {"is_active": True}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.school_b.refresh_from_db()
        self.assertTrue(self.school_b.is_active)

    def test_multi_institution_admin_sees_only_institutions_where_admin(self):
        InstitutionMembership.objects.create(user=self.admin_a, institution=self.school_b, role="teacher")
        self.authenticate_as(self.admin_a)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [self.school_a.pk])


class InstitutionMembershipManagementAPITests(Phase6APITestCase):
    url = "/api/v1/memberships/"

    def setUp(self):
        self.school_a = Institution.objects.create(name="Membership School A")
        self.school_b = Institution.objects.create(name="Membership School B")
        self.admin_a = self.make_user("member-admin-a@example.test", self.school_a, "institution_admin")
        self.admin_b = self.make_user("member-admin-b@example.test", self.school_b, "institution_admin")
        self.teacher = self.make_user("member-teacher@example.test", self.school_a, "teacher")
        self.examiner = self.make_user("member-examiner@example.test", self.school_a, "examiner")
        self.student = self.make_user("member-student@example.test", self.school_a, "student")
        self.platform = self.make_user("member-platform@example.test", self.school_a, "platform_admin")
        self.teacher_membership = self.teacher.institution_memberships.get(institution=self.school_a)
        self.examiner_membership = self.examiner.institution_memberships.get(institution=self.school_a)
        self.admin_membership = self.admin_a.institution_memberships.get(institution=self.school_a)

    def scoped_get(self, url=None, institution=None):
        headers = self.institution_context(institution) if institution else {}
        return self.client.get(url or self.url, **headers)

    def test_admin_lists_members_in_selected_tenant(self):
        self.authenticate_as(self.admin_a)
        response = self.scoped_get(institution=self.school_a)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(row["institution"] == self.school_a.pk for row in response.data))

    def test_single_manageable_institution_is_inferred(self):
        self.authenticate_as(self.admin_a)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_multi_institution_admin_must_select_context(self):
        InstitutionMembership.objects.create(user=self.admin_a, institution=self.school_b, role="institution_admin")
        self.authenticate_as(self.admin_a)
        self.assertEqual(self.client.get(self.url).status_code, 400)

    def test_platform_admin_must_select_context(self):
        self.authenticate_as(self.platform)
        self.assertEqual(self.client.get(self.url).status_code, 400)

    def test_admin_cannot_list_foreign_tenant_members(self):
        self.authenticate_as(self.admin_a)
        response = self.client.get(self.url, **self.institution_context(self.school_b))
        self.assertEqual(response.status_code, 404)

    def test_foreign_membership_id_is_hidden(self):
        self.authenticate_as(self.admin_a)
        membership_b = self.admin_b.institution_memberships.get(institution=self.school_b)
        response = self.client.get(f"{self.url}{membership_b.pk}/", **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 404)

    def test_teacher_cannot_list_memberships(self):
        self.authenticate_as(self.teacher)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_examiner_cannot_list_memberships(self):
        self.authenticate_as(self.examiner)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_student_cannot_list_memberships(self):
        self.authenticate_as(self.student)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_unauthenticated_user_cannot_list_memberships(self):
        self.assertIn(self.client.get(self.url).status_code, (401, 403))

    def test_inactive_membership_cannot_manage_memberships(self):
        self.authenticate_as(self.admin_a)
        self.admin_membership.is_active = False
        self.admin_membership.save(update_fields=("is_active",))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_admin_can_add_existing_user_without_affecting_other_tenant_membership(self):
        self.authenticate_as(self.admin_a)
        response = self.client.post(self.url, {"email": self.admin_b.email, "role": "teacher"},
                                    format="json", **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.admin_b.institution_memberships.get(institution=self.school_b).role, "institution_admin")
        self.assertEqual(self.admin_b.institution_memberships.get(institution=self.school_a).role, "teacher")

    def test_existing_user_addition_is_audited(self):
        self.authenticate_as(self.admin_a)
        target = self.make_user("new-member@example.test")
        response = self.client.post(self.url, {"email": "new-member@example.test", "role": "student"},
                                    format="json", **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["user"], target.pk)
        event = AuditEvent.objects.get(event_type=AuditEvent.Type.MEMBERSHIP_CHANGED)
        self.assertEqual(event.institution, self.school_a)
        self.assertEqual(event.actor, self.admin_a)
        self.assertEqual(event.metadata, {"action": "created", "role": "student"})

    def test_unknown_email_does_not_create_user(self):
        self.authenticate_as(self.admin_a)
        response = self.client.post(self.url, {"email": "absent@example.test", "role": "student"},
                                    format="json", **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="absent@example.test").exists())

    def test_duplicate_membership_is_rejected(self):
        self.authenticate_as(self.admin_a)
        response = self.client.post(self.url, {"email": self.teacher.email, "role": "student"},
                                    format="json", **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.teacher.institution_memberships.filter(institution=self.school_a).count(), 1)

    def test_institution_cannot_be_supplied_in_create_payload(self):
        self.authenticate_as(self.admin_a)
        response = self.client.post(self.url, {"email": "new@example.test", "role": "student", "institution": self.school_b.pk},
                                    format="json", **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 400)

    def test_invalid_role_is_rejected(self):
        self.authenticate_as(self.admin_a)
        response = self.client.post(self.url, {"email": "new@example.test", "role": "owner"},
                                    format="json", **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 400)

    def test_institution_admin_cannot_assign_platform_admin(self):
        self.authenticate_as(self.admin_a)
        response = self.client.post(self.url, {"email": "new@example.test", "role": "platform_admin"},
                                    format="json", **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 400)

    def test_institution_admin_cannot_assign_institution_admin(self):
        self.authenticate_as(self.admin_a)
        response = self.client.post(self.url, {"email": "new@example.test", "role": "institution_admin"},
                                    format="json", **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 400)

    def test_institution_admin_cannot_add_existing_platform_admin(self):
        self.authenticate_as(self.admin_a)
        response = self.client.post(self.url, {"email": self.platform.email, "role": "teacher"},
                                    format="json", **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 400)

    def test_teacher_cannot_create_memberships(self):
        self.authenticate_as(self.teacher)
        self.assertEqual(self.client.post(self.url, {"email": "x@example.test", "role": "student"}, format="json").status_code, 403)

    def test_examiner_cannot_create_memberships(self):
        self.authenticate_as(self.examiner)
        self.assertEqual(self.client.post(self.url, {"email": "x@example.test", "role": "student"}, format="json").status_code, 403)

    def test_student_cannot_create_memberships(self):
        self.authenticate_as(self.student)
        self.assertEqual(self.client.post(self.url, {"email": "x@example.test", "role": "student"}, format="json").status_code, 403)

    def test_institution_admin_cannot_change_own_membership(self):
        self.authenticate_as(self.admin_a)
        response = self.client.patch(f"{self.url}{self.admin_membership.pk}/", {"role": "platform_admin"}, format="json",
                                      **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 400)
        self.admin_membership.refresh_from_db()
        self.assertEqual(self.admin_membership.role, "institution_admin")

    def test_institution_admin_cannot_change_another_admin(self):
        self.authenticate_as(self.admin_a)
        response = self.client.patch(f"{self.url}{self.admin_b.institution_memberships.get(institution=self.school_b).pk}/",
                                     {"role": "teacher"}, format="json", **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 404)

    def test_admin_can_change_subordinate_role_within_allowed_roles(self):
        self.authenticate_as(self.admin_a)
        response = self.client.patch(f"{self.url}{self.teacher_membership.pk}/", {"role": "examiner"}, format="json",
                                     **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 200, response.data)
        self.teacher_membership.refresh_from_db()
        self.assertEqual(self.teacher_membership.role, "examiner")

    def test_admin_can_deactivate_and_reactivate_member(self):
        self.authenticate_as(self.admin_a)
        detail = f"{self.url}{self.teacher_membership.pk}/"
        deactivated = self.client.patch(detail, {"is_active": False}, format="json", **self.institution_context(self.school_a))
        self.assertEqual(deactivated.status_code, 200, deactivated.data)
        self.assertFalse(deactivated.data["is_active"])
        reactivated = self.client.patch(detail, {"is_active": True}, format="json", **self.institution_context(self.school_a))
        self.assertEqual(reactivated.status_code, 200, reactivated.data)
        self.assertTrue(reactivated.data["is_active"])

    def test_deactivation_and_reactivation_are_audited(self):
        self.authenticate_as(self.admin_a)
        detail = f"{self.url}{self.teacher_membership.pk}/"
        self.client.patch(detail, {"is_active": False}, format="json", **self.institution_context(self.school_a))
        self.client.patch(detail, {"is_active": True}, format="json", **self.institution_context(self.school_a))
        actions = set(AuditEvent.objects.filter(
            institution=self.school_a, event_type=AuditEvent.Type.MEMBERSHIP_CHANGED,
        ).values_list("metadata__action", flat=True))
        self.assertEqual(actions, {"deactivated", "reactivated"})

    def test_user_can_have_independent_roles_in_two_institutions(self):
        InstitutionMembership.objects.create(user=self.teacher, institution=self.school_b, role="student")
        self.authenticate_as(self.admin_a)
        response = self.client.patch(f"{self.url}{self.teacher_membership.pk}/", {"role": "examiner"}, format="json",
                                     **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.teacher.institution_memberships.get(institution=self.school_b).role, "student")

    def test_platform_admin_can_assign_platform_admin_role(self):
        self.authenticate_as(self.platform)
        target = self.make_user("new-platform@example.test")
        response = self.client.post(self.url, {"email": "new-platform@example.test", "role": "platform_admin"},
                                    format="json", **self.institution_context(self.school_b))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["user"], target.pk)
        self.assertEqual(response.data["role"], "platform_admin")

    def test_inactive_institution_memberships_are_not_manageable(self):
        self.school_a.is_active = False
        self.school_a.save(update_fields=("is_active",))
        self.authenticate_as(self.platform)
        response = self.client.get(self.url, **self.institution_context(self.school_a))
        self.assertEqual(response.status_code, 404)


class InstitutionDashboardAPITests(Phase6APITestCase):
    url = "/api/v1/institution/dashboard/"

    def setUp(self):
        self.school_a = Institution.objects.create(name="Dashboard A")
        self.school_b = Institution.objects.create(name="Dashboard B")
        self.admin_a = self.make_user("dashboard-admin-a@example.test", self.school_a, "institution_admin")
        self.teacher = self.make_user("dashboard-teacher@example.test", self.school_a, "teacher")
        self.examiner = self.make_user("dashboard-examiner@example.test", self.school_a, "examiner")
        self.student = self.make_user("dashboard-student@example.test", self.school_a, "student")
        self.admin_b = self.make_user("dashboard-admin-b@example.test", self.school_b, "institution_admin")
        self.platform = self.make_user("dashboard-platform@example.test", self.school_a, "platform_admin")

    def test_dashboard_returns_safe_tenant_scoped_aggregate_counts(self):
        now = timezone.now()
        Candidate.objects.create(institution=self.school_a, candidate_id="DA1", first_name="A", last_name="Candidate")
        Candidate.objects.create(institution=self.school_a, candidate_id="DA2", first_name="Inactive", last_name="Candidate", status="inactive")
        Candidate.objects.create(institution=self.school_b, candidate_id="DB1", first_name="B", last_name="Candidate")
        Group.objects.create(institution=self.school_a, name="A group", code="A1")
        Group.objects.create(institution=self.school_a, name="Inactive group", code="A2", is_active=False)
        Group.objects.create(institution=self.school_b, name="B group", code="B1")
        subject_a = Subject.objects.create(institution=self.school_a, name="A subject", code="AS")
        Subject.objects.create(institution=self.school_a, name="Inactive subject", code="AIS", is_active=False)
        subject_b = Subject.objects.create(institution=self.school_b, name="B subject", code="BS")
        available = Assessment.objects.create(
            institution=self.school_a, title="Available", assessment_type="quiz", subject=subject_a,
            duration_minutes=30, created_by=self.admin_a, status=Assessment.Status.APPROVED,
        )
        Assessment.objects.create(
            institution=self.school_a, title="Future", assessment_type="quiz", subject=subject_a,
            duration_minutes=30, created_by=self.admin_a, status=Assessment.Status.SCHEDULED,
            start_at=now + timedelta(hours=1),
        )
        Assessment.objects.create(
            institution=self.school_b, title="Other tenant", assessment_type="quiz", subject=subject_b,
            duration_minutes=30, created_by=self.admin_b, status=Assessment.Status.APPROVED,
        )
        candidate = Candidate.objects.create(institution=self.school_a, candidate_id="DA3", first_name="Attempt", last_name="Candidate")
        submitted = Attempt.objects.create(
            institution=self.school_a, assessment=available, candidate=candidate, attempt_number=1,
            status=Attempt.Status.SUBMITTED, started_at=now, expires_at=now + timedelta(hours=1),
            submitted_at=now, last_activity_at=now,
        )
        Result.objects.create(
            institution=self.school_a, attempt=submitted, candidate=candidate, assessment=available,
            total_marks=10, marks_obtained=8, pass_mark=5, status=Result.Status.PUBLISHED,
            marked_at=now, published_at=now,
        )
        other_candidate = Candidate.objects.create(institution=self.school_b, candidate_id="DB2", first_name="B", last_name="Attempt")
        other_assessment = Assessment.objects.filter(institution=self.school_b).first()
        other_attempt = Attempt.objects.create(
            institution=self.school_b, assessment=other_assessment, candidate=other_candidate, attempt_number=1,
            status=Attempt.Status.SUBMITTED, started_at=now, expires_at=now + timedelta(hours=1),
            submitted_at=now, last_activity_at=now,
        )
        Result.objects.create(
            institution=self.school_b, attempt=other_attempt, candidate=other_candidate, assessment=other_assessment,
            total_marks=10, marks_obtained=8, pass_mark=5, status=Result.Status.PUBLISHED,
            marked_at=now, published_at=now,
        )
        self.authenticate_as(self.admin_a)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["institution"]["id"], self.school_a.pk)
        self.assertEqual(response.data["counts"], {
            "active_members": 5,
            "active_candidates": 2,
            "active_groups": 1,
            "active_subjects": 1,
            "available_assessments": 1,
            "submitted_attempts": 1,
            "published_results": 1,
        })
        self.assertNotIn("email", response.data["institution"])
        self.assertNotIn("other_candidate", response.data)

    def test_dashboard_infers_a_single_managed_institution(self):
        self.authenticate_as(self.admin_a)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_multi_tenant_admin_must_select_institution(self):
        InstitutionMembership.objects.create(user=self.admin_a, institution=self.school_b, role="institution_admin")
        self.authenticate_as(self.admin_a)
        self.assertEqual(self.client.get(self.url).status_code, 400)

    def test_dashboard_accepts_explicit_query_context(self):
        self.authenticate_as(self.admin_a)
        response = self.client.get(self.url, {"institution": self.school_a.pk})
        self.assertEqual(response.status_code, 200)

    def test_foreign_dashboard_context_is_not_found(self):
        self.authenticate_as(self.admin_a)
        response = self.client.get(self.url, **self.institution_context(self.school_b))
        self.assertEqual(response.status_code, 404)

    def test_teacher_cannot_access_dashboard(self):
        self.authenticate_as(self.teacher)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_examiner_cannot_access_dashboard(self):
        self.authenticate_as(self.examiner)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_student_cannot_access_dashboard(self):
        self.authenticate_as(self.student)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_inactive_membership_cannot_access_dashboard(self):
        self.authenticate_as(self.admin_a)
        self.admin_a.institution_memberships.filter(institution=self.school_a).update(is_active=False)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_platform_admin_must_select_dashboard_tenant(self):
        self.authenticate_as(self.platform)
        self.assertEqual(self.client.get(self.url).status_code, 400)

    def test_dashboard_does_not_serve_inactive_institution(self):
        self.school_a.is_active = False
        self.school_a.save(update_fields=("is_active",))
        self.authenticate_as(self.platform)
        self.assertEqual(self.client.get(self.url, **self.institution_context(self.school_a)).status_code, 404)

    def test_unauthenticated_user_cannot_access_dashboard(self):
        self.assertIn(self.client.get(self.url).status_code, (401, 403))
