from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from assessments.models import Assessment, AssessmentQuestion
from attempts.models import Attempt, AttemptQuestion
from attempts.services import _validate_assessment_for_candidate
from attempts.tenancy import active_group_ids_for_candidate, assessment_window_state
from audit.models import AuditEvent
from audit.services import record_event
from candidates.models import Candidate
from groups.models import Group, GroupMembership
from institutions.models import Institution
from questions.models import Question, QuestionOption, Topic
from questions.serializers import QuestionSerializer
from subjects.models import Subject
from tenants.models import InstitutionMembership


INSTITUTION_NAME = "Demo Training Institute"
CANDIDATE_CODE = "TEST001"
CANDIDATE_EMAIL = "teststudent@example.com"
GROUP_NAME = "Backend Engineering Cohort 1"
GROUP_CODE = "BEC001"
SUBJECT_NAME = "Backend Engineering Fundamentals"
SUBJECT_CODE = "BEF101"
TOPIC_NAME = "Python & Backend Fundamentals"
QUESTION_SOURCE = "Development fixture: seed_demo_assessment"
ASSESSMENT_DESCRIPTION = "Development-only seed managed by seed_demo_assessment."


QUESTION_DATA = (
    {
        "question_type": Question.Type.MULTIPLE_CHOICE,
        "difficulty": Question.Difficulty.EASY,
        "text": "In Python, what does len([2, 4, 6]) return?",
        "learning_objective": "Use Python's built-in sequence functions.",
        "options": [("2", False), ("3", True), ("6", False)],
    },
    {
        "question_type": Question.Type.MULTIPLE_CHOICE,
        "difficulty": Question.Difficulty.EASY,
        "text": "Which HTTP method is normally used to retrieve a resource without changing it?",
        "learning_objective": "Recognise common HTTP method semantics.",
        "options": [("GET", True), ("PATCH", False), ("POST", False)],
    },
    {
        "question_type": Question.Type.MULTIPLE_CHOICE,
        "difficulty": Question.Difficulty.MEDIUM,
        "text": "What is the main purpose of a primary key in a relational table?",
        "learning_objective": "Explain relational database identifiers.",
        "options": [("Uniquely identify a row", True), ("Encrypt every column", False), ("Sort rows permanently", False)],
    },
    {
        "question_type": Question.Type.MULTIPLE_SELECT,
        "difficulty": Question.Difficulty.MEDIUM,
        "text": "Which HTTP methods are defined as idempotent by their intended semantics?",
        "learning_objective": "Compare HTTP method semantics.",
        "options": [("GET", True), ("PUT", True), ("POST", False), ("DELETE", True)],
    },
    {
        "question_type": Question.Type.MULTIPLE_SELECT,
        "difficulty": Question.Difficulty.MEDIUM,
        "text": "Which database features can help preserve data integrity?",
        "learning_objective": "Identify database integrity mechanisms.",
        "options": [("Foreign key constraints", True), ("Unique constraints", True), ("CSS selectors", False), ("Page margins", False)],
    },
    {
        "question_type": Question.Type.MULTIPLE_SELECT,
        "difficulty": Question.Difficulty.HARD,
        "text": "What are common purposes of Django migrations?",
        "learning_objective": "Describe schema migration workflows.",
        "options": [("Record schema changes", True), ("Apply schema changes in environments", True), ("Store user passwords", False), ("Replace database backups", False)],
    },
    {
        "question_type": Question.Type.TRUE_FALSE,
        "difficulty": Question.Difficulty.EASY,
        "text": "Django's ORM can perform many common database operations without handwritten SQL.",
        "learning_objective": "Recognise the purpose of an object-relational mapper.",
        "options": [("True", True), ("False", False)],
    },
    {
        "question_type": Question.Type.TRUE_FALSE,
        "difficulty": Question.Difficulty.EASY,
        "text": "An HTTP 404 response generally means that the requested resource was not found.",
        "learning_objective": "Interpret common HTTP status codes.",
        "options": [("True", True), ("False", False)],
    },
    {
        "question_type": Question.Type.TRUE_FALSE,
        "difficulty": Question.Difficulty.EASY,
        "text": "A backend application should store user passwords as readable plain text.",
        "learning_objective": "Apply safe credential-storage principles.",
        "options": [("True", False), ("False", True)],
    },
)


class Command(BaseCommand):
    help = "Create or refresh development-only assessment fixtures for TEST001."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo_assessment is available only when DEBUG=True.")

        with transaction.atomic():
            institution = self._institution()
            candidate = self._candidate(institution)
            approver = self._approver(institution)
            group = self._group(institution)
            self._membership(candidate, group)
            subject = self._subject(institution)
            topic = self._topic(institution, subject)
            questions = self._questions(institution, subject, topic, approver)
            available = self._assessment(
                institution, subject, group, approver,
                title="Backend Fundamentals Practice Assessment",
                duration=30,
                questions=questions[:5],
                start_at=timezone.now() - timedelta(hours=1),
                end_at=timezone.now() + timedelta(hours=24),
            )
            upcoming = self._assessment(
                institution, subject, group, approver,
                title="Backend Engineering Progress Test",
                duration=45,
                questions=questions[4:9],
                start_at=timezone.now() + timedelta(hours=24),
                end_at=timezone.now() + timedelta(hours=48),
            )
            check_time = timezone.now()
            eligible_groups = active_group_ids_for_candidate(candidate)
            for assessment, expected_window in ((available, "open"), (upcoming, "upcoming")):
                if assessment_window_state(assessment, check_time) != expected_window:
                    raise CommandError(f"Seeded assessment '{assessment.title}' has an unexpected availability window.")
                try:
                    _validate_assessment_for_candidate(
                        assessment, candidate, check_time,
                        check_window=False, eligible_group_ids=eligible_groups,
                    )
                except (APIException, DjangoValidationError) as exc:
                    raise CommandError(f"Seeded assessment '{assessment.title}' failed candidate eligibility checks: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Demo assessment data ready."))
        self.stdout.write(f"Institution: {institution.name}")
        self.stdout.write(f"Candidate: {candidate.candidate_id}")
        self.stdout.write(f"Group: {group.name}")
        self.stdout.write(f"Subject: {subject.code}")
        self.stdout.write("Available:")
        self.stdout.write(f"- {available.title}")
        self.stdout.write("Upcoming:")
        self.stdout.write(f"- {upcoming.title}")
        self.stdout.write("No attempts or results were created.")

    def _institution(self):
        matches = Institution.objects.filter(name=INSTITUTION_NAME)
        if matches.count() != 1:
            raise CommandError(
                f"Expected one '{INSTITUTION_NAME}' institution. Create the Phase 1 development institution first."
            )
        institution = matches.get()
        if not institution.is_active:
            raise CommandError(f"'{INSTITUTION_NAME}' is inactive; refusing to change its status.")
        return institution

    def _candidate(self, institution):
        try:
            candidate = Candidate.objects.select_related("user").get(
                institution=institution, candidate_id=CANDIDATE_CODE,
            )
        except Candidate.DoesNotExist:
            raise CommandError(
                "Candidate TEST001 was not found in Demo Training Institute. "
                "Create the Phase 1 development account and linked Candidate first."
            )
        if not candidate.user_id or candidate.user.email.casefold() != CANDIDATE_EMAIL.casefold():
            raise CommandError(
                "Candidate TEST001 is not linked to teststudent@example.com; refusing to change account linkage."
            )
        if candidate.status != Candidate.Status.ACTIVE:
            raise CommandError("Candidate TEST001 is inactive; refusing to change candidate status.")
        return candidate

    def _approver(self, institution):
        membership = InstitutionMembership.objects.filter(
            institution=institution,
            is_active=True,
            institution__is_active=True,
            role__in=(InstitutionMembership.Role.INSTITUTION_ADMIN, InstitutionMembership.Role.PLATFORM_ADMIN),
        ).select_related("user").order_by("role", "pk").first()
        if membership is None:
            raise CommandError(
                "An existing active institution administrator is required to approve seeded questions "
                "and assessments. No user or role was created."
            )
        return membership.user

    def _group(self, institution):
        current_year = timezone.localdate().year
        session = f"{current_year}/{current_year + 1}"
        group, _ = Group.objects.get_or_create(
            institution=institution,
            code=GROUP_CODE,
            defaults={
                "name": GROUP_NAME,
                "group_type": "cohort",
                "academic_session": session,
                "is_active": True,
            },
        )
        if group.name != GROUP_NAME or group.group_type != "cohort":
            raise CommandError(f"Group code {GROUP_CODE} is already used by a different group; refusing to overwrite it.")
        fields = []
        if not group.is_active:
            group.is_active = True
            fields.append("is_active")
        if group.academic_session != session:
            group.academic_session = session
            fields.append("academic_session")
        if fields:
            group.save(update_fields=(*fields, "updated_at"))
        return group

    def _membership(self, candidate, group):
        membership, _ = GroupMembership.objects.get_or_create(candidate=candidate, group=group)
        changed = []
        if not membership.is_active:
            membership.is_active = True
            changed.append("is_active")
        for field in ("start_date", "end_date"):
            if getattr(membership, field) is not None:
                setattr(membership, field, None)
                changed.append(field)
        if changed:
            membership.save(update_fields=(*changed, "updated_at"))

    def _subject(self, institution):
        subject, _ = Subject.objects.get_or_create(
            institution=institution,
            code=SUBJECT_CODE,
            defaults={
                "name": SUBJECT_NAME,
                "description": "Development subject for frontend assessment integration testing.",
                "is_active": True,
            },
        )
        if subject.name != SUBJECT_NAME:
            raise CommandError(f"Subject code {SUBJECT_CODE} is already used by a different subject; refusing to overwrite it.")
        updates = []
        description = "Development subject for frontend assessment integration testing."
        if subject.description != description:
            subject.description = description
            updates.append("description")
        if not subject.is_active:
            subject.is_active = True
            updates.append("is_active")
        if updates:
            subject.save(update_fields=(*updates, "updated_at"))
        return subject

    def _topic(self, institution, subject):
        topic, _ = Topic.objects.get_or_create(
            institution=institution,
            subject=subject,
            name=TOPIC_NAME,
            defaults={"description": "Development-only topic for the seeded backend questions."},
        )
        if not topic.is_active:
            topic.is_active = True
            topic.save(update_fields=("is_active", "updated_at"))
        return topic

    def _questions(self, institution, subject, topic, approver):
        questions = []
        for item in QUESTION_DATA:
            payload = {
                "subject": subject.pk,
                "topic": topic.pk,
                "question_type": item["question_type"],
                "difficulty": item["difficulty"],
                "text": item["text"],
                "explanation": "Development practice content written for this project.",
                "marks": "1.00",
                "source": QUESTION_SOURCE,
                "learning_objective": item["learning_objective"],
                "options": [
                    {"text": text, "is_correct": correct, "order": order}
                    for order, (text, correct) in enumerate(item["options"], start=1)
                ],
            }
            serializer = QuestionSerializer(data=payload, context={"institution": institution})
            try:
                serializer.is_valid(raise_exception=True)
            except Exception as exc:
                raise CommandError(f"Seed question validation failed: {exc}") from exc

            question, created = Question.objects.get_or_create(
                institution=institution,
                subject=subject,
                text=item["text"],
                defaults={
                    "topic": topic,
                    "question_type": item["question_type"],
                    "difficulty": item["difficulty"],
                    "explanation": payload["explanation"],
                    "marks": Decimal("1.00"),
                    "source": QUESTION_SOURCE,
                    "learning_objective": item["learning_objective"],
                    "created_by": approver,
                    "status": Question.Status.DRAFT,
                },
            )
            if not created and question.source != QUESTION_SOURCE:
                raise CommandError(f"A non-seed question already uses a demo prompt; refusing to modify it: {question.pk}.")
            if AttemptQuestion.objects.filter(question=question).exists():
                raise CommandError(f"Seed question {question.pk} already belongs to an attempt; refusing to modify it.")

            for option in payload["options"]:
                QuestionOption.objects.update_or_create(
                    question=question,
                    order=option["order"],
                    defaults={"text": option["text"], "is_correct": option["is_correct"]},
                )

            question.topic = topic
            question.question_type = item["question_type"]
            question.difficulty = item["difficulty"]
            question.explanation = payload["explanation"]
            question.marks = Decimal("1.00")
            question.source = QUESTION_SOURCE
            question.learning_objective = item["learning_objective"]
            question.full_clean()
            question.save()
            self._approve_question(question, approver)
            questions.append(question)
        return questions

    def _approve_question(self, question, approver):
        options = list(question.options.order_by("order", "pk"))
        correct_count = sum(option.is_correct for option in options)
        valid = len(options) >= 2
        if question.question_type == Question.Type.MULTIPLE_CHOICE:
            valid = valid and correct_count == 1
        elif question.question_type == Question.Type.MULTIPLE_SELECT:
            valid = valid and correct_count >= 1
        elif question.question_type == Question.Type.TRUE_FALSE:
            valid = valid and len(options) == 2 and correct_count == 1
        if not valid:
            raise CommandError(f"Seed question {question.pk} has invalid option configuration.")

        if question.status == Question.Status.ARCHIVED:
            raise CommandError(f"Seed question {question.pk} is archived; refusing to reopen it.")
        if question.status == Question.Status.DRAFT:
            question.status = Question.Status.REVIEW
            question.full_clean()
            question.save(update_fields=("status", "updated_at"))
        if question.status == Question.Status.REVIEW:
            question.status = Question.Status.APPROVED
        elif question.status != Question.Status.APPROVED:
            raise CommandError(f"Seed question {question.pk} is in an unsupported workflow state.")
        question.reviewed_by = approver
        question.full_clean()
        question.save(update_fields=("status", "reviewed_by", "updated_at"))

    def _assessment(self, institution, subject, group, approver, *, title, duration, questions, start_at, end_at):
        existing = Assessment.objects.filter(institution=institution, title=title).first()
        if existing and existing.description != ASSESSMENT_DESCRIPTION:
            raise CommandError(f"An assessment named '{title}' already exists and is not owned by this seed command.")
        if existing and Attempt.objects.filter(assessment=existing).exists():
            raise CommandError(f"'{title}' already has attempts; refusing to update its seeded configuration.")

        assessment, created = Assessment.objects.get_or_create(
            institution=institution,
            title=title,
            defaults={
                "description": ASSESSMENT_DESCRIPTION,
                "assessment_type": Assessment.Type.TRAINING_ASSESSMENT,
                "subject": subject,
                "group": group,
                "duration_minutes": duration,
                "pass_mark": Decimal("5.00"),
                "start_at": start_at,
                "end_at": end_at,
                "attempt_limit": 1,
                "resume_allowed": True,
                "randomize_questions": True,
                "randomize_options": True,
                "security_level": Assessment.SecurityLevel.STANDARD,
                "result_visibility": Assessment.ResultVisibility.HIDDEN,
                "candidate_access": Assessment.CandidateAccess.ASSIGNED_GROUP,
                "review_allowed": False,
                "result_release_mode": Assessment.ResultReleaseMode.APPROVAL_REQUIRED,
                "created_by": approver,
                "status": Assessment.Status.DRAFT,
            },
        )
        if not created:
            assessment.description = ASSESSMENT_DESCRIPTION
            assessment.assessment_type = Assessment.Type.TRAINING_ASSESSMENT
            assessment.subject = subject
            assessment.group = group
            assessment.duration_minutes = duration
            assessment.pass_mark = Decimal("5.00")
            assessment.start_at = start_at
            assessment.end_at = end_at
            assessment.attempt_limit = 1
            assessment.resume_allowed = True
            assessment.randomize_questions = True
            assessment.randomize_options = True
            assessment.security_level = Assessment.SecurityLevel.STANDARD
            assessment.result_visibility = Assessment.ResultVisibility.HIDDEN
            assessment.candidate_access = Assessment.CandidateAccess.ASSIGNED_GROUP
            assessment.review_allowed = False
            assessment.result_release_mode = Assessment.ResultReleaseMode.APPROVAL_REQUIRED
            assessment.save()

        if assessment.status == Assessment.Status.ARCHIVED:
            raise CommandError(f"'{title}' is archived; refusing to reopen it.")
        for order, question in enumerate(questions, start=1):
            AssessmentQuestion.objects.update_or_create(
                assessment=assessment,
                question=question,
                defaults={"order": order, "marks": Decimal("2.00")},
            )
        assessment.validate_configuration(require_questions=True, require_schedule=True)
        self._schedule_assessment(assessment, approver)
        return assessment

    def _schedule_assessment(self, assessment, approver):
        if assessment.status == Assessment.Status.DRAFT:
            assessment.status = Assessment.Status.REVIEW
            assessment.save(update_fields=("status", "updated_at"))
        if assessment.status == Assessment.Status.REVIEW:
            assessment.validate_configuration(require_questions=True, require_schedule=True)
            assessment.status = Assessment.Status.APPROVED
            assessment.reviewed_by = approver
            assessment.approved_by = approver
            assessment.save(update_fields=("status", "reviewed_by", "approved_by", "updated_at"))
            record_event(
                institution=assessment.institution,
                actor=approver,
                event_type=AuditEvent.Type.ASSESSMENT_APPROVED,
                resource=assessment,
                metadata={"status": Assessment.Status.APPROVED, "source": "development_seed"},
            )
        if assessment.status == Assessment.Status.APPROVED:
            assessment.validate_configuration(require_questions=True, require_schedule=True)
            assessment.status = Assessment.Status.SCHEDULED
            assessment.reviewed_by = approver
            assessment.approved_by = approver
            assessment.save(update_fields=("status", "reviewed_by", "approved_by", "updated_at"))
            record_event(
                institution=assessment.institution,
                actor=approver,
                event_type=AuditEvent.Type.ASSESSMENT_SCHEDULED,
                resource=assessment,
                metadata={"status": Assessment.Status.SCHEDULED, "source": "development_seed"},
            )
        if assessment.status != Assessment.Status.SCHEDULED:
            raise CommandError(f"'{assessment.title}' is in an unsupported workflow state: {assessment.status}.")
        assessment.validate_configuration(require_questions=True, require_schedule=True)
