"""Assessment lifecycle events; use existing append-only audit storage."""
from audit.services import record_event


def audit_assessment(resource, actor, action, **metadata):
    assessment = getattr(resource, "assessment", resource)
    record_event(
        institution=assessment.institution, actor=actor,
        event_type=action, resource=resource,
        metadata={"assessment_id": assessment.pk, **metadata},
    )
