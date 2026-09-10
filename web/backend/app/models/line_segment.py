from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LineSegment(Base):
    __tablename__ = "line_segments"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    segment_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
    )

    start_location_id: Mapped[int] = mapped_column(
        ForeignKey(
            "locations.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    end_location_id: Mapped[int] = mapped_column(
        ForeignKey(
            "locations.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    length_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    polyline_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )