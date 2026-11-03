"""Camera observation linked to a verified AGV delivery command."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgvCargoEvidence(Base):
    __tablename__ = "agv_cargo_evidence"
    __table_args__ = (
        CheckConstraint("presence IN ('PRESENT', 'ABSENT', 'UNCERTAIN')", name="ck_agv_cargo_presence"),
        CheckConstraint("review_status IN ('WAITING_FOR_REMOVAL', 'MANUAL_REVIEW')", name="ck_agv_cargo_review"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_agv_cargo_confidence"),
    )

    capture_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id", ondelete="RESTRICT"), nullable=False)
    command_id: Mapped[str] = mapped_column(ForeignKey("agv_mission_commands.command_id", ondelete="RESTRICT"), nullable=False)
    station: Mapped[str] = mapped_column(String(32), nullable=False)
    image_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    presence: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    provenance: Mapped[str] = mapped_column(String(120), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
