from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.location import Location
from app.models.task import Task
from app.schemas.ros import (
    NavigationGoal,
    NavigationPathPayload,
    NavigationStatusUpdate,
    RosMapPayload,
    RosPosePayload,
    RosStatusPayload,
)
from app.services.navigation import navigation_state
from app.services.realtime import queue_broadcast, queue_event
from app.services.ros_state import ros_state
from app.services.task_executor import task_executor
from app.api.routes.tasks import build_task_response, task_query


router = APIRouter(
    prefix="/ros",
    tags=["ROS bridge"],
)


def broadcast_status(background_tasks, status):
    queue_broadcast(
        background_tasks,
        "NAVIGATION_STATUS_UPDATED",
        status,
    )


@router.get("/state")
def get_ros_state():
    return ros_state.get_status()


@router.post("/state")
def update_ros_state(
    data: RosStatusPayload,
    background_tasks: BackgroundTasks,
):
    payload = data.model_dump()
    payload = ros_state.set_status(payload)
    nav_status = navigation_state.set_nav2_online(payload["nav2_online"])
    broadcast_status(background_tasks, nav_status)
    queue_broadcast(
        background_tasks,
        "SLAM_STATUS_UPDATED",
        payload,
    )
    return payload


@router.get("/map")
def get_ros_map():
    return ros_state.get_map()


@router.post("/map")
def update_ros_map(
    data: RosMapPayload,
    background_tasks: BackgroundTasks,
):
    changed, payload = ros_state.set_map(data.model_dump())

    if changed:
        queue_broadcast(
            background_tasks,
            "SLAM_MAP_UPDATED",
            payload,
        )

    return payload


@router.get("/pose")
def get_ros_pose():
    return ros_state.get_pose()


@router.post("/pose")
def update_ros_pose(
    data: RosPosePayload,
    background_tasks: BackgroundTasks,
):
    payload = ros_state.set_pose(data.model_dump())
    queue_broadcast(
        background_tasks,
        "ROBOT_POSE_UPDATED",
        payload,
    )
    return payload


@router.post("/navigation/goal")
def create_navigation_goal(
    data: NavigationGoal,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    location_data = None
    planning_point = None
    if data.planning_point_id is not None:
        from app.api.routes.maps import find_map
        from app.services.planning import read_layer
        from app.services.map_session import map_session
        record = find_map(db, data.map_id)
        session = map_session.status()
        if not session.get("ready") or session.get("map_id") != record.id:
            raise HTTPException(409, "Viewed map is not the verified Nav2 map")
        layer = read_layer(db, record.id)
        if layer["revision"] != data.planning_revision:
            raise HTTPException(409, "Planning layer changed; reload the target")
        point = next((p for p in layer["objects"] if p["id"] == str(data.planning_point_id)), None)
        if not point or point["type"] not in {"HOME", "PICKUP", "DELIVERY", "CHARGING"}:
            raise HTTPException(422, "Choose a valid navigation point")
        planning_point = dict(id=point["id"], name=point["name"], map_id=record.id,
                              revision=layer["revision"])
    x, y, yaw = data.x, data.y, data.yaw
    if data.location_id is not None:
        location = db.get(Location, data.location_id)
        if location is None:
            raise HTTPException(status_code=404, detail="Location not found")
        if not location.is_active:
            raise HTTPException(status_code=409, detail="Location is inactive")
        x, y, yaw = location.x, location.y, location.yaw
        location_data = {
            "id": location.id,
            "code": location.code,
            "name": location.name,
        }

    if planning_point:
        x, y, yaw = point["x"], point["y"], point["yaw"]
    try:
        status = navigation_state.create_goal(
            x,
            y,
            yaw,
            location_data,
            planning_point=planning_point,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    broadcast_status(background_tasks, status)
    queue_broadcast(
        background_tasks,
        "NAVIGATION_PATH_UPDATED",
        {"frame_id": "map", "poses": []},
    )
    return status


@router.post("/navigation/cancel")
def cancel_navigation(
    background_tasks: BackgroundTasks,
):
    try:
        status = navigation_state.create_cancel()
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    broadcast_status(background_tasks, status)
    return status


@router.get("/navigation/status")
def get_navigation_status():
    return navigation_state.get_status()


@router.get("/navigation/path")
def get_navigation_path():
    return navigation_state.get_path()


@router.get("/navigation/command")
def get_navigation_command():
    return navigation_state.claim_pending()


@router.post("/navigation/command/{command_id}/status")
def update_navigation_status(
    command_id: int,
    data: NavigationStatusUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if data.command_id != command_id:
        raise HTTPException(status_code=400, detail="Command id mismatch")

    try:
        status = navigation_state.set_status(
            command_id,
            data.model_dump(exclude={"command_id"}, exclude_none=True),
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    broadcast_status(background_tasks, status)
    task_result = task_executor.handle_navigation_status(db, status)
    if task_result is not None:
        task, events = task_result
        for event in events:
            queue_event(background_tasks, event)
        row = db.execute(task_query().where(Task.id == task.id)).first()
        queue_broadcast(
            background_tasks,
            "TASK_UPDATED",
            build_task_response(row),
        )
    if data.state in {"SUCCEEDED", "FAILED", "CANCELLED", "REJECTED"}:
        queue_broadcast(
            background_tasks,
            "NAVIGATION_PATH_UPDATED",
            {"frame_id": "map", "poses": []},
        )
    return status


@router.post("/navigation/path")
def update_navigation_path(
    data: NavigationPathPayload,
    background_tasks: BackgroundTasks,
):
    try:
        payload = navigation_state.set_path(
            data.command_id,
            data.model_dump(exclude={"command_id"}, exclude_none=True),
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    queue_broadcast(
        background_tasks,
        "NAVIGATION_PATH_UPDATED",
        payload,
    )
    return payload
