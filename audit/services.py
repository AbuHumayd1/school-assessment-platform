from .models import AuditEvent


def record_event(*, institution, actor, event_type, resource, metadata=None):
    """Append a minimal event; callers must not pass answer content or secrets."""
    metadata = dict(metadata or {})
    if institution is None:
        from institutions.permissions import is_platform_administrator
        from django.core.exceptions import ValidationError
        if not is_platform_administrator(actor) or getattr(resource, 'owner_scope', None) != 'platform':
            raise ValidationError('Platform audit events require a platform actor and resource.')
        metadata['content_scope'] = 'platform'
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
