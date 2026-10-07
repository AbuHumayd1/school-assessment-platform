import csv
import io
import json
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from audit.models import AuditEvent
from institutions.models import Institution
from questions.models import Question, QuestionOption, Topic
from subjects.models import Subject
from tenants.models import InstitutionMembership


class QuestionBankSearchTests(APITestCase):
    def setUp(self):
        self.school_a = Institution.objects.create(name="Search School A")
        self.school_b = Institution.objects.create(name="Search School B")
        self.teacher = self.make_user("search-a@example.test", self.school_a, "teacher")
        self.teacher_b = self.make_user("search-b@example.test", self.school_b, "teacher")
        self.subject = Subject.objects.create(institution=self.school_a, name="Mathematics", code="MATH")
        self.science = Subject.objects.create(institution=self.school_a, name="Science", code="SCI")
        self.subject_b = Subject.objects.create(institution=self.school_b, name="Mathematics", code="MATH")
        self.topic = Topic.objects.create(institution=self.school_a, subject=self.subject, name="Algebra")
        self.other_topic = Topic.objects.create(institution=self.school_a, subject=self.science, name="Biology")
        self.topic_b = Topic.objects.create(institution=self.school_b, subject=self.subject_b, name="Algebra")
        self.question = self.make_question(self.school_a, self.subject, self.topic, "Which value is prime?", "multiple_choice", "easy", "draft")
        self.question.explanation = "Do not search this explanation only token."
        self.question.save(update_fields=("explanation", "updated_at"))
        self.science_question = self.make_question(self.school_a, self.science, self.other_topic, "Name a cell part", "multiple_select", "hard", "approved")
        self.foreign_question = self.make_question(self.school_b, self.subject_b, self.topic_b, "Which value is prime?", "multiple_choice", "easy", "draft", self.teacher_b)
        self.client.force_authenticate(self.teacher)
        self.url = "/api/v1/questions/"

    @staticmethod
    def make_user(email, institution, role):
        user = User.objects.create_user(email, "Safe-search-test-pass")
        InstitutionMembership.objects.create(user=user, institution=institution, role=role)
        return user

    def make_question(self, institution, subject, topic, text, qtype, difficulty, qstatus, creator=None):
        question = Question.objects.create(
            institution=institution, subject=subject, topic=topic, question_type=qtype,
            difficulty=difficulty, text=text, status='draft',
            created_by=creator or self.teacher,
        )
        QuestionOption.objects.bulk_create([QuestionOption(question=question, text=str(order),
            order=order, is_correct=order == 1) for order in (1, 2)])
        if qstatus != 'draft':
            question.status = qstatus
            question.save(update_fields=['status'])
        return question

    def result_ids(self, query):
        response = self.client.get(f"{self.url}{query}")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {row["id"] for row in response.data}

    def test_search_results_are_tenant_isolated_even_for_matching_text(self):
        ids = self.result_ids("?search=prime")
        self.assertEqual(ids, {self.question.pk})
        self.assertNotIn(self.foreign_question.pk, ids)

    def test_subject_filter(self):
        self.assertEqual(self.result_ids(f"?subject={self.science.pk}"), {self.science_question.pk})

    def test_topic_filter(self):
        self.assertEqual(self.result_ids(f"?topic={self.topic.pk}"), {self.question.pk})

    def test_question_type_filter(self):
        self.assertEqual(self.result_ids("?question_type=multiple_select"), {self.science_question.pk})

    def test_difficulty_filter(self):
        self.assertEqual(self.result_ids("?difficulty=hard"), {self.science_question.pk})

    def test_status_filter(self):
        self.assertEqual(self.result_ids("?status=approved"), {self.science_question.pk})

    def test_is_active_filter_excludes_archived_questions(self):
        self.question.status = Question.Status.APPROVED
        self.question.save(update_fields=['status'])
        self.question.status = Question.Status.ARCHIVED
        self.question.save(update_fields=("status", "updated_at"))
        self.assertEqual(self.result_ids("?is_active=true"), {self.science_question.pk})
        self.assertEqual(self.result_ids("?is_active=false"), {self.question.pk})

    def test_text_search_is_case_insensitive_and_limited_to_question_text(self):
        self.assertEqual(self.result_ids("?search=PRIME"), {self.question.pk})
        self.assertEqual(self.result_ids("?search=not-present"), set())
        self.assertEqual(self.result_ids("?search=explanation-only-token"), set())

    def test_invalid_filter_values_follow_filter_contract(self):
        for query in ("?question_type=essay", "?difficulty=impossible", "?status=published"):
            response = self.client.get(f"{self.url}{query}")
            self.assertEqual(response.status_code, status.HTTP_200_OK, query)
            self.assertEqual(response.data, [], query)

        for query in ("?subject=bad", "?topic=-1", "?is_active=maybe"):
            response = self.client.get(f"{self.url}{query}")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, query)

    def test_overlong_search_is_rejected(self):
        response = self.client.get(f"{self.url}?search={'x' * 201}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class QuestionCsvImportTests(APITestCase):
    headers = (
        "question_text", "question_type", "difficulty", "marks", "subject_code",
        "topic_name", "options", "correct_options", "explanation", "learning_objective",
    )
    url = "/api/v1/questions/import/"

    def setUp(self):
        self.school_a = Institution.objects.create(name="Import School A")
        self.school_b = Institution.objects.create(name="Import School B")
        self.teacher = self.make_user("import-teacher@example.test", self.school_a, "teacher")
        self.examiner = self.make_user("import-examiner@example.test", self.school_a, "examiner")
        self.admin = self.make_user("import-admin@example.test", self.school_a, "institution_admin")
        self.student = self.make_user("import-student@example.test", self.school_a, "student")
        self.teacher_b = self.make_user("import-teacher-b@example.test", self.school_b, "teacher")
        self.subject = Subject.objects.create(institution=self.school_a, name="Mathematics", code="MATH")
        self.subject_b = Subject.objects.create(institution=self.school_b, name="Biology", code="BIO")
        self.topic = Topic.objects.create(institution=self.school_a, subject=self.subject, name="Algebra")
        self.topic_b = Topic.objects.create(institution=self.school_b, subject=self.subject_b, name="Genetics")
        self.client.force_authenticate(self.teacher)

    @staticmethod
    def make_user(email, institution, role):
        user = User.objects.create_user(email, "Safe-import-test-pass")
        InstitutionMembership.objects.create(user=user, institution=institution, role=role)
        return user

    def row(self, **overrides):
        values = {
            "question_text": "Which number is prime?",
            "question_type": "multiple_choice",
            "difficulty": "medium",
            "marks": "1.50",
            "subject_code": "MATH",
            "topic_name": "Algebra",
            "options": json.dumps(["9", "11", "15"]),
            "correct_options": json.dumps([2]),
            "explanation": "11 has exactly two positive divisors.",
            "learning_objective": "Identify prime numbers.",
        }
        values.update(overrides)
        return values

    def csv_bytes(self, rows, headers=None):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=headers or self.headers)
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode("utf-8")

    def upload(self, content):
        return SimpleUploadedFile("questions.csv", content, content_type="text/csv")

    def import_rows(self, rows, headers=None):
        return self.client.post(self.url, {"file": self.upload(self.csv_bytes(rows, headers))}, format="multipart")

    def test_teacher_imports_existing_question_fields_as_draft(self):
        response = self.import_rows([self.row()])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["total_rows"], 1)
        self.assertEqual(response.data["imported_rows"], 1)
        self.assertEqual(response.data["failed_rows"], 0)
        question = Question.objects.get(institution=self.school_a)
        self.assertEqual(question.status, Question.Status.DRAFT)
        self.assertEqual(question.created_by, self.teacher)
        self.assertEqual(question.subject, self.subject)
        self.assertEqual(question.topic, self.topic)
        self.assertEqual(question.marks, Decimal("1.50"))
        self.assertEqual(list(question.options.values_list("text", "is_correct", "order")), [
            ("9", False, 1), ("11", True, 2), ("15", False, 3),
        ])

    def test_imported_question_must_follow_existing_review_workflow(self):
        imported = self.import_rows([self.row()])
        question_id = Question.objects.get(institution=self.school_a).pk
        self.assertEqual(imported.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Question.objects.get(pk=question_id).status, Question.Status.DRAFT)
        submitted = self.client.post(f"/api/v1/questions/{question_id}/submit-for-review/")
        self.assertEqual(submitted.status_code, status.HTTP_200_OK, submitted.data)
        self.client.force_authenticate(self.admin)
        approved = self.client.post(f"/api/v1/questions/{question_id}/approve/")
        self.assertEqual(approved.status_code, status.HTTP_200_OK, approved.data)
        self.assertEqual(approved.data["status"], Question.Status.APPROVED)

    def test_examiner_can_import_questions(self):
        self.client.force_authenticate(self.examiner)
        self.assertEqual(self.import_rows([self.row()]).status_code, status.HTTP_201_CREATED)

    def test_institution_admin_can_import_questions(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.import_rows([self.row()]).status_code, status.HTTP_201_CREATED)

    def test_student_cannot_import_questions(self):
        self.client.force_authenticate(self.student)
        response = self.import_rows([self.row()])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Question.objects.count(), 0)

    def test_unauthenticated_user_cannot_import_questions(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.import_rows([self.row()]).status_code, (401, 403))

    def test_foreign_institution_context_is_rejected(self):
        response = self.client.post(
            self.url, {"file": self.upload(self.csv_bytes([self.row()]))}, format="multipart",
            HTTP_X_INSTITUTION_ID=str(self.school_b.pk),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Question.objects.count(), 0)

    def test_foreign_subject_code_is_rejected(self):
        response = self.import_rows([self.row(subject_code=self.subject_b.code)])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("subject_code", response.data["errors"][0]["errors"])
        self.assertEqual(Question.objects.count(), 0)

    def test_foreign_topic_name_is_rejected(self):
        response = self.import_rows([self.row(topic_name=self.topic_b.name)])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("topic_name", response.data["errors"][0]["errors"])
        self.assertEqual(Question.objects.count(), 0)

    def test_unknown_subject_code_is_rejected(self):
        response = self.import_rows([self.row(subject_code="UNKNOWN")])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("subject_code", response.data["errors"][0]["errors"])

    def test_malformed_csv_returns_file_error(self):
        broken = (",".join(self.headers) + '\n"unfinished').encode("utf-8")
        response = self.client.post(self.url, {"file": self.upload(broken)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["errors"])
        self.assertEqual(Question.objects.count(), 0)

    def test_missing_required_header_is_rejected(self):
        headers = tuple(header for header in self.headers if header != "subject_code")
        response = self.import_rows([{key: value for key, value in self.row().items() if key in headers}], headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Question.objects.count(), 0)

    def test_client_cannot_add_institution_column_to_import(self):
        headers = (*self.headers, "institution")
        row = self.row(institution=str(self.school_b.pk))
        response = self.import_rows([row], headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Question.objects.count(), 0)

    def test_invalid_question_type_is_reported_for_its_row(self):
        response = self.import_rows([self.row(question_type="essay")])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["errors"][0]["row"], 2)
        self.assertIn("question_type", response.data["errors"][0]["errors"])

    def test_malformed_options_json_is_reported(self):
        response = self.import_rows([self.row(options="not-json")])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("options", response.data["errors"][0]["errors"])

    def test_multiple_choice_requires_exactly_one_correct_option(self):
        response = self.import_rows([self.row(correct_options="[]")])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("options", response.data["errors"][0]["errors"])

    def test_invalid_correct_option_position_is_reported(self):
        response = self.import_rows([self.row(correct_options="[4]")])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("correct_options", response.data["errors"][0]["errors"])

    def test_true_false_option_rules_are_enforced(self):
        response = self.import_rows([self.row(question_type="true_false")])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("options", response.data["errors"][0]["errors"])

    def test_marks_must_pass_existing_question_validation(self):
        response = self.import_rows([self.row(marks="0")])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("marks", response.data["errors"][0]["errors"])

    def test_invalid_difficulty_is_reported(self):
        response = self.import_rows([self.row(difficulty="extreme")])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("difficulty", response.data["errors"][0]["errors"])

    def test_one_invalid_row_prevents_all_rows_from_being_created(self):
        response = self.import_rows([self.row(), self.row(subject_code="MISSING")])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["total_rows"], 2)
        self.assertEqual(response.data["imported_rows"], 0)
        self.assertEqual(response.data["failed_rows"], 1)
        self.assertEqual(Question.objects.count(), 0)

    def test_valid_file_imports_all_rows(self):
        response = self.import_rows([self.row(), self.row(question_text="Which shape has three sides?")])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["imported_rows"], 2)
        self.assertEqual(Question.objects.filter(institution=self.school_a).count(), 2)

    def test_duplicate_wording_is_not_rejected(self):
        response = self.import_rows([self.row(), self.row()])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Question.objects.filter(text="Which number is prime?").count(), 2)

    def test_successful_import_is_audited_without_question_content(self):
        self.import_rows([self.row()])
        event = AuditEvent.objects.get(event_type=AuditEvent.Type.QUESTION_IMPORT)
        self.assertEqual(event.institution, self.school_a)
        self.assertEqual(event.actor, self.teacher)
        self.assertEqual(event.metadata, {"outcome": "imported", "total_rows": 1, "imported_rows": 1, "failed_rows": 0})
        self.assertNotIn("Which number is prime?", str(event.metadata))

    def test_rejected_import_is_audited(self):
        self.import_rows([self.row(subject_code="MISSING")])
        event = AuditEvent.objects.get(event_type=AuditEvent.Type.QUESTION_IMPORT)
        self.assertEqual(event.metadata["outcome"], "rejected")
        self.assertEqual(event.metadata["imported_rows"], 0)

    def test_import_response_does_not_return_correctness_or_question_content(self):
        response = self.import_rows([self.row()])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("options", response.data)
        self.assertNotIn("question_text", response.data)
        self.assertNotIn("is_correct", str(response.data))

    def test_missing_upload_returns_structured_error_without_creation(self):
        response = self.client.post(self.url, {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["imported_rows"], 0)
        self.assertEqual(Question.objects.count(), 0)
