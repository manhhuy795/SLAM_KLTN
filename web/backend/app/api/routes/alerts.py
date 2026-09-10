from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.deps import get_db

from app.models.alert import Alert
from app.models.operator import Operator
from app.models.robot import Robot
from app.models.task import Task

from app.schemas.alert import (
    AlertAction,
    AlertCreate,
    AlertOut,
)

from app.services.event_logger import add_event
from app.services.realtime import queue_broadcast, queue_event


router = APIRouter(
    prefix="/alerts",
    tags=["Alerts"],
)


def get_operator(
    db: Session,
    operator_id: int,
):
    operator = db.get(
        Operator,
        operator_id,
    )

    if operator is None:
        raise HTTPException(
            status_code=404,
            detail="Operator not found",
        )

    if not operator.is_active:
        raise HTTPException(
            status_code=400,
            detail="Operator is inactive",
        )

    return operator


def build_alert_response(alert: Alert):
    return {
        "id": alert.id,
        "alert_code": alert.alert_code,
        "robot_id": alert.robot_id,
        "task_id": alert.task_id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "message": alert.message,
        "status": alert.status,
        "group_key": alert.group_key,
        "occurrence_count": alert.occurrence_count,
        "acknowledged_by": alert.acknowledged_by,
        "resolved_by": alert.resolved_by,
        "first_seen_at": alert.first_seen_at,
        "last_seen_at": alert.last_seen_at,
        "acknowledged_at": alert.acknowledged_at,
        "resolved_at": alert.resolved_at,
    }


@router.get(
    "",
    response_model=list[AlertOut],
)
def get_alerts(
    status: str | None = None,
    severity: str | None = None,
    robot_id: int | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Alert)

    if status is not None:
        stmt = stmt.where(
            Alert.status == status
        )

    if severity is not None:
        stmt = stmt.where(
            Alert.severity == severity
        )

    if robot_id is not None:
        stmt = stmt.where(
            Alert.robot_id == robot_id
        )

    stmt = stmt.order_by(
        Alert.last_seen_at.desc()
    )

    return db.scalars(stmt).all()


@router.get(
    "/{alert_id}",
    response_model=AlertOut,
)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
):
    alert = db.get(
        Alert,
        alert_id,
    )

    if alert is None:
        raise HTTPException(
            status_code=404,
            detail="Alert not found",
        )

    return alert


@router.post(
    "",
    response_model=AlertOut,
    status_code=201,
)
def create_alert(
    data: AlertCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    robot = db.get(
        Robot,
        data.robot_id,
    )

    if robot is None:
        raise HTTPException(
            status_code=404,
            detail="Robot not found",
        )

    if data.task_id is not None:
        task = db.get(
            Task,
            data.task_id,
        )

        if task is None:
            raise HTTPException(
                status_code=404,
                detail="Task not found",
            )

    existing = db.scalar(
        select(Alert)
        .where(
            Alert.group_key == data.group_key,
            Alert.status != "RESOLVED",
        )
        .order_by(Alert.id.desc())
    )

    if existing is not None:
        existing.occurrence_count += 1
        existing.last_seen_at = func.current_timestamp()
        existing.message = data.message
        existing.severity = data.severity

        event = add_event(
            db=db,
            event_type="ALERT_REPEATED",
            source="SYSTEM",
            message=(
                f"Alert {existing.alert_code} "
                f"xuất hiện lại."
            ),
            robot_id=data.robot_id,
            task_id=data.task_id,
            metadata={
                "alert_id": existing.id,
                "group_key": data.group_key,
                "occurrence_count":
                    existing.occurrence_count,
            },
        )

        db.commit()
        db.refresh(existing)
        db.refresh(event)

        queue_event(background_tasks, event)
        queue_broadcast(
            background_tasks,
            "ALERT_UPDATED",
            build_alert_response(existing),
        )

        return existing

    max_id = db.scalar(
        select(func.max(Alert.id))
    ) or 0

    alert = Alert(
        alert_code=f"A-{max_id + 1:04d}",
        robot_id=data.robot_id,
        task_id=data.task_id,

        alert_type=data.alert_type,
        severity=data.severity,
        message=data.message,

        status="NEW",

        group_key=data.group_key,
        occurrence_count=1,
    )

    db.add(alert)
    db.flush()

    event = add_event(
        db=db,
        event_type="ALERT_CREATED",
        source="SYSTEM",
        message=f"Tạo cảnh báo {alert.alert_code}.",
        robot_id=alert.robot_id,
        task_id=alert.task_id,
        metadata={
            "alert_id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
        },
    )

    db.commit()
    db.refresh(alert)
    db.refresh(event)

    queue_event(background_tasks, event)
    queue_broadcast(
        background_tasks,
        "ALERT_UPDATED",
        build_alert_response(alert),
    )

    return alert


@router.patch(
    "/{alert_id}/acknowledge",
    response_model=AlertOut,
)
def acknowledge_alert(
    alert_id: int,
    data: AlertAction,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    alert = db.get(
        Alert,
        alert_id,
    )

    if alert is None:
        raise HTTPException(
            status_code=404,
            detail="Alert not found",
        )

    operator = get_operator(
        db,
        data.operator_id,
    )

    if alert.status == "RESOLVED":
        raise HTTPException(
            status_code=400,
            detail="Resolved alert cannot be acknowledged",
        )

    if alert.status == "ACKNOWLEDGED":
        return alert

    alert.status = "ACKNOWLEDGED"
    alert.acknowledged_by = operator.id
    alert.acknowledged_at = (
        func.current_timestamp()
    )

    event = add_event(
        db=db,
        event_type="ALERT_ACKNOWLEDGED",
        source="OPERATOR",
        message=(
            f"Operator xác nhận cảnh báo "
            f"{alert.alert_code}."
        ),
        robot_id=alert.robot_id,
        task_id=alert.task_id,
        operator_id=operator.id,
        metadata={
            "alert_id": alert.id,
        },
    )

    db.commit()
    db.refresh(alert)
    db.refresh(event)

    queue_event(background_tasks, event)
    queue_broadcast(
        background_tasks,
        "ALERT_UPDATED",
        build_alert_response(alert),
    )

    return alert


@router.patch(
    "/{alert_id}/resolve",
    response_model=AlertOut,
)
def resolve_alert(
    alert_id: int,
    data: AlertAction,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    alert = db.get(
        Alert,
        alert_id,
    )

    if alert is None:
        raise HTTPException(
            status_code=404,
            detail="Alert not found",
        )

    operator = get_operator(
        db,
        data.operator_id,
    )

    if alert.status == "RESOLVED":
        return alert

    if alert.status != "ACKNOWLEDGED":
        raise HTTPException(
            status_code=400,
            detail=(
                "Alert must be acknowledged "
                "before resolving"
            ),
        )

    alert.status = "RESOLVED"
    alert.resolved_by = operator.id
    alert.resolved_at = (
        func.current_timestamp()
    )

    event = add_event(
        db=db,
        event_type="ALERT_RESOLVED",
        source="OPERATOR",
        message=(
            f"Đã xử lý cảnh báo "
            f"{alert.alert_code}."
        ),
        robot_id=alert.robot_id,
        task_id=alert.task_id,
        operator_id=operator.id,
        metadata={
            "alert_id": alert.id,
        },
    )

    db.commit()
    db.refresh(alert)
    db.refresh(event)

    queue_event(background_tasks, event)
    queue_broadcast(
        background_tasks,
        "ALERT_UPDATED",
        build_alert_response(alert),
    )

    return alert
