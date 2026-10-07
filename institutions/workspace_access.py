"""Server-side mode restrictions, in addition to existing role/tenant checks."""
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Institution
from .permissions import is_platform_administrator


def can_release_results(actor, institution_id):
    if not getattr(actor, "is_authenticated", False):
        return False
    if is_platform_administrator(actor):
        return Institution.objects.filter(pk=institution_id, is_active=True).exists()
    return actor.institution_memberships.filter(
        institution_id=institution_id, is_active=True, role="institution_admin",
        institution__is_active=True, institution__can_release_candidate_results=True,
    ).exists()


def require_result_release(actor, institution_id):
    # Permission toggles and publication serialize on the client row. Callers are atomic.
    Institution.objects.select_for_update().get(pk=institution_id)
    if not can_release_results(actor, institution_id):
        raise PermissionDenied("You do not have permission to release these results.")


def enforce_workspace_mode(request, module):
    if module is None:
        return
    user = request.user
    if not user.is_authenticated:
        return  # Existing authentication permissions remain authoritative.
    if is_platform_administrator(user):
        return  # Existing selected-client role checks still apply to preparation.
    memberships = user.institution_memberships.filter(
        is_active=True, institution__is_active=True,
        role__in=("institution_admin", "teacher", "examiner"),
    )
    selector = request.headers.get("X-Institution-ID") or request.query_params.get("institution")
    if selector:
        try:
            institution_id = int(selector)
        except (TypeError, ValueError):
            memberships = memberships.none()  # Existing context validation reports invalid selectors.
        else:
            memberships = memberships.filter(institution_id=institution_id)
    elif memberships.values("institution_id").distinct().count() > 1 and memberships.filter(
        institution__workspace_mode=Institution.WorkspaceMode.MANAGED_EXAM,
    ).exists():
        raise ValidationError({"institution": "Select a workspace."})
    if not memberships.filter(institution__workspace_mode=Institution.WorkspaceMode.MANAGED_EXAM).exists():
        return
    if module in {"questions", "subjects", "groups", "memberships", "institution"}:
        raise PermissionDenied("This page is not available in this workspace.")
    if module == "preparation" or (module == "assessments" and request.method not in ("GET", "HEAD", "OPTIONS")):
        raise PermissionDenied("Examination preparation requires platform administration.")


class WorkspaceAccessMixin:
    workspace_module = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        enforce_workspace_mode(request, self.workspace_module)
