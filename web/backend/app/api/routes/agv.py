"""AGV endpoints: keep verified line controller separate from ROS2 AMR control."""
import csv
import hmac
import io
import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.robots import build_robot_response
from app.db.deps import get_db
from app.models.robot import Robot
from app.models.robot_status import RobotStatus
from app.services.agv_runtime import COMMANDS, agv_runtime, status_from_firmware
from app.services.realtime import queue_broadcast

router = APIRouter(prefix="/agv", tags=["AGV line telemetry"])


class Telemetry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    yaw: float = Field(allow_inf_nan=False)
    dist: float = Field(ge=0, allow_inf_nan=False)
    speed: float = Field(allow_inf_nan=False)
    line_mask: int = Field(ge=0, le=31)
    line_err: float = Field(allow_inf_nan=False)
    ticks_l: int
    ticks_r: int
    pwm_l: int = Field(ge=-255, le=255)
    pwm_r: int = Field(ge=-255, le=255)
    ack_id: int = Field(ge=0, le=2_147_483_647)
    auto_loop: bool = False
    state: str = Field(min_length=1, max_length=64)


class CommandRequest(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    mission_id: str | None = None


def _robot(db, code):
    robot = db.scalar(select(Robot).where(Robot.robot_code == code))
    if robot is None or robot.robot_type != "LINE":
        raise HTTPException(404, "AGV line robot not found")
    return robot


def _commands_enabled():
    return os.getenv("WRMS_AGV_ENABLE_COMMANDS") == "1"


def _require_device_key(value):
    expected = os.getenv("WRMS_AGV_TOKEN", "")
    if not expected:
        raise HTTPException(503, "Set WRMS_AGV_TOKEN on the backend first")
    if not value or not hmac.compare_digest(expected, value):
        raise HTTPException(401, "Invalid AGV device key")


@router.post("/{robot_code}/telemetry")
def ingest_telemetry(robot_code: str, data: Telemetry,
                     background_tasks: BackgroundTasks,
                     x_agv_token: str | None = Header(default=None, alias="X-AGV-Token"),
                     db: Session = Depends(get_db)):
    _require_device_key(x_agv_token)
    robot = _robot(db, robot_code)
    raw = data.model_dump()
    result = agv_runtime.ingest(robot_code, raw)

    status = db.get(RobotStatus, robot.id)
    if status is None:
        status = RobotStatus(robot_id=robot.id, online=True, state="UNKNOWN")
        db.add(status)
    status.online = True
    status.state = status_from_firmware(raw["state"])
    # These are AGV-local coordinates, NOT ROS map-frame coordinates.
    status.x = raw["x"]
    status.y = raw["y"]
    status.yaw = raw["yaw"]
    db.commit()
    db.refresh(status)

    queue_broadcast(background_tasks, "ROBOT_STATUS_UPDATED",
                    build_robot_response(robot, status))
    queue_broadcast(background_tasks, "AGV_TELEMETRY_UPDATED",
                    agv_runtime.get(robot_code, _commands_enabled()))
    return result


@router.get("/{robot_code}/state")
def get_agv_state(robot_code: str, db: Session = Depends(get_db)):
    _robot(db, robot_code)
    return agv_runtime.get(robot_code, _commands_enabled())


@router.post("/{robot_code}/command")
def queue_agv_command(robot_code: str, request: CommandRequest,
                      background_tasks: BackgroundTasks,
                      db: Session = Depends(get_db)):
    _robot(db, robot_code)
    if not _commands_enabled():
        raise HTTPException(403, "Remote AGV commands disabled; set WRMS_AGV_ENABLE_COMMANDS=1")
    if request.action == "mission":
        if request.mission_id not in {"M1", "M2", "M3", "M4"}:
            raise HTTPException(422, "mission_id must be M1, M2, M3, or M4")
        cmd = f"MISSION:{request.mission_id}"
    else:
        if request.action not in COMMANDS or request.mission_id is not None:
            raise HTTPException(422, "Unsupported AGV command")
        cmd = COMMANDS[request.action]
    try:
        result = agv_runtime.command(robot_code, cmd)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    queue_broadcast(background_tasks, "AGV_TELEMETRY_UPDATED",
                    agv_runtime.get(robot_code, _commands_enabled()))
    return result


@router.get("/{robot_code}/logs")
def get_logs(robot_code: str, db: Session = Depends(get_db)):
    _robot(db, robot_code)
    return {"logs": agv_runtime.logs(robot_code)}


@router.get("/{robot_code}/export_csv")
def export_csv(robot_code: str, db: Session = Depends(get_db)):
    _robot(db, robot_code)
    buffer = io.StringIO()
    fields = ["timestamp", "x", "y", "yaw", "dist", "speed", "line_mask",
              "line_err", "ticks_l", "ticks_r", "pwm_l", "pwm_r", "ack_id",
              "auto_loop", "state"]
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in agv_runtime.logs(robot_code, limit=5000):
        writer.writerow(row)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    buffer.seek(0)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition":
                                      f'attachment; filename="{robot_code}_{stamp}.csv"'})


@router.post("/{robot_code}/clear_logs")
def clear_logs(robot_code: str, db: Session = Depends(get_db)):
    _robot(db, robot_code)
    if not _commands_enabled():
        raise HTTPException(403, "AGV operations disabled")
    agv_runtime.clear_logs(robot_code)
    return {"status": "logs_cleared"}
