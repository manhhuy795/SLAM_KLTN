from typing import Literal

from pydantic import BaseModel, ConfigDict


class RobotStatusUpdate(BaseModel):
    online: bool | None = None
    state: Literal[
        "UNKNOWN",
        "IDLE",
        "MOVING",
        "PICKING_UP",
        "DELIVERING",
        "PAUSED",
        "ERROR",
    ] | None = None

    battery_percent: float | None = None
    voltage: float | None = None

    x: float | None = None
    y: float | None = None
    yaw: float | None = None

    line_segment_id: int | None = None
    localization_quality: Literal[
        "GOOD",
        "MEDIUM",
        "POOR",
    ] | None = None


class RobotStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    online: bool
    state: str
    battery_percent: float | None
    voltage: float | None

    x: float | None
    y: float | None
    yaw: float | None

    line_segment_id: int | None
    localization_quality: str | None


class RobotOut(BaseModel):
    id: int
    robot_code: str
    name: str
    robot_type: str
    model: str | None
    is_active: bool

    status: RobotStatusOut | None
