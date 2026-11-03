"""Mock-injectable LINE task adapter. Production has no graph or transport."""

from datetime import datetime
from hashlib import sha256
import json
import os

from sqlalchemy import or_, select, update

from app.models.agv_mission import AgvMission, AgvMissionCommand
from app.models.location import Location
from app.models.robot import Robot
from app.models.saved_map import SavedMap
from app.models.task import Task
from app.models.agv_vision import AgvVisionJob
from app.services.agv_mission_store import (
    AgvMissionConflict, advance_command, claim_dispatch, claim_mission, create_command,
    confirm_cancelled, mark_uncertain, request_cancel, verify_arrival, verify_stopped,
)
from app.services.agv_station_graph import StationGraphError, plan_station_route
from app.services.event_logger import add_event


RACKS = frozenset({"RACK_A", "RACK_B", "RACK_C", "RACK_D"})
PROGRESS = {"MOVING_TO_PICKUP": 15, "ARRIVED_AT_PICKUP": 30,
            "TRANSPORTING": 60, "ARRIVED_AT_DELIVERY": 75,
            "COMPLETED": 100}


class AgvMissionAdapter:
    def __init__(self, graph_provider=None, transport=None):
        self.graph_provider = graph_provider
        self.transport = transport

    def _enabled(self):
        # shortcut: no production graph/transport provider exists; add a verified provider before hardware use.
        if (os.getenv("WRMS_AGV_AUTO_DISPATCH_ENABLED") != "1"
                or self.graph_provider is None or self.transport is None):
            raise AgvMissionConflict("AGV automatic dispatch is disabled or unconfigured")
        if not all(callable(getattr(self.transport, name, None)) for name in
                   ("send", "stop", "current_station")):
            raise AgvMissionConflict("AGV transport does not support verified station and stop contracts")

    def _verified_source(self, robot_id, station):
        evidence = self.transport.current_station(robot_id)
        if (not isinstance(evidence, dict) or evidence.get("robot_id") != robot_id
                or evidence.get("station") != station
                or evidence.get("physical_marker_verified") is not True
                or evidence.get("stopped") is not True):
            raise AgvMissionConflict("AGV starting station is not verified")

    @staticmethod
    def _owner(db, task):
        robot = db.get(Robot, task.robot_id) if task.robot_id is not None else None
        if robot is None or robot.robot_type != "LINE" or not robot.is_active:
            raise AgvMissionConflict("Task has no active LINE robot owner")
        return robot

    def _context(self, db, task, *, require_rack=True):
        self._enabled()
        robot = self._owner(db, task)
        maps = db.scalars(select(SavedMap).where(SavedMap.is_selected.is_(True)).limit(2)).all()
        if len(maps) != 1:
            raise AgvMissionConflict("Exactly one active map is required")
        saved_map = maps[0]
        pickup = db.get(Location, task.pickup_location_id)
        dropoff = db.get(Location, task.dropoff_location_id) if task.dropoff_location_id is not None else None
        home = db.scalar(select(Location).where(Location.code == "HOME"))
        vision_job = db.get(AgvVisionJob, task.id)
        if (pickup is None or pickup.code != "PICKUP" or pickup.location_type != "PICKUP"
                or home is None or home.location_type != "HOME"
                or not pickup.is_active or not home.is_active
                or (vision_job is not None and (vision_job.robot_id != robot.id
                    or vision_job.map_id != saved_map.id))):
            raise AgvMissionConflict("Task stations are not verified HOME/PICKUP/RACK destinations")
        unassigned = vision_job is not None and vision_job.status != "ASSIGNED"
        if unassigned and task.dropoff_location_id is not None:
            raise AgvMissionConflict("Unassigned vision task has an invalid destination")
        if vision_job is not None and vision_job.status == "ASSIGNED":
            if vision_job.assigned_rack_id != task.dropoff_location_id:
                raise AgvMissionConflict("Vision rack assignment does not match Task")
        if not unassigned and (dropoff is None or dropoff.code not in RACKS
                or dropoff.location_type != "RACK" or not dropoff.is_active):
            raise AgvMissionConflict("Task stations are not verified HOME/PICKUP/RACK destinations")
        if require_rack and unassigned:
            raise AgvMissionConflict("AGV destination rack is not assigned")
        graph = self.graph_provider(saved_map.id, robot.id)
        if not isinstance(graph, dict) or not isinstance(graph.get("version"), str) or not graph["version"]:
            raise AgvMissionConflict("A versioned station graph is required")
        return robot, saved_map, graph, None if unassigned else dropoff.code

    @staticmethod
    def _route(graph, map_id, robot_id, source, target):
        try:
            steps = plan_station_route(graph, map_id=map_id, robot_id=robot_id,
                                       source=source, destination=target)
        except StationGraphError as error:
            raise AgvMissionConflict(str(error)) from error
        marker = steps[-1].get("verification_marker") if steps else None
        if not marker:
            raise AgvMissionConflict("Destination has no verified physical marker contract")
        route_id = sha256(json.dumps([graph["version"], steps], sort_keys=True).encode()).hexdigest()
        return route_id, steps, marker

    @staticmethod
    def _status_event(db, task, old_status):
        return add_event(db=db, event_type="TASK_STATUS_CHANGED", source="AGV_MISSION",
                         message=f"Task {task.task_code} changed from {old_status} to {task.status}.",
                         robot_id=task.robot_id, task_id=task.id,
                         metadata={"from_status": old_status, "to_status": task.status})

    def _send_mock(self, db, command):
        # The only transport is test-injected. A durable claim commits before any send.
        claimed = claim_dispatch(db, command_id=command.command_id,
                                 task_id=command.task_id, robot_id=command.robot_id,
                                 command_sequence=command.command_sequence)
        db.commit()
        if not claimed:
            # An earlier caller owns delivery; do not resend or rewrite Task state.
            return []
        try:
            self.transport.send(command)
        except Exception:
            mark_uncertain(db, command_id=command.command_id, task_id=command.task_id,
                           robot_id=command.robot_id, command_sequence=command.command_sequence,
                           reason="MOCK_TRANSPORT_FAILURE")
            db.commit()
            return self._uncertain_event(db, command)
        accepted = advance_command(db, command_id=command.command_id, task_id=command.task_id,
                                   robot_id=command.robot_id, command_sequence=command.command_sequence,
                                   expected_status="REQUESTED", new_status="ACCEPTED")
        db.commit()
        if not accepted:
            return self._uncertain_event(db, command)
        return []

    @staticmethod
    def _uncertain_event(db, command):
        task = db.get(Task, command.task_id)
        if task.status != "COMPLETED":
            task.fail_reason = "AGV command outcome requires reconciliation"
        event = add_event(db=db, event_type="AGV_COMMAND_UNCERTAIN", source="AGV_MISSION",
                          message=f"AGV command {command.command_id} requires reconciliation.",
                          robot_id=command.robot_id, task_id=command.task_id,
                          metadata={"command_id": command.command_id})
        db.commit()
        db.refresh(event)
        return [event]

    def start_pickup(self, db, task):
        if task.status != "WAITING":
            raise AgvMissionConflict("Task is not waiting")
        robot, saved_map, graph, _ = self._context(db, task, require_rack=False)
        prior_return = db.scalar(select(AgvMissionCommand).join(
            AgvMission, AgvMission.id == AgvMissionCommand.mission_id).where(
            AgvMissionCommand.robot_id == robot.id,
            AgvMissionCommand.mission_stage.in_(("RETURN_PICKUP", "RETURN_HOME")),
            AgvMission.status == "COMPLETED").order_by(
            AgvMissionCommand.command_sequence.desc()).limit(1))
        if prior_return and prior_return.target_station == "PICKUP":
            if (prior_return.status != "ARRIVED" or not prior_return.arrival_evidence
                    or prior_return.map_id != saved_map.id
                    or prior_return.graph_version != graph["version"]):
                raise AgvMissionConflict("Previous PICKUP handoff is not verified")
            self._verified_source(robot.id, "PICKUP")
            mission = claim_mission(db, task_id=task.id, robot_id=robot.id,
                                    map_id=saved_map.id, graph_version=graph["version"],
                                    handoff_command_id=prior_return.command_id)
            old_status = task.status
            task.status = "ARRIVED_AT_PICKUP"
            task.progress = PROGRESS[task.status]
            task.started_at = datetime.utcnow()
            event = self._status_event(db, task, old_status)
            db.commit()
            db.refresh(event)
            return None, [event]
        self._verified_source(robot.id, "HOME")
        route_id, steps, marker = self._route(graph, saved_map.id, robot.id, "HOME", "PICKUP")
        mission = claim_mission(db, task_id=task.id, robot_id=robot.id,
                                map_id=saved_map.id, graph_version=graph["version"])
        command = create_command(db, mission=mission, mission_stage="PICKUP",
                                 source_station="HOME", target_station="PICKUP",
                                 route_id=route_id, route_steps=steps, target_marker=marker)
        old_status = task.status
        task.status = "MOVING_TO_PICKUP"
        task.progress = PROGRESS[task.status]
        task.started_at = datetime.utcnow()
        event = self._status_event(db, task, old_status)
        db.commit()
        db.refresh(event)
        return None, [event, *self._send_mock(db, command)]

    def start_delivery(self, db, task):
        if task.status != "PICKUP_CONFIRMED":
            raise AgvMissionConflict("Pickup proof is not confirmed")
        robot, saved_map, graph, rack = self._context(db, task)
        mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task.id))
        if (mission is None or mission.status != "ACTIVE" or mission.robot_id != robot.id
                or mission.map_id != saved_map.id or mission.graph_version != graph["version"]):
            raise AgvMissionConflict("AGV mission ownership or graph changed")
        pickup = db.scalar(select(AgvMissionCommand).where(
            AgvMissionCommand.mission_id == mission.id,
            AgvMissionCommand.mission_stage == "PICKUP"))
        handoff = db.get(AgvMissionCommand, mission.handoff_command_id) if mission.handoff_command_id else None
        if not ((pickup is not None and pickup.status == "ARRIVED")
                or (pickup is None and handoff is not None and handoff.status == "ARRIVED"
                    and handoff.robot_id == robot.id and handoff.target_station == "PICKUP"
                    and handoff.arrival_evidence and handoff.map_id == saved_map.id
                    and handoff.graph_version == graph["version"])):
            raise AgvMissionConflict("Pickup arrival is not verified")
        self._verified_source(robot.id, "PICKUP")
        route_id, steps, marker = self._route(graph, saved_map.id, robot.id, "PICKUP", rack)
        command = create_command(db, mission=mission, mission_stage="DELIVERY",
                                 source_station="PICKUP", target_station=rack,
                                 route_id=route_id, route_steps=steps, target_marker=marker)
        old_status = task.status
        task.status = "TRANSPORTING"
        task.progress = PROGRESS[task.status]
        event = self._status_event(db, task, old_status)
        db.commit()
        db.refresh(event)
        return None, [event, *self._send_mock(db, command)]

    def complete_delivery(self, db, task):
        if task.status != "DELIVERY_CONFIRMED":
            raise AgvMissionConflict("Delivery proof is not confirmed")
        robot, saved_map, graph, rack = self._context(db, task)
        mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task.id))
        delivery = db.scalar(select(AgvMissionCommand).where(
            AgvMissionCommand.mission_id == mission.id,
            AgvMissionCommand.mission_stage == "DELIVERY")) if mission else None
        if (mission is None or mission.status != "ACTIVE" or mission.robot_id != robot.id
                or mission.map_id != saved_map.id or mission.graph_version != graph["version"]
                or delivery is None or delivery.status != "ARRIVED"):
            raise AgvMissionConflict("Delivery arrival is not verified")
        self._verified_source(robot.id, rack)
        pending = db.scalar(select(Task.id).outerjoin(
            AgvVisionJob, AgvVisionJob.task_id == Task.id).where(
            Task.robot_id == robot.id, Task.id != task.id, Task.status == "WAITING",
            Task.pickup_location_id.in_(select(Location.id).where(
                Location.code == "PICKUP", Location.location_type == "PICKUP",
                Location.is_active.is_(True))),
            or_(Task.dropoff_location_id.in_(select(Location.id).where(
                Location.code.in_(RACKS), Location.location_type == "RACK",
                Location.is_active.is_(True))),
                (AgvVisionJob.map_id == saved_map.id) &
                (AgvVisionJob.status.in_(("PENDING", "REVIEW"))) &
                Task.dropoff_location_id.is_(None))).limit(1))
        target = "PICKUP" if pending is not None else "HOME"
        stage = "RETURN_PICKUP" if pending is not None else "RETURN_HOME"
        route_id, steps, marker = self._route(graph, saved_map.id, robot.id, rack, target)
        command = create_command(db, mission=mission, mission_stage=stage,
                                 source_station=rack, target_station=target,
                                 route_id=route_id, route_steps=steps, target_marker=marker)
        old_status = task.status
        task.status = "COMPLETED"
        task.progress = 100
        task.completed_at = datetime.utcnow()
        event = self._status_event(db, task, old_status)
        completed = add_event(db=db, event_type="TASK_COMPLETED", source="AGV_MISSION",
                              message=f"Task {task.task_code} completed.",
                              robot_id=robot.id, task_id=task.id)
        db.commit()
        db.refresh(event)
        db.refresh(completed)
        return None, [event, completed, *self._send_mock(db, command)]

    def arrival(self, db, *, command_id, task_id, robot_id, command_sequence, evidence):
        if not verify_arrival(db, command_id=command_id, task_id=task_id,
                              robot_id=robot_id, command_sequence=command_sequence,
                              evidence=evidence):
            return None
        command = db.get(AgvMissionCommand, command_id)
        task = db.get(Task, task_id)
        expected = {"PICKUP": ("MOVING_TO_PICKUP", "ARRIVED_AT_PICKUP"),
                    "DELIVERY": ("TRANSPORTING", "ARRIVED_AT_DELIVERY")}.get(command.mission_stage)
        events = []
        if expected:
            if task is None or task.robot_id != robot_id or task.status != expected[0]:
                db.rollback()
                return None
            old_status = task.status
            task.status = expected[1]
            task.progress = PROGRESS[task.status]
            events.append(self._status_event(db, task, old_status))
        elif command.mission_stage in {"RETURN_PICKUP", "RETURN_HOME"}:
            mission = db.get(AgvMission, command.mission_id)
            if mission.status != "ACTIVE" or task.status != "COMPLETED":
                db.rollback()
                return None
            db.execute(update(AgvMission).where(AgvMission.id == mission.id,
                AgvMission.status == "ACTIVE", AgvMission.active_slot == 1).values(
                    status="COMPLETED", active_slot=None, completed_at=datetime.utcnow()))
        else:
            db.rollback()
            return None
        db.commit()
        for event in events:
            db.refresh(event)
        return task, events

    @staticmethod
    def acknowledge(db, *, command_id, task_id, robot_id, command_sequence):
        changed = advance_command(db, command_id=command_id, task_id=task_id,
                                  robot_id=robot_id, command_sequence=command_sequence,
                                  expected_status="ACCEPTED", new_status="ACKNOWLEDGED")
        if changed:
            db.commit()
        return changed

    @staticmethod
    def executing(db, *, command_id, task_id, robot_id, command_sequence):
        changed = advance_command(db, command_id=command_id, task_id=task_id,
                                  robot_id=robot_id, command_sequence=command_sequence,
                                  expected_status="ACKNOWLEDGED", new_status="EXECUTING")
        if changed:
            db.commit()
        return changed

    def cancel(self, db, task):
        mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task.id))
        if mission is None or mission.robot_id != task.robot_id or mission.active_slot != 1:
            raise AgvMissionConflict("No active AGV mission to cancel")
        command = db.scalar(select(AgvMissionCommand).where(
            AgvMissionCommand.mission_id == mission.id).order_by(
            AgvMissionCommand.command_sequence.desc()).limit(1))
        if task.status == "COMPLETED" and (command is None or command.mission_stage not in {
                "RETURN_PICKUP", "RETURN_HOME"}):
            raise AgvMissionConflict("Only an active return can be cancelled after delivery")
        if command is None or not request_cancel(db, command_id=command.command_id,
            task_id=task.id, robot_id=task.robot_id, command_sequence=command.command_sequence):
            raise AgvMissionConflict("AGV cancellation is already pending or command is stale")
        task.cancel_requested = True
        db.commit()
        try:
            self.transport.stop(command)
        except Exception:
            # shortcut: no authenticated hardware stop protocol exists; keep motion UNKNOWN.
            pass
        return None, []

    @staticmethod
    def stopped_after_cancel(db, *, command_id, task_id, robot_id, command_sequence, evidence):
        command = db.get(AgvMissionCommand, command_id)
        if not verify_stopped(db, command_id=command_id, task_id=task_id,
                              robot_id=robot_id, command_sequence=command_sequence,
                              evidence=evidence):
            return None
        if not confirm_cancelled(db, command_id=command_id, task_id=task_id,
                                 robot_id=robot_id, command_sequence=command_sequence):
            db.rollback()
            return None
        task = db.get(Task, task_id)
        if (task is None or task.robot_id != robot_id
                or (task.status == "COMPLETED" and command.mission_stage not in {
                    "RETURN_PICKUP", "RETURN_HOME"})):
            db.rollback()
            return None
        events = []
        if task.status != "COMPLETED":
            old_status = task.status
            task.status = "CANCELLED"
            events.append(AgvMissionAdapter._status_event(db, task, old_status))
        task.cancel_requested = False
        db.commit()
        for event in events:
            db.refresh(event)
        return task, events


agv_mission_adapter = AgvMissionAdapter()
