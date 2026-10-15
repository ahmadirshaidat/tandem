"""Audit contains metadata only, never free text, prompts or provider responses."""

from app.agent.models import AuditEvent


def audit(
    db,
    workspace_id,
    actor_type,
    actor_id,
    action,
    target_type,
    target_id,
    status="ok",
    arguments=None,
    request_id=None,
):
    event = AuditEvent(
        workspace_id=workspace_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        result_status=status,
        redacted_arguments=arguments or {},
    )
    if request_id:
        event.request_id = request_id
    db.add(event)
    return event
