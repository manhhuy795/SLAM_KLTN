from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from fastapi.exceptions import RequestValidationError

from app.api.routes.maps import find_map, LimitedUploadRoute
from app.db.deps import get_db
from app.schemas.planning import PlanningSave
from app.services.planning import read_layer, save_layer
from app.services.saved_maps import load_grid
from app.services.realtime import queue_broadcast

class PlanningRoute(LimitedUploadRoute):
    def get_route_handler(self):
        handler=super().get_route_handler()

        async def validated(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # Invalid NaN/Infinity input cannot be echoed in a JSON error body.
                raise HTTPException(422, "; ".join(
                    ".".join(str(p) for p in e["loc"])+": "+e["msg"]
                    for e in exc.errors())) from exc
        return validated


router=APIRouter(prefix="/maps", tags=["Planning"], route_class=PlanningRoute)


@router.get("/{map_id}/planning")
def get_planning(map_id: UUID, db: Session=Depends(get_db)):
    find_map(db,map_id)
    return read_layer(db,map_id.hex)


@router.put("/{map_id}/planning")
def put_planning(map_id: UUID, payload: PlanningSave, background_tasks: BackgroundTasks,
                 db: Session=Depends(get_db)):
    result=save_layer(db,map_id.hex,payload,load_grid(find_map(db,map_id)))
    queue_broadcast(background_tasks,"PLANNING_UPDATED",
                    dict(map_id=map_id.hex,revision=result["revision"]))
    return result


@router.delete("/{map_id}/planning")
def clear_planning(map_id: UUID, background_tasks: BackgroundTasks,
                   revision: int=Query(ge=0), db: Session=Depends(get_db)):
    return put_planning(map_id,PlanningSave(revision=revision,objects=[]),background_tasks,db)
