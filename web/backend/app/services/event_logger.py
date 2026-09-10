import json

from sqlalchemy.orm import Session

from app.models.event_log import EventLog


def add_event(
    db: Session,
    event_type: str,
    source: str,
    message: str,
    robot_id: int | None = None,
    task_id: int | None = None,
    operator_id: int | None = None,
    metadata: dict | None = None,
):
    event = EventLog(
        robot_id=robot_id,
        task_id=task_id,
        operator_id=operator_id,
        event_type=event_type,
        source=source,
        message=message,
        metadata_json=(
            json.dumps(metadata, ensure_ascii=False)
            if metadata is not None
            else None
        ),
    )

    db.add(event)

    return event