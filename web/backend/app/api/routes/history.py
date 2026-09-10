from fastapi import (
    APIRouter,
    Depends,
    Query,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.event_log import EventLog
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

    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),

    db: Session = Depends(get_db),
):
    stmt = select(EventLog)

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

    stmt = (
        stmt
        .order_by(
            EventLog.created_at.desc()
        )
        .limit(limit)
    )

    return db.scalars(stmt).all()