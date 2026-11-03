"""Pickup classification and rack policy for a LINE task."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgvClassRackPolicy(Base):
    __tablename__ = "agv_class_rack_policies"
    __table_args__ = (
        CheckConstraint("revision > 0", name="ck_agv_policy_revision"),
        CheckConstraint("min_confidence > 0 AND min_confidence <= 1", name="ck_agv_policy_confidence"),
        CheckConstraint("min_margin > 0 AND min_margin <= 1", name="ck_agv_policy_margin"),
    )

    map_id: Mapped[str] = mapped_column(ForeignKey("saved_maps.id", ondelete="RESTRICT"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping: Mapped[dict] = mapped_column(JSON, nullable=False)
    min_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    min_margin: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), nullable=False)


class AgvVisionJob(Base):
    __tablename__ = "agv_vision_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'REVIEW', 'ASSIGNED')", name="ck_agv_vision_job_status"),
    )

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), primary_key=True)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id", ondelete="RESTRICT"), nullable=False)
    map_id: Mapped[str] = mapped_column(ForeignKey("saved_maps.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    active_capture_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_rack_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), nullable=False)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgvVisionCapture(Base):
    __tablename__ = "agv_vision_captures"
    __table_args__ = (
        CheckConstraint("review_status IN ('REVIEW', 'REJECTED', 'ACCEPTED')", name="ck_agv_vision_capture_review"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_agv_vision_capture_confidence"),
    )

    capture_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agv_vision_jobs.task_id", ondelete="RESTRICT"), nullable=False)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id", ondelete="RESTRICT"), nullable=False)
    image_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    predicted_class: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    probabilities: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_version: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="REVIEW")
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("operators.id", ondelete="SET NULL"), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
