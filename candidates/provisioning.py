import secrets

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from accounts.models import User
from audit.models import AuditEvent
from audit.services import record_event
from .models import Candidate


@transaction.atomic
def provision_candidate_access(candidate, actor):
    candidate = Candidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.user_id:
        raise ValidationError({"code": "already_linked", "detail": "Portal access already has a linked account. Credentials cannot be issued again."})
    if not candidate.email:
        raise ValidationError({"code": "email_required", "detail": "Add a candidate email before enabling email-based portal access."})
    if candidate.status != Candidate.Status.ACTIVE:
        raise ValidationError({"code": "candidate_inactive", "detail": "Activate this candidate before enabling portal access."})
    if candidate.attempts.exists():
        raise ValidationError({"code": "identity_locked", "detail": "Account linkage cannot change after an examination attempt starts."})
    email = User.objects.normalize_email(candidate.email)
    try:
        validate_email(email)
    except DjangoValidationError:
        raise ValidationError({"code": "email_required", "detail": "Add a valid candidate email before enabling portal access."})
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError({"code": "email_exists", "detail": "An account with this email already exists. Linking requires a separate controlled process."})
    password = secrets.token_urlsafe(24)
    validate_password(password, User(email=email, first_name=candidate.first_name, last_name=candidate.last_name))
    try:
        with transaction.atomic():
            user = User.objects.create_user(email, password, first_name=candidate.first_name, last_name=candidate.last_name)
    except IntegrityError:
        raise ValidationError({"code": "email_exists", "detail": "An account with this email already exists. Linking requires a separate controlled process."})
    candidate.user = user
    candidate.save(update_fields=["user", "updated_at"])
    # Reuse the existing relationship-change audit category; no staff membership is created.
    record_event(institution=candidate.institution, actor=actor, event_type=AuditEvent.Type.MEMBERSHIP_CHANGED,
                 resource=candidate, metadata={"action": "candidate_portal_access_provisioned", "user_id": user.pk})
    return {"account": {"id": user.pk, "email": user.email}, "initial_password": password}
