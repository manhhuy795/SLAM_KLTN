from fastapi import APIRouter, BackgroundTasks

from app.schemas.ros import (
    RosMapPayload,
    RosPosePayload,
    RosStatusPayload,
)
from app.services.realtime import queue_broadcast
from app.services.ros_state import ros_state


router = APIRouter(
    prefix="/ros",
    tags=["ROS bridge"],
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
