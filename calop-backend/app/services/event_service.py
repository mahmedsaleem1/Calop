import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.request_context import request_id_var
from app.models import Event


def record_event(
    db: Session,
    actor_type: str,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: Any,
    data: dict | None = None,
) -> Event:
    """Adds an Event to the session without committing, so it commits with the change itself.
    Never put tokens, API keys or passwords in `data`."""
    request_id = request_id_var.get()
    event = Event(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        request_id=uuid.UUID(request_id) if request_id else None,
        data=data,
    )
    db.add(event)
    return event
