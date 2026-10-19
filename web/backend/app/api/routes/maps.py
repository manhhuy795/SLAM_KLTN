from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.routing import APIRoute
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db.deps import get_db
from app.models.saved_map import SavedMap
from app.services import saved_maps
from app.services.realtime import queue_broadcast


class LimitedUploadRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def limited(request):
            if request.method not in {"POST", "PUT"}:
                return await handler(request)
            received = 0
            limit = saved_maps.MAX_IMAGE_BYTES + saved_maps.MAX_YAML_BYTES + 64 * 1024

            async def receive():
                nonlocal received
                message = await request.receive()
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, "Map upload exceeds the request size limit")
                return message

            return await handler(Request(request.scope, receive=receive))
        return limited


router = APIRouter(prefix="/maps", tags=["Saved maps"], route_class=LimitedUploadRoute)


def find_map(db, map_id):
    record = db.get(SavedMap, map_id.hex)
    if record is None:
        raise HTTPException(404, "Saved map not found")
    return record


@router.get("")
def list_maps(db: Session = Depends(get_db)):
    return [saved_maps.describe(record) for record in
            db.scalars(select(SavedMap).order_by(SavedMap.created_at.desc(), SavedMap.id))]


@router.get("/selected")
def selected_map(db: Session = Depends(get_db)):
    record = db.scalar(select(SavedMap).where(SavedMap.is_selected.is_(True)))
    return saved_maps.load_grid(record) if record else None


@router.get("/{map_id}")
def read_map(map_id: UUID, db: Session = Depends(get_db)):
    return saved_maps.load_grid(find_map(db, map_id))


@router.post("", status_code=201)
async def upload_map(
    background_tasks: BackgroundTasks,
    yaml_file: UploadFile = File(...),
    image_file: UploadFile = File(...),
    name: str = Form(..., min_length=1, max_length=120),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        raise HTTPException(422, "Map name cannot be blank")
    try:
        yaml_bytes = await yaml_file.read(saved_maps.MAX_YAML_BYTES + 1)
        image_bytes = await image_file.read(saved_maps.MAX_IMAGE_BYTES + 1)
        result = await run_in_threadpool(
            saved_maps.save_map, db, yaml_bytes, image_bytes,
            yaml_file.filename or "", image_file.filename or "", name,
        )
    finally:
        await yaml_file.close()
        await image_file.close()
    queue_broadcast(background_tasks, "SAVED_MAPS_UPDATED", {"action": "uploaded", "id": result["id"]})
    return result


@router.post("/{map_id}/select")
def select_map(map_id: UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # SQLite serializes these writes, keeping the selection atomic.
    db.execute(update(SavedMap).values(is_selected=False))
    record = find_map(db, map_id)
    grid = saved_maps.load_grid(record)
    record.is_selected = True
    db.commit()
    grid["is_selected"] = True
    queue_broadcast(background_tasks, "SAVED_MAPS_UPDATED", {"action": "selected", "id": record.id})
    return grid


@router.delete("/{map_id}", status_code=204)
def delete_map(map_id: UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    record = find_map(db, map_id)
    from app.services.map_session import map_session
    status=map_session.status()
    if status.get("enabled") and (status.get("map_id")==record.id
        or (map_session.pending or {}).get("map_id")==record.id):
        raise HTTPException(409, "Map is in use by Nav2; load another map before deleting")
    db.delete(record)
    db.commit()
    saved_maps.delete_files(map_id.hex)
    queue_broadcast(background_tasks, "SAVED_MAPS_UPDATED", {"action": "deleted", "id": map_id.hex})
