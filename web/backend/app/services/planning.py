from datetime import datetime, timezone
import math

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert

from app.models.planning_layer import PlanningLayer


def footprint(obj):
    if obj.type == "RACK":
        points = [(-obj.width/2,-obj.height/2), (obj.width/2,-obj.height/2),
                  (obj.width/2,obj.height/2), (-obj.width/2,obj.height/2)]
    elif obj.type == "NO_GO":
        points = [(p.x,p.y) for p in obj.vertices]
    else:
        points = [(0,0)]
    c,s=math.cos(obj.yaw),math.sin(obj.yaw)
    return [(obj.x+c*x-s*y,obj.y+s*x+c*y) for x,y in points]


def cell(grid,x,y):
    origin=grid["origin"]
    dx,dy=x-origin["x"],y-origin["y"]
    c,s=math.cos(origin["yaw"]),math.sin(origin["yaw"])
    return ((c*dx+s*dy)/grid["resolution"],(-s*dx+c*dy)/grid["resolution"])


def validate_objects(grid, objects):
    warnings=[]
    for obj in objects:
        for x,y in footprint(obj):
            col,row=cell(grid,x,y)
            if not (0 <= col < grid["width"] and 0 <= row < grid["height"]):
                raise HTTPException(422, f"{obj.name}: object extends outside map bounds")
        if obj.type not in {"RACK","NO_GO"}:
            col,row=cell(grid,obj.x,obj.y)
            occupancy=grid["data"][int(row)*grid["width"]+int(col)]
            if occupancy != 0:
                warnings.append(dict(id=str(obj.id), message=(
                    "Ô chưa biết; chưa xác nhận có thể tiếp cận." if occupancy < 0 else
                    "Ô có xác suất bị chiếm dụng; chưa xác nhận có thể tiếp cận.")))
    return warnings


def read_layer(db, map_id):
    row=db.get(PlanningLayer,map_id)
    return dict(map_id=map_id,revision=row.revision if row else 0,
                objects=row.objects if row else [],updated_at=row.updated_at if row else None)


def save_layer(db, map_id, payload, grid):
    warnings=validate_objects(grid,payload.objects)
    # Serialize writes and compare revisions inside one transaction.
    db.execute(insert(PlanningLayer).values(map_id=map_id,revision=0,objects=[])
               .on_conflict_do_nothing(index_elements=["map_id"]))
    row=db.get(PlanningLayer,map_id,populate_existing=True)
    if row.revision != payload.revision:
        db.rollback()
        raise HTTPException(409,"Planning layer changed elsewhere. Cancel/reload before editing again.")
    previous={item["id"]:item for item in row.objects}
    now=datetime.now(timezone.utc)
    stamp=now.isoformat()
    objects=[]
    for obj in payload.objects:
        value=obj.model_dump(mode="json")
        old=previous.get(value["id"])
        unchanged=old and all(old.get(k)==v for k,v in value.items())
        objects.append({**value,"map_id":map_id,
                        "created_at":old["created_at"] if old else stamp,
                        "updated_at":old["updated_at"] if unchanged else stamp})
    db.execute(update(PlanningLayer).where(PlanningLayer.map_id==map_id)
               .values(objects=objects,revision=payload.revision+1,updated_at=now))
    db.commit()
    return {**read_layer(db,map_id),"warnings":warnings}
