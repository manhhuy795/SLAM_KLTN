from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.robot import Robot
from app.models.robot_status import RobotStatus
from app.schemas.robot import RobotOut, RobotStatusUpdate
from app.services.event_logger import add_event
from app.services.realtime import queue_broadcast, queue_event


router = APIRouter(
    prefix="/robots",
    tags=["Robots"],
)


def build_robot_response(
    robot: Robot,
    status: RobotStatus | None,
):
    status_data = None

    if status is not None:
        status_data = {
            "online": status.online,
            "state": status.state,
            "battery_percent": status.battery_percent,
            "voltage": status.voltage,
            "x": status.x,
            "y": status.y,
            "yaw": status.yaw,
            "line_segment_id": status.line_segment_id,
            "localization_quality": status.localization_quality,
        }

    return {
        "id": robot.id,
        "robot_code": robot.robot_code,
        "name": robot.name,
        "robot_type": robot.robot_type,
        "model": robot.model,
        "is_active": robot.is_active,
        "status": status_data,
    }


@router.get(
    "",
    response_model=list[RobotOut],
)
def get_robots(
    db: Session = Depends(get_db),
):
    stmt = (
        select(Robot, RobotStatus)
        .outerjoin(
            RobotStatus,
            Robot.id == RobotStatus.robot_id,
        )
        .order_by(Robot.id)
    )

    rows = db.execute(stmt).all()

    return [
        build_robot_response(robot, status)
        for robot, status in rows
    ]


@router.get(
    "/{robot_id}",
    response_model=RobotOut,
)
def get_robot(
    robot_id: int,
    db: Session = Depends(get_db),
):
    stmt = (
        select(Robot, RobotStatus)
        .outerjoin(
            RobotStatus,
            Robot.id == RobotStatus.robot_id,
        )
        .where(Robot.id == robot_id)
    )

    row = db.execute(stmt).first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Robot not found",
        )

    robot, status = row

    return build_robot_response(robot, status)


@router.patch(
    "/{robot_id}/status",
    response_model=RobotOut,
)
def update_robot_status(
    robot_id: int,
    data: RobotStatusUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    robot = db.get(Robot, robot_id)

    if robot is None:
        raise HTTPException(
            status_code=404,
            detail="Robot not found",
        )

    status = db.get(RobotStatus, robot_id)

    if status is None:
        status = RobotStatus(
            robot_id=robot.id,
            online=False,
            state="UNKNOWN",
        )
        db.add(status)

    previous_online = status.online
    previous_state = status.state

    for field, value in data.model_dump(
        exclude_unset=True
    ).items():
        setattr(status, field, value)

    status.updated_at = datetime.utcnow()

    event = None
    if status.online != previous_online or status.state != previous_state:
        event = add_event(
            db=db,
            event_type="ROBOT_STATUS_UPDATED",
            source="SIMULATION",
            message=f"Robot {robot.robot_code} status updated.",
            robot_id=robot.id,
            metadata={
                "online": status.online,
                "state": status.state,
            },
        )

    db.commit()
    db.refresh(status)

    if event is not None:
        db.refresh(event)
        queue_event(background_tasks, event)

    response = build_robot_response(robot, status)

    queue_broadcast(
        background_tasks,
        "ROBOT_STATUS_UPDATED",
        response,
    )

    return response
