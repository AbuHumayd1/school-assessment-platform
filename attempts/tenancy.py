from django.utils import timezone
from django.db.models import Q

from candidates.models import Candidate
from groups.models import GroupMembership
from tenants.models import InstitutionMembership


STAFF_ATTEMPT_ROLES = {"platform_admin", "institution_admin", "examiner"}


def candidates_for_user(user):
    return Candidate.objects.filter(user=user, institution__is_active=True)


def active_group_ids_for_candidate(candidate, local_date=None):
    local_date = local_date or active_local_date(candidate.institution)
    return set(
        GroupMembership.objects.filter(
            candidate=candidate,
            is_active=True,
            group__is_active=True,
            group__institution_id=candidate.institution_id,
        )
        .filter(Q(start_date__isnull=True) | Q(start_date__lte=local_date))
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=local_date))
        .values_list("group_id", flat=True)
    )


def assessment_window_state(assessment, now):
    """Compare aware instants; entry includes both boundaries of the saved window."""
    if assessment.start_at and now < assessment.start_at:
        return "upcoming"
    if assessment.end_at and now > assessment.end_at:
        return "ended"
    return "open"


def is_attempt_staff(user, institution_id):
    from institutions.models import Institution
    if user.is_superuser or user.institution_memberships.filter(is_active=True, institution__is_active=True, role="platform_admin").exists():
        return Institution.objects.filter(pk=institution_id, is_active=True).exists()
    return InstitutionMembership.objects.filter(
        user=user, institution_id=institution_id, role__in=STAFF_ATTEMPT_ROLES,
        is_active=True, institution__is_active=True,
    ).exists()


def is_candidate_owner(user, attempt):
    return attempt.candidate.user_id == user.pk


def active_local_date(institution):
    """Return today's date in the institution's configured timezone."""
    try:
        from zoneinfo import ZoneInfo
        return timezone.localtime(timezone.now(), ZoneInfo(institution.timezone)).date()
    except Exception:
        return timezone.localdate()
