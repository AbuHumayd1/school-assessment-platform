import copy
import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from assessments.views import AssessmentViewSet
from audit.models import AuditEvent
from institutions.models import Institution
from questions.management.commands import clone_prepared_question_batch as clone
from questions.models import DocxImportSession, Question, QuestionMedia, QuestionOption
from subjects.models import Subject
from tenants.models import InstitutionMembership


class ClonePreparedQuestionBatchTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = FileSystemStorage(location=self.directory.name)
        storage_patch = patch.object(QuestionMedia._meta.get_field("file"), "storage", self.storage)
        storage_patch.start()
        self.addCleanup(storage_patch.stop)
        self.source = Institution.objects.create(name="Demo Training Institute")
        self.destination = Institution.objects.create(name="ACTIVUS HEALTHCARE", workspace_mode="managed_exam")
        self.actor = User.objects.create_superuser("clone-platform@example.test", "Strong-clone-password-42")
        self.subject = Subject.objects.create(institution=self.source, name=clone.SUBJECT_NAME, code=clone.SUBJECT_CODE)
        self.session = DocxImportSession.objects.create(id=clone.SOURCE_SESSION, institution=self.source,
            uploaded_by=self.actor, revision=22, confirmed_at=timezone.now(), expires_at=timezone.now(), preview={})
        self.questions = []
        section_titles = [title for title, count in clone.SECTION_COUNTS.items() for _ in range(count)]
        for index in range(151):
            metadata = {"section_title": section_titles[index], "section_order": list(clone.SECTION_COUNTS).index(section_titles[index]),
                        "document_order": index + 1, "question_number": index + 1, "review_modified": index % 2 == 0,
                        "equations": ([{"status": "converted", "representation": "V=IR"}] if index < 11 else [])}
            question = Question.objects.create(institution=self.source, subject=self.subject,
                created_by=self.actor, question_type="true_false" if index >= 147 else "multiple_choice",
                text=f"Prepared question {index}: V=IR", explanation="Prepared explanation",
                learning_objective="Prepared objective", source="DOCX", source_metadata=metadata)
            option_count = 2 if index >= 147 else 5 if index < 102 else 4
            QuestionOption.objects.bulk_create([QuestionOption(question=question, text=f"Option {order} Ω",
                order=order, is_correct=order == 2) for order in range(1, option_count + 1)])
            self.questions.append(question)
        self.ids = [q.pk for q in self.questions]
        self.session.metadata = {"subject": self.subject.pk, "topic": None,
            "completion": {"created_question_ids": self.ids, "imported_count": 151, "question_status": "draft"}}
        self.session.save()
        image = io.BytesIO()
        Image.new("RGB", (2, 3), "blue").save(image, format="PNG")
        for index, question in enumerate(self.questions[:4]):
            asset = QuestionMedia(question=question, parsed_id=f"m{index}", caption="Prepared caption",
                                  alt_text="Prepared illustration", source_metadata={"status": "converted", "source_order": index})
            asset.file.save(f"source-{index}.png", ContentFile(image.getvalue()), save=True)
        self.fingerprint = clone.source_fingerprint(self.session, self.ids)
        fingerprint_patch = patch.object(clone, "SOURCE_FINGERPRINT", self.fingerprint)
        fingerprint_patch.start()
        self.addCleanup(fingerprint_patch.stop)
        self.source_files = self.files()

    def files(self):
        return {str(path.relative_to(self.directory.name)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in Path(self.directory.name).rglob("*") if path.is_file()}

    def run_command(self, **overrides):
        options = dict(source_session=clone.SOURCE_SESSION, expected_revision=22, expected_question_count=151,
                       destination_institution=self.destination.pk, actor=self.actor.pk,
                       expected_source_fingerprint=self.fingerprint)
        options.update(overrides)
        output = io.StringIO()
        call_command("clone_prepared_question_batch", stdout=output, **options)
        return json.loads(output.getvalue())

    def assert_source_unchanged(self):
        self.assertEqual(clone.source_fingerprint(self.session, self.ids), self.fingerprint)
        self.assertEqual(Question.objects.filter(institution=self.source, status="draft").count(), 151)
        for name, digest in self.source_files.items():
            self.assertEqual(self.files().get(name), digest)

    def assert_no_destination(self):
        self.assertFalse(Question.objects.filter(institution=self.destination).exists())
        self.assertFalse(Subject.objects.filter(institution=self.destination).exists())
        self.assertFalse(AuditEvent.objects.filter(institution=self.destination).exists())
        self.assertEqual(self.files(), self.source_files)
        self.assert_source_unchanged()

    def test_default_dry_run_creates_no_records_or_files(self):
        manifest = self.run_command()
        self.assertEqual(manifest["mode"], "dry_run")
        self.assertEqual(manifest["counts"], {"questions": 151, "options": 698, "media": 4, "converted_equations": 11})
        self.assert_no_destination()

    def test_apply_preserves_content_options_media_ownership_and_approves_only_copies(self):
        manifest = self.run_command(apply=True)
        self.assertEqual(len(manifest["mapping"]), 151)
        subject = Subject.objects.get(institution=self.destination)
        copies = list(Question.objects.filter(institution=self.destination).order_by("pk"))
        self.assertEqual(len(copies), 151)
        for original, question in zip(self.questions, copies):
            self.assertNotEqual(original.pk, question.pk)
            self.assertEqual(clone.canonical(original), clone.canonical(question, destination=True))
            self.assertEqual(question.status, "approved")
            self.assertEqual(question.subject_id, subject.pk)
            self.assertIsNone(question.topic_id)
            self.assertEqual(question.created_by_id, self.actor.pk)
            self.assertEqual(question.reviewed_by_id, self.actor.pk)
            self.assertGreater(question.created_at, original.created_at)
            self.assertEqual(question.source_metadata[clone.LINEAGE]["source_question_id"], original.pk)
            question.full_clean()
        self.assertEqual(QuestionOption.objects.filter(question__institution=self.destination).count(), 698)
        new_assets = QuestionMedia.objects.filter(question__institution=self.destination)
        self.assertEqual(new_assets.count(), 4)
        for asset in new_assets:
            self.assertNotIn(asset.file.name, self.source_files)
            self.assertIsNone(asset.import_session_id)
            self.assertNotIn(asset.pk, QuestionMedia.objects.filter(question__institution=self.source).values_list("pk", flat=True))
        self.assertEqual(len(self.files()), 8)
        self.assertEqual(manifest["content_fingerprint"], manifest["destination_verification_fingerprint"])
        event = AuditEvent.objects.get(institution=self.destination,
            event_type='question_import', metadata__operation=clone.OPERATION)
        self.assertEqual(event.actor, self.actor)
        self.assertEqual(event.metadata["operation"], clone.OPERATION)
        self.assertNotIn("Option", json.dumps(event.metadata))
        self.assertNotIn("is_correct", json.dumps(event.metadata))
        self.assert_source_unchanged()
        request = APIRequestFactory().get("/api/v1/assessments/question-options/", {"subject": subject.pk},
                                         HTTP_X_INSTITUTION_ID=str(self.destination.pk))
        force_authenticate(request, user=self.actor)
        response = AssessmentViewSet.as_view({"get": "question_options"})(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 151)

    def test_unauthorized_and_inactive_actor_rejected(self):
        user = User.objects.create_user("clone-client@example.test", is_staff=True)
        InstitutionMembership.objects.create(user=user, institution=self.destination, role="institution_admin")
        with self.assertRaisesMessage(CommandError, "Platform Administrator"):
            self.run_command(actor=user.pk)
        self.actor.is_active = False
        self.actor.save(update_fields=["is_active"])
        with self.assertRaises(CommandError):
            self.run_command()
        self.assert_no_destination()

    def test_active_platform_membership_actor_supported(self):
        user = User.objects.create_user("clone-member@example.test")
        membership = InstitutionMembership.objects.create(user=user, institution=self.source, role="platform_admin")
        self.assertEqual(self.run_command(actor=user.pk)["mode"], "dry_run")
        membership.is_active = False
        membership.save()
        with self.assertRaises(CommandError):
            self.run_command(actor=user.pk)

    def test_wrong_session_revision_count_or_expected_fingerprint_rejected(self):
        for overrides in ({"source_session": "bad"}, {"expected_revision": 21},
                          {"expected_question_count": 150}, {"expected_source_fingerprint": "0" * 64}):
            with self.subTest(overrides=overrides), self.assertRaises(CommandError):
                self.run_command(**overrides)
        self.assert_no_destination()

    def test_changed_source_fingerprint_rejected(self):
        Question.objects.filter(pk=self.ids[0]).update(text="Changed prepared content")
        with self.assertRaisesMessage(CommandError, "fingerprint"):
            self.run_command(apply=True)
        self.assertFalse(Question.objects.filter(institution=self.destination).exists())
        self.assertEqual(self.files(), self.source_files)

    def test_malformed_or_duplicate_receipt_rejected(self):
        metadata = copy.deepcopy(self.session.metadata)
        metadata["completion"]["created_question_ids"][-1] = self.ids[0]
        self.session.metadata = metadata
        self.session.save()
        with self.assertRaisesMessage(CommandError, "receipt"):
            self.run_command()

    def test_destination_subject_conflicts_rejected(self):
        Subject.objects.create(institution=self.destination, name="Unrelated subject", code=clone.SUBJECT_CODE)
        with self.assertRaisesMessage(CommandError, "subject conflict"):
            self.run_command(apply=True)
        self.assertFalse(Question.objects.filter(institution=self.destination).exists())

    def test_exact_unused_subject_reused(self):
        subject = Subject.objects.create(institution=self.destination, name=clone.SUBJECT_NAME, code=clone.SUBJECT_CODE)
        self.assertEqual(self.run_command()["subject_action"], "reuse")
        self.assertEqual(self.run_command(apply=True)["destination_subject_id"], subject.pk)
        self.assertEqual(Subject.objects.filter(institution=self.destination).count(), 1)

    def test_rerun_refuses_without_creating_duplicates(self):
        self.run_command(apply=True)
        with self.assertRaisesMessage(CommandError, "already been productionized"):
            self.run_command(apply=True)
        self.assertEqual(Question.objects.filter(institution=self.destination).count(), 151)

    def test_audit_marker_alone_prevents_duplicate_apply(self):
        AuditEvent.objects.create(institution=self.destination, actor=self.actor, event_type="question_import",
            resource_type="subjects.subject", resource_id="previous",
            metadata={"operation": clone.OPERATION, "source_import_session_uuid": clone.SOURCE_SESSION})
        with self.assertRaisesMessage(CommandError, "already been productionized"):
            self.run_command(apply=True)
        self.assertFalse(Question.objects.filter(institution=self.destination).exists())

    def test_lineage_protects_rerun_without_audit_marker(self):
        self.run_command(apply=True)
        with patch.object(clone.AuditEvent.objects, "filter") as audit_filter:
            audit_filter.return_value.exists.return_value = False
            with self.assertRaisesMessage(CommandError, "already been productionized"):
                self.run_command(apply=True)
        self.assertEqual(Question.objects.filter(institution=self.destination).count(), 151)

    def test_audit_failure_rolls_back_all_rows_and_cleans_only_destination_files(self):
        with patch.object(clone, "record_event", side_effect=IntegrityError("audit failure")):
            with self.assertRaises(CommandError):
                self.run_command(apply=True)
        self.assert_no_destination()

    def test_media_save_failure_cleans_new_files_and_preserves_source(self):
        with patch.object(QuestionMedia, "save", side_effect=IntegrityError("media failure")):
            with self.assertRaises(CommandError):
                self.run_command(apply=True)
        self.assert_no_destination()

    def test_approval_failure_rolls_back_drafts_and_files(self):
        with patch.object(clone.Command, "approve", side_effect=CommandError("approval failure")):
            with self.assertRaisesMessage(CommandError, "approval failure"):
                self.run_command(apply=True)
        self.assert_no_destination()

    def test_missing_media_aborts_before_any_write(self):
        original = QuestionMedia.objects.filter(question__institution=self.source).first()
        self.storage.delete(original.file.name)
        with self.assertRaisesMessage(CommandError, "media file is missing"):
            self.run_command(apply=True)
        self.assertFalse(Subject.objects.filter(institution=self.destination).exists())

    def test_invalid_option_payload_aborts_before_any_write(self):
        QuestionOption.objects.filter(question_id=self.ids[0]).update(is_correct=False)
        new_fingerprint = clone.source_fingerprint(self.session, self.ids)
        with patch.object(clone, "SOURCE_FINGERPRINT", new_fingerprint):
            with self.assertRaisesMessage(CommandError, "objective payload"):
                self.run_command(apply=True, expected_source_fingerprint=new_fingerprint)
        self.assertFalse(Subject.objects.filter(institution=self.destination).exists())

    def test_wrong_source_asset_count_aborts_before_any_write(self):
        QuestionMedia.objects.filter(question__institution=self.source).first().delete()
        fingerprint = clone.source_fingerprint(self.session, self.ids)
        with patch.object(clone, "SOURCE_FINGERPRINT", fingerprint):
            with self.assertRaisesMessage(CommandError, "counts"):
                self.run_command(apply=True, expected_source_fingerprint=fingerprint)
        self.assertFalse(Subject.objects.filter(institution=self.destination).exists())
