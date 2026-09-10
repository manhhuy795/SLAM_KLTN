from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.db.deps import get_db

from app.models.location import Location
from app.models.operator import Operator
from app.models.product import Product
from app.models.robot import Robot
from app.models.task import Task
from app.models.task_proof import TaskProof

from app.schemas.task import (
    TaskCreate,
    TaskOut,
    TaskProofCreate,
    TaskProofOut,
    TaskStatusUpdate,
)

from app.services.event_logger import add_event
from app.services.realtime import queue_broadcast, queue_event
from app.services.robot_command import (
    add_robot_command,
    build_robot_command_response,
)


router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
)


PickupLocation = aliased(Location)
DropoffLocation = aliased(Location)


LIFECYCLE_STATUSES = (
    "WAITING",
    "MOVING_TO_PICKUP",
    "ARRIVED_AT_PICKUP",
    "PICKUP_CONFIRMED",
    "TRANSPORTING",
    "ARRIVED_AT_DELIVERY",
    "DELIVERY_CONFIRMED",
    "COMPLETED",
)

TERMINAL_STATUSES = {
    "COMPLETED",
    "FAILED",
    "CANCELLED",
}

PROGRESS_BY_STATUS = {
    "WAITING": 0,
    "MOVING_TO_PICKUP": 15,
    "ARRIVED_AT_PICKUP": 30,
    "PICKUP_CONFIRMED": 40,
    "TRANSPORTING": 60,
    "ARRIVED_AT_DELIVERY": 75,
    "DELIVERY_CONFIRMED": 90,
    "COMPLETED": 100,
}


def task_query():
    return (
        select(
            Task,
            Product,
            Robot,
            PickupLocation,
            DropoffLocation,
        )
        .join(
            Product,
            Task.product_id == Product.id,
        )
        .outerjoin(
            Robot,
            Task.robot_id == Robot.id,
        )
        .join(
            PickupLocation,
            Task.pickup_location_id == PickupLocation.id,
        )
        .join(
            DropoffLocation,
            Task.dropoff_location_id == DropoffLocation.id,
        )
    )


def build_task_response(row):
    task, product, robot, pickup, dropoff = row

    return {
        "id": task.id,
        "task_code": task.task_code,

        "product_id": product.id,
        "product_code": product.product_code,
        "product_name": product.name,

        "robot_id": robot.id if robot else None,
        "robot_code": robot.robot_code if robot else None,

        "pickup_location_id": pickup.id,
        "pickup_location_code": pickup.code,
        "pickup_location_name": pickup.name,

        "dropoff_location_id": dropoff.id,
        "dropoff_location_code": dropoff.code,
        "dropoff_location_name": dropoff.name,

        "status": task.status,
        "progress": task.progress,

        "is_paused": task.is_paused,
        "cancel_requested": task.cancel_requested,

        "fail_reason": task.fail_reason,
        "retry_of_task_id": task.retry_of_task_id,

        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "updated_at": task.updated_at,
    }


def build_proof_response(proof: TaskProof):
    return {
        "id": proof.id,
        "task_id": proof.task_id,
        "proof_type": proof.proof_type,
        "image_path": proof.image_path,
        "verification_status": proof.verification_status,
        "confirmed_by": proof.confirmed_by,
        "captured_at": proof.captured_at,
        "verified_at": proof.verified_at,
    }


@router.get(
    "",
    response_model=list[TaskOut],
)
def get_tasks(
    db: Session = Depends(get_db),
):
    rows = db.execute(
        task_query().order_by(Task.id.desc())
    ).all()

    return [
        build_task_response(row)
        for row in rows
    ]


@router.get(
    "/{task_id}",
    response_model=TaskOut,
)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    row = db.execute(
        task_query().where(Task.id == task_id)
    ).first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    return build_task_response(row)


@router.post(
    "",
    response_model=TaskOut,
    status_code=201,
)
def create_task(
    data: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    product = db.get(
        Product,
        data.product_id,
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    dropoff = db.get(
        Location,
        data.dropoff_location_id,
    )

    if dropoff is None:
        raise HTTPException(
            status_code=404,
            detail="Dropoff location not found",
        )

    if dropoff.location_type != "DELIVERY":
        raise HTTPException(
            status_code=400,
            detail="Selected location is not a delivery location",
        )

    robot = None

    if data.robot_id is not None:
        robot = db.get(
            Robot,
            data.robot_id,
        )

        if robot is None:
            raise HTTPException(
                status_code=404,
                detail="Robot not found",
            )

        if not robot.is_active:
            raise HTTPException(
                status_code=400,
                detail="Robot is inactive",
            )

    pickup = db.get(
        Location,
        product.default_rack_id,
    )

    if pickup is None:
        raise HTTPException(
            status_code=400,
            detail="Product default rack does not exist",
        )

    max_id = db.scalar(
        select(
            func.max(Task.id)
        )
    ) or 0

    next_number = max_id + 1

    retry_task = None

    if data.retry_of_task_id is not None:
        retry_task = db.get(
            Task,
            data.retry_of_task_id,
        )

        if retry_task is None:
            raise HTTPException(
                status_code=404,
                detail="Original task not found",
            )

        if retry_task.status != "FAILED":
            raise HTTPException(
                status_code=400,
                detail="Only failed tasks can be retried",
            )
    task = Task(
        task_code=f"T-{next_number:04d}",
        product_id=product.id,
        robot_id=robot.id if robot else None,

        pickup_location_id=pickup.id,
        dropoff_location_id=dropoff.id,

        status="WAITING",
        progress=0,

        is_paused=False,
        cancel_requested=False,
        retry_of_task_id=data.retry_of_task_id,
    )

    db.add(task)
    db.flush()
    event = add_event(
        db=db,
        event_type="TASK_CREATED",
        source="OPERATOR",
        message=f"Task {task.task_code} created.",
        robot_id=task.robot_id,
        task_id=task.id,
        metadata={
            "product_id": task.product_id,
            "dropoff_location_id": task.dropoff_location_id,
        },
    )
    db.commit()
    db.refresh(task)
    db.refresh(event)
    queue_event(background_tasks, event)

    row = db.execute(
        task_query().where(Task.id == task.id)
    ).first()

    response = build_task_response(row)
    queue_broadcast(
        background_tasks,
        "TASK_UPDATED",
        response,
    )

    return response


@router.patch(
    "/{task_id}/pause",
    response_model=TaskOut,
)
def pause_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    if task.status in {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }:
        raise HTTPException(
            status_code=400,
            detail="Terminal task cannot be paused",
        )

    if task.robot_id is None:
        raise HTTPException(
            status_code=400,
            detail="Task has no assigned robot",
        )

    command = add_robot_command(
        db=db,
        robot_id=task.robot_id,
        command="PAUSE",
        task_id=task.id,
    )
    event = add_event(
        db=db,
        event_type="ROBOT_COMMAND_CREATED",
        source="OPERATOR",
        message=f"PAUSE command created for task {task.task_code}.",
        robot_id=task.robot_id,
        task_id=task.id,
        metadata={"command_id": command.id, "command": command.command},
    )

    db.commit()
    db.refresh(event)
    db.refresh(command)
    queue_event(background_tasks, event)
    queue_broadcast(
        background_tasks,
        "COMMAND_CREATED",
        build_robot_command_response(command),
    )

    row = db.execute(
        task_query().where(Task.id == task.id)
    ).first()

    response = build_task_response(row)
    queue_broadcast(
        background_tasks,
        "TASK_UPDATED",
        response,
    )

    return response


@router.patch(
    "/{task_id}/resume",
    response_model=TaskOut,
)
def resume_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    if task.status in {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }:
        raise HTTPException(
            status_code=400,
            detail="Terminal task cannot be resumed",
        )

    if task.robot_id is None:
        raise HTTPException(
            status_code=400,
            detail="Task has no assigned robot",
        )

    command = add_robot_command(
        db=db,
        robot_id=task.robot_id,
        command="RESUME",
        task_id=task.id,
    )
    event = add_event(
        db=db,
        event_type="ROBOT_COMMAND_CREATED",
        source="OPERATOR",
        message=f"RESUME command created for task {task.task_code}.",
        robot_id=task.robot_id,
        task_id=task.id,
        metadata={"command_id": command.id, "command": command.command},
    )

    db.commit()
    db.refresh(event)
    db.refresh(command)
    queue_event(background_tasks, event)
    queue_broadcast(
        background_tasks,
        "COMMAND_CREATED",
        build_robot_command_response(command),
    )

    row = db.execute(
        task_query().where(Task.id == task.id)
    ).first()

    response = build_task_response(row)
    queue_broadcast(
        background_tasks,
        "TASK_UPDATED",
        response,
    )

    return response


@router.patch(
    "/{task_id}/cancel",
    response_model=TaskOut,
)
def request_cancel_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    if task.status in {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }:
        raise HTTPException(
            status_code=400,
            detail="Terminal task cannot be cancelled",
        )

    if task.robot_id is None:
        raise HTTPException(
            status_code=400,
            detail="Task has no assigned robot",
        )

    task.cancel_requested = True
    task.updated_at = datetime.utcnow()
    command = add_robot_command(
        db=db,
        robot_id=task.robot_id,
        command="CANCEL",
        task_id=task.id,
    )
    event = add_event(
        db=db,
        event_type="ROBOT_COMMAND_CREATED",
        source="OPERATOR",
        message=f"CANCEL command created for task {task.task_code}.",
        robot_id=task.robot_id,
        task_id=task.id,
        metadata={"command_id": command.id, "command": command.command},
    )

    db.commit()
    db.refresh(event)
    db.refresh(command)
    queue_event(background_tasks, event)
    queue_broadcast(
        background_tasks,
        "COMMAND_CREATED",
        build_robot_command_response(command),
    )

    row = db.execute(
        task_query().where(Task.id == task.id)
    ).first()

    response = build_task_response(row)
    queue_broadcast(
        background_tasks,
        "TASK_UPDATED",
        response,
    )

    return response


@router.patch(
    "/{task_id}/status",
    response_model=TaskOut,
)
def update_task_status(
    task_id: int,
    data: TaskStatusUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    current_status = task.status
    next_status = data.status

    if current_status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Terminal task cannot change status",
        )

    if next_status == current_status:
        raise HTTPException(
            status_code=400,
            detail="Task is already in this status",
        )

    if next_status not in {"FAILED", "CANCELLED"}:
        if (
            current_status not in LIFECYCLE_STATUSES
            or next_status not in LIFECYCLE_STATUSES
            or LIFECYCLE_STATUSES.index(next_status)
            != LIFECYCLE_STATUSES.index(current_status) + 1
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid task status transition",
            )

    if next_status == "FAILED":
        task.fail_reason = data.fail_reason

    if next_status == "MOVING_TO_PICKUP" and task.started_at is None:
        task.started_at = datetime.utcnow()

    if next_status in PROGRESS_BY_STATUS:
        task.progress = PROGRESS_BY_STATUS[next_status]

    task.status = next_status

    if next_status == "COMPLETED":
        task.progress = 100
        task.completed_at = datetime.utcnow()

    task.updated_at = datetime.utcnow()

    events = []

    events.append(
        add_event(
            db=db,
            event_type="TASK_STATUS_CHANGED",
            source="ROBOT",
            message=(
                f"Task {task.task_code} changed from "
                f"{current_status} to {next_status}."
            ),
            robot_id=task.robot_id,
            task_id=task.id,
            metadata={
                "from_status": current_status,
                "to_status": next_status,
            },
        )
    )

    if next_status == "FAILED":
        events.append(
            add_event(
                db=db,
                event_type="TASK_FAILED",
                source="ROBOT",
                message=f"Task {task.task_code} failed.",
                robot_id=task.robot_id,
                task_id=task.id,
                metadata={
                    "fail_reason": task.fail_reason,
                },
            )
        )

    if next_status == "COMPLETED":
        events.append(
            add_event(
                db=db,
                event_type="TASK_COMPLETED",
                source="ROBOT",
                message=f"Task {task.task_code} completed.",
                robot_id=task.robot_id,
                task_id=task.id,
            )
        )

    db.commit()
    db.refresh(task)

    for event in events:
        db.refresh(event)
        queue_event(background_tasks, event)

    row = db.execute(
        task_query().where(Task.id == task.id)
    ).first()

    response = build_task_response(row)
    queue_broadcast(
        background_tasks,
        "TASK_UPDATED",
        response,
    )

    return response


@router.post(
    "/{task_id}/proofs",
    response_model=TaskProofOut,
    status_code=201,
)
def create_task_proof(
    task_id: int,
    data: TaskProofCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    operator = None

    if data.confirmed_by is not None:
        operator = db.get(
            Operator,
            data.confirmed_by,
        )

        if operator is None:
            raise HTTPException(
                status_code=404,
                detail="Operator not found",
            )

    if (
        data.verification_status == "MANUAL_CONFIRMED"
        and operator is None
    ):
        raise HTTPException(
            status_code=400,
            detail="MANUAL_CONFIRMED requires confirmed_by",
        )

    is_verified = data.verification_status in {
        "AUTO_VERIFIED",
        "MANUAL_CONFIRMED",
    }
    captured_at = datetime.utcnow()

    proof = TaskProof(
        task_id=task.id,
        proof_type=data.proof_type,
        image_path=data.image_path,
        verification_status=data.verification_status,
        confirmed_by=operator.id if operator else None,
        captured_at=captured_at,
        verified_at=captured_at if is_verified else None,
    )

    db.add(proof)
    db.flush()

    event_source = "OPERATOR" if operator else "ROBOT"

    events = [
        add_event(
            db=db,
            event_type="TASK_PROOF_CREATED",
            source=event_source,
            message=f"Proof created for task {task.task_code}.",
            robot_id=task.robot_id,
            task_id=task.id,
            operator_id=proof.confirmed_by,
            metadata={
                "proof_id": proof.id,
                "proof_type": proof.proof_type,
                "verification_status": proof.verification_status,
            },
        )
    ]

    confirmation_status = {
        "PICKUP": "PICKUP_CONFIRMED",
        "DELIVERY": "DELIVERY_CONFIRMED",
    }[proof.proof_type]
    expected_status = {
        "PICKUP": "ARRIVED_AT_PICKUP",
        "DELIVERY": "ARRIVED_AT_DELIVERY",
    }[proof.proof_type]

    if is_verified and task.status == expected_status:
        old_status = task.status
        task.status = confirmation_status
        task.progress = PROGRESS_BY_STATUS[confirmation_status]
        task.updated_at = datetime.utcnow()

        events.append(
            add_event(
                db=db,
                event_type="TASK_STATUS_CHANGED",
                source=event_source,
                message=(
                    f"Task {task.task_code} changed from "
                    f"{old_status} to {confirmation_status}."
                ),
                robot_id=task.robot_id,
                task_id=task.id,
                operator_id=proof.confirmed_by,
                metadata={
                    "from_status": old_status,
                    "to_status": confirmation_status,
                },
            )
        )

        events.append(
            add_event(
                db=db,
                event_type=f"TASK_{proof.proof_type}_CONFIRMED",
                source=event_source,
                message=(
                    f"Task {task.task_code} {proof.proof_type.lower()} "
                    "confirmed."
                ),
                robot_id=task.robot_id,
                task_id=task.id,
                operator_id=proof.confirmed_by,
                metadata={
                    "proof_id": proof.id,
                },
            )
        )

    db.commit()
    db.refresh(proof)

    for event in events:
        db.refresh(event)
        queue_event(background_tasks, event)

    row = db.execute(
        task_query().where(Task.id == task.id)
    ).first()
    queue_broadcast(
        background_tasks,
        "TASK_UPDATED",
        build_task_response(row),
    )

    return build_proof_response(proof)


@router.get(
    "/{task_id}/proofs",
    response_model=list[TaskProofOut],
)
def get_task_proofs(
    task_id: int,
    db: Session = Depends(get_db),
):
    if db.get(Task, task_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    proofs = db.scalars(
        select(TaskProof)
        .where(TaskProof.task_id == task_id)
        .order_by(TaskProof.id)
    ).all()

    return [
        build_proof_response(proof)
        for proof in proofs
    ]
