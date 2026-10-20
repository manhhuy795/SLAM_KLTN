"""Import the versioned demo fixtures; never overwrite an existing planning layer."""
import argparse
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from init_db import init_database
from app.db.database import SessionLocal
from app.models.saved_map import SavedMap
from app.schemas.planning import PlanningSave
from app.services.planning import read_layer, save_layer, validate_objects
from app.services.saved_maps import load_grid, parse_map, save_map

DEMOS = Path(__file__).resolve().parents[2] / "demo"


def import_demo(dataset="final"):
    folder = DEMOS / dataset
    yaml_name = "warehouse_line_web_v3.yaml" if dataset == "final" else "warehouse.yaml"
    image_name = Path(yaml_name).with_suffix(".pgm").name
    yaml_bytes, image_bytes = (folder / yaml_name).read_bytes(), (folder / image_name).read_bytes()
    config, grid = parse_map(yaml_bytes, image_bytes, yaml_name, image_name)
    data = json.loads((folder / "planning_layer_payload.json").read_text(encoding="utf-8-sig"))
    objects = []
    for point in data["points"]:
        objects.append(dict(name=point["name"],
                            type="PICKUP" if point["type"] == "RACK_STOP" else point["type"],
                            x=point["x_m"], y=point["y_m"], yaw=point.get("yaw_rad", 0)))
    for rack in data["racks"]:
        objects.append(dict(name=rack["name"], type="RACK", x=rack["center_x_m"],
                            y=rack["center_y_m"], yaw=rack["yaw_rad"],
                            width=rack["width_m"], height=rack["height_m"]))
    for zone in data.get("no_go", []):
        objects.append({**zone, "type": "NO_GO"})
    for obj in objects:
        obj["id"] = str(uuid5(NAMESPACE_URL, grid["map_hash"] + ":" + obj["name"]))
    payload = PlanningSave(revision=0, objects=objects)
    warnings = validate_objects(grid, payload.objects)

    with SessionLocal() as db:
        maps = list(db.scalars(select(SavedMap).order_by(SavedMap.is_selected.desc(), SavedMap.id)))
        record = next((m for m in maps if m.metadata_json.get("map_hash") == grid["map_hash"]), None)
        if record is None:
            created = save_map(db, yaml_bytes, image_bytes, yaml_name, image_name, data["map_name"])
            record = db.get(SavedMap, created["id"])
        else:
            # A hash in SQLite alone does not prove that the persisted image/grid is intact.
            actual = load_grid(record)
            if actual["data"] != grid["data"]:
                raise ValueError("Existing map data differs from the bundled map; restore its files first.")
        layer = read_layer(db, record.id)
        if layer["objects"]:
            def geometry(items):
                return sorted(
                    [{k: v for k, v in item.items()
                      if k not in {"id", "map_id", "created_at", "updated_at"}} for item in items],
                    key=lambda item: (item["name"], item["type"]))
            desired = [obj.model_dump(mode="json") for obj in payload.objects]
            if geometry(layer["objects"]) != geometry(desired):
                raise ValueError(f"{record.name}: existing planning differs; kept unchanged. "
                                 "Use Map Editor to review it; this command does not overwrite it.")
            action = "already imported"
        else:
            payload.revision = layer["revision"]
            save_layer(db, record.id, payload, grid)
            action = "imported"
        if not db.scalar(select(SavedMap).where(SavedMap.is_selected.is_(True))):
            record.is_selected = True
            db.commit()
        print(f"{action}: {record.name} ({record.id}), {len(objects)} objects")
        by_id = {obj["id"]: obj["name"] for obj in objects}
        for warning in warnings:
            print(f"WARNING {by_id[warning['id']]}: {warning['message']}")
        return record.id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["final", "simulation"], default="final")
    args = parser.parse_args()
    init_database()
    import_demo(args.dataset)
