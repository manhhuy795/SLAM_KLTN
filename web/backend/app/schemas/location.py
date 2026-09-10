from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


LocationType = Literal[
    "HOME",
    "RACK",
    "PICKUP",
    "DELIVERY",
    "CHARGING",
]


class LocationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    location_type: LocationType
    x: float
    y: float
    yaw: float = 0.0
    is_active: bool = True


class LocationUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    location_type: LocationType | None = None
    x: float | None = None
    y: float | None = None
    yaw: float | None = None
    is_active: bool | None = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    location_type: str

    x: float
    y: float
    yaw: float

    is_active: bool
