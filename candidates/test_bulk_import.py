import io
import zipfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from institutions.models import Institution
from tenants.models import InstitutionMembership
from .models import Candidate


class CandidateBulkImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = Institution.objects.create(name="Managed import", workspace_mode="managed_exam")
        cls.other = Institution.objects.create(name="Other import")
        cls.admin = User.objects.create_user("import@example.test", "import-password-123")
        cls.other_admin = User.objects.create_user("other-import@example.test", "import-password-123")
        for actor in (cls.admin, cls.other_admin):
            InstitutionMembership.objects.create(institution=cls.school, user=actor, role="institution_admin")
        Candidate.objects.create(institution=cls.school, candidate_id="EXISTING", first_name="Old", last_name="Name")
        Candidate.objects.create(institution=cls.other, candidate_id="FOREIGN", first_name="Other", last_name="Name")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))

    def preview(self, content="first_name,last_name,candidate_id,email\nAmina,Person,001,\nNew,Person,,\n", name="candidates.csv"):
        upload = SimpleUploadedFile(name, content.encode() if isinstance(content, str) else content)
        return self.client.post("/api/v1/candidates/import-preview/", {"file": upload}, format="multipart")

    def confirm(self, token):
        return self.client.post("/api/v1/candidates/import-confirm/", {"token": token}, format="json")

    def test_preview_is_read_only_and_confirm_preserves_id_without_accounts(self):
        original_users = User.objects.count()
        preview = self.preview()
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data["errors"], [])
        self.assertEqual(Candidate.objects.count(), 2)
        self.assertTrue(preview.data["rows"][1]["candidate_id"].startswith("C-"))
        response = self.confirm(preview.data["token"])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["created_count"], 2)
        candidate = Candidate.objects.get(institution=self.school, candidate_id="001")
        self.assertEqual(candidate.email, "")
        self.assertIsNone(candidate.user_id)
        self.assertEqual(User.objects.count(), original_users)
        from assessments.quick_models import QuickExamCredential
        self.assertEqual(QuickExamCredential.objects.count(), 0)
        self.assertEqual(self.confirm(preview.data["token"]).status_code, 400)
        self.assertEqual(Candidate.objects.count(), 4)

    def test_row_validation_blocks_whole_file(self):
        response = self.preview("first_name,last_name,candidate_id,email\n,,ID,bad\nA,B,SAME,\nA,B,SAME,\nX,Y,EXISTING,\n")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["token"])
        self.assertEqual([row["row"] for row in response.data["errors"]], [2, 4, 5])
        self.assertEqual(Candidate.objects.count(), 2)

    def test_duplicate_rows_without_ids_are_detected(self):
        response = self.preview("full_name\nAmina Person\nAmina Person\n")
        self.assertIsNone(response.data["token"])
        self.assertIn("row", response.data["errors"][0]["errors"])

    def test_foreign_id_is_allowed_in_current_tenant(self):
        response = self.preview("candidate_name,candidate_id\nAmina Person,FOREIGN\n")
        self.assertEqual(self.confirm(response.data["token"]).status_code, 201)
        self.assertEqual(Candidate.objects.filter(candidate_id="FOREIGN").count(), 2)

    def test_token_bound_to_actor_institution_and_current_authority(self):
        token = self.preview().data["token"]
        self.client.force_authenticate(self.other_admin)
        self.assertEqual(self.confirm(token).status_code, 400)
        self.client.force_authenticate(self.admin)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.other.pk))
        self.assertIn(self.confirm(token).status_code, (403, 404))
        InstitutionMembership.objects.create(institution=self.other, user=self.admin, role="institution_admin")
        self.assertEqual(self.confirm(token).status_code, 400)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.school.pk))
        self.admin.institution_memberships.filter(institution=self.school).update(is_active=False)
        self.assertIn(self.confirm(token).status_code, (403, 404))

    def test_confirmation_revalidates_conflicts_and_is_atomic(self):
        token = self.preview().data["token"]
        Candidate.objects.create(institution=self.school, candidate_id="001", first_name="Concurrent", last_name="Person")
        self.assertEqual(self.confirm(token).status_code, 400)
        self.assertEqual(Candidate.objects.count(), 3)

    def test_database_failure_rolls_back_earlier_rows(self):
        token = self.preview().data["token"]
        original_save = Candidate.save
        calls = []
        def save(instance, *args, **kwargs):
            calls.append(instance)
            if len(calls) == 2:
                raise IntegrityError("Concurrent conflict")
            return original_save(instance, *args, **kwargs)
        with patch.object(Candidate, "save", save):
            self.assertEqual(self.confirm(token).status_code, 400)
        self.assertEqual(Candidate.objects.count(), 2)

    def test_tampered_expired_missing_tokens(self):
        token = self.preview().data["token"]
        self.assertEqual(self.confirm(token + "x").status_code, 400)
        self.assertEqual(self.confirm(None).status_code, 400)
        with patch("django.core.signing.time.time", return_value=9999999999):
            self.assertEqual(self.confirm(token).status_code, 400)

    def test_malformed_unsupported_empty_and_oversize_files(self):
        for content, name in (("bad", "file.txt"), ("bad", "file.xlsx"), ("wrong\nA\n", "file.csv"),
                              ("first_name,last_name\n", "file.csv"), ("first_name,last_name\nA,B,C\n", "file.csv"),
                              (b"\xff\xff", "file.csv"), (b"x" * (2 * 1024 * 1024 + 1), "file.csv")):
            self.assertEqual(self.preview(content, name).status_code, 400, name)

    def test_row_limit_and_lengths(self):
        self.assertEqual(self.preview("first_name,last_name\n" + "A,B\n" * 1001).status_code, 400)
        response = self.preview("first_name,last_name\n" + "A" * 151 + ",B\n")
        self.assertIsNone(response.data["token"])

    def test_xlsx_inline_text_and_shared_strings(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Candidates" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            archive.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Amina Person</t></si></sst>')
            archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>full_name</t></is></c><c r="B1" t="inlineStr"><is><t>candidate_id</t></is></c></row><row r="2"><c r="A2" t="s"><v>0</v></c><c r="B2" t="inlineStr"><is><t>0007</t></is></c></row></sheetData></worksheet>')
        response = self.preview(buffer.getvalue(), "candidates.xlsx")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["rows"][0]["candidate_id"], "0007")
        self.assertEqual(self.confirm(response.data["token"]).status_code, 201)

    def test_anonymous_and_student_cannot_preview_or_confirm(self):
        for actor in (None, User.objects.create_user("student-import@example.test")):
            self.client.force_authenticate(actor)
            self.assertIn(self.preview().status_code, (401, 403))
            self.assertIn(self.confirm("invalid").status_code, (401, 403))
