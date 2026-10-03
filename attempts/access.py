from dataclasses import dataclass
from typing import Optional

from accounts.models import User
from assessments.models import Assessment, QuickExamSession
from candidates.models import Candidate
from institutions.models import Institution


@dataclass(frozen=True)
class ExamAccessContext:
    """Server-resolved examination identity, never constructed from request input."""

    access_mode: str
    candidate: Candidate
    assessment: Assessment
    institution: Institution
    user: Optional[User] = None
    quick_session: Optional[QuickExamSession] = None


def validate_quick_context(context):
    # Lazy import keeps the access boundary independent of HTTP authentication.
    from assessments.quick_sessions import resolve_session
    return resolve_session(session_id=context.quick_session.pk, lock=True)
