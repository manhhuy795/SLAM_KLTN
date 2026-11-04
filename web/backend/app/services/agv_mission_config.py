"""Read-only readiness and route preview for an operator-supplied AGV graph."""

from math import cos, isfinite, sin
import os

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models.agv_mission_config import AgvMissionConfig
from app.models.agv_vision import AgvClassRackPolicy
from app.models.location import Location
from app.models.saved_map import SavedMap
from app.services.agv_station_graph import (
    REQUIRED_STATIONS, StationGraphError, plan_station_route, validate_station_graph,
)
from app.services.agv_vision import CLASSES, RACKS, agv_pickup_classifier
from app.services.agv_runtime import agv_runtime


class MissionConfigError(ValueError):
    pass


def selected_map(db):
    maps = db.scalars(select(SavedMap).where(SavedMap.is_selected.is_(True)).limit(2)).all()
    return maps[0] if len(maps) == 1 else None


def config_for(db, robot_id, map_id):
    return db.scalar(select(AgvMissionConfig).where(
        AgvMissionConfig.robot_id == robot_id, AgvMissionConfig.map_id == map_id))


def _inside_map(location, saved_map):
    metadata = saved_map.metadata_json or {}
    origin = metadata.get("origin")
    try:
        width, height, resolution = (metadata[key] for key in ("width", "height", "resolution"))
        x0, y0, yaw = (origin[key] for key in ("x", "y", "yaw"))
        values = (width, height, resolution, x0, y0, yaw, location.x, location.y)
        if any(type(value) not in (int, float) or not isfinite(value) for value in values):
            return False
        if width <= 0 or height <= 0 or resolution <= 0:
            return False
        dx, dy = location.x - x0, location.y - y0
        local_x = cos(yaw) * dx + sin(yaw) * dy
        local_y = -sin(yaw) * dx + cos(yaw) * dy
        return 0 <= local_x <= width * resolution and 0 <= local_y <= height * resolution
    except (KeyError, TypeError):
        return False


def station_errors(db, saved_map, bindings):
    errors = []
    if not isinstance(bindings, dict) or set(bindings) - REQUIRED_STATIONS:
        return ["Station bindings contain unknown identifiers"]
    if not all(type(value) is int for value in bindings.values()) or len(set(bindings.values())) != len(bindings):
        errors.append("Station bindings must use unique location IDs")
    for code in sorted(REQUIRED_STATIONS):
        location_id = bindings.get(code)
        if type(location_id) is not int or location_id <= 0:
            errors.append(f"{code}: select an existing active location")
            continue
        location = db.get(Location, location_id)
        kind = "RACK" if code in RACKS else code
        if location is None or location.code != code or location.location_type != kind or not location.is_active:
            errors.append(f"{code}: location is missing, inactive or has the wrong code/type")
        elif not _inside_map(location, saved_map):
            errors.append(f"{code}: coordinates are outside the selected map or map bounds are invalid")
    return errors


def save_config(db, *, robot, saved_map, station_location_ids, graph, expected_revision):
    if robot.robot_type != "LINE" or not robot.is_active or not saved_map.is_selected:
        raise MissionConfigError("An active LINE robot and selected map are required")
    if not isinstance(station_location_ids, dict) or set(station_location_ids) - REQUIRED_STATIONS:
        raise MissionConfigError("Unknown station identifier")
    if len(set(station_location_ids.values())) != len(station_location_ids):
        raise MissionConfigError("Station location IDs must be unique")
    for code, location_id in station_location_ids.items():
        location = db.get(Location, location_id) if type(location_id) is int else None
        kind = "RACK" if code in RACKS else code
        if (location is None or location.code != code or location.location_type != kind
                or not location.is_active or not _inside_map(location, saved_map)):
            raise MissionConfigError(f"{code}: choose an active matching location within the selected map")
    if graph is not None:
        if not isinstance(graph, dict) or not isinstance(graph.get("version"), str) or not graph["version"]:
            raise MissionConfigError("A versioned station graph is required")
        try:
            validate_station_graph(graph, map_id=saved_map.id, robot_id=robot.id)
        except StationGraphError as error:
            raise MissionConfigError(str(error)) from error
    record = config_for(db, robot.id, saved_map.id)
    if record is None:
        if expected_revision not in (None, 0):
            raise MissionConfigError("Configuration revision changed")
        record = AgvMissionConfig(robot_id=robot.id, map_id=saved_map.id,
            station_location_ids=dict(station_location_ids), graph=graph, revision=1)
        db.add(record)
        try:
            db.flush()
        except IntegrityError as error:
            db.rollback()
            raise MissionConfigError("Concurrent configuration update rejected") from error
    else:
        changed = db.execute(update(AgvMissionConfig).where(
            AgvMissionConfig.id == record.id,
            AgvMissionConfig.revision == expected_revision).values(
            station_location_ids=dict(station_location_ids), graph=graph,
            revision=record.revision + 1))
        if changed.rowcount != 1:
            raise MissionConfigError("Configuration revision changed")
        db.refresh(record)
    return record


def readiness(db, robot, *, backend_available=True):
    saved_map = selected_map(db)
    config = config_for(db, robot.id, saved_map.id) if saved_map else None
    bindings = config.station_location_ids if config else {}
    graph = config.graph if config else None
    policy = db.get(AgvClassRackPolicy, saved_map.id) if saved_map else None
    station_issues = station_errors(db, saved_map, bindings) if saved_map else ["Select one saved map"]
    graph_issues = []
    if not graph:
        graph_issues.append("Supply a versioned physical station graph")
    elif saved_map:
        try:
            validate_station_graph(graph, map_id=saved_map.id, robot_id=robot.id)
            for rack in sorted(RACKS):
                for source, target in (("HOME", "PICKUP"), ("PICKUP", rack),
                                       (rack, "HOME"), (rack, "PICKUP")):
                    plan_station_route(graph, map_id=saved_map.id, robot_id=robot.id,
                                       source=source, destination=target)
        except StationGraphError as error:
            graph_issues.append(str(error))
    policy_issues = []
    if policy is None:
        policy_issues.append("Configure class-to-rack policy for the selected map")
    elif (not isinstance(policy.mapping, dict) or set(policy.mapping) != CLASSES
          or any(value not in RACKS or value not in bindings for value in policy.mapping.values())):
        policy_issues.append("Each cargo class must map to a configured delivery rack")
    if station_issues and policy is not None:
        policy_issues.append("Policy racks must remain active and bound to this map")
    telemetry = agv_runtime.get(robot.robot_code)
    dispatch_enabled = os.getenv("WRMS_AGV_AUTO_DISPATCH_ENABLED") == "1"
    vision_available = agv_pickup_classifier.classifier is not None
    checks = [
        ("robot", robot.robot_type == "LINE" and robot.is_active, "Activate a LINE robot"),
        ("backend", backend_available, "Connect to the WRMS backend"),
        ("telemetry", telemetry["connected"], "Connect fresh ESP32 telemetry"),
        ("map", saved_map is not None, "Select exactly one saved map"),
        ("HOME", saved_map is not None and "HOME" in bindings and not any(e.startswith("HOME:") for e in station_issues), "Configure HOME on the selected map"),
        ("PICKUP", saved_map is not None and "PICKUP" in bindings and not any(e.startswith("PICKUP:") for e in station_issues), "Configure PICKUP on the selected map"),
        ("racks", saved_map is not None and RACKS.issubset(bindings) and not any(e.startswith("RACK_") for e in station_issues), "Configure RACK_A–D on the selected map"),
        ("graph", not graph_issues, "Provide reachable HOME/PICKUP/rack/return routes"),
        ("class_mapping", not policy_issues, "Map all three cargo classes to configured racks"),
        ("vision", vision_available, "Install and validate a pickup classifier and capture source"),
        ("dispatch", dispatch_enabled, "AGV automatic dispatch is disabled"),
    ]
    checklist = [{"id": key, "ok": bool(ok), "detail": "OK" if ok else hint}
                 for key, ok, hint in checks]
    issues = station_issues + graph_issues + policy_issues
    simulation_ok = all(check["ok"] for check in checklist if check["id"] in
                        {"robot", "backend", "map", "HOME", "PICKUP", "racks", "graph", "class_mapping"})
    return {
        "robot_code": robot.robot_code, "robot_id": robot.id,
        "selected_map": {"id": saved_map.id, "name": saved_map.name} if saved_map else None,
        "station_location_ids": bindings, "graph": graph,
        "revision": config.revision if config else None,
        "policy": {"mapping": policy.mapping, "revision": policy.revision,
                   "min_confidence": policy.min_confidence, "min_margin": policy.min_margin} if policy else None,
        "checklist": checklist, "errors": issues,
        "simulation_status": "READY_FOR_SIMULATION" if simulation_ok else "BLOCKED",
        # No verified physical graph, station marker, stop or camera contract exists yet.
        "hardware_status": "BLOCKED",
        "hardware_blockers": ["Physical graph and station/stop evidence are not hardware-verified",
                              "Device-side deduplication and camera capture are not validated"],
    }


def preview(db, robot, cargo_class, return_station):
    result = readiness(db, robot)
    if cargo_class not in CLASSES:
        result["errors"].append("Select cylinder, rectangular_box or triangular_prism")
    if return_station not in {"HOME", "PICKUP"}:
        result["errors"].append("Return station must be HOME or PICKUP")
    if result["simulation_status"] != "READY_FOR_SIMULATION" or result["errors"]:
        return {"validation": result, "sequence": [], "target_rack": None}
    graph = result["graph"]
    rack = result["policy"]["mapping"][cargo_class]
    sequence = []
    for stage, source, target in (("pickup", "HOME", "PICKUP"),
                                  ("delivery", "PICKUP", rack),
                                  ("return", rack, return_station)):
        steps = plan_station_route(graph, map_id=result["selected_map"]["id"],
                                   robot_id=robot.id, source=source, destination=target)
        sequence.append({"stage": stage, "source": source, "target": target,
                         "stations": [source, *(step["destination"] for step in steps)],
                         "steps": steps})
    return {"validation": result, "robot_code": robot.robot_code,
            "pickup": "PICKUP", "cargo_class": cargo_class, "target_rack": rack,
            "sequence": sequence}
