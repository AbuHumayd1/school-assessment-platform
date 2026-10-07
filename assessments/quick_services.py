import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from audit.models import AuditEvent
from audit.services import record_event
from candidates.models import Candidate
from tenants.querysets import can_manage_institution
from .models import Assessment, QuickExamConfiguration, QuickExamCredential, QuickExamSession
from .eligibility import directly_assigned_candidates


PIN_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
UNSET = object()


class QuickAccessConflict(APIException):
    status_code = 409
    default_detail = {"code": "credential_exists", "detail": "A credential already exists. Use explicit reset to issue a new PIN."}


def _authorize(actor, assessment):
    if not actor or not actor.is_authenticated or not actor.is_active or not can_manage_institution(actor, assessment.institution_id, {"institution_admin"}):
        raise PermissionDenied("Only an authorized institution administrator can manage Quick Exam access.")
    from institutions.permissions import is_platform_administrator
    if assessment.institution.workspace_mode == "managed_exam" and not is_platform_administrator(actor):
        raise PermissionDenied("Examination preparation requires platform administration.")
    if assessment.candidate_access not in {Assessment.CandidateAccess.ACCESS_CODE, Assessment.CandidateAccess.SPECIFIC_CANDIDATES}:
        raise ValidationError({"assessment": "Quick Exam supports Specific Candidates eligibility. Choose Specific Candidates first."})


def _save(instance):
    try:
        with transaction.atomic():
            instance.save()
    except DjangoValidationError as error:
        raise ValidationError(error.message_dict if hasattr(error, "message_dict") else error.messages)
    except IntegrityError:
        raise ValidationError({"detail": "This exam code or candidate credential is already in use."})


def _audit(resource, actor, action):
    configuration = resource if isinstance(resource, QuickExamConfiguration) else resource.configuration
    metadata = {"action": action, "assessment_id": configuration.assessment_id, "configuration_id": configuration.pk}
    if isinstance(resource, QuickExamCredential):
        metadata.update(candidate_id=resource.candidate_id, version=resource.version)
    record_event(institution=configuration.assessment.institution, actor=actor,
                 event_type=AuditEvent.Type.MEMBERSHIP_CHANGED, resource=resource, metadata=metadata)


def _invalidate(configuration=None, credential=None, now=None):
    sessions = QuickExamSession.objects.filter(revoked_at__isnull=True)
    sessions = sessions.filter(credential=credential) if credential else sessions.filter(credential__configuration=configuration)
    sessions.update(revoked_at=now or timezone.now())


def _expiry(expires_at):
    if expires_at is not None and (timezone.is_naive(expires_at) or expires_at <= timezone.now()):
        raise ValidationError({"expires_at": "Choose a future timezone-aware expiry, or no expiry."})
    return expires_at


@transaction.atomic
def configure_quick_access(assessment, actor, *, exam_code=UNSET, enabled=UNSET):
    assessment = Assessment.objects.select_for_update().select_related("institution").get(pk=assessment.pk)
    _authorize(actor, assessment)
    configuration = QuickExamConfiguration.objects.select_for_update().filter(assessment=assessment).first()
    created = configuration is None
    if created:
        if assessment.candidate_access != Assessment.CandidateAccess.ACCESS_CODE:
            raise ValidationError({"assessment": "Delivery method is fixed when the exam is created. This exam uses account delivery."})
        if exam_code is UNSET:
            raise ValidationError({"exam_code": "An exam code is required."})
        configuration = QuickExamConfiguration(assessment=assessment, exam_code=exam_code)
    elif exam_code is not UNSET:
        from .quick_models import normalize_exam_code
        try:
            normalized = normalize_exam_code(exam_code)
        except DjangoValidationError as error:
            raise ValidationError(error.message_dict)
        if normalized != configuration.exam_code and (configuration.credentials.exists() or assessment.attempts.exists()):
            raise ValidationError({"exam_code": "The exam code cannot change after credentials or attempts exist."})
        configuration.exam_code = normalized
    if assessment.status == Assessment.Status.ARCHIVED and (created or enabled is True):
        raise ValidationError({"assessment": "Archived assessments cannot enable Quick Exam access."})
    was_enabled = configuration.enabled
    if enabled is not UNSET:
        if not isinstance(enabled, bool):
            raise ValidationError({"enabled": "Use true or false."})
        configuration.enabled = enabled
    if was_enabled and not configuration.enabled:
        configuration.session_version += 1
    _save(configuration)
    if created:
        _audit(configuration, actor, "quick_configuration_created")
    elif exam_code is not UNSET:
        _audit(configuration, actor, "quick_configuration_updated")
    if was_enabled != configuration.enabled:
        if not configuration.enabled:
            _invalidate(configuration=configuration)
        _audit(configuration, actor, "quick_configuration_enabled" if configuration.enabled else "quick_configuration_disabled")
    return configuration, created


def _locked_context(configuration, candidate, actor, *, issuing=False):
    # Match Candidate lifecycle locking, then Assessment and its access configuration.
    candidate = Candidate.objects.select_for_update().get(pk=candidate.pk)
    assessment = Assessment.objects.select_for_update().select_related("institution").get(pk=configuration.assessment_id)
    _authorize(actor, assessment)
    configuration = QuickExamConfiguration.objects.select_for_update().get(pk=configuration.pk, assessment=assessment)
    configuration.assessment = assessment
    if candidate.institution_id != assessment.institution_id:
        raise NotFound()
    if issuing and (candidate.status != Candidate.Status.ACTIVE or assessment.status == Assessment.Status.ARCHIVED):
        raise ValidationError({"detail": "Issue credentials only for active candidates and non-archived assessments."})
    if issuing and assessment.candidate_access == Assessment.CandidateAccess.SPECIFIC_CANDIDATES and not directly_assigned_candidates(assessment).filter(pk=candidate.pk).exists():
        raise ValidationError({"candidate": "Assign this active candidate to the exam before generating credentials."})
    return configuration, candidate


@transaction.atomic
def generate_credential(configuration, candidate, actor, *, expires_at=None):
    configuration, candidate = _locked_context(configuration, candidate, actor, issuing=True)
    if not directly_assigned_candidates(configuration.assessment).filter(pk=candidate.pk).exists():
        raise ValidationError({"candidate": "Assign this active candidate to the exam before generating credentials."})
    if QuickExamCredential.objects.filter(configuration=configuration, candidate=candidate).exists():
        raise QuickAccessConflict()
    pin = "".join(secrets.choice(PIN_ALPHABET) for _ in range(10))
    credential = QuickExamCredential(configuration=configuration, candidate=candidate, pin_hash=make_password(pin),
                                     expires_at=_expiry(expires_at), issued_by=actor)
    _save(credential)
    _audit(credential, actor, "quick_credential_generated")
    return credential, pin


@transaction.atomic
def reset_credential(configuration, candidate, actor, *, expires_at=UNSET):
    configuration, candidate = _locked_context(configuration, candidate, actor, issuing=True)
    try:
        credential = QuickExamCredential.objects.select_for_update().get(configuration=configuration, candidate=candidate)
    except QuickExamCredential.DoesNotExist:
        raise NotFound()
    pin = "".join(secrets.choice(PIN_ALPHABET) for _ in range(10))
    credential.pin_hash = make_password(pin)
    credential.version += 1
    credential.active = True
    credential.revoked_at = None
    credential.generated_at = timezone.now()
    credential.issued_by = actor
    credential.expires_at = _expiry(credential.expires_at if expires_at is UNSET else expires_at)
    _save(credential)
    _invalidate(credential=credential)
    _audit(credential, actor, "quick_credential_reset")
    return credential, pin


@transaction.atomic
def revoke_credential(configuration, candidate, actor):
    configuration, candidate = _locked_context(configuration, candidate, actor)
    try:
        credential = QuickExamCredential.objects.select_for_update().get(configuration=configuration, candidate=candidate)
    except QuickExamCredential.DoesNotExist:
        raise NotFound()
    if credential.active:
        credential.active = False
        credential.revoked_at = timezone.now()
        credential.version += 1
        _save(credential)
        _invalidate(credential=credential)
        _audit(credential, actor, "quick_credential_revoked")
    return credential


def _credential_valid(credential, now):
    configuration = credential.configuration
    assessment = configuration.assessment
    return bool(credential.active and credential.revoked_at is None and configuration.enabled
                and (credential.expires_at is None or now < credential.expires_at)
                and assessment.candidate_access in {Assessment.CandidateAccess.ACCESS_CODE, Assessment.CandidateAccess.SPECIFIC_CANDIDATES}
                and (assessment.candidate_access == Assessment.CandidateAccess.ACCESS_CODE
                     or assessment.candidate_assignments.filter(candidate_id=credential.candidate_id).exists())
                and assessment.institution.is_active
                and credential.candidate.status == Candidate.Status.ACTIVE
                and credential.candidate.institution_id == assessment.institution_id)


def credential_counts(configuration):
    candidates = directly_assigned_candidates(configuration.assessment)
    credentials = configuration.credentials.filter(candidate__in=candidates)
    now = timezone.now()
    from django.db.models import Q
    valid = credentials.filter(active=True, revoked_at__isnull=True).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).count()
    assigned = candidates.count()
    missing = candidates.exclude(quick_credentials__configuration=configuration).count()
    return {"assigned_count": assigned, "generated_count": valid, "needed_count": assigned - valid,
            "generatable_count": missing, "reset_needed_count": assigned - valid - missing}


@transaction.atomic
def generate_assigned_credentials(configuration, actor, *, expected_count=None):
    # Candidate -> assessment -> configuration matches the existing Quick lock order.
    candidate_ids = directly_assigned_candidates(configuration.assessment).values_list("pk", flat=True)
    candidates = list(Candidate.objects.select_for_update().filter(pk__in=candidate_ids).order_by("pk")[:1001])
    assessment = Assessment.objects.select_for_update().select_related("institution").get(pk=configuration.assessment_id)
    _authorize(actor, assessment)
    configuration = QuickExamConfiguration.objects.select_for_update().get(pk=configuration.pk, assessment=assessment)
    configuration.assessment = assessment
    if assessment.status != Assessment.Status.DRAFT or assessment.attempts.exists():
        raise ValidationError({"assessment": "Generate credentials only while the exam is editable and has no participation."})
    if not configuration.enabled:
        raise ValidationError({"assessment": "Enable Quick Exam access before generating usable credentials."})
    eligible_ids = set(directly_assigned_candidates(assessment).values_list("pk", flat=True))
    if eligible_ids != {candidate.pk for candidate in candidates}:
        raise ValidationError({"detail": "Candidate assignments changed or exceed 1000. Refresh and try again."})
    existing = set(configuration.credentials.values_list("candidate_id", flat=True))
    missing = [candidate for candidate in candidates if candidate.pk not in existing]
    if expected_count is not None and expected_count != len(missing):
        raise ValidationError({"detail": "Credential counts changed. Refresh before generating credentials."})
    if not missing:
        raise ValidationError({"detail": "No assigned active candidates need new credentials. Existing PINs are not regenerated."})
    issued = []
    for candidate in sorted(missing, key=lambda c: (c.candidate_id, c.pk)):
        credential, pin = generate_credential(configuration, candidate, actor)
        issued.append((candidate, pin))
    return configuration, issued


def verify_credential(credential, pin, *, now=None):
    """Internal credential check only; public verification/delivery eligibility is Slice 2."""
    credential = QuickExamCredential.objects.select_related("configuration__assessment__institution", "candidate").filter(pk=credential.pk).first()
    return bool(credential and isinstance(pin, str) and _credential_valid(credential, now or timezone.now()) and check_password(pin, credential.pin_hash))


def session_is_current(session, *, now=None):
    """Version/expiry helper for the approved model; does not authenticate requests."""
    now = now or timezone.now()
    session = QuickExamSession.objects.select_related("credential__configuration__assessment__institution", "credential__candidate").filter(pk=session.pk).first()
    return bool(session and session.revoked_at is None and now < session.expires_at
                and _credential_valid(session.credential, now)
                and session.credential_version == session.credential.version
                and session.configuration_version == session.credential.configuration.session_version)
