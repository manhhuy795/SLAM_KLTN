from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.event_log import EventLog
from app.models.robot import Robot
from app.models.task import Task
from app.schemas.history import EventLogOut


router = APIRouter(
    prefix="/history",
    tags=["History"],
)


@router.get(
    "",
    response_model=list[EventLogOut],
)
def get_history(
    robot_id: int | None = None,
    task_id: int | None = None,
    operator_id: int | None = None,
    event_type: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,

    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),

    db: Session = Depends(get_db),
):
    if (
        created_from is not None
        and created_to is not None
        and created_from > created_to
    ):
        raise HTTPException(
            status_code=400,
            detail="created_from must be before created_to",
        )

    stmt = (
        select(
            EventLog,
            Robot.robot_code,
            Task.task_code,
        )
        .outerjoin(
            Robot,
            EventLog.robot_id == Robot.id,
        )
        .outerjoin(
            Task,
            EventLog.task_id == Task.id,
        )
    )

    if robot_id is not None:
        stmt = stmt.where(
            EventLog.robot_id == robot_id
        )

    if task_id is not None:
        stmt = stmt.where(
            EventLog.task_id == task_id
        )

    if operator_id is not None:
        stmt = stmt.where(
            EventLog.operator_id == operator_id
        )

    if event_type is not None:
        stmt = stmt.where(
            EventLog.event_type == event_type
        )

    if created_from is not None:
        stmt = stmt.where(
            EventLog.created_at >= created_from
        )

    if created_to is not None:
        stmt = stmt.where(
            EventLog.created_at <= created_to
        )

    stmt = (
        stmt
        .order_by(
            EventLog.created_at.desc()
        )
        .limit(limit)
    )

    return [
        {
            "id": event.id,
            "robot_id": event.robot_id,
            "robot_code": robot_code,
            "task_id": event.task_id,
            "task_code": task_code,
            "operator_id": event.operator_id,
            "event_type": event.event_type,
            "source": event.source,
            "message": event.message,
            "metadata_json": event.metadata_json,
            "created_at": event.created_at,
        }
        for event, robot_code, task_code in db.execute(stmt).all()
    ]
