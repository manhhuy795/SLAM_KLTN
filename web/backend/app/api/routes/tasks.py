from datetime import datetime
import hmac
import os
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.db.deps import get_db

from app.models.location import Location
from app.models.operator import Operator
from app.models.product import Product
from app.models.robot import Robot
from app.models.task import Task
from app.models.task_proof import TaskProof
from app.models.agv_mission import AgvMission
from app.models.agv_cargo_evidence import AgvCargoEvidence
from app.models.agv_vision import AgvVisionCapture, AgvVisionJob

from app.schemas.task import (
    TaskCreate,
    TaskOut,
    TaskProofCreate,
    TaskProofOut,
    TaskStatusUpdate,
    AgvPickupTaskCreate,
    AgvPolicyUpdate,
    AgvVisionCaptureCreate,
    AgvVisionReview,
)

from app.services.event_logger import add_event
from app.services.realtime import queue_broadcast, queue_event
from app.services.robot_command import (
    add_robot_command,
    build_robot_command_response,
)
from app.services.task_executor import TaskExecutorError, task_executor
from app.services.agv_mission_adapter import agv_mission_adapter
from app.services.agv_mission_store import AgvMissionConflict
from app.services.agv_vision import (
    AgvVisionError, agv_pickup_classifier, configure_policy,
)
from app.models.saved_map import SavedMap


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
            AgvVisionJob,
        )
        .outerjoin(
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
        .outerjoin(
            DropoffLocation,
            Task.dropoff_location_id == DropoffLocation.id,
        )
        .outerjoin(AgvVisionJob, AgvVisionJob.task_id == Task.id)
    )


def build_task_response(row):
    task, product, robot, pickup, dropoff, vision_job = row
    unassigned = vision_job is not None and vision_job.status != "ASSIGNED"

    return {
        "id": task.id,
        "task_code": task.task_code,

        "product_id": product.id if product else None,
        "product_code": product.product_code if product else None,
        "product_name": product.name if product else None,

        "robot_id": robot.id if robot else None,
        "robot_code": robot.robot_code if robot else None,

        "pickup_location_id": pickup.id,
        "pickup_location_code": pickup.code,
        "pickup_location_name": pickup.name,

        "dropoff_location_id": None if unassigned or dropoff is None else dropoff.id,
        "dropoff_location_code": None if unassigned or dropoff is None else dropoff.code,
        "dropoff_location_name": None if unassigned or dropoff is None else dropoff.name,

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


def publish_executor_updates(background_tasks, navigation_status, events):
    for event in events:
        queue_event(background_tasks, event)
    if navigation_status is None:
        return
    queue_broadcast(
        background_tasks,
        "NAVIGATION_STATUS_UPDATED",
        navigation_status,
    )
    if navigation_status["state"] == "SENDING":
        queue_broadcast(
            background_tasks,
            "NAVIGATION_PATH_UPDATED",
            {"frame_id": "map", "poses": []},
        )


def publish_agv_callback_updates(background_tasks, result, db):
    """Reuse existing task/event WS shapes for authenticated future AGV callbacks."""
    if result is None:
        return False
    task, events = result
    for event in events:
        queue_event(background_tasks, event)
    row = db.execute(task_query().where(Task.id == task.id)).first()
    queue_broadcast(background_tasks, "TASK_UPDATED", build_task_response(row))
    return True


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


@router.post("/agv", response_model=TaskOut, status_code=201)
def create_agv_pickup_task(data: AgvPickupTaskCreate,
                           background_tasks: BackgroundTasks,
                           db: Session = Depends(get_db)):
    """Create a LINE task with an explicitly unassigned destination."""
    product = db.get(Product, data.product_id) if data.product_id is not None else None
    robot = db.get(Robot, data.robot_id)
    pickup = db.scalar(select(Location).where(Location.code == "PICKUP"))
    maps = db.scalars(select(SavedMap).where(SavedMap.is_selected.is_(True)).limit(2)).all()
    if ((data.product_id is not None and product is None) or robot is None
            or robot.robot_type != "LINE" or not robot.is_active):
        raise HTTPException(400, "Active LINE robot and valid product are required")
    if pickup is None or pickup.location_type != "PICKUP" or not pickup.is_active or len(maps) != 1:
        raise HTTPException(409, "Active PICKUP station and selected map are required")
    task = Task(task_code=f"AGV-{uuid4().hex[:20]}", product_id=product.id if product else None,
                robot_id=robot.id, pickup_location_id=pickup.id,
                dropoff_location_id=None, status="WAITING", progress=0,
                is_paused=False, cancel_requested=False)
    db.add(task)
    db.flush()
    db.add(AgvVisionJob(task_id=task.id, robot_id=robot.id,
                        map_id=maps[0].id, status="PENDING"))
    event = add_event(db=db, event_type="TASK_CREATED", source="OPERATOR",
                      message=f"Task {task.task_code} created for AGV pickup.",
                      robot_id=robot.id, task_id=task.id,
                      metadata={"destination_assignment": "PENDING"})
    db.commit()
    db.refresh(event)
    queue_event(background_tasks, event)
    row = db.execute(task_query().where(Task.id == task.id)).first()
    response = build_task_response(row)
    queue_broadcast(background_tasks, "TASK_UPDATED", response)
    return response


@router.put("/agv/class-rack-policy")
def update_agv_class_rack_policy(data: AgvPolicyUpdate,
                                  x_wrms_policy_token: str | None = Header(
                                      default=None, alias="X-WRMS-Policy-Token"),
                                  db: Session = Depends(get_db)):
    expected = os.getenv("WRMS_AGV_POLICY_TOKEN", "")
    if not expected or not x_wrms_policy_token or not hmac.compare_digest(expected, x_wrms_policy_token):
        raise HTTPException(403, "AGV policy configuration is disabled or unauthorized")
    operator = db.get(Operator, data.operator_id)
    if operator is None or not operator.is_active:
        raise HTTPException(400, "Active operator is required")
    try:
        policy = configure_policy(db, map_id=data.map_id, mapping=data.mapping,
                                  min_confidence=data.min_confidence,
                                  min_margin=data.min_margin,
                                  expected_revision=data.expected_revision)
    except AgvVisionError as error:
        raise HTTPException(409, str(error)) from error
    db.commit()
    return {"map_id": policy.map_id, "revision": policy.revision,
            "mapping": policy.mapping, "min_confidence": policy.min_confidence,
            "min_margin": policy.min_margin}


@router.post("/{task_id}/vision/captures", status_code=201)
def capture_agv_pickup_shape(task_id: int, data: AgvVisionCaptureCreate,
                              x_wrms_vision_token: str | None = Header(
                                  default=None, alias="X-WRMS-Vision-Token"),
                              db: Session = Depends(get_db)):
    expected = os.getenv("WRMS_AGV_VISION_TOKEN", "")
    if not expected or not x_wrms_vision_token or not hmac.compare_digest(expected, x_wrms_vision_token):
        raise HTTPException(403, "AGV pickup vision is disabled or unauthorized")
    try:
        capture = agv_pickup_classifier.capture(db, task_id=task_id,
            robot_id=data.robot_id, capture_id=data.capture_id, image_ref=data.image_ref)
    except AgvVisionError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    db.commit()
    return {"capture_id": capture.capture_id, "task_id": capture.task_id,
            "predicted_class": capture.predicted_class,
            "confidence": capture.confidence, "model_version": capture.model_version,
            "review_status": capture.review_status}


@router.post("/{task_id}/vision/review")
def review_agv_pickup_shape(task_id: int, data: AgvVisionReview,
                             background_tasks: BackgroundTasks,
                             x_wrms_policy_token: str | None = Header(
                                 default=None, alias="X-WRMS-Policy-Token"),
                             db: Session = Depends(get_db)):
    expected = os.getenv("WRMS_AGV_POLICY_TOKEN", "")
    if not expected or not x_wrms_policy_token or not hmac.compare_digest(expected, x_wrms_policy_token):
        raise HTTPException(403, "AGV vision review is disabled or unauthorized")
    try:
        capture, rack = agv_pickup_classifier.review(db, task_id=task_id,
            capture_id=data.capture_id, operator_id=data.operator_id, approve=data.approve)
    except AgvVisionError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    db.commit()
    row = db.execute(task_query().where(Task.id == task_id)).first()
    if rack is not None:
        queue_broadcast(background_tasks, "TASK_UPDATED", build_task_response(row))
    return {"capture_id": capture.capture_id, "review_status": capture.review_status,
            "rack_location_id": rack.id if rack else None,
            "rack_code": rack.code if rack else None}


@router.get("/{task_id}/vision")
def get_agv_vision_review(task_id: int, db: Session = Depends(get_db)):
    job = db.get(AgvVisionJob, task_id)
    if job is None:
        raise HTTPException(404, "AGV vision task not found")
    captures = db.scalars(select(AgvVisionCapture).where(
        AgvVisionCapture.task_id == task_id).order_by(AgvVisionCapture.captured_at)).all()
    return {"task_id": task_id, "status": job.status,
            "assigned_rack_id": job.assigned_rack_id,
            "captures": [{"capture_id": item.capture_id, "image_ref": item.image_ref,
                          "predicted_class": item.predicted_class,
                          "confidence": item.confidence,
                          "class_probabilities": item.probabilities,
                          "model_version": item.model_version,
                          "review_status": item.review_status,
                          "confirmed_by": item.confirmed_by}
                         for item in captures]}


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
    "/{task_id}/start",
    response_model=TaskOut,
)
def start_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    robot = db.get(Robot, task.robot_id) if task.robot_id is not None else None
    try:
        navigation_status, events = (
            agv_mission_adapter.start_pickup(db, task) if robot and robot.robot_type == "LINE"
            else task_executor.start_pickup(db, task)
        )
    except (TaskExecutorError, AgvMissionConflict) as error:
        detail = str(error)
        if detail == "AGV automatic dispatch is disabled or unconfigured":
            detail = "Task robot does not support AMR navigation"
        raise HTTPException(status_code=409, detail=detail) from error

    publish_executor_updates(background_tasks, navigation_status, events)
    row = db.execute(task_query().where(Task.id == task.id)).first()
    response = build_task_response(row)
    queue_broadcast(background_tasks, "TASK_UPDATED", response)
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

    try:
        navigation_status, executor_events = task_executor.pause(db, task)
    except TaskExecutorError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

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
    publish_executor_updates(
        background_tasks,
        navigation_status,
        executor_events,
    )
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

    try:
        navigation_status, executor_events = task_executor.resume(db, task)
    except TaskExecutorError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

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
    publish_executor_updates(
        background_tasks,
        navigation_status,
        executor_events,
    )
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

    robot = db.get(Robot, task.robot_id) if task.robot_id is not None else None

    if task.status in {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    } and not (robot and robot.robot_type == "LINE" and task.status == "COMPLETED"):
        raise HTTPException(
            status_code=400,
            detail="Terminal task cannot be cancelled",
        )

    if task.robot_id is None:
        raise HTTPException(
            status_code=400,
            detail="Task has no assigned robot",
        )

    if robot and robot.robot_type == "LINE":
        try:
            agv_mission_adapter.cancel(db, task)
        except AgvMissionConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        row = db.execute(task_query().where(Task.id == task.id)).first()
        response = build_task_response(row)
        queue_broadcast(background_tasks, "TASK_UPDATED", response)
        return response

    try:
        navigation_status, executor_events = task_executor.cancel(db, task)
    except TaskExecutorError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

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
    publish_executor_updates(
        background_tasks,
        navigation_status,
        executor_events,
    )
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

    robot = db.get(Robot, task.robot_id) if task.robot_id is not None else None
    if robot and robot.robot_type == "LINE":
        raise HTTPException(status_code=409, detail="LINE task status requires verified mission evidence")

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
    robot = db.get(Robot, task.robot_id) if task.robot_id is not None else None
    if (robot and robot.robot_type == "LINE" and is_verified
            and data.verification_status != "MANUAL_CONFIRMED"):
        raise HTTPException(status_code=409, detail="AGV automatic proof is disabled")
    if robot and robot.robot_type == "LINE" and is_verified and data.proof_type == "PICKUP":
        vision_job = db.get(AgvVisionJob, task.id)
        if vision_job is not None and vision_job.status != "ASSIGNED":
            raise HTTPException(status_code=409, detail="AGV destination rack is not assigned")
    if robot and robot.robot_type == "LINE" and is_verified and data.proof_type == "DELIVERY":
        latest_capture = db.scalar(select(AgvCargoEvidence).where(
            AgvCargoEvidence.task_id == task.id).order_by(
            AgvCargoEvidence.observed_at.desc(), AgvCargoEvidence.created_at.desc()).limit(1))
        if latest_capture and latest_capture.presence == "PRESENT":
            raise HTTPException(status_code=409, detail="Cargo is still present; delivery proof is blocked")
    expected_status = {
        "PICKUP": "ARRIVED_AT_PICKUP",
        "DELIVERY": "ARRIVED_AT_DELIVERY",
    }[data.proof_type]
    if is_verified and task.status != expected_status:
        raise HTTPException(
            status_code=409,
            detail=f"Task must be {expected_status} to confirm {data.proof_type.lower()}",
        )

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
    confirmed_response = None
    navigation_status = None
    executor_events = []
    if is_verified:
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

        row = db.execute(task_query().where(Task.id == task.id)).first()
        confirmed_response = build_task_response(row)

        try:
            if robot and robot.robot_type == "LINE":
                if proof.proof_type == "PICKUP":
                    navigation_status, executor_events = agv_mission_adapter.start_delivery(db, task)
                else:
                    navigation_status, executor_events = agv_mission_adapter.complete_delivery(db, task)
            elif proof.proof_type == "PICKUP":
                navigation_status, executor_events = task_executor.start_delivery(db, task)
            else:
                navigation_status, executor_events = task_executor.complete_delivery(
                    db, task,
                )
        except (TaskExecutorError, AgvMissionConflict) as error:
            db.rollback()
            raise HTTPException(status_code=409, detail=str(error)) from error

    db.commit()
    db.refresh(proof)

    for event in events:
        db.refresh(event)
        queue_event(background_tasks, event)

    publish_executor_updates(
        background_tasks,
        navigation_status,
        executor_events,
    )

    if confirmed_response is not None:
        queue_broadcast(
            background_tasks,
            "TASK_UPDATED",
            confirmed_response,
        )

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
