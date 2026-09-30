from django.utils import timezone

from candidates.models import Candidate
from tenants.models import InstitutionMembership


STAFF_ATTEMPT_ROLES = {"platform_admin", "institution_admin", "examiner"}


def candidates_for_user(user):
    return Candidate.objects.filter(user=user, institution__is_active=True)


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
