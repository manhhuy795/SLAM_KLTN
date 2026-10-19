from copy import deepcopy
from threading import RLock
from time import monotonic
from uuid import uuid4

from fastapi import HTTPException

from app.services.saved_maps import MAPS_DIR, load_grid
from app.services.planning import read_layer


class MapSession:
    def __init__(self):
        self.lock = RLock()
        self.report = {"enabled": False, "ready": False, "state": "OFFLINE"}
        self.received = 0
        self.pending = None
        self.started = 0

    def status(self):
        with self.lock:
            result = deepcopy(self.report)
            if monotonic()-self.received > 4:
                result.update(ready=False, keepout_verified=False, localization_valid=False, state="OFFLINE", error="Managed ROS bridge offline")
            if self.pending:
                result.update(ready=False, keepout_verified=False, state="APPLYING", request_id=self.pending["id"])
                if monotonic()-self.started > 60:
                    result.update(state="FAILED", error="ROS operation timed out; result not confirmed")
            return result

    def update(self, report):
        with self.lock:
            self.report = report
            self.received = monotonic()
            if self.pending and report.get("request_id") == self.pending["id"] and report.get("state") != "APPLYING":
                self.pending = None
            return self.status()

    def request(self, record, db, operation, initial_pose=None, planning_revision=None):
        from app.services.navigation import navigation_state
        with self.lock:
            status = self.status()
            if not status.get("enabled") or status["state"] == "OFFLINE":
                raise HTTPException(409, "Start the managed simulation bridge first")
            if navigation_state.get_status()["state"] in {"SENDING","NAVIGATING"}:
                raise HTTPException(409, "Cancel navigation before changing map or keepouts")
            if self.pending and monotonic()-self.started < 60:
                raise HTTPException(409, "Another map operation is in progress")
            grid = load_grid(record)
            if abs(grid["origin"]["yaw"]) > 1e-6:
                raise HTTPException(422, "Nav2 Jazzy costmaps require map origin yaw = 0; original map was not modified")
            if grid["frame_id"] != "map":
                raise HTTPException(422, "Map frame must be map")
            planning = read_layer(db,record.id)
            if operation == "APPLY_KEEPOUTS":
                if status.get("map_id") != record.id or not status.get("map_verified"):
                    raise HTTPException(409, "Load and verify this map first")
                if planning_revision != planning["revision"]:
                    raise HTTPException(409, "Planning changed; reload before applying keepouts")
            if initial_pose:
                from app.services.planning import cell
                col,row = cell(grid, initial_pose["x"], initial_pose["y"])
                if not (0 <= col < grid["width"] and 0 <= row < grid["height"]):
                    raise HTTPException(422, "Initial pose is outside map")
            self.pending = dict(id=uuid4().hex, operation=operation, map_id=record.id,
                                map_hash=grid["map_hash"], yaml_path=str(MAPS_DIR/record.id/"map.yaml"),
                                planning=planning, initial_pose=initial_pose)
            self.started = monotonic()
            return self.status()

    def claim(self):
        with self.lock:
            if self.pending is None or self.pending.get("claimed"):
                return None
            self.pending["claimed"] = True
            return deepcopy(self.pending)

    def guard(self):
        status = self.status()
        if status.get("enabled") and not status.get("ready"):
            raise ValueError("Nav2 map/localization not verified: "+status.get("error",status["state"]))
        if status.get("enabled") and status.get("map_id"):
            from app.db.database import SessionLocal
            from app.models.saved_map import SavedMap
            with SessionLocal() as db:
                record=db.get(SavedMap,status["map_id"])
                if record is None or record.metadata_json["map_hash"] != status.get("map_hash"):
                    raise ValueError("Active Nav2 map is missing or changed")
                if read_layer(db,record.id)["revision"] != status.get("planning_revision"):
                    raise ValueError("Apply the current planning keepouts before navigation")
        return status


map_session = MapSession()
