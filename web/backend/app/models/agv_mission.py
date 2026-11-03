"""Durable AGV mission ownership and command intent. No hardware dispatch."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgvMission(Base):
    __tablename__ = "agv_missions"
    __table_args__ = (
        CheckConstraint("active_slot IS NULL OR active_slot = 1", name="ck_agv_missions_active_slot"),
        CheckConstraint("status IN ('ACTIVE', 'UNKNOWN', 'COMPLETED', 'CANCELLED')", name="ck_agv_missions_status"),
        UniqueConstraint("robot_id", "active_slot", name="uq_agv_active_robot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), unique=True, nullable=False)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id", ondelete="RESTRICT"), nullable=False, index=True)
    map_id: Mapped[str] = mapped_column(ForeignKey("saved_maps.id", ondelete="RESTRICT"), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handoff_command_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)


class AgvMissionCommand(Base):
    __tablename__ = "agv_mission_commands"
    __table_args__ = (
        CheckConstraint("status IN ('REQUESTED', 'ACCEPTED', 'ACKNOWLEDGED', 'EXECUTING', 'ARRIVED', 'STOPPED', 'FAILED', 'CANCELLED', 'UNKNOWN')", name="ck_agv_command_status"),
        CheckConstraint("command_sequence > 0", name="ck_agv_command_sequence"),
        UniqueConstraint("mission_id", "mission_stage", name="uq_agv_mission_stage"),
        UniqueConstraint("robot_id", "command_sequence", name="uq_agv_robot_sequence"),
    )

    command_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[int] = mapped_column(ForeignKey("agv_missions.id", ondelete="RESTRICT"), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id", ondelete="RESTRICT"), nullable=False, index=True)
    map_id: Mapped[str] = mapped_column(ForeignKey("saved_maps.id", ondelete="RESTRICT"), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(64), nullable=False)
    mission_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    source_station: Mapped[str] = mapped_column(String(32), nullable=False)
    target_station: Mapped[str] = mapped_column(String(32), nullable=False)
    route_id: Mapped[str] = mapped_column(String(64), nullable=False)
    route_steps: Mapped[list] = mapped_column(JSON, nullable=False)
    target_marker: Mapped[str | None] = mapped_column(String(64), nullable=True)
    command_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="REQUESTED")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    arrival_evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    stopped_evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    failure_details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dispatch_claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
