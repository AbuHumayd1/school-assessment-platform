from .models import AuditEvent


def record_event(*, institution, actor, event_type, resource, metadata=None):
    """Append a minimal event; callers must not pass answer content or secrets."""
    metadata = dict(metadata or {})
    if getattr(actor, "is_authenticated", False):
        from institutions.permissions import is_platform_administrator
        if is_platform_administrator(actor):
            metadata["management_context"] = "platform"
    return AuditEvent.objects.create(
        institution=institution,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        event_type=event_type,
        resource_type=resource._meta.label_lower,
        resource_id=str(resource.pk),
        metadata=metadata or {},
    )
