from datetime import datetime
from math import isfinite
from threading import Lock

from sqlalchemy import select

from app.models.location import Location
from app.models.robot import Robot
from app.models.task import Task
from app.services.event_logger import add_event
from app.services.navigation import navigation_state
from app.services.ros_state import ros_state


TERMINAL_TASK_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}
NAVIGATION_PHASES = {
    "MOVING_TO_PICKUP": ("PICKUP", "pickup_location_id"),
    "TRANSPORTING": ("DELIVERY", "dropoff_location_id"),
}


class TaskExecutorError(ValueError):
    pass


class TaskExecutor:
    def __init__(self, nav_state=navigation_state, current_ros_state=ros_state):
        self.navigation_state = nav_state
        self.ros_state = current_ros_state
        self._lock = Lock()

    def start_pickup(self, db, task):
        with self._lock:
            if task.status != "WAITING":
                raise TaskExecutorError("Only a waiting task can be started")

            pickup = self._validate_task(db, task, "PICKUP")
            self._ensure_robot_available(db, task)
            navigation_status = self._create_goal(task, pickup, "PICKUP")

            old_status = task.status
            task.status = "MOVING_TO_PICKUP"
            task.progress = 15
            task.is_paused = False
            task.cancel_requested = False
            task.fail_reason = None
            task.started_at = task.started_at or datetime.utcnow()
            task.updated_at = datetime.utcnow()
            event = self._status_event(db, task, old_status, task.status)
            self._commit(db, task, [event], navigation_status)
            return navigation_status, [event]

    def start_delivery(self, db, task):
        with self._lock:
            if task.status != "PICKUP_CONFIRMED":
                raise TaskExecutorError("Pickup is not confirmed")

            delivery = self._validate_task(db, task, "DELIVERY")
            self._ensure_robot_available(db, task)
            navigation_status = self._create_goal(task, delivery, "DELIVERY")

            old_status = task.status
            task.status = "TRANSPORTING"
            task.progress = 60
            task.is_paused = False
            task.cancel_requested = False
            task.updated_at = datetime.utcnow()
            event = self._status_event(db, task, old_status, task.status)
            self._commit(db, task, [event], navigation_status)
            return navigation_status, [event]

    def complete_delivery(self, db, task):
        with self._lock:
            if task.status != "DELIVERY_CONFIRMED":
                raise TaskExecutorError("Delivery is not confirmed")

            navigation_status = self._cancel_owned_navigation(task.id)
            old_status = task.status
            task.status = "COMPLETED"
            task.progress = 100
            task.is_paused = False
            task.cancel_requested = False
            task.completed_at = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            events = [
                self._status_event(db, task, old_status, task.status),
                add_event(
                    db=db,
                    event_type="TASK_COMPLETED",
                    source="TASK_EXECUTOR",
                    message=f"Task {task.task_code} completed.",
                    robot_id=task.robot_id,
                    task_id=task.id,
                ),
            ]
            self._commit(db, task, events, navigation_status)
            return navigation_status, events

    def pause(self, db, task):
        with self._lock:
            if task.status not in NAVIGATION_PHASES:
                raise TaskExecutorError("Only a navigating task can be paused")
            if task.is_paused:
                raise TaskExecutorError("Task is already paused")

            navigation_status = self._cancel_owned_navigation(task.id)
            task.is_paused = True
            task.updated_at = datetime.utcnow()
            event = add_event(
                db=db,
                event_type="TASK_PAUSED",
                source="TASK_EXECUTOR",
                message=f"Task {task.task_code} paused during navigation.",
                robot_id=task.robot_id,
                task_id=task.id,
            )
            self._commit(db, task, [event], navigation_status)
            return navigation_status, [event]

    def resume(self, db, task):
        with self._lock:
            if task.status not in NAVIGATION_PHASES or not task.is_paused:
                raise TaskExecutorError("Task is not paused during navigation")

            stage, _ = NAVIGATION_PHASES[task.status]
            location = self._validate_task(db, task, stage)
            self._ensure_robot_available(db, task)
            navigation_status = self._create_goal(task, location, stage)
            task.is_paused = False
            task.updated_at = datetime.utcnow()
            event = add_event(
                db=db,
                event_type="TASK_RESUMED",
                source="TASK_EXECUTOR",
                message=f"Task {task.task_code} resumed navigation.",
                robot_id=task.robot_id,
                task_id=task.id,
            )
            self._commit(db, task, [event], navigation_status)
            return navigation_status, [event]

    def cancel(self, db, task):
        with self._lock:
            navigation_status = self._cancel_owned_navigation(task.id)
            old_status = task.status
            task.status = "CANCELLED"
            task.cancel_requested = False
            task.updated_at = datetime.utcnow()
            event = self._status_event(db, task, old_status, task.status)
            self._commit(db, task, [event], navigation_status)
            return navigation_status, [event]

    def handle_navigation_status(self, db, status):
        goal = status.get("goal") or {}
        task_metadata = goal.get("task") or {}
        task_id = task_metadata.get("id")
        if task_id is None:
            return None

        with self._lock:
            task = db.get(Task, task_id)
            stage = task_metadata.get("stage")
            phase = {
                "PICKUP": (
                    "MOVING_TO_PICKUP",
                    "ARRIVED_AT_PICKUP",
                    task.pickup_location_id if task else None,
                ),
                "DELIVERY": (
                    "TRANSPORTING",
                    "ARRIVED_AT_DELIVERY",
                    task.dropoff_location_id if task else None,
                ),
            }.get(stage)
            if (
                task is None
                or phase is None
                or task.status != phase[0]
                or task_metadata.get("robot_id") != task.robot_id
                or (goal.get("location") or {}).get("id") != phase[2]
                or task.is_paused
                or task.cancel_requested
            ):
                return None

            state = status.get("state")
            if state == "SUCCEEDED":
                old_status = task.status
                task.status = phase[1]
                task.progress = 30 if stage == "PICKUP" else 75
                task.updated_at = datetime.utcnow()
                event = self._status_event(db, task, old_status, task.status)
            elif state in {"FAILED", "REJECTED"}:
                old_status = task.status
                task.status = "FAILED"
                task.fail_reason = self._failure_reason(status)
                task.updated_at = datetime.utcnow()
                event = self._status_event(db, task, old_status, task.status)
            else:
                return None

            db.commit()
            db.refresh(task)
            db.refresh(event)
            return task, [event]

    def _validate_task(self, db, task, stage):
        if task.robot_id is None:
            raise TaskExecutorError("Task has no assigned robot")

        robot = db.get(Robot, task.robot_id)
        if robot is None or not robot.is_active:
            raise TaskExecutorError("Task robot is missing or inactive")

        location_id = (
            task.pickup_location_id
            if stage == "PICKUP"
            else task.dropoff_location_id
        )
        location = db.get(Location, location_id)
        label = "Pickup" if stage == "PICKUP" else "Delivery"
        if location is None or not location.is_active:
            raise TaskExecutorError(f"{label} location is missing or inactive")
        if not all(isfinite(value) for value in (
            location.x, location.y, location.yaw,
        )):
            raise TaskExecutorError(f"{label} location coordinates are invalid")

        ros_status = self.ros_state.get_status()
        if not ros_status.get("bridge_online"):
            raise TaskExecutorError("ROS bridge is offline")
        if not ros_status.get("nav2_online"):
            raise TaskExecutorError("Nav2 is offline")
        if not (
            ros_status.get("localization_available")
            and ros_status.get("tf_available")
        ):
            raise TaskExecutorError("Task robot localization is offline")

        pose = self.ros_state.get_pose()
        if pose is None or pose.get("robot_id") != task.robot_id:
            raise TaskExecutorError("Task robot is offline")
        return location

    @staticmethod
    def _ensure_robot_available(db, task):
        active_task_id = db.scalar(
            select(Task.id).where(
                Task.robot_id == task.robot_id,
                Task.id != task.id,
                Task.status.notin_(TERMINAL_TASK_STATUSES | {"WAITING"}),
            )
        )
        if active_task_id is not None:
            raise TaskExecutorError("Robot already has an active task")

    def _create_goal(self, task, location, stage):
        try:
            return self.navigation_state.create_goal(
                location.x,
                location.y,
                location.yaw,
                location={
                    "id": location.id,
                    "code": location.code,
                    "name": location.name,
                },
                task={
                    "id": task.id,
                    "code": task.task_code,
                    "robot_id": task.robot_id,
                    "stage": stage,
                },
            )
        except ValueError as error:
            raise TaskExecutorError(str(error)) from error

    def _cancel_owned_navigation(self, task_id):
        status = self.navigation_state.get_status()
        owner_id = ((status.get("goal") or {}).get("task") or {}).get("id")
        if owner_id != task_id or status.get("state") not in {
            "SENDING", "NAVIGATING",
        }:
            return None
        try:
            return self.navigation_state.create_cancel()
        except ValueError as error:
            raise TaskExecutorError(str(error)) from error

    @staticmethod
    def _failure_reason(status):
        message = (status.get("error_message") or "").strip()
        if message:
            return message
        state = status.get("state", "FAILED")
        error_code = status.get("error_code", 0)
        return f"Nav2 {state.lower()} (error code {error_code})"

    @staticmethod
    def _status_event(db, task, old_status, new_status):
        return add_event(
            db=db,
            event_type=(
                "TASK_FAILED" if new_status == "FAILED" else "TASK_STATUS_CHANGED"
            ),
            source="TASK_EXECUTOR",
            message=(
                f"Task {task.task_code} changed from {old_status} to {new_status}."
            ),
            robot_id=task.robot_id,
            task_id=task.id,
            metadata={
                "from_status": old_status,
                "to_status": new_status,
                "fail_reason": task.fail_reason,
            },
        )

    def _commit(self, db, task, events, navigation_status):
        try:
            db.commit()
        except Exception:
            db.rollback()
            if (
                navigation_status is not None
                and navigation_status.get("state") in {"SENDING", "NAVIGATING"}
            ):
                try:
                    self.navigation_state.create_cancel()
                except ValueError:
                    pass
            raise
        db.refresh(task)
        for event in events:
            db.refresh(event)


task_executor = TaskExecutor()
