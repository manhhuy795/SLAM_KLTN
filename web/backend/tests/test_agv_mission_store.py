import tempfile
import threading
import unittest
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

import init_db  # noqa: F401 - registers existing tables with Base
from app.db.base import Base
from app.models.agv_mission import AgvMission, AgvMissionCommand
from app.models.agv_cargo_evidence import AgvCargoEvidence
from app.models.location import Location
from app.models.operator import Operator
from app.models.product import Product
from app.models.robot import Robot
from app.models.robot_command import RobotCommand
from app.models.saved_map import SavedMap
from app.models.task import Task
from app.services.agv_mission_store import (
    AgvMissionConflict, advance_command, claim_dispatch, claim_mission, create_command,
    confirm_cancelled, expire_command, mark_uncertain, recover_unresolved_commands,
    request_cancel, verify_arrival, verify_stopped,
)
from app.services.agv_mission_adapter import AgvMissionAdapter
from app.services.agv_cargo_verifier import AgvCargoVerifier, CargoEvidenceError
from app.schemas.task import TaskProofCreate, TaskStatusUpdate
from app.schemas.robot_command import RobotCommandAck, RobotCommandCreate
from app.api.routes import tasks as task_routes, commands as command_routes
from app.api.routes import agv as agv_routes
from app import main as app_main


class MockTransport:
    def __init__(self, robot_id):
        self.robot_id = robot_id
        self.sent = []
        self.sent_commands = []
        self.stops = []
        self.source_verified = True
        self.fail_send = False

    def current_station(self, robot_id):
        latest = self.sent_commands[-1] if self.sent_commands else None
        station = latest.target_station if latest and latest.status == "ARRIVED" else "HOME"
        return {"robot_id": self.robot_id, "station": station,
                "physical_marker_verified": self.source_verified, "stopped": True}

    def send(self, command):
        if self.fail_send:
            raise RuntimeError("mock send failed")
        self.sent.append(command.command_id)
        self.sent_commands.append(command)

    def stop(self, command):
        self.stops.append(command.command_id)


class MockAnalyzer:
    def __init__(self, presence):
        self.presence = presence
        self.calls = 0

    def analyze(self, _image_ref):
        self.calls += 1
        return {"presence": self.presence, "confidence": 0.9,
                "provenance": "mock-cargo-presence", "shape_class": "cylinder"}


class AgvMissionStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{(Path(self.folder.name) / 'mission.db').as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 1},
        )

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            pickup = Location(code="PICKUP", name="Pickup", location_type="PICKUP", x=0, y=0)
            home = Location(code="HOME", name="Home", location_type="HOME", x=0, y=0)
            rack = Location(code="RACK_A", name="Rack A", location_type="RACK", x=1, y=1)
            robot = Robot(robot_code="LINE-T1", name="LINE", robot_type="LINE", is_active=True)
            other = Robot(robot_code="LINE-T2", name="LINE 2", robot_type="LINE", is_active=True)
            saved_map = SavedMap(id="test-map", name="Test", metadata_json={}, is_selected=True)
            db.add_all([home, pickup, rack, robot, other, saved_map])
            db.flush()
            product = Product(product_code="P1", name="Product", default_rack_id=rack.id)
            operator = Operator(operator_code="O1", full_name="Operator")
            db.add_all([product, operator])
            db.flush()
            self.operator_id = operator.id
            tasks = [Task(task_code=f"T{i}", product_id=product.id, robot_id=robot.id,
                          pickup_location_id=pickup.id, dropoff_location_id=rack.id)
                     for i in (1, 2)]
            db.add_all(tasks)
            db.flush()
            self.task_ids = [task.id for task in tasks]
            self.robot_id, self.other_robot_id = robot.id, other.id
            db.commit()

    def tearDown(self):
        self.engine.dispose()
        self.folder.cleanup()

    def claim(self, db, task_id=None, robot_id=None, map_id="test-map"):
        return claim_mission(db, task_id=task_id or self.task_ids[0],
                             robot_id=robot_id or self.robot_id, map_id=map_id,
                             graph_version="fixture-v1")

    def command(self, db, mission):
        return create_command(db, mission=mission, mission_stage="PICKUP",
                              source_station="HOME", target_station="PICKUP",
                              route_id="fixture-route", route_steps=[{"source": "HOME", "destination": "PICKUP"}])

    def identified_command(self, db):
        return create_command(db, mission=self.claim(db), mission_stage="PICKUP",
                              source_station="HOME", target_station="PICKUP",
                              route_id="fixture-route", route_steps=[{"source": "HOME", "destination": "PICKUP"}],
                              target_marker="PICKUP-MARKER")

    @staticmethod
    def identity(command):
        return dict(command_id=command.command_id, task_id=command.task_id,
                    robot_id=command.robot_id, command_sequence=command.command_sequence)

    @staticmethod
    def evidence(command, **overrides):
        data = dict(AgvMissionStoreTests.identity(command), target_station=command.target_station,
                    current_station=command.target_station, marker=command.target_marker,
                    physical_marker_verified=True, stopped=True, stopped_verified=True,
                    timestamp=datetime.now(timezone.utc).isoformat())
        data.update(overrides)
        return data

    def adapter(self):
        graph = {
            "map_id": "test-map", "robot_id": self.robot_id, "version": "fixture-v1",
            "nodes": [{"id": name, "kind": "STATION"} for name in
                      ("HOME", "PICKUP", "RACK_A", "RACK_B", "RACK_C", "RACK_D")],
            "edges": [
                {"source": source, "destination": target, "direction": "FORWARD",
                 "cost": 1, "action": "STRAIGHT", "verification_marker": marker}
                for source, target, marker in (
                    ("HOME", "PICKUP", "PICKUP-MARKER"),
                    ("PICKUP", "RACK_A", "RACK-A-MARKER"),
                    ("RACK_A", "PICKUP", "PICKUP-RETURN-MARKER"),
                    ("RACK_A", "HOME", "HOME-MARKER"),
                )
            ],
            "junction_transitions": [],
        }
        transport = MockTransport(self.robot_id)
        return AgvMissionAdapter(graph_provider=lambda *_: graph, transport=transport), graph, transport

    def ready_delivery(self, db, adapter):
        task = db.get(Task, self.task_ids[0])
        adapter.start_pickup(db, task)
        mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task.id))
        pickup = db.scalar(select(AgvMissionCommand).where(
            AgvMissionCommand.mission_id == mission.id,
            AgvMissionCommand.mission_stage == "PICKUP"))
        adapter.acknowledge(db, **self.identity(pickup))
        adapter.executing(db, **self.identity(pickup))
        adapter.arrival(db, **self.identity(pickup), evidence=self.evidence(pickup))
        task.status = "PICKUP_CONFIRMED"  # Explicit operator confirmation fixture.
        adapter.start_delivery(db, task)
        delivery = db.scalar(select(AgvMissionCommand).where(
            AgvMissionCommand.mission_id == mission.id,
            AgvMissionCommand.mission_stage == "DELIVERY"))
        adapter.acknowledge(db, **self.identity(delivery))
        adapter.executing(db, **self.identity(delivery))
        adapter.arrival(db, **self.identity(delivery), evidence=self.evidence(delivery))
        return task, delivery

    def test_claim_is_durable_idempotent_and_one_active_per_robot(self):
        with Session(self.engine) as db:
            mission = self.claim(db)
            self.assertEqual(self.claim(db).id, mission.id)
            with self.assertRaises(AgvMissionConflict):
                self.claim(db, task_id=self.task_ids[1])
            db.commit()
            mission_id = mission.id
        with Session(self.engine) as db:
            self.assertEqual(self.claim(db).task_id, self.task_ids[0])
            self.assertEqual(db.scalar(select(AgvMission).where(AgvMission.robot_id == self.robot_id)).id,
                             mission_id)

    def test_wrong_owner_and_map_are_rejected(self):
        with Session(self.engine) as db:
            with self.assertRaisesRegex(AgvMissionConflict, "ownership"):
                self.claim(db, robot_id=self.other_robot_id)
            with self.assertRaisesRegex(AgvMissionConflict, "active map"):
                self.claim(db, map_id="other-map")
            self.assertEqual(db.query(AgvMission).count(), 0)

    def test_claim_does_not_commit_before_caller_commits(self):
        with Session(self.engine) as db:
            self.claim(db)
            db.rollback()
        with Session(self.engine) as db:
            self.assertEqual(db.query(AgvMission).count(), 0)

    def test_stage_command_is_idempotent_and_route_immutable(self):
        with Session(self.engine) as db:
            mission = self.claim(db)
            command = self.command(db, mission)
            self.assertEqual(self.command(db, mission).command_id, command.command_id)
            with self.assertRaisesRegex(AgvMissionConflict, "different route"):
                create_command(db, mission=mission, mission_stage="PICKUP",
                               source_station="HOME", target_station="PICKUP",
                               route_id="changed", route_steps=[{"source": "HOME"}])
            with self.assertRaisesRegex(AgvMissionConflict, "unresolved"):
                create_command(db, mission=mission, mission_stage="DELIVERY",
                               source_station="PICKUP", target_station="RACK_A",
                               route_id="another", route_steps=[{"source": "PICKUP"}])
            db.commit()
            command_id = command.command_id
        with Session(self.engine) as db:
            self.assertEqual(db.get(AgvMissionCommand, command_id).status, "REQUESTED")

    def test_wrong_robot_stale_and_duplicate_ack_are_rejected(self):
        with Session(self.engine) as db:
            command = self.command(db, self.claim(db))
            args = dict(command_id=command.command_id, task_id=command.task_id,
                        robot_id=command.robot_id, command_sequence=command.command_sequence)
            self.assertFalse(advance_command(db, **{**args, "robot_id": self.other_robot_id},
                                             expected_status="REQUESTED", new_status="ACCEPTED"))
            self.assertFalse(advance_command(db, **{**args, "command_sequence": 999},
                                             expected_status="REQUESTED", new_status="ACCEPTED"))
            self.assertTrue(advance_command(db, **args, expected_status="REQUESTED", new_status="ACCEPTED"))
            self.assertTrue(advance_command(db, **args, expected_status="ACCEPTED", new_status="ACKNOWLEDGED"))
            self.assertFalse(advance_command(db, **args, expected_status="ACCEPTED", new_status="ACKNOWLEDGED"))
            with self.assertRaisesRegex(AgvMissionConflict, "Unsupported"):
                advance_command(db, **args, expected_status="ACKNOWLEDGED", new_status="ARRIVED")
            db.refresh(command)
            self.assertEqual(command.status, "ACKNOWLEDGED")
            self.assertIsNotNone(command.acknowledged_at)

    def test_restart_quarantines_unresolved_command_without_resend(self):
        with Session(self.engine) as db:
            command = self.command(db, self.claim(db))
            db.commit()
            command_id = command.command_id
        with Session(self.engine) as restarted:
            self.assertEqual(recover_unresolved_commands(restarted), 1)
            restarted.commit()
        with Session(self.engine) as db:
            command = db.get(AgvMissionCommand, command_id)
            self.assertEqual(command.status, "UNKNOWN")
            self.assertEqual(db.get(AgvMission, command.mission_id).status, "UNKNOWN")
            with self.assertRaises(AgvMissionConflict):
                self.claim(db, task_id=self.task_ids[1])

    def test_concurrent_claims_leave_only_one_mission(self):
        barrier = threading.Barrier(2)

        def start(task_id):
            with Session(self.engine) as db:
                barrier.wait()
                try:
                    self.claim(db, task_id=task_id)
                    db.commit()
                    return "claimed"
                except AgvMissionConflict:
                    db.rollback()
                    return "rejected"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(start, self.task_ids))
        self.assertEqual(sorted(outcomes), ["claimed", "rejected"])
        with Session(self.engine) as db:
            self.assertEqual(db.query(AgvMission).count(), 1)

    def test_dispatch_claim_is_atomic_across_sessions_and_not_replayed_after_restart(self):
        with Session(self.engine) as db:
            command = self.command(db, self.claim(db))
            identity = self.identity(command)
            db.commit()
        barrier = threading.Barrier(2)

        def claim(_):
            with Session(self.engine) as db:
                barrier.wait()
                result = claim_dispatch(db, **identity)
                db.commit()
                return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, (1, 2)))
        self.assertEqual(sorted(results), [False, True])
        with Session(self.engine) as db:
            command = db.get(AgvMissionCommand, identity["command_id"])
            self.assertIsNotNone(command.dispatch_claimed_at)
            self.assertEqual(recover_unresolved_commands(db), 1)
            db.commit()
        with Session(self.engine) as db:
            self.assertFalse(claim_dispatch(db, **identity))

    def test_app_startup_does_not_quarantine_live_worker_command(self):
        with Session(self.engine) as db:
            command = self.command(db, self.claim(db))
            command_id = command.command_id
            db.commit()

        async def startup():
            async with app_main.lifespan(None):
                pass

        with patch.object(app_main, "engine", self.engine):
            asyncio.run(startup())
        with Session(self.engine) as db:
            self.assertEqual(db.get(AgvMissionCommand, command_id).status, "REQUESTED")

    def test_additive_table_creation_preserves_existing_robot_data(self):
        path = Path(self.folder.name) / "existing.db"
        engine = create_engine(f"sqlite:///{path.as_posix()}")
        existing_tables = [table for table in Base.metadata.sorted_tables
                           if table.name not in {"agv_missions", "agv_mission_commands"}]
        Base.metadata.create_all(engine, tables=existing_tables)
        with engine.begin() as conn:
            conn.execute(Robot.__table__.insert().values(robot_code="OLD", name="Existing",
                                                        robot_type="AMR", is_active=True))
        AgvMission.__table__.create(engine, checkfirst=True)
        AgvMissionCommand.__table__.create(engine, checkfirst=True)
        with Session(engine) as db:
            self.assertEqual(db.scalar(select(Robot.robot_code).where(Robot.robot_code == "OLD")), "OLD")
            self.assertEqual(db.query(AgvMission).count(), 0)
        engine.dispose()

    def test_ack_and_distance_never_count_as_arrival_without_stopped_marker(self):
        with Session(self.engine) as db:
            command = self.identified_command(db)
            identity = self.identity(command)
            self.assertTrue(advance_command(db, **identity, expected_status="REQUESTED", new_status="ACCEPTED"))
            self.assertTrue(advance_command(db, **identity, expected_status="ACCEPTED", new_status="ACKNOWLEDGED"))
            self.assertFalse(verify_arrival(db, **identity, evidence=self.evidence(command)))
            self.assertTrue(advance_command(db, **identity, expected_status="ACKNOWLEDGED", new_status="EXECUTING"))
            db.refresh(command)
            for bad in (
                {"stopped": False}, {"physical_marker_verified": False},
                {"current_station": "HOME"}, {"marker": "WRONG"},
                {"timestamp": "2000-01-01T00:00:00Z"},
            ):
                self.assertFalse(verify_arrival(db, **identity, evidence=self.evidence(command, **bad)))
            self.assertFalse(verify_arrival(db, **{**identity, "robot_id": self.other_robot_id},
                                            evidence=self.evidence(command)))
            self.assertTrue(verify_arrival(db, **identity, evidence=self.evidence(command)))
            self.assertFalse(verify_arrival(db, **identity, evidence=self.evidence(command)))
            db.refresh(command)
            self.assertEqual(command.status, "ARRIVED")
            self.assertIsNotNone(command.arrival_evidence)

    def test_timeout_and_disconnect_quarantine_without_reissue(self):
        with Session(self.engine) as db:
            command = self.identified_command(db)
            identity = self.identity(command)
            db.refresh(command)
            self.assertFalse(expire_command(db, **identity,
                                            now=command.created_at + timedelta(seconds=9),
                                            ack_timeout=10, execution_timeout=60))
            self.assertTrue(expire_command(db, **identity,
                                           now=command.created_at + timedelta(seconds=11),
                                           ack_timeout=10, execution_timeout=60))
            self.assertFalse(expire_command(db, **identity,
                                            now=command.created_at + timedelta(seconds=20),
                                            ack_timeout=10, execution_timeout=60))
            db.refresh(command)
            self.assertEqual(command.status, "UNKNOWN")
            with self.assertRaises(AgvMissionConflict):
                self.identified_command(db)
        with Session(self.engine) as db:
            command = self.identified_command(db)
            self.assertTrue(mark_uncertain(db, **self.identity(command), reason="DISCONNECTED"))
            self.assertFalse(mark_uncertain(db, **self.identity(command), reason="DISCONNECTED"))

    def test_cancel_needs_correlated_stopped_evidence(self):
        with Session(self.engine) as db:
            command = self.identified_command(db)
            identity = self.identity(command)
            self.assertTrue(request_cancel(db, **identity))
            self.assertFalse(request_cancel(db, **identity))
            db.refresh(command)
            mission = db.get(AgvMission, command.mission_id)
            self.assertEqual((command.status, mission.status), ("UNKNOWN", "UNKNOWN"))
            self.assertFalse(confirm_cancelled(db, **identity))
            self.assertFalse(verify_stopped(db, **identity,
                                            evidence=self.evidence(command, stopped=False)))
            self.assertFalse(verify_stopped(db, **identity,
                                            evidence=self.evidence(command, stopped_verified=False)))
            self.assertFalse(verify_stopped(db, **{**identity, "task_id": self.task_ids[1]},
                                            evidence=self.evidence(command)))
            midroute_stop = self.evidence(command, current_station=None, target_station=None,
                                          marker=None, physical_marker_verified=False)
            self.assertTrue(verify_stopped(db, **identity, evidence=midroute_stop))
            self.assertFalse(verify_stopped(db, **identity, evidence=self.evidence(command)))
            self.assertTrue(confirm_cancelled(db, **identity))
            self.assertFalse(confirm_cancelled(db, **identity))
            db.refresh(mission)
            self.assertEqual((mission.status, mission.active_slot), ("CANCELLED", None))

    def test_stale_stage_cannot_cancel_newer_command(self):
        with Session(self.engine) as db:
            pickup = self.identified_command(db)
            identity = self.identity(pickup)
            for old, new in (("REQUESTED", "ACCEPTED"), ("ACCEPTED", "ACKNOWLEDGED"),
                             ("ACKNOWLEDGED", "EXECUTING")):
                self.assertTrue(advance_command(db, **identity, expected_status=old, new_status=new))
            db.refresh(pickup)
            self.assertTrue(verify_arrival(db, **identity, evidence=self.evidence(pickup)))
            mission = db.get(AgvMission, pickup.mission_id)
            delivery = create_command(db, mission=mission, mission_stage="DELIVERY",
                                      source_station="PICKUP", target_station="RACK_A",
                                      route_id="delivery-route", route_steps=[{"source": "PICKUP", "destination": "RACK_A"}],
                                      target_marker="RACK-A-MARKER")
            self.assertFalse(request_cancel(db, **identity))
            db.refresh(mission)
            self.assertEqual((mission.status, delivery.status), ("ACTIVE", "REQUESTED"))

    def test_mock_adapter_full_mission_and_return_home(self):
        adapter, graph, transport = self.adapter()
        with patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}), Session(self.engine) as db:
            db.get(Task, self.task_ids[1]).dropoff_location_id = db.scalar(
                select(Location.id).where(Location.code == "HOME"))  # Invalid pending destination.
            task = db.get(Task, self.task_ids[0])
            adapter.start_pickup(db, task)
            self.assertEqual(task.status, "MOVING_TO_PICKUP")
            mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task.id))
            pickup = db.scalar(select(AgvMissionCommand).where(AgvMissionCommand.mission_id == mission.id))
            self.assertEqual(pickup.status, "ACCEPTED")
            self.assertTrue(adapter.acknowledge(db, **self.identity(pickup)))
            self.assertEqual(task.status, "MOVING_TO_PICKUP")
            self.assertTrue(adapter.executing(db, **self.identity(pickup)))
            self.assertIsNotNone(adapter.arrival(db, **self.identity(pickup), evidence=self.evidence(pickup)))
            self.assertEqual(task.status, "ARRIVED_AT_PICKUP")
            task.status = "PICKUP_CONFIRMED"  # Operator proof is exercised in task-route tests.
            adapter.start_delivery(db, task)
            delivery = db.scalar(select(AgvMissionCommand).where(
                AgvMissionCommand.mission_id == mission.id,
                AgvMissionCommand.mission_stage == "DELIVERY"))
            self.assertEqual(task.status, "TRANSPORTING")
            self.assertTrue(adapter.acknowledge(db, **self.identity(delivery)))
            self.assertTrue(adapter.executing(db, **self.identity(delivery)))
            self.assertIsNotNone(adapter.arrival(db, **self.identity(delivery), evidence=self.evidence(delivery)))
            self.assertEqual(task.status, "ARRIVED_AT_DELIVERY")
            task.status = "DELIVERY_CONFIRMED"
            adapter.complete_delivery(db, task)
            self.assertEqual(task.status, "COMPLETED")
            returning = db.scalar(select(AgvMissionCommand).where(
                AgvMissionCommand.mission_id == mission.id,
                AgvMissionCommand.mission_stage == "RETURN_HOME"))
            self.assertIsNotNone(returning)
            self.assertTrue(adapter.acknowledge(db, **self.identity(returning)))
            self.assertTrue(adapter.executing(db, **self.identity(returning)))
            self.assertIsNotNone(adapter.arrival(db, **self.identity(returning), evidence=self.evidence(returning)))
            db.refresh(mission)
            self.assertEqual((mission.status, mission.active_slot), ("COMPLETED", None))
            self.assertEqual(len(transport.sent), 3)

    def test_mock_adapter_pending_mission_returns_to_pickup(self):
        adapter, _, transport = self.adapter()
        with patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}), Session(self.engine) as db:
            task = db.get(Task, self.task_ids[0])
            adapter.start_pickup(db, task)
            mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task.id))
            pickup = db.scalar(select(AgvMissionCommand).where(AgvMissionCommand.mission_id == mission.id))
            adapter.acknowledge(db, **self.identity(pickup))
            adapter.executing(db, **self.identity(pickup))
            callback_result = adapter.arrival(db, **self.identity(pickup), evidence=self.evidence(pickup))
            callback_background = BackgroundTasks()
            self.assertTrue(task_routes.publish_agv_callback_updates(callback_background,
                                                                       callback_result, db))
            callback_types = [item.args[0] for item in callback_background.tasks]
            self.assertIn("TASK_UPDATED", callback_types)
            self.assertIn("EVENT_CREATED", callback_types)
            self.assertNotIn("NAVIGATION_STATUS_UPDATED", callback_types)
            task.status = "PICKUP_CONFIRMED"
            adapter.start_delivery(db, task)
            delivery = db.scalar(select(AgvMissionCommand).where(
                AgvMissionCommand.mission_id == mission.id,
                AgvMissionCommand.mission_stage == "DELIVERY"))
            adapter.acknowledge(db, **self.identity(delivery))
            adapter.executing(db, **self.identity(delivery))
            adapter.arrival(db, **self.identity(delivery), evidence=self.evidence(delivery))
            task.status = "DELIVERY_CONFIRMED"
            adapter.complete_delivery(db, task)
            returning = db.scalar(select(AgvMissionCommand).where(
                AgvMissionCommand.mission_id == mission.id,
                AgvMissionCommand.mission_stage == "RETURN_PICKUP"))
            self.assertIsNotNone(returning)
            adapter.acknowledge(db, **self.identity(returning))
            adapter.executing(db, **self.identity(returning))
            adapter.arrival(db, **self.identity(returning), evidence=self.evidence(returning))
            next_task = db.get(Task, self.task_ids[1])
            adapter.start_pickup(db, next_task)
            self.assertEqual(next_task.status, "ARRIVED_AT_PICKUP")
            next_mission = db.scalar(select(AgvMission).where(AgvMission.task_id == next_task.id))
            self.assertEqual(next_mission.handoff_command_id, returning.command_id)
            self.assertEqual(len(transport.sent), 3)  # No duplicate pickup movement.
            next_task.status = "PICKUP_CONFIRMED"
            adapter.start_delivery(db, next_task)
            self.assertEqual(next_task.status, "TRANSPORTING")

    def test_completed_task_can_cancel_uncertain_return_without_reversing_delivery(self):
        adapter, _, transport = self.adapter()
        with (patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}),
              patch.object(task_routes, "agv_mission_adapter", adapter),
              Session(self.engine) as db):
            task, _ = self.ready_delivery(db, adapter)
            task.status = "DELIVERY_CONFIRMED"
            adapter.complete_delivery(db, task)
            mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task.id))
            returning = db.scalar(select(AgvMissionCommand).where(
                AgvMissionCommand.mission_id == mission.id,
                AgvMissionCommand.mission_stage == "RETURN_PICKUP"))
            response = task_routes.request_cancel_task(task.id, BackgroundTasks(), db)
            self.assertEqual(response["status"], "COMPLETED")
            self.assertTrue(response["cancel_requested"])
            self.assertIn(returning.command_id, transport.stops)
            self.assertEqual(mission.status, "UNKNOWN")
            self.assertIsNone(adapter.stopped_after_cancel(db, **self.identity(returning),
                evidence=self.evidence(returning, stopped=False)))
            self.assertIsNotNone(adapter.stopped_after_cancel(db, **self.identity(returning),
                evidence=self.evidence(returning)))
            db.refresh(mission)
            self.assertEqual((mission.status, mission.active_slot), ("CANCELLED", None))
            self.assertEqual(task.status, "COMPLETED")

    def test_delivery_and_return_recheck_physical_source_before_state_change(self):
        adapter, _, transport = self.adapter()
        with patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}), Session(self.engine) as db:
            task = db.get(Task, self.task_ids[0])
            adapter.start_pickup(db, task)
            pickup = db.scalar(select(AgvMissionCommand).where(
                AgvMissionCommand.task_id == task.id,
                AgvMissionCommand.mission_stage == "PICKUP"))
            adapter.acknowledge(db, **self.identity(pickup))
            adapter.executing(db, **self.identity(pickup))
            adapter.arrival(db, **self.identity(pickup), evidence=self.evidence(pickup))
            task.status = "PICKUP_CONFIRMED"
            transport.source_verified = False
            with self.assertRaisesRegex(AgvMissionConflict, "starting station"):
                adapter.start_delivery(db, task)
            self.assertEqual(task.status, "PICKUP_CONFIRMED")
            transport.source_verified = True
            adapter.start_delivery(db, task)
            delivery = db.scalar(select(AgvMissionCommand).where(
                AgvMissionCommand.task_id == task.id,
                AgvMissionCommand.mission_stage == "DELIVERY"))
            adapter.acknowledge(db, **self.identity(delivery))
            adapter.executing(db, **self.identity(delivery))
            adapter.arrival(db, **self.identity(delivery), evidence=self.evidence(delivery))
            task.status = "DELIVERY_CONFIRMED"
            transport.source_verified = False
            with self.assertRaisesRegex(AgvMissionConflict, "starting station"):
                adapter.complete_delivery(db, task)
            self.assertEqual(task.status, "DELIVERY_CONFIRMED")

    def test_proof_response_remains_coherent_when_following_mock_send_is_uncertain(self):
        adapter, _, transport = self.adapter()
        with (patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}),
              patch.object(task_routes, "agv_mission_adapter", adapter),
              Session(self.engine) as db):
            task, _ = self.ready_delivery(db, adapter)
            transport.fail_send = True
            proof = task_routes.create_task_proof(task.id, TaskProofCreate(
                proof_type="DELIVERY", image_path="mock://delivered",
                verification_status="MANUAL_CONFIRMED", confirmed_by=self.operator_id),
                BackgroundTasks(), db)
            self.assertEqual(proof["verification_status"], "MANUAL_CONFIRMED")
            db.refresh(task)
            self.assertEqual(task.status, "COMPLETED")
            returning = db.scalar(select(AgvMissionCommand).where(
                AgvMissionCommand.task_id == task.id,
                AgvMissionCommand.mission_stage == "RETURN_PICKUP"))
            self.assertEqual(returning.status, "UNKNOWN")
            self.assertEqual(db.get(AgvMission, returning.mission_id).status, "UNKNOWN")

    def test_adapter_fails_closed_without_config_or_verified_source(self):
        adapter, graph, transport = self.adapter()
        with Session(self.engine) as db:
            task = db.get(Task, self.task_ids[0])
            with self.assertRaisesRegex(AgvMissionConflict, "disabled"):
                adapter.start_pickup(db, task)
            with patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}):
                with self.assertRaisesRegex(AgvMissionConflict, "disabled"):
                    AgvMissionAdapter().start_pickup(db, task)
                transport.source_verified = False
                with self.assertRaisesRegex(AgvMissionConflict, "starting station"):
                    adapter.start_pickup(db, task)
                transport.source_verified = True
                graph["edges"] = []
                with self.assertRaises(AgvMissionConflict):
                    adapter.start_pickup(db, task)
            self.assertEqual(db.query(AgvMission).count(), 0)

    def test_mock_transport_failure_quarantines_durable_command(self):
        adapter, _, transport = self.adapter()
        transport.fail_send = True
        with patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}), Session(self.engine) as db:
            task = db.get(Task, self.task_ids[0])
            _, events = adapter.start_pickup(db, task)
            command = db.scalar(select(AgvMissionCommand).where(AgvMissionCommand.task_id == task.id))
            self.assertEqual(command.status, "UNKNOWN")
            self.assertEqual(task.status, "MOVING_TO_PICKUP")
            self.assertIn("AGV_COMMAND_UNCERTAIN", [event.event_type for event in events])
            with self.assertRaises(AgvMissionConflict):
                adapter.start_pickup(db, task)

    def test_duplicate_dispatch_claim_does_not_resend_or_mutate_task(self):
        adapter, _, transport = self.adapter()
        with patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}), Session(self.engine) as db:
            task = db.get(Task, self.task_ids[0])
            adapter.start_pickup(db, task)
            command = db.scalar(select(AgvMissionCommand).where(AgvMissionCommand.task_id == task.id))
            self.assertEqual(adapter._send_mock(db, command), [])
            db.refresh(task)
            self.assertEqual((len(transport.sent), task.status, task.fail_reason),
                             (1, "MOVING_TO_PICKUP", None))

    def test_authenticated_mock_callback_reuses_task_ws_contract(self):
        adapter, _, _ = self.adapter()
        with (patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1",
                                     "WRMS_AGV_TOKEN": "test-device-token"}),
              patch.object(agv_routes, "agv_mission_adapter", adapter),
              Session(self.engine) as db):
            task = db.get(Task, self.task_ids[0])
            adapter.start_pickup(db, task)
            command = db.scalar(select(AgvMissionCommand).where(AgvMissionCommand.task_id == task.id))
            body = dict(self.identity(command), event="ACKNOWLEDGED")
            with self.assertRaises(HTTPException) as blocked:
                agv_routes.receive_mission_event("LINE-T1", agv_routes.MissionEvent(**body),
                    BackgroundTasks(), x_agv_token="wrong", db=db)
            self.assertEqual(blocked.exception.status_code, 401)
            with patch.object(agv_routes, "agv_mission_adapter", AgvMissionAdapter()):
                with self.assertRaises(HTTPException) as blocked:
                    agv_routes.receive_mission_event("LINE-T1", agv_routes.MissionEvent(**body),
                        BackgroundTasks(), x_agv_token="test-device-token", db=db)
                self.assertEqual(blocked.exception.status_code, 403)
            self.assertTrue(agv_routes.receive_mission_event("LINE-T1",
                agv_routes.MissionEvent(**body), BackgroundTasks(),
                x_agv_token="test-device-token", db=db)["accepted"])
            with self.assertRaises(HTTPException) as stale:
                agv_routes.receive_mission_event("LINE-T1", agv_routes.MissionEvent(**body),
                    BackgroundTasks(), x_agv_token="test-device-token", db=db)
            self.assertEqual(stale.exception.status_code, 409)
            agv_routes.receive_mission_event("LINE-T1",
                agv_routes.MissionEvent(**{**body, "event": "EXECUTING"}),
                BackgroundTasks(), x_agv_token="test-device-token", db=db)
            updates = BackgroundTasks()
            agv_routes.receive_mission_event("LINE-T1",
                agv_routes.MissionEvent(**{**body, "event": "ARRIVED",
                    "evidence": self.evidence(command)}), updates,
                x_agv_token="test-device-token", db=db)
            self.assertEqual(task.status, "ARRIVED_AT_PICKUP")
            self.assertEqual([item.args[0] for item in updates.tasks],
                             ["EVENT_CREATED", "TASK_UPDATED"])

    def test_task_routes_preserve_shape_and_use_mock_agv_not_nav2(self):
        adapter, _, transport = self.adapter()
        with (patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}),
              patch.object(task_routes, "agv_mission_adapter", adapter),
              Session(self.engine) as db):
            db.get(Task, self.task_ids[1]).status = "FAILED"
            task_id = self.task_ids[0]
            background = BackgroundTasks()
            response = task_routes.start_task(task_id, background, db)
            self.assertEqual(response["status"], "MOVING_TO_PICKUP")
            self.assertEqual(response["robot_code"], "LINE-T1")
            self.assertNotIn("NAVIGATION_STATUS_UPDATED", [item.args[0] for item in background.tasks])
            mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task_id))
            pickup = db.scalar(select(AgvMissionCommand).where(AgvMissionCommand.mission_id == mission.id))
            adapter.acknowledge(db, **self.identity(pickup))
            adapter.executing(db, **self.identity(pickup))
            adapter.arrival(db, **self.identity(pickup), evidence=self.evidence(pickup))
            proof = task_routes.create_task_proof(task_id, TaskProofCreate(
                proof_type="PICKUP", image_path="mock://pickup",
                verification_status="MANUAL_CONFIRMED", confirmed_by=self.operator_id),
                BackgroundTasks(), db)
            self.assertEqual(proof["verification_status"], "MANUAL_CONFIRMED")
            delivery = db.scalar(select(AgvMissionCommand).where(
                AgvMissionCommand.mission_id == mission.id,
                AgvMissionCommand.mission_stage == "DELIVERY"))
            self.assertEqual(db.get(Task, task_id).status, "TRANSPORTING")
            adapter.acknowledge(db, **self.identity(delivery))
            adapter.executing(db, **self.identity(delivery))
            adapter.arrival(db, **self.identity(delivery), evidence=self.evidence(delivery))
            proof = task_routes.create_task_proof(task_id, TaskProofCreate(
                proof_type="DELIVERY", image_path="mock://delivery",
                verification_status="MANUAL_CONFIRMED", confirmed_by=self.operator_id),
                BackgroundTasks(), db)
            self.assertEqual(proof["verification_status"], "MANUAL_CONFIRMED")
            self.assertEqual(db.get(Task, task_id).status, "COMPLETED")
            self.assertEqual(len(transport.sent), 3)

    def test_manual_status_generic_ack_and_auto_proof_cannot_bypass_line_evidence(self):
        adapter, _, _ = self.adapter()
        with patch.object(task_routes, "agv_mission_adapter", adapter), Session(self.engine) as db:
            task = db.get(Task, self.task_ids[0])
            with self.assertRaises(HTTPException) as blocked:
                task_routes.update_task_status(task.id, TaskStatusUpdate(status="MOVING_TO_PICKUP"),
                                               BackgroundTasks(), db)
            self.assertEqual(blocked.exception.status_code, 409)
            with self.assertRaises(HTTPException) as blocked:
                task_routes.create_task_proof(task.id, TaskProofCreate(
                    proof_type="PICKUP", image_path="mock://pickup",
                    verification_status="AUTO_VERIFIED"), BackgroundTasks(), db)
            self.assertEqual(blocked.exception.status_code, 409)
            with self.assertRaises(HTTPException) as blocked:
                command_routes.create_robot_command(self.robot_id,
                    RobotCommandCreate(command="CANCEL", task_id=task.id), BackgroundTasks(), db)
            self.assertEqual(blocked.exception.status_code, 409)
            legacy = RobotCommand(robot_id=self.robot_id, task_id=task.id,
                                  command="CANCEL", status="PENDING")
            db.add(legacy)
            db.commit()
            command_routes.acknowledge_robot_command(self.robot_id, legacy.id,
                RobotCommandAck(status="ACKNOWLEDGED"), BackgroundTasks(), db)
            db.refresh(task)
            self.assertEqual(task.status, "WAITING")

    def test_task_cancel_requests_mock_stop_but_waits_for_verified_stopped(self):
        adapter, _, transport = self.adapter()
        with (patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}),
              patch.object(task_routes, "agv_mission_adapter", adapter),
              Session(self.engine) as db):
            task = db.get(Task, self.task_ids[0])
            task_routes.start_task(task.id, BackgroundTasks(), db)
            mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task.id))
            command = db.scalar(select(AgvMissionCommand).where(AgvMissionCommand.mission_id == mission.id))
            response = task_routes.request_cancel_task(task.id, BackgroundTasks(), db)
            self.assertEqual(response["status"], "MOVING_TO_PICKUP")
            self.assertTrue(response["cancel_requested"])
            self.assertEqual(transport.stops, [command.command_id])
            self.assertIsNone(adapter.stopped_after_cancel(db, **self.identity(command),
                evidence=self.evidence(command, stopped=False)))
            self.assertEqual(task.status, "MOVING_TO_PICKUP")
            self.assertIsNotNone(adapter.stopped_after_cancel(db, **self.identity(command),
                evidence=self.evidence(command)))
            self.assertEqual(task.status, "CANCELLED")

    def test_camera_absent_evidence_is_durable_but_not_automatic_proof(self):
        adapter, _, _ = self.adapter()
        analyzer = MockAnalyzer("ABSENT")
        verifier = AgvCargoVerifier(analyzer=analyzer)
        with patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}), Session(self.engine) as db:
            task, command = self.ready_delivery(db, adapter)
            observed = datetime.now(timezone.utc)
            args = dict(capture_id="cap-1", task_id=task.id, robot_id=task.robot_id,
                        command_id=command.command_id, station="RACK_A",
                        image_ref="mock://cargo-1", observed_at=observed)
            evidence = verifier.submit(db, **args)
            self.assertEqual((evidence.presence, evidence.review_status), ("ABSENT", "MANUAL_REVIEW"))
            self.assertEqual(task.status, "ARRIVED_AT_DELIVERY")
            self.assertEqual(verifier.submit(db, **args).capture_id, evidence.capture_id)
            self.assertEqual(analyzer.calls, 1)
            with self.assertRaises(CargoEvidenceError):
                verifier.submit(db, **{**args, "image_ref": "mock://other"})
            db.commit()
        with Session(self.engine) as db:
            self.assertEqual(db.get(AgvCargoEvidence, "cap-1").presence, "ABSENT")
            self.assertFalse(AgvCargoVerifier().automatic_proof_enabled())
            with patch.dict("os.environ", {"WRMS_AGV_CAMERA_AUTO_CONFIRM_ENABLED": "1"}):
                self.assertFalse(AgvCargoVerifier().automatic_proof_enabled())

    def test_camera_present_blocks_delivery_proof_until_new_review(self):
        adapter, _, _ = self.adapter()
        analyzer = MockAnalyzer("PRESENT")
        verifier = AgvCargoVerifier(analyzer=analyzer)
        with (patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}),
              patch.object(task_routes, "agv_mission_adapter", adapter),
              Session(self.engine) as db):
            task, command = self.ready_delivery(db, adapter)
            args = dict(task_id=task.id, robot_id=task.robot_id,
                        command_id=command.command_id, station="RACK_A",
                        image_ref="mock://cargo", observed_at=datetime.now(timezone.utc))
            verifier.submit(db, capture_id="present", **args)
            db.commit()
            with self.assertRaises(HTTPException) as blocked:
                task_routes.create_task_proof(task.id, TaskProofCreate(
                    proof_type="DELIVERY", image_path="mock://proof",
                    verification_status="MANUAL_CONFIRMED", confirmed_by=self.operator_id),
                    BackgroundTasks(), db)
            self.assertEqual(blocked.exception.status_code, 409)
            self.assertEqual(task.status, "ARRIVED_AT_DELIVERY")
            analyzer.presence = "UNCERTAIN"
            verifier.submit(db, capture_id="uncertain", **{**args,
                "image_ref": "mock://new", "observed_at": datetime.now(timezone.utc)})
            db.commit()
            self.assertEqual(db.get(AgvCargoEvidence, "uncertain").review_status, "MANUAL_REVIEW")
            proof = task_routes.create_task_proof(task.id, TaskProofCreate(
                proof_type="DELIVERY", image_path="mock://manual-review",
                verification_status="MANUAL_CONFIRMED", confirmed_by=self.operator_id),
                BackgroundTasks(), db)
            self.assertEqual(proof["verification_status"], "MANUAL_CONFIRMED")

    def test_camera_rejects_wrong_owner_station_stale_capture_and_missing_analyzer(self):
        adapter, _, _ = self.adapter()
        with patch.dict("os.environ", {"WRMS_AGV_AUTO_DISPATCH_ENABLED": "1"}), Session(self.engine) as db:
            task, command = self.ready_delivery(db, adapter)
            args = dict(capture_id="bad", task_id=task.id, robot_id=task.robot_id,
                        command_id=command.command_id, station="RACK_A",
                        image_ref="mock://cargo", observed_at=datetime.now(timezone.utc))
            verifier = AgvCargoVerifier(analyzer=MockAnalyzer("ABSENT"))
            for bad in ({"robot_id": self.other_robot_id}, {"station": "RACK_B"},
                        {"command_id": "missing"},
                        {"observed_at": datetime(2000, 1, 1, tzinfo=timezone.utc)}):
                with self.assertRaises(CargoEvidenceError):
                    verifier.submit(db, **{**args, **bad})
            with self.assertRaisesRegex(CargoEvidenceError, "not configured"):
                AgvCargoVerifier().submit(db, **args)
            self.assertEqual(db.query(AgvCargoEvidence).count(), 0)


if __name__ == "__main__":
    unittest.main()
