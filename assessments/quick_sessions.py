import hashlib
import secrets
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from attempts.access import ExamAccessContext
from audit.models import AuditEvent
from audit.services import record_event
from candidates.models import Candidate
from .models import Assessment, QuickExamConfiguration, QuickExamCredential, QuickExamSession
from .quick_models import normalize_exam_code
from .quick_services import _credential_valid


COOKIE_NAME = "quick_exam_session"
COOKIE_PATH = "/api/v1/quick-exam/"
INVALID_DETAILS = "The exam details or access credentials are incorrect."
INVALID_SESSION = "The Quick Exam session is unavailable or has expired. Verify your exam details again."


@lru_cache(maxsize=1)
def dummy_password_hash():
    return make_password(secrets.token_urlsafe(32))


def token_digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _context(session):
    credential = session.credential
    assessment = credential.configuration.assessment
    return ExamAccessContext("quick", credential.candidate, assessment, assessment.institution, quick_session=session)


def _session_valid(session, now):
    return (session.revoked_at is None and now < session.expires_at
            and _credential_valid(session.credential, now)
            and session.credential_version == session.credential.version
            and session.configuration_version == session.credential.configuration.session_version)


def _locked_credential(credential_id):
    identity = QuickExamCredential.objects.filter(pk=credential_id).values("candidate_id", "configuration_id", "configuration__assessment_id").first()
    if not identity:
        return None
    candidate = Candidate.objects.select_for_update().filter(pk=identity["candidate_id"]).first()
    assessment = Assessment.objects.select_for_update().select_related("institution").filter(pk=identity["configuration__assessment_id"]).first()
    configuration = QuickExamConfiguration.objects.select_for_update().filter(pk=identity["configuration_id"]).first()
    credential = QuickExamCredential.objects.select_for_update().filter(pk=credential_id).first()
    if not all((candidate, assessment, configuration, credential)):
        return None
    # Attach freshly resolved related rows, not cached request-time objects.
    configuration.assessment = assessment
    credential.configuration = configuration
    credential.candidate = candidate
    return credential


@transaction.atomic
def resolve_session(*, token=None, session_id=None, lock=False):
    if token is not None:
        if not isinstance(token, str) or len(token) != 43 or not token.isascii():
            raise AuthenticationFailed(INVALID_SESSION)
        filters = {"token_digest": token_digest(token)}
    else:
        filters = {"pk": session_id}
    session = QuickExamSession.objects.select_related("credential__configuration__assessment__institution", "credential__candidate").filter(**filters).first()
    if session and lock:
        credential = _locked_credential(session.credential_id)
        session = QuickExamSession.objects.select_for_update().filter(**filters).first()
        if not credential or not session:
            raise AuthenticationFailed(INVALID_SESSION)
        session.credential = credential
    if not session or not _session_valid(session, timezone.now()):
        raise AuthenticationFailed(INVALID_SESSION)
    return _context(session)


def session_expiry(credential, now):
    base = max(1, settings.QUICK_EXAM_SESSION_BASE_SECONDS)
    buffer = max(1, settings.QUICK_EXAM_RECOVERY_BUFFER_SECONDS)
    duration = credential.configuration.assessment.duration_minutes * 60
    expires = now + timedelta(seconds=max(base, duration + buffer))
    end = credential.configuration.assessment.end_at
    if end:
        # Recovery may extend beyond the entry window. Only the Attempt Engine
        # decides whether a new start/resume/deadline operation is permissible.
        expires = min(expires, max(now, end) + timedelta(seconds=duration + buffer))
    if credential.expires_at:
        expires = min(expires, credential.expires_at)
    return expires


def audit_session(session, action, **extra):
    configuration = session.credential.configuration
    record_event(institution=configuration.assessment.institution, actor=None,
                 event_type=AuditEvent.Type.MEMBERSHIP_CHANGED, resource=session,
                 metadata={"action": action, "assessment_id": configuration.assessment_id,
                           "configuration_id": configuration.pk, "candidate_id": session.credential.candidate_id, **extra})


def verify_and_create_session(exam_code, candidate_id, pin):
    credential = None
    try:
        normalized = normalize_exam_code(exam_code)
    except DjangoValidationError:
        normalized = None
    if normalized:
        credential = QuickExamCredential.objects.select_related("configuration__assessment__institution", "candidate").filter(
            configuration__exam_code=normalized, candidate__candidate_id=candidate_id.strip(),
        ).first()
    # Always pay the password verification cost, including absent/disabled rows.
    password_matches = check_password(pin, credential.pin_hash if credential else dummy_password_hash())
    if not credential or not password_matches or not _credential_valid(credential, timezone.now()):
        raise AuthenticationFailed(INVALID_DETAILS)
    with transaction.atomic():
        locked = _locked_credential(credential.pk)
        now = timezone.now()
        if not locked or locked.version != credential.version or locked.pin_hash != credential.pin_hash or not _credential_valid(locked, now):
            raise AuthenticationFailed(INVALID_DETAILS)
        replaced = QuickExamSession.objects.filter(credential=locked, revoked_at__isnull=True).update(revoked_at=now)
        token = secrets.token_urlsafe(32)
        session = QuickExamSession.objects.create(credential=locked, token_digest=token_digest(token),
            credential_version=locked.version, configuration_version=locked.configuration.session_version,
            expires_at=session_expiry(locked, now))
        audit_session(session, "quick_session_created", replaced_sessions=replaced)
    return session, token


@transaction.atomic
def logout_session(token):
    if not isinstance(token, str) or len(token) != 43 or not token.isascii():
        return
    session = QuickExamSession.objects.select_related("credential__configuration__assessment__institution").filter(token_digest=token_digest(token)).first()
    if session:
        credential = _locked_credential(session.credential_id)
        session = QuickExamSession.objects.select_for_update().filter(pk=session.pk).first()
        if session and credential and session.revoked_at is None:
            session.credential = credential
            session.revoked_at = timezone.now()
            session.save(update_fields=("revoked_at",))
            audit_session(session, "quick_session_revoked")
