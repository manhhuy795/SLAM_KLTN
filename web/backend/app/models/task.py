from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Task(Base):
    __tablename__ = "tasks"

    __table_args__ = (
        CheckConstraint(
            """
            status IN (
                'WAITING',
                'MOVING_TO_PICKUP',
                'ARRIVED_AT_PICKUP',
                'PICKUP_CONFIRMED',
                'TRANSPORTING',
                'ARRIVED_AT_DELIVERY',
                'DELIVERY_CONFIRMED',
                'COMPLETED',
                'FAILED',
                'CANCELLED'
            )
            """,
            name="ck_tasks_status",
        ),
        CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_tasks_progress",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    task_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey(
            "products.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    robot_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "robots.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    pickup_location_id: Mapped[int] = mapped_column(
        ForeignKey(
            "locations.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    dropoff_location_id: Mapped[int] = mapped_column(
        ForeignKey(
            "locations.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="WAITING",
        index=True,
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    is_paused: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    cancel_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    fail_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    retry_of_task_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "tasks.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )