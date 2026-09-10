from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AlertCreate(BaseModel):
    robot_id: int
    task_id: int | None = None

    alert_type: str

    severity: Literal[
        "INFO",
        "WARNING",
        "CRITICAL",
    ]

    message: str
    group_key: str


class AlertAction(BaseModel):
    operator_id: int


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_code: str

    robot_id: int
    task_id: int | None

    alert_type: str
    severity: str
    message: str

    status: str
    group_key: str
    occurrence_count: int

    acknowledged_by: int | None
    resolved_by: int | None

    first_seen_at: datetime
    last_seen_at: datetime

    acknowledged_at: datetime | None
    resolved_at: datetime | None
