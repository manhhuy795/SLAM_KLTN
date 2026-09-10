from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


RobotCommandType = Literal[
    "PAUSE",
    "RESUME",
    "CANCEL",
    "SAFE_STOP",
]

RobotCommandStatus = Literal[
    "PENDING",
    "ACKNOWLEDGED",
    "FAILED",
]


class RobotCommandCreate(BaseModel):
    command: RobotCommandType
    task_id: int | None = None


class RobotCommandAck(BaseModel):
    status: Literal["ACKNOWLEDGED", "FAILED"]
    failure_reason: str | None = None


class RobotCommandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    robot_id: int
    task_id: int | None
    command: RobotCommandType
    status: RobotCommandStatus
    failure_reason: str | None
    created_at: datetime
    acknowledged_at: datetime | None
