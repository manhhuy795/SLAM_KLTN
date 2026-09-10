from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Landmark(Base):
    __tablename__ = "landmarks"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    landmark_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
    )

    landmark_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="APRILTAG",
    )

    segment_id: Mapped[int] = mapped_column(
        ForeignKey(
            "line_segments.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    x: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    y: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    yaw: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )