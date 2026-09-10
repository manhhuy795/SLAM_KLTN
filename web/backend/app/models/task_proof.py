from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskProof(Base):
    __tablename__ = "task_proofs"

    __table_args__ = (
        CheckConstraint(
            "proof_type IN ('PICKUP', 'DELIVERY')",
            name="ck_task_proofs_type",
        ),
        CheckConstraint(
            """
            verification_status IN (
                'PENDING',
                'AUTO_VERIFIED',
                'MANUAL_CONFIRMED',
                'FAILED'
            )
            """,
            name="ck_task_proofs_verification_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    task_id: Mapped[int] = mapped_column(
        ForeignKey(
            "tasks.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    proof_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    image_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    verification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDING",
    )

    confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey(
            "operators.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )