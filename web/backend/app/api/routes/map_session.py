from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.routes.maps import find_map
from app.db.deps import get_db
from app.services.map_session import map_session
from app.services.realtime import queue_broadcast

router=APIRouter(prefix="/ros/map-session",tags=["Nav2 saved map"])


class InitialPose(BaseModel):
    x: float=Field(allow_inf_nan=False)
    y: float=Field(allow_inf_nan=False)
    yaw: float=Field(allow_inf_nan=False)


class ApplyMap(BaseModel):
    map_id: UUID
    operation: Literal["LOAD_MAP","APPLY_KEEPOUTS"]="LOAD_MAP"
    initial_pose: InitialPose | None=None
    planning_revision: int | None=Field(default=None,ge=0)


class SessionReport(BaseModel):
    enabled: bool=True
    ready: bool=False
    state: Literal["WAITING","APPLYING","READY","FAILED","UNLOCALIZED"]
    request_id: str | None=None
    map_id: str | None=None
    map_hash: str | None=None
    planning_revision: int | None=None
    keepout_verified: bool=False
    keepout_cells: dict[str,int]={}
    mask_topic: str | None=None
    map_verified: bool=False
    map_server_active: bool=False
    nav2_active: bool=False
    localization_valid: bool=False
    environment: str="simulation"
    error: str=""
    session_id: str


@router.get("")
def status():
    return map_session.status()


@router.post("/apply")
def apply(data:ApplyMap, background_tasks:BackgroundTasks,db:Session=Depends(get_db)):
    result=map_session.request(find_map(db,data.map_id),db,data.operation,
                               data.initial_pose.model_dump() if data.initial_pose else None,data.planning_revision)
    queue_broadcast(background_tasks,"MAP_SESSION_UPDATED",result)
    return result


@router.get("/command")
def command():
    return map_session.claim()


@router.post("/status")
def report(data:SessionReport,background_tasks:BackgroundTasks):
    result=map_session.update(data.model_dump())
    queue_broadcast(background_tasks,"MAP_SESSION_UPDATED",result)
    return result
