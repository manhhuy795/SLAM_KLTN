from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RobotStatus(Base):
    __tablename__ = "robot_status"

    __table_args__ = (
        CheckConstraint(
            """
            state IN (
                'UNKNOWN',
                'IDLE',
                'MOVING',
                'PICKING_UP',
                'DELIVERING',
                'PAUSED',
                'ERROR'
            )
            """,
            name="ck_robot_status_state",
        ),
        CheckConstraint(
            """
            battery_percent IS NULL
            OR (battery_percent >= 0 AND battery_percent <= 100)
            """,
            name="ck_robot_status_battery",
        ),
        CheckConstraint(
            """
            localization_quality IS NULL
            OR localization_quality IN ('GOOD', 'MEDIUM', 'POOR')
            """,
            name="ck_robot_status_localization_quality",
        ),
    )

    robot_id: Mapped[int] = mapped_column(
        ForeignKey(
            "robots.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    online: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="UNKNOWN",
    )

    battery_percent: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    voltage: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    x: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    y: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    yaw: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    line_segment_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "line_segments.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    localization_quality: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )