from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RobotCommand(Base):
    __tablename__ = "robot_commands"

    __table_args__ = (
        CheckConstraint(
            "command IN ('PAUSE', 'RESUME', 'CANCEL', 'SAFE_STOP')",
            name="ck_robot_commands_command",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'ACKNOWLEDGED', 'FAILED')",
            name="ck_robot_commands_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    robot_id: Mapped[int] = mapped_column(
        ForeignKey("robots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    command: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDING",
    )

    failure_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
