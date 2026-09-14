from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.schemas.ros import (
    NavigationGoal,
    NavigationPathPayload,
    NavigationStatusUpdate,
    RosMapPayload,
    RosPosePayload,
    RosStatusPayload,
)
from app.services.navigation import navigation_state
from app.services.realtime import queue_broadcast
from app.services.ros_state import ros_state


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
):
    try:
        status = navigation_state.create_goal(
            data.x,
            data.y,
            data.yaw,
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
