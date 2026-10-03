from datetime import timedelta
from unittest.mock import patch
from types import SimpleNamespace

from django.db.models.deletion import ProtectedError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from assessments.models import Assessment
from attempts.models import Attempt
from audit.models import AuditEvent
from groups.models import Group, GroupMembership
from results.models import Result
from subjects.models import Subject
from tenants.models import InstitutionMembership
from .models import Candidate
from .test_management import CandidateManagementTests


class CandidateDeletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CandidateManagementTests.setUpTestData.__func__(cls)

    setUp = CandidateManagementTests.setUp

    def delete(self, candidate=None):
        return self.client.delete(f"/api/v1/candidates/{(candidate or self.own).pk}/")

    def history(self, candidate=None):
        subject = Subject.objects.create(institution=self.a, name="Deletion subject", code="DEL")
        assessment = Assessment.objects.create(institution=self.a, subject=subject, title="History", assessment_type="quiz", duration_minutes=5, created_by=self.admin)
        now = timezone.now()
        return Attempt.objects.create(institution=self.a, assessment=assessment, candidate=candidate or self.own, attempt_number=1, started_at=now, expires_at=now + timedelta(minutes=5), last_activity_at=now)

    def test_admin_delete_removes_list_detail_search_and_updates_dashboard(self):
        candidate_pk = self.own.pk
        before = self.client.get("/api/v1/institution/dashboard/").data["counts"]["active_candidates"]
        response = self.delete()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertFalse(Candidate.objects.filter(pk=candidate_pk).exists())
        self.assertEqual(self.client.get(f"/api/v1/candidates/{candidate_pk}/").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/candidates/", {"search": "A-1"}).data["count"], 0)
        self.assertEqual(self.client.get("/api/v1/candidates/").data["count"], 1)
        self.assertEqual(self.client.get("/api/v1/institution/dashboard/").data["counts"]["active_candidates"], before - 1)
        self.assertTrue(Candidate.objects.filter(pk=self.foreign.pk).exists())

    def test_any_attempt_blocks_deletion_and_deactivation_remains_available(self):
        attempt = self.history()
        for attempt_status in Attempt.Status.values:
            attempt.status = attempt_status
            attempt.save()
            response = self.delete()
            self.assertEqual(response.status_code, 409)
            self.assertEqual(str(response.data["code"]), "candidate_has_assessment_history")
            self.assertIn("Deactivate", str(response.data["detail"]))
            self.assertTrue(Candidate.objects.filter(pk=self.own.pk).exists())
        self.assertFalse(AuditEvent.objects.filter(metadata__action="candidate_deleted").exists())
        response = self.client.patch(f"/api/v1/candidates/{self.own.pk}/", {"status": "inactive"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Attempt.objects.filter(pk=attempt.pk).exists())

    def test_results_are_preserved_with_assessment_history(self):
        attempt = self.history()
        result = Result.objects.create(institution=self.a, attempt=attempt, candidate=self.own, assessment=attempt.assessment, total_marks=0, marks_obtained=0, pass_mark=0, marked_at=timezone.now())
        self.assertEqual(self.delete().status_code, 409)
        self.assertTrue(Result.objects.filter(pk=result.pk).exists())

    def test_teacher_and_examiner_cannot_delete(self):
        for user in (self.teacher, self.examiner):
            self.client.force_authenticate(user)
            self.assertEqual(self.delete().status_code, 403)
        self.assertTrue(Candidate.objects.filter(pk=self.own.pk).exists())

    def test_candidate_user_and_anonymous_cannot_delete(self):
        self.client.force_authenticate(self.learner)
        self.assertEqual(self.delete(self.linked).status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.delete().status_code, (401, 403))
        self.assertTrue(Candidate.objects.filter(pk=self.linked.pk).exists())

    def test_cross_tenant_delete_is_rejected_even_for_admin_in_other_workspace(self):
        InstitutionMembership.objects.create(user=self.admin, institution=self.b, role="institution_admin")
        self.assertEqual(self.delete(self.foreign).status_code, 404)
        self.assertTrue(Candidate.objects.filter(pk=self.foreign.pk).exists())
        self.assertTrue(Candidate.objects.filter(pk=self.own.pk).exists())

    def test_admin_in_a_teacher_in_b_cannot_delete_b(self):
        InstitutionMembership.objects.create(user=self.admin, institution=self.b, role="teacher")
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.b.pk))
        self.assertEqual(self.delete(self.foreign).status_code, 404)

    def test_linked_user_and_unrelated_memberships_are_retained(self):
        membership = InstitutionMembership.objects.create(user=self.learner, institution=self.b, role="student")
        other = Candidate.objects.create(institution=self.b, user=self.learner, candidate_id="OTHER", first_name="Other", last_name="Identity")
        self.assertEqual(self.delete(self.linked).status_code, 204)
        self.assertTrue(User.objects.filter(pk=self.learner.pk).exists())
        self.assertTrue(InstitutionMembership.objects.filter(pk=membership.pk).exists())
        self.assertTrue(Candidate.objects.filter(pk=other.pk, user=self.learner).exists())

    def test_ordinary_group_membership_cascades_without_deleting_group(self):
        group = Group.objects.create(institution=self.a, name="Group", code="DEL")
        membership = GroupMembership.objects.create(candidate=self.own, group=group)
        self.assertEqual(self.delete().status_code, 204)
        self.assertFalse(GroupMembership.objects.filter(pk=membership.pk).exists())
        self.assertTrue(Group.objects.filter(pk=group.pk).exists())

    def test_audit_survives_deletion_without_unnecessary_personal_data(self):
        candidate_pk = self.own.pk
        self.assertEqual(self.delete().status_code, 204)
        event = AuditEvent.objects.get(resource_type="candidates.candidate", resource_id=str(candidate_pk))
        self.assertEqual(event.institution_id, self.a.pk)
        self.assertEqual(event.actor_id, self.admin.pk)
        self.assertEqual(event.metadata, {"action": "candidate_deleted", "candidate_id": "A-1"})

    def test_audit_failure_rolls_back_deletion(self):
        for failure in (RuntimeError("Audit unavailable"), IntegrityError("Audit unavailable")):
            with patch("candidates.views.record_event", side_effect=failure):
                with self.assertRaises(type(failure)):
                    self.delete()
            self.assertTrue(Candidate.objects.filter(pk=self.own.pk).exists())

    def test_fk_protection_conflict_is_safe_and_rolls_back_audit(self):
        with patch("candidates.models.Candidate.delete", side_effect=ProtectedError("Protected history", [])):
            response = self.delete()
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Candidate.objects.filter(pk=self.own.pk).exists())
        self.assertFalse(AuditEvent.objects.exists())

    def test_deletion_rechecks_history_created_after_candidate_was_loaded(self):
        from .views import CandidateDeletionConflict, CandidateViewSet
        stale = Candidate.objects.get(pk=self.own.pk)
        attempt = self.history()
        view = CandidateViewSet()
        view.request = SimpleNamespace(user=self.admin)
        with self.assertRaises(CandidateDeletionConflict):
            view.perform_destroy(stale)
        self.assertTrue(Candidate.objects.filter(pk=stale.pk).exists())
        self.assertTrue(Attempt.objects.filter(pk=attempt.pk).exists())

    def test_concurrent_previous_delete_returns_not_found(self):
        from rest_framework.exceptions import NotFound
        from .views import CandidateViewSet
        stale = Candidate.objects.get(pk=self.own.pk)
        self.assertEqual(self.delete().status_code, 204)
        view = CandidateViewSet()
        view.request = SimpleNamespace(user=self.admin)
        with self.assertRaises(NotFound):
            view.perform_destroy(stale)
