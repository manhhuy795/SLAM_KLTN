import tempfile
import unittest
from math import pi
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

import init_db  # noqa: F401 - register tables
from app.db.base import Base
from app.db.deps import get_db
from app.main import app
from app.models.agv_mission_config import AgvMissionConfig
from app.models.location import Location
from app.models.operator import Operator
from app.models.robot import Robot
from app.models.robot_command import RobotCommand
from app.models.saved_map import SavedMap
from app.models.task import Task
from app.services.agv_mission_config import _inside_map


STATIONS = ("HOME", "PICKUP", "RACK_A", "RACK_B", "RACK_C", "RACK_D")
CLASSES = ("cylinder", "rectangular_box", "triangular_prism")


def graph(robot_id):
    links = [("HOME", "PICKUP")]
    for rack in STATIONS[2:]:
        links += [("PICKUP", rack), (rack, "HOME"), (rack, "PICKUP")]
    return {"map_id": "test-map", "robot_id": robot_id, "version": "operator-draft-v1",
            "nodes": [{"id": code, "kind": "STATION"} for code in STATIONS],
            "edges": [{"source": source, "destination": target,
                       "direction": "FORWARD", "action": "STRAIGHT", "cost": 1,
                       "verification_marker": f"draft-{target}"} for source, target in links],
            "junction_transitions": []}


class AgvMissionConfigTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{(Path(self.folder.name) / 'config.db').as_posix()}",
                                    connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            robot = Robot(robot_code="LINE-01", name="AGV", robot_type="LINE", is_active=True)
            operator = Operator(operator_code="OP1", full_name="Operator", is_active=True)
            saved_map = SavedMap(id="test-map", name="Measured map", is_selected=True,
                metadata_json={"width": 100, "height": 100, "resolution": 0.1,
                               "origin": {"x": 0, "y": 0, "yaw": 0}, "frame_id": "map"})
            db.add_all([robot, operator, saved_map])
            db.flush()
            self.robot_id, self.operator_id = robot.id, operator.id
            locations = [Location(code=code, name=code, location_type="RACK" if code.startswith("RACK") else code,
                                  x=index + 1, y=1, is_active=True)
                         for index, code in enumerate(STATIONS)]
            db.add_all(locations)
            db.flush()
            self.bindings = {location.code: location.id for location in locations}
            db.commit()

        def fixture_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = fixture_db
        self.addCleanup(app.dependency_overrides.pop, get_db, None)
        self.client = TestClient(app)
        self.flags = patch.dict("os.environ", {"WRMS_AGV_POLICY_TOKEN": "test-policy-token",
                                             "WRMS_AGV_AUTO_DISPATCH_ENABLED": "0",
                                             "WRMS_AGV_CAMERA_AUTO_CONFIRM_ENABLED": "0"})
        self.flags.start()
        self.addCleanup(self.flags.stop)
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(self.engine.dispose)

    def save(self, bindings=None, supplied_graph=None, revision=None):
        return self.client.put("/api/agv/LINE-01/mission-config",
            json={"station_location_ids": self.bindings if bindings is None else bindings,
                  "graph": graph(self.robot_id) if supplied_graph is None else supplied_graph,
                  "expected_revision": revision, "operator_id": self.operator_id},
            headers={"X-WRMS-Policy-Token": "test-policy-token"})

    def policy(self):
        return self.client.put("/api/tasks/agv/class-rack-policy", json={
            "map_id": "test-map", "operator_id": self.operator_id,
            "mapping": dict(zip(CLASSES, STATIONS[2:5])),
            "min_confidence": 0.8, "min_margin": 0.2},
            headers={"X-WRMS-Policy-Token": "test-policy-token"})

    def test_valid_configuration_preview_is_read_only_and_hardware_stays_blocked(self):
        with patch("app.services.agv_runtime.agv_runtime.command") as command:
            self.assertEqual(self.save().status_code, 200)
            self.assertEqual(self.policy().status_code, 200)
            readiness = self.client.get("/api/agv/LINE-01/mission-config").json()
            self.assertEqual(readiness["simulation_status"], "READY_FOR_SIMULATION")
            self.assertEqual(readiness["hardware_status"], "BLOCKED")
            self.assertFalse(next(check for check in readiness["checklist"] if check["id"] == "telemetry")["ok"])
            preview = self.client.get("/api/agv/LINE-01/mission-preview",
                                      params={"cargo_class": "cylinder"}).json()
            self.assertEqual(preview["target_rack"], "RACK_A")
            self.assertEqual([(leg["source"], leg["target"]) for leg in preview["sequence"]],
                             [("HOME", "PICKUP"), ("PICKUP", "RACK_A"), ("RACK_A", "HOME")])
            command.assert_not_called()
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(Task)).all()), 0)
            self.assertEqual(len(db.scalars(select(RobotCommand)).all()), 0)

    def test_missing_stations_mapping_and_unreachable_rack_block(self):
        missing = self.client.get("/api/agv/LINE-01/mission-config").json()
        self.assertEqual(missing["simulation_status"], "BLOCKED")
        self.assertIn("HOME", " ".join(missing["errors"]))
        self.assertIn("PICKUP", " ".join(missing["errors"]))
        self.assertEqual(self.save().status_code, 200)
        no_policy = self.client.get("/api/agv/LINE-01/mission-config").json()
        self.assertFalse(next(check for check in no_policy["checklist"] if check["id"] == "class_mapping")["ok"])
        self.assertEqual(self.policy().status_code, 200)
        disconnected = graph(self.robot_id)
        disconnected["edges"] = [edge for edge in disconnected["edges"]
                                 if edge["destination"] != "RACK_D"]
        self.assertEqual(self.save(supplied_graph=disconnected, revision=1).status_code, 200)
        blocked = self.client.get("/api/agv/LINE-01/mission-preview",
                                  params={"cargo_class": "cylinder"}).json()
        self.assertEqual(blocked["validation"]["simulation_status"], "BLOCKED")
        self.assertEqual(blocked["sequence"], [])
        self.assertIn("unreachable", " ".join(blocked["validation"]["errors"]))

    def test_wrong_map_duplicate_outside_or_inactive_station_rejected(self):
        self.assertEqual(self.client.put("/api/agv/LINE-01/mission-config", json={
            "station_location_ids": {}, "operator_id": self.operator_id}).status_code, 403)
        self.assertEqual(self.save(bindings={**self.bindings, "HOME": self.bindings["PICKUP"]}).status_code, 409)
        wrong = graph(self.robot_id)
        wrong["map_id"] = "other-map"
        self.assertEqual(self.save(supplied_graph=wrong).status_code, 409)
        wrong = graph(self.robot_id + 1)
        self.assertEqual(self.save(supplied_graph=wrong).status_code, 409)
        with Session(self.engine) as db:
            rack = db.get(Location, self.bindings["RACK_A"])
            rack.x = 1000
            db.commit()
        self.assertEqual(self.save().status_code, 409)
        with Session(self.engine) as db:
            rack = db.get(Location, self.bindings["RACK_A"])
            rack.x = 3
            db.commit()
        self.assertEqual(self.save().status_code, 200)
        self.assertEqual(self.policy().status_code, 200)
        with Session(self.engine) as db:
            db.get(Location, self.bindings["RACK_A"]).is_active = False
            db.commit()
        readiness = self.client.get("/api/agv/LINE-01/mission-config").json()
        self.assertEqual(readiness["simulation_status"], "BLOCKED")
        self.assertIn("inactive", " ".join(readiness["errors"]))
        self.assertEqual(self.client.get("/api/agv/AMR-01/mission-config").status_code, 404)

    def test_rotated_map_bounds_use_map_frame(self):
        saved_map = SavedMap(metadata_json={"width": 10, "height": 10, "resolution": 0.1,
                                            "origin": {"x": 1, "y": 2, "yaw": pi / 2}})
        location = Location(x=0.5, y=2.5)
        self.assertTrue(_inside_map(location, saved_map))
        location.x = 1.5
        self.assertFalse(_inside_map(location, saved_map))


if __name__ == "__main__":
    unittest.main()
