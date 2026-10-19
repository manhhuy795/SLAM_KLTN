from math import isfinite
from uuid import UUID
from time import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
    nav2_online: bool = False
    slam_online: bool
    map_status: Literal["RECEIVED", "WAITING"]
    lidar_online: bool
    localization_available: bool
    tf_available: bool
    scan_rate_hz: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    last_scan_age_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    lidar_status: Literal["ONLINE", "STALE", "OFFLINE"] | None = None
    scan_frame_id: str | None = None
    scan_points_valid: int | None = Field(default=None, ge=0)
    scan_points_total: int | None = Field(default=None, ge=0)
    nearest_obstacle_m: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    scan_gap_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    scan_max_gap_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    bridge_queue_age_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    scan_stale_sec: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    scan_offline_sec: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    timestamp: float = Field(default_factory=time)

    @model_validator(mode="after")
    def validate_scan_diagnostics(self):
        if (self.scan_points_valid is not None and self.scan_points_total is not None
                and self.scan_points_valid > self.scan_points_total):
            raise ValueError("Valid scan points cannot exceed total points")
        if (self.scan_stale_sec is None) != (self.scan_offline_sec is None):
            raise ValueError("Provide both scan freshness thresholds")
        if (self.scan_stale_sec is not None
                and self.scan_stale_sec >= self.scan_offline_sec):
            raise ValueError("Require scan_stale_sec < scan_offline_sec")
        return self


class NavigationGoal(BaseModel):
    x: float
    y: float
    yaw: float = 0.0
    location_id: int | None = Field(default=None, gt=0)
    map_id: UUID | None = None
    planning_point_id: UUID | None = None
    planning_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_source(self):
        fields = (self.map_id, self.planning_point_id, self.planning_revision)
        if any(v is not None for v in fields) and not all(v is not None for v in fields):
            raise ValueError("Provide map_id, planning_point_id and planning_revision together")
        if self.map_id is not None and self.location_id is not None:
            raise ValueError("Choose one goal source")
        return self

    @field_validator("x", "y", "yaw")
    @classmethod
    def validate_finite(cls, value):
        if not isfinite(value):
            raise ValueError("Navigation coordinates must be finite")
        return value


class NavigationPose(BaseModel):
    x: float
    y: float
    yaw: float = 0.0

    @field_validator("x", "y", "yaw")
    @classmethod
    def validate_finite(cls, value):
        if not isfinite(value):
            raise ValueError("Navigation pose must be finite")
        return value


class NavigationStatusUpdate(BaseModel):
    command_id: int = Field(gt=0)
    state: Literal[
        "IDLE",
        "SENDING",
        "NAVIGATING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "REJECTED",
    ]
    distance_remaining: float | None = None
    current_pose: NavigationPose | None = None
    navigation_time: float | None = Field(default=None, ge=0)
    number_of_recoveries: int = Field(default=0, ge=0)
    error_code: int = Field(default=0, ge=0)
    error_message: str = ""
    cancel_requested: bool | None = None

    @field_validator("distance_remaining")
    @classmethod
    def validate_distance(cls, value):
        if value is not None and not isfinite(value):
            raise ValueError("distance_remaining must be finite")
        return value


class NavigationPathPose(BaseModel):
    x: float
    y: float

    @field_validator("x", "y")
    @classmethod
    def validate_finite(cls, value):
        if not isfinite(value):
            raise ValueError("Path coordinates must be finite")
        return value


class NavigationPathPayload(BaseModel):
    command_id: int = Field(gt=0)
    frame_id: str = "map"
    poses: list[NavigationPathPose]
