from sqlalchemy import ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgvMissionConfig(Base):
    __tablename__ = "agv_mission_configs"
    __table_args__ = (UniqueConstraint("robot_id", "map_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id", ondelete="CASCADE"), nullable=False)
    map_id: Mapped[str] = mapped_column(String(32), ForeignKey("saved_maps.id", ondelete="CASCADE"), nullable=False)
    station_location_ids: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    graph: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
