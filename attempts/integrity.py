from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from audit.models import AuditEvent
from audit.services import record_event

from .models import Attempt
from .access import ExamAccessContext
from .services import (
    CompletionReason, expire_attempt, finalize_attempt, lock_candidate_attempt, lock_access_attempt,
)


INTERRUPTION_SIGNALS = frozenset({"page_hidden", "navigation_attempt"})
SUPPORTED_SIGNALS = frozenset({
    *INTERRUPTION_SIGNALS,
    "page_visible",
    "page_hide",
    "window_blur",
    "window_focus",
    "copy_attempt",
    "cut_attempt",
    "select_all_attempt",
    "context_menu_attempt",
    "screenshot_key_attempt",
})
class ClosedAttemptIntegrityEvent(APIException):
    status_code = 409
    default_detail = "Integrity events can only be recorded for an active attempt."
    default_code = "attempt_not_active"


def interruption_limit():
    return max(1, int(getattr(settings, "EXAM_INTEGRITY_INTERRUPTION_LIMIT", 3)))


def interruption_count(attempt):
    return AuditEvent.objects.filter(
        institution_id=attempt.institution_id,
        resource_type=Attempt._meta.label_lower,
        resource_id=str(attempt.pk),
        event_type__in=INTERRUPTION_SIGNALS,
    ).count()


def integrity_state(attempt):
    count = interruption_count(attempt)
    limit = interruption_limit()
    return {
        "attempt_status": attempt.status,
        "interruption_count": count,
        "interruption_limit": limit,
        "warning": attempt.status == Attempt.Status.IN_PROGRESS and count > 0,
        "automatically_submitted": attempt.status == Attempt.Status.SUBMITTED and count >= limit,
    }


@transaction.atomic
def record_integrity_signal(user, attempt_id, signal):
    if isinstance(user, ExamAccessContext):
        attempt = lock_access_attempt(user, attempt_id)
        user = user.user
    else:
        attempt = lock_candidate_attempt(user, attempt_id)
    if expire_attempt(attempt, actor=user):
        state = integrity_state(attempt)
        return {**state, "deduplicated": False, "event_rejected": True}
    if attempt.status != Attempt.Status.IN_PROGRESS:
        raise ClosedAttemptIntegrityEvent()

    now = timezone.now()
    counts_as_interruption = signal in INTERRUPTION_SIGNALS
    duplicate = False
    if counts_as_interruption:
        window = max(0, int(getattr(settings, "EXAM_INTEGRITY_DEDUPE_SECONDS", 5)))
        latest_transition = AuditEvent.objects.filter(
            institution_id=attempt.institution_id,
            resource_type=Attempt._meta.label_lower,
            resource_id=str(attempt.pk),
            event_type__in=(*INTERRUPTION_SIGNALS, "page_visible"),
        ).order_by("-occurred_at", "-pk").values_list("event_type", "occurred_at").first()
        duplicate = bool(
            latest_transition
            and latest_transition[0] in INTERRUPTION_SIGNALS
            and latest_transition[1] >= now - timedelta(seconds=window)
        )

    if not duplicate:
        # AuditEvent's existing varchar/JSON schema supports additional append-only
        # event names without storing answers, device fingerprints, or client counts.
        record_event(
            institution=attempt.institution,
            actor=user,
            event_type=signal,
            resource=attempt,
            metadata={"signal": signal, "counts_as_interruption": counts_as_interruption},
        )

    count = interruption_count(attempt)
    limit = interruption_limit()
    automatically_submitted = count >= limit
    if automatically_submitted:
        attempt, _ = finalize_attempt(
            attempt, reason=CompletionReason.INTEGRITY, actor=user,
            metadata={"interruption_count": count},
        )
        automatically_submitted = attempt.status == Attempt.Status.SUBMITTED

    return {
        "attempt_status": attempt.status,
        "interruption_count": count,
        "interruption_limit": limit,
        "warning": attempt.status == Attempt.Status.IN_PROGRESS and count > 0,
        "automatically_submitted": automatically_submitted,
        "deduplicated": duplicate,
    }
