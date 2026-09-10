from datetime import datetime
from typing import Literal

from pydantic import BaseModel


TaskStatus = Literal[
    "WAITING",
    "MOVING_TO_PICKUP",
    "ARRIVED_AT_PICKUP",
    "PICKUP_CONFIRMED",
    "TRANSPORTING",
    "ARRIVED_AT_DELIVERY",
    "DELIVERY_CONFIRMED",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
]

ProofType = Literal[
    "PICKUP",
    "DELIVERY",
]

VerificationStatus = Literal[
    "PENDING",
    "AUTO_VERIFIED",
    "MANUAL_CONFIRMED",
    "FAILED",
]


class TaskCreate(BaseModel):
    product_id: int
    dropoff_location_id: int
    robot_id: int | None = None
    retry_of_task_id: int | None = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus
    fail_reason: str | None = None


class TaskProofCreate(BaseModel):
    proof_type: ProofType
    image_path: str
    verification_status: VerificationStatus = "PENDING"
    confirmed_by: int | None = None


class TaskProofOut(BaseModel):
    id: int
    task_id: int
    proof_type: ProofType
    image_path: str
    verification_status: VerificationStatus
    confirmed_by: int | None
    captured_at: datetime
    verified_at: datetime | None


class TaskOut(BaseModel):
    id: int
    task_code: str

    product_id: int
    product_code: str
    product_name: str

    robot_id: int | None
    robot_code: str | None

    pickup_location_id: int
    pickup_location_code: str
    pickup_location_name: str

    dropoff_location_id: int
    dropoff_location_code: str
    dropoff_location_name: str

    status: str
    progress: int

    is_paused: bool
    cancel_requested: bool

    fail_reason: str | None
    retry_of_task_id: int | None

    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
