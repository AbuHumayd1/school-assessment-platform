from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from assessments.models import Assessment, AssessmentQuestion, QuickExamCredential
from assessments.quick_services import configure_quick_access, generate_credential, reset_credential
from attempts.models import Attempt
from attempts.services import _validate_assessment_for_candidate
from attempts.tenancy import assessment_window_state
from candidates.models import Candidate
from institutions.models import Institution
from questions.models import Question
from questions.serializers import QuestionSerializer
from tenants.models import InstitutionMembership

from .seed_demo_assessment import (
    CANDIDATE_CODE, QUESTION_DATA, QUESTION_SOURCE, Command as DemoAssessmentCommand,
)


ASSESSMENT_TITLE = "Development Quick Exam Practice"
ASSESSMENT_DESCRIPTION = "Development-only seed managed by seed_quick_exam."
EXAM_CODE = "DEMO-QUICK-01"
ADMIN_EMAIL = "demo.admin@example.com"


class Command(BaseCommand):
    help = "Prepare a DEBUG-only Quick Exam fixture for TEST001 without starting an attempt."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Explicitly reset the existing credential and display its new one-time PIN.")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_quick_exam is available only when DEBUG=True.")

        demo = DemoAssessmentCommand()
        try:
            with transaction.atomic():
                institution = demo._institution()
                # Serialise reruns without adding schema or duplicate fixture identities.
                institution = Institution.objects.select_for_update().get(pk=institution.pk)
                candidate = self._candidate(institution)
                actor = self._admin(institution)
                subject = demo._subject(institution)
                topic = demo._topic(institution, subject)
                questions = self._questions(demo, institution, subject, topic, actor)
                assessment = self._assessment(demo, institution, subject, questions, actor)
                _validate_assessment_for_candidate(assessment, candidate, timezone.now(), access_mode="quick")

                configuration, _ = configure_quick_access(assessment, actor, exam_code=EXAM_CODE, enabled=True)
                credential = QuickExamCredential.objects.filter(configuration=configuration, candidate=candidate).first()
                pin = None
                if credential is None:
                    credential, pin = generate_credential(configuration, candidate, actor)
                elif options["reset"]:
                    credential, pin = reset_credential(configuration, candidate, actor, expires_at=None)
        except (APIException, DjangoValidationError) as exc:
            raise CommandError(f"Quick Exam seed validation failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Quick Exam development access ready"))
        self.stdout.write(f"Exam Code: {configuration.exam_code}")
        self.stdout.write(f"Candidate ID: {candidate.candidate_id}")
        if pin is not None:
            self.stdout.write(f"Access PIN: {pin}")
        else:
            self.stdout.write("Credential already exists. Its PIN cannot be redisplayed.")
            if not credential.active or credential.revoked_at or (credential.expires_at and credential.expires_at <= timezone.now()):
                self.stdout.write("The existing credential is inactive or expired; use --reset to issue a valid new PIN.")
        self.stdout.write("\nTake an Exam:\nhttp://localhost:5173/take-exam")
        self.stdout.write("The PIN is displayed only when issued. Use --reset to issue a new one.")
        self.stdout.write("No attempt, timer, or Quick Exam session was created.")

    def _candidate(self, institution):
        try:
            candidate = Candidate.objects.get(institution=institution, candidate_id=CANDIDATE_CODE)
        except Candidate.DoesNotExist as exc:
            raise CommandError("Candidate TEST001 was not found in Demo Training Institute. Create the existing development candidate first.") from exc
        if candidate.status != Candidate.Status.ACTIVE:
            raise CommandError("Candidate TEST001 is inactive; refusing to change candidate status.")
        # Quick access does not require or alter a linked User account.
        return candidate

    def _admin(self, institution):
        membership = InstitutionMembership.objects.select_related("user").filter(
            institution=institution, is_active=True, role=InstitutionMembership.Role.INSTITUTION_ADMIN,
            user__is_active=True, user__email=ADMIN_EMAIL,
        ).first()
        if membership is None:
            raise CommandError("An active demo.admin@example.com institution administrator is required. No user or role was created.")
        return membership.user

    def _questions(self, demo, institution, subject, topic, actor):
        questions = []
        # Reuse one of the existing demo prompts per supported objective type.
        for item in (QUESTION_DATA[0], QUESTION_DATA[3], QUESTION_DATA[6]):
            matches = Question.objects.filter(institution=institution, subject=subject, text=item["text"])
            if matches.count() > 1:
                raise CommandError("A demo question prompt is ambiguous; refusing to modify or duplicate it.")
            question = matches.first()
            if question:
                if question.source != QUESTION_SOURCE or question.question_type != item["question_type"] or question.status != Question.Status.APPROVED:
                    raise CommandError("An existing demo question is not an approved, matching seed question; refusing to overwrite it.")
                # Preserve options and questions used by existing Portal/Quick attempts.
            else:
                serializer = QuestionSerializer(data={
                    "subject": subject.pk, "topic": topic.pk, "question_type": item["question_type"],
                    "difficulty": item["difficulty"], "text": item["text"], "marks": "1.00",
                    "source": QUESTION_SOURCE, "learning_objective": item["learning_objective"],
                    "explanation": "Development practice content written for this project.",
                    "options": [{"text": text, "is_correct": correct, "order": order}
                                for order, (text, correct) in enumerate(item["options"], start=1)],
                }, context={"institution": institution, "request": SimpleNamespace(user=actor)})
                serializer.is_valid(raise_exception=True)
                question = serializer.save()
                demo._approve_question(question, actor)
            question.full_clean()
            questions.append(question)
        return questions

    def _assessment(self, demo, institution, subject, questions, actor):
        matches = Assessment.objects.filter(institution=institution, title=ASSESSMENT_TITLE)
        if matches.count() > 1:
            raise CommandError("The Quick demo assessment title is ambiguous; refusing to create a duplicate.")
        assessment = matches.first()
        if assessment:
            if assessment.description != ASSESSMENT_DESCRIPTION or assessment.subject_id != subject.pk or assessment.candidate_access != Assessment.CandidateAccess.ACCESS_CODE:
                raise CommandError("The Quick demo assessment title is already used by different data; refusing to overwrite it.")
            if assessment.status not in (Assessment.Status.APPROVED, Assessment.Status.SCHEDULED):
                raise CommandError("The existing Quick demo assessment is not approved or scheduled; refusing to reopen it.")
            if assessment_window_state(assessment, timezone.now()) != "open":
                if assessment.attempts.exists():
                    raise CommandError("The Quick demo window is closed and has attempt history; its configuration cannot be changed.")
                assessment.start_at = timezone.now() - timedelta(minutes=5)
                assessment.end_at = timezone.now() + timedelta(days=7)
                assessment.full_clean()
                assessment.save(update_fields=("start_at", "end_at", "updated_at"))
        else:
            assessment = Assessment(
                institution=institution, title=ASSESSMENT_TITLE, description=ASSESSMENT_DESCRIPTION,
                subject=subject, assessment_type=Assessment.Type.TRAINING_ASSESSMENT,
                candidate_access=Assessment.CandidateAccess.ACCESS_CODE, duration_minutes=30,
                start_at=timezone.now() - timedelta(minutes=5), end_at=timezone.now() + timedelta(days=7),
                attempt_limit=5, resume_allowed=True, pass_mark=Decimal("3.00"), created_by=actor,
            )
            assessment.full_clean()
            assessment.save()
            for order, question in enumerate(questions, start=1):
                row = AssessmentQuestion(assessment=assessment, question=question, order=order, marks=Decimal("2.00"))
                row.full_clean()
                row.save()
            demo._schedule_assessment(assessment, actor)

        assessment.full_clean()
        assessment.validate_configuration(require_questions=True, require_schedule=True)
        types = set(assessment.assessment_questions.values_list("question__question_type", flat=True))
        if not {Question.Type.MULTIPLE_CHOICE, Question.Type.MULTIPLE_SELECT, Question.Type.TRUE_FALSE}.issubset(types):
            raise CommandError("The Quick demo must retain all three supported objective question types.")
        attempts = Attempt.objects.filter(assessment=assessment, candidate__candidate_id=CANDIDATE_CODE, candidate__institution=institution)
        if attempts.count() >= assessment.attempt_limit and not attempts.filter(status=Attempt.Status.IN_PROGRESS, expires_at__gt=timezone.now()).exists():
            raise CommandError("TEST001 has reached this demo's attempt limit; existing attempt history was preserved.")
        return assessment
