from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from institutions.models import Institution
from questions.models import Question, QuestionOption, Topic
from questions.serializers import QuestionSerializer, TopicSerializer
from subjects.models import Subject
from tenants.models import InstitutionMembership


class QuestionBankAPITests(APITestCase):
    def setUp(self):
        self.institution_a = Institution.objects.create(name="Institution A")
        self.institution_b = Institution.objects.create(name="Institution B")
        self.teacher = self.make_user("teacher@example.test", self.institution_a, "teacher")
        self.teacher_b = self.make_user("teacher-b@example.test", self.institution_b, "teacher")
        self.examiner = self.make_user("examiner@example.test", self.institution_a, "examiner")
        self.admin = self.make_user("admin@example.test", self.institution_a, "institution_admin")
        self.student = self.make_user("student@example.test", self.institution_a, "student")
        self.subject_a = Subject.objects.create(institution=self.institution_a, name="Mathematics", code="MATH")
        self.subject_a2 = Subject.objects.create(institution=self.institution_a, name="Science", code="SCI")
        self.subject_b = Subject.objects.create(institution=self.institution_b, name="Mathematics", code="MATH")
        self.topic_a = Topic.objects.create(institution=self.institution_a, subject=self.subject_a, name="Algebra")
        self.topic_b = Topic.objects.create(institution=self.institution_b, subject=self.subject_b, name="Algebra")
        self.client.force_authenticate(self.teacher)

    @staticmethod
    def make_user(email, institution, role):
        user = User.objects.create_user(email, "safe-test-password")
        InstitutionMembership.objects.create(user=user, institution=institution, role=role)
        return user

    def question_payload(self, **overrides):
        payload = {
            "subject": self.subject_a.pk,
            "topic": self.topic_a.pk,
            "question_type": "multiple_choice",
            "difficulty": "medium",
            "text": "Which value is prime?",
            "explanation": "A prime has two positive divisors.",
            "marks": "1.50",
            "source": "Practice set",
            "source_year": 2025,
            "learning_objective": "Recognise prime numbers",
            "options": [
                {"text": "9", "is_correct": False, "order": 1},
                {"text": "11", "is_correct": True, "order": 2},
            ],
        }
        payload.update(overrides)
        return payload

    def create_question(self, **overrides):
        return self.client.post("/api/v1/questions/", self.question_payload(**overrides), format="json")

    def test_topic_creation_hierarchy_and_institution_assignment(self):
        response = self.client.post("/api/v1/topics/", {
            "subject": self.subject_a.pk, "parent": self.topic_a.pk, "name": "Linear equations",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["institution"], self.institution_a.pk)
        self.assertEqual(response.data["parent"], self.topic_a.pk)

    def test_topic_rejects_foreign_subject_and_parent(self):
        foreign_subject = self.client.post("/api/v1/topics/", {"subject": self.subject_b.pk, "name": "Foreign"}, format="json")
        foreign_parent = self.client.post("/api/v1/topics/", {"subject": self.subject_a.pk, "parent": self.topic_b.pk, "name": "Foreign parent"}, format="json")
        self.assertEqual(foreign_subject.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(foreign_parent.status_code, status.HTTP_400_BAD_REQUEST)

    def test_topic_rejects_parent_from_another_subject_and_cycles(self):
        cross_subject = self.client.post("/api/v1/topics/", {"subject": self.subject_a2.pk, "parent": self.topic_a.pk, "name": "Invalid"}, format="json")
        self.assertEqual(cross_subject.status_code, status.HTTP_400_BAD_REQUEST)
        child = Topic.objects.create(institution=self.institution_a, subject=self.subject_a, parent=self.topic_a, name="Child")
        cycle = self.client.patch(f"/api/v1/topics/{self.topic_a.pk}/", {"parent": child.pk}, format="json")
        self.assertEqual(cycle.status_code, status.HTTP_400_BAD_REQUEST)

    def test_topic_filters(self):
        response = self.client.get(f"/api/v1/topics/?subject={self.subject_a.pk}&is_active=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [self.topic_a.pk])
        invalid = self.client.get("/api/v1/topics/?is_active=perhaps")
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

    def test_question_types_options_and_metadata(self):
        mcq = self.create_question()
        self.assertEqual(mcq.status_code, status.HTTP_201_CREATED, mcq.data)
        self.assertEqual(mcq.data["status"], "draft")
        self.assertEqual(mcq.data["created_by"], self.teacher.pk)
        self.assertEqual(mcq.data["institution"], self.institution_a.pk)
        self.assertEqual(Decimal(mcq.data["marks"]), Decimal("1.50"))
        self.assertEqual([option["order"] for option in mcq.data["options"]], [1, 2])
        self.assertIn("is_correct", mcq.data["options"][0])

        multiple = self.create_question(question_type="multiple_select", options=[
            {"text": "A", "is_correct": True, "order": 1},
            {"text": "B", "is_correct": True, "order": 2},
            {"text": "C", "is_correct": False, "order": 3},
        ])
        self.assertEqual(multiple.status_code, status.HTTP_201_CREATED, multiple.data)
        self.assertEqual(sum(option["is_correct"] for option in multiple.data["options"]), 2)

        true_false = self.create_question(question_type="true_false", options=[
            {"text": "True", "is_correct": True, "order": 1},
            {"text": "False", "is_correct": False, "order": 2},
        ])
        self.assertEqual(true_false.status_code, status.HTTP_201_CREATED, true_false.data)

    def test_question_rejects_invalid_option_configurations(self):
        no_correct = self.create_question(options=[
            {"text": "A", "is_correct": False, "order": 1},
            {"text": "B", "is_correct": False, "order": 2},
        ])
        two_correct_mcq = self.create_question(options=[
            {"text": "A", "is_correct": True, "order": 1},
            {"text": "B", "is_correct": True, "order": 2},
        ])
        no_options = self.create_question(options=[])
        bad_true_false = self.create_question(question_type="true_false", options=[
            {"text": "True", "is_correct": True, "order": 1},
            {"text": "False", "is_correct": True, "order": 2},
            {"text": "Maybe", "is_correct": False, "order": 3},
        ])
        self.assertEqual(no_correct.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(two_correct_mcq.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(no_options.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(bad_true_false.status_code, status.HTTP_400_BAD_REQUEST)

    def test_marks_source_year_and_option_order_validation(self):
        bad_marks = self.create_question(marks="0")
        future_year = self.create_question(source_year=9999)
        duplicate_order = self.create_question(options=[
            {"text": "A", "is_correct": True, "order": 1},
            {"text": "B", "is_correct": False, "order": 1},
        ])
        self.assertEqual(bad_marks.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(future_year.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(duplicate_order.status_code, status.HTTP_400_BAD_REQUEST)

    def test_question_rejects_foreign_subject_topic_and_client_tenant_assignment(self):
        foreign_subject = self.create_question(subject=self.subject_b.pk, topic=None)
        foreign_topic = self.create_question(topic=self.topic_b.pk)
        client_institution = self.create_question(institution=self.institution_b.pk)
        self.assertEqual(foreign_subject.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(foreign_topic.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(client_institution.status_code, status.HTTP_201_CREATED)
        # institution is read-only: the request cannot override server-derived Institution A.
        self.assertEqual(client_institution.data["institution"], self.institution_a.pk)

    def test_multiple_institution_creator_must_select_authorized_tenant(self):
        InstitutionMembership.objects.create(user=self.teacher, institution=self.institution_b, role="teacher")
        ambiguous = self.create_question()
        selected = self.client.post(
            "/api/v1/questions/?institution=" + str(self.institution_b.pk),
            self.question_payload(subject=self.subject_b.pk, topic=self.topic_b.pk), format="json",
        )
        self.assertEqual(ambiguous.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(selected.status_code, status.HTTP_201_CREATED, selected.data)
        self.assertEqual(selected.data["institution"], self.institution_b.pk)

    def test_platform_admin_can_select_and_manage_another_institution(self):
        platform_admin = self.make_user("platform@example.test", self.institution_a, "platform_admin")
        self.client.force_authenticate(platform_admin)
        self.client.credentials(HTTP_X_INSTITUTION_ID=str(self.institution_b.pk))
        created = self.create_question(subject=self.subject_b.pk, topic=self.topic_b.pk)
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(created.data["institution"], self.institution_b.pk)

    def test_question_relationship_validation_and_model_clean(self):
        foreign = Question(
            institution=self.institution_a, subject=self.subject_b, topic=self.topic_a,
            question_type=Question.Type.MULTIPLE_CHOICE, text="Invalid", created_by=self.teacher,
        )
        with self.assertRaises(ValidationError):
            foreign.full_clean()

    def test_question_filters(self):
        question = self.create_question()
        self.assertEqual(question.status_code, status.HTTP_201_CREATED, question.data)
        filters = {
            "subject": self.subject_a.pk,
            "topic": self.topic_a.pk,
            "question_type": "multiple_choice",
            "difficulty": "medium",
            "status": "draft",
        }
        for key, value in filters.items():
            response = self.client.get(f"/api/v1/questions/?{key}={value}")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual([item["id"] for item in response.data], [question.data["id"]])
        self.assertEqual(self.client.get("/api/v1/questions/?difficulty=impossible").data, [])

    def test_workflow_transitions_and_unauthorized_approval(self):
        created = self.create_question()
        question_id = created.data["id"]
        submitted = self.client.post(f"/api/v1/questions/{question_id}/submit-for-review/")
        self.assertEqual(submitted.status_code, status.HTTP_200_OK, submitted.data)
        self.assertEqual(submitted.data["status"], "review")

        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.post(f"/api/v1/questions/{question_id}/approve/").status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.examiner)
        changes = self.client.post(f"/api/v1/questions/{question_id}/request-changes/")
        self.assertEqual(changes.status_code, status.HTTP_200_OK, changes.data)
        self.assertEqual(changes.data["status"], "draft")
        self.assertEqual(changes.data["reviewed_by"], self.examiner.pk)

        self.client.force_authenticate(self.teacher)
        self.client.post(f"/api/v1/questions/{question_id}/submit-for-review/")
        self.client.force_authenticate(self.admin)
        approved = self.client.post(f"/api/v1/questions/{question_id}/approve/")
        self.assertEqual(approved.status_code, status.HTTP_200_OK, approved.data)
        self.assertEqual(approved.data["status"], "approved")
        archived = self.client.post(f"/api/v1/questions/{question_id}/archive/")
        self.assertEqual(archived.status_code, status.HTTP_200_OK, archived.data)
        self.assertEqual(archived.data["status"], "archived")
        invalid = self.client.post(f"/api/v1/questions/{question_id}/submit-for-review/")
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creator_cannot_approve_and_student_cannot_manage_question_bank(self):
        created = self.create_question()
        self.client.post(f"/api/v1/questions/{created.data['id']}/submit-for-review/")
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.post(f"/api/v1/questions/{created.data['id']}/approve/").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get("/api/v1/questions/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post("/api/v1/questions/", self.question_payload(), format="json").status_code, status.HTTP_403_FORBIDDEN)

    def test_question_institution_is_not_client_assignable_and_reviewed_by_is_server_managed(self):
        response = self.client.post("/api/v1/questions/", self.question_payload(institution=self.institution_b.pk, reviewed_by=self.teacher_b.pk), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["institution"], self.institution_a.pk)
        self.assertIsNone(response.data["reviewed_by"])

    def test_foreign_tenant_topics_and_questions_are_hidden_for_all_operations(self):
        foreign_question = Question.objects.create(
            institution=self.institution_b, subject=self.subject_b, topic=self.topic_b,
            question_type=Question.Type.MULTIPLE_CHOICE, text="Foreign question", created_by=self.teacher_b,
        )
        QuestionOption.objects.create(question=foreign_question, text="Correct", is_correct=True, order=1)
        QuestionOption.objects.create(question=foreign_question, text="Wrong", is_correct=False, order=2)
        for base, foreign_id in (("/api/v1/topics/", self.topic_b.pk), ("/api/v1/questions/", foreign_question.pk)):
            listing = self.client.get(base)
            self.assertEqual(listing.status_code, status.HTTP_200_OK)
            self.assertNotIn(foreign_id, {item["id"] for item in listing.data})
            detail = f"{base}{foreign_id}/"
            self.assertEqual(self.client.get(detail).status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(self.client.patch(detail, {"name": "Tampered", "text": "Tampered"}, format="json").status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(self.client.delete(detail).status_code, status.HTTP_404_NOT_FOUND)

    def test_question_mutations_reject_foreign_subject_and_topic_ids(self):
        created = self.create_question()
        detail = f"/api/v1/questions/{created.data['id']}/"
        wrong_subject = self.client.patch(detail, {"subject": self.subject_b.pk}, format="json")
        wrong_topic = self.client.patch(detail, {"topic": self.topic_b.pk}, format="json")
        self.assertEqual(wrong_subject.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(wrong_topic.status_code, status.HTTP_400_BAD_REQUEST)

    def test_options_are_owned_by_question_and_answer_flags_are_not_client_writable_on_update(self):
        created = self.create_question()
        option = created.data["options"][0]
        detail = f"/api/v1/questions/{created.data['id']}/"
        response = self.client.patch(detail, {"options": [
            {"id": option["id"], "text": "Changed", "is_correct": True, "order": 1},
            {"text": "New", "is_correct": False, "order": 2},
        ]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([o["order"] for o in response.data["options"]], [1, 2])
        self.assertFalse(QuestionOption.objects.filter(pk=option["id"]).exists())

    def test_student_cannot_manage_topics(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get("/api/v1/topics/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post("/api/v1/topics/", {"subject": self.subject_a.pk, "name": "No"}, format="json").status_code, status.HTTP_403_FORBIDDEN)

    def test_related_field_querysets_are_tenant_scoped(self):
        request = Request(APIRequestFactory().get("/api/v1/questions/"))
        request.user = self.teacher
        topic_serializer = TopicSerializer(context={"request": request, "institution": self.institution_a})
        question_serializer = QuestionSerializer(context={"request": request, "institution": self.institution_a})
        self.assertNotIn(self.subject_b.pk, topic_serializer.fields["subject"].queryset.values_list("id", flat=True))
        self.assertNotIn(self.topic_b.pk, topic_serializer.fields["parent"].queryset.values_list("id", flat=True))
        self.assertNotIn(self.subject_b.pk, question_serializer.fields["subject"].queryset.values_list("id", flat=True))
        self.assertNotIn(self.topic_b.pk, question_serializer.fields["topic"].queryset.values_list("id", flat=True))
