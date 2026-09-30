from .models import AuditEvent


def record_event(*, institution, actor, event_type, resource, metadata=None):
    """Append a minimal event; callers must not pass answer content or secrets."""
    return AuditEvent.objects.create(
        institution=institution,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        event_type=event_type,
        resource_type=resource._meta.label_lower,
        resource_id=str(resource.pk),
        metadata=metadata or {},
    )
