from time import time
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RosMapOrigin(BaseModel):
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0


class RosMapPayload(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    resolution: float = Field(gt=0)
    origin: RosMapOrigin
    frame_id: str = "map"
    timestamp: float = Field(default_factory=time)
    map_hash: str
    data: list[int]

    @model_validator(mode="after")
    def validate_data_size(self):
        expected = self.width * self.height
        if len(self.data) != expected:
            raise ValueError(
                f"OccupancyGrid data must contain {expected} cells"
            )
        if any(value < -1 or value > 100 for value in self.data):
            raise ValueError("OccupancyGrid values must be between -1 and 100")
        return self


class RosPosePayload(BaseModel):
    robot_id: int = Field(gt=0)
    frame_id: str = "map"
    timestamp: float = Field(default_factory=time)
    x: float
    y: float
    yaw: float


class RosStatusPayload(BaseModel):
    bridge_online: bool = True
    slam_online: bool
    map_status: Literal["RECEIVED", "WAITING"]
    lidar_online: bool
    localization_available: bool
    tf_available: bool
    scan_rate_hz: float | None = Field(default=None, ge=0)
    last_scan_age_ms: float | None = Field(default=None, ge=0)
    timestamp: float = Field(default_factory=time)
