from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.tasks import (
    TERMINAL_STATUSES,
    build_task_response,
    task_query,
)
from app.db.deps import get_db
from app.models.robot import Robot
from app.models.robot_command import RobotCommand
from app.models.robot_status import RobotStatus
from app.models.task import Task
from app.schemas.robot_command import (
    RobotCommandAck,
    RobotCommandCreate,
    RobotCommandOut,
)
from app.services.event_logger import add_event
from app.services.realtime import queue_broadcast, queue_event
from app.services.robot_command import (
    add_robot_command,
    build_robot_command_response,
)


router = APIRouter(
    prefix="/robots",
    tags=["Robot Commands"],
)


@router.post(
    "/safe-stop",
    response_model=list[RobotCommandOut],
    status_code=201,
)
def request_safe_stop(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Robot, RobotStatus)
        .join(RobotStatus, Robot.id == RobotStatus.robot_id)
        .where(
            Robot.is_active.is_(True),
            RobotStatus.online.is_(True),
        )
        .order_by(Robot.id)
    ).all()

    events = [
        add_event(
            db=db,
            event_type="SAFE_STOP_REQUESTED",
            source="OPERATOR",
            message="Safe Stop software request sent to online robots.",
            metadata={"robot_count": len(rows)},
        )
    ]
    commands = []

    for robot, _status in rows:
        command = add_robot_command(
            db=db,
            robot_id=robot.id,
            command="SAFE_STOP",
        )
        commands.append(command)
        events.append(
            add_event(
                db=db,
                event_type="ROBOT_COMMAND_CREATED",
                source="OPERATOR",
                message=f"SAFE_STOP command created for robot {robot.robot_code}.",
                robot_id=robot.id,
                metadata={"command_id": command.id, "command": command.command},
            )
        )

    db.commit()

    for command in commands:
        db.refresh(command)
        queue_broadcast(
            background_tasks,
            "COMMAND_CREATED",
            build_robot_command_response(command),
        )

    for event in events:
        db.refresh(event)
        queue_event(background_tasks, event)

    return [
        build_robot_command_response(command)
        for command in commands
    ]


@router.post(
    "/{robot_id}/commands",
    response_model=RobotCommandOut,
    status_code=201,
)
def create_robot_command(
    robot_id: int,
    data: RobotCommandCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    robot = db.get(Robot, robot_id)

    if robot is None:
        raise HTTPException(status_code=404, detail="Robot not found")

    if data.command == "SAFE_STOP":
        status = db.get(RobotStatus, robot.id)
        if not robot.is_active or status is None or not status.online:
            raise HTTPException(
                status_code=400,
                detail="Robot is offline or inactive",
            )

    task = None
    if data.task_id is not None:
        task = db.get(Task, data.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.robot_id != robot.id:
            raise HTTPException(
                status_code=400,
                detail="Task is not assigned to this robot",
            )
        if task.status in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail="Terminal task cannot receive a command",
            )

    if data.command == "CANCEL" and task is not None:
        task.cancel_requested = True
        task.updated_at = datetime.utcnow()

    command = add_robot_command(
        db=db,
        robot_id=robot.id,
        command=data.command,
        task_id=task.id if task else None,
    )
    events = [
        add_event(
            db=db,
            event_type="ROBOT_COMMAND_CREATED",
            source="OPERATOR",
            message=f"{command.command} command created for robot {robot.robot_code}.",
            robot_id=robot.id,
            task_id=command.task_id,
            metadata={"command_id": command.id, "command": command.command},
        )
    ]

    if command.command == "SAFE_STOP":
        events.append(
            add_event(
                db=db,
                event_type="SAFE_STOP_REQUESTED",
                source="OPERATOR",
                message=f"Safe Stop software request sent to robot {robot.robot_code}.",
                robot_id=robot.id,
                metadata={"command_id": command.id},
            )
        )

    db.commit()
    db.refresh(command)

    for event in events:
        db.refresh(event)
        queue_event(background_tasks, event)

    queue_broadcast(
        background_tasks,
        "COMMAND_CREATED",
        build_robot_command_response(command),
    )

    if task is not None and data.command == "CANCEL":
        row = db.execute(task_query().where(Task.id == task.id)).first()
        queue_broadcast(
            background_tasks,
            "TASK_UPDATED",
            build_task_response(row),
        )

    return build_robot_command_response(command)


@router.patch(
    "/{robot_id}/commands/{command_id}/ack",
    response_model=RobotCommandOut,
)
def acknowledge_robot_command(
    robot_id: int,
    command_id: int,
    data: RobotCommandAck,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    command = db.get(RobotCommand, command_id)

    if command is None or command.robot_id != robot_id:
        raise HTTPException(status_code=404, detail="Command not found")

    if command.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail="Command has already been acknowledged",
        )

    command.status = data.status
    command.failure_reason = data.failure_reason
    command.acknowledged_at = datetime.utcnow()

    task = None
    events = []

    if data.status == "ACKNOWLEDGED":
        events.append(
            add_event(
                db=db,
                event_type="ROBOT_COMMAND_ACKNOWLEDGED",
                source="ROBOT",
                message=f"Robot command {command.id} acknowledged.",
                robot_id=command.robot_id,
                task_id=command.task_id,
                metadata={"command_id": command.id, "command": command.command},
            )
        )

        if command.task_id is not None:
            task = db.get(Task, command.task_id)
            if task is not None:
                old_status = task.status
                if command.command == "PAUSE":
                    task.is_paused = True
                elif command.command == "RESUME":
                    task.is_paused = False
                elif command.command == "CANCEL":
                    task.cancel_requested = True
                    if task.status not in TERMINAL_STATUSES:
                        task.status = "CANCELLED"

                task.updated_at = datetime.utcnow()

                if task.status != old_status:
                    events.append(
                        add_event(
                            db=db,
                            event_type="TASK_STATUS_CHANGED",
                            source="ROBOT",
                            message=(
                                f"Task {task.task_code} changed from "
                                f"{old_status} to {task.status}."
                            ),
                            robot_id=task.robot_id,
                            task_id=task.id,
                            metadata={
                                "from_status": old_status,
                                "to_status": task.status,
                                "command_id": command.id,
                            },
                        )
                    )
    else:
        events.append(
            add_event(
                db=db,
                event_type="ROBOT_COMMAND_FAILED",
                source="ROBOT",
                message=f"Robot command {command.id} failed.",
                robot_id=command.robot_id,
                task_id=command.task_id,
                metadata={
                    "command_id": command.id,
                    "command": command.command,
                    "failure_reason": command.failure_reason,
                },
            )
        )

    db.commit()
    db.refresh(command)

    for event in events:
        db.refresh(event)
        queue_event(background_tasks, event)

    queue_broadcast(
        background_tasks,
        "COMMAND_ACKNOWLEDGED"
        if data.status == "ACKNOWLEDGED"
        else "COMMAND_FAILED",
        build_robot_command_response(command),
    )

    if task is not None:
        db.refresh(task)
        row = db.execute(task_query().where(Task.id == task.id)).first()
        queue_broadcast(
            background_tasks,
            "TASK_UPDATED",
            build_task_response(row),
        )

    return build_robot_command_response(command)
