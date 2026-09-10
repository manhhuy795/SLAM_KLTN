from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EventLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int

    robot_id: int | None
    robot_code: str | None
    task_id: int | None
    task_code: str | None
    operator_id: int | None

    event_type: str
    source: str
    message: str

    metadata_json: str | None

    created_at: datetime
