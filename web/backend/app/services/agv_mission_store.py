"""Database ownership for AGV mission intents; this module never sends commands."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.agv_mission import AgvMission, AgvMissionCommand
from app.models.robot import Robot
from app.models.saved_map import SavedMap
from app.models.task import Task
from app.services.agv_station_graph import REQUIRED_STATIONS


class AgvMissionConflict(ValueError):
    pass


PENDING = ("REQUESTED", "ACCEPTED", "ACKNOWLEDGED", "EXECUTING", "UNKNOWN")
STAGES = frozenset({"PICKUP", "DELIVERY", "RETURN_PICKUP", "RETURN_HOME"})


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)
SAFE_TRANSITIONS = {
    "REQUESTED": frozenset({"ACCEPTED", "UNKNOWN"}),
    "ACCEPTED": frozenset({"ACKNOWLEDGED", "UNKNOWN"}),
    "ACKNOWLEDGED": frozenset({"EXECUTING", "UNKNOWN"}),
    "EXECUTING": frozenset({"UNKNOWN"}),
}


def claim_mission(db, *, task_id, robot_id, map_id, graph_version,
                  handoff_command_id=None):
    """Claim one active task per robot; caller commits the transaction."""
    task, robot, saved_map = db.get(Task, task_id), db.get(Robot, robot_id), db.get(SavedMap, map_id)
    if (task is None or robot is None or task.robot_id != robot.id
            or robot.robot_type != "LINE" or not robot.is_active):
        raise AgvMissionConflict("Invalid LINE task ownership")
    if saved_map is None or not saved_map.is_selected or not graph_version:
        raise AgvMissionConflict("An active map and graph version are required")
    existing = db.scalar(select(AgvMission).where(AgvMission.task_id == task_id))
    if existing:
        if (existing.robot_id, existing.map_id, existing.graph_version,
                existing.handoff_command_id) != (robot_id, map_id, graph_version, handoff_command_id):
            raise AgvMissionConflict("Task already belongs to a different AGV mission")
        return existing
    mission = AgvMission(task_id=task_id, robot_id=robot_id, map_id=map_id,
                         graph_version=graph_version, handoff_command_id=handoff_command_id,
                         status="ACTIVE", active_slot=1)
    try:
        db.add(mission)
        db.flush()
    except (IntegrityError, OperationalError) as error:
        db.rollback()
        existing = db.scalar(select(AgvMission).where(AgvMission.task_id == task_id))
        if existing and (existing.robot_id, existing.map_id, existing.graph_version,
                         existing.handoff_command_id) == (robot_id, map_id, graph_version, handoff_command_id):
            return existing
        raise AgvMissionConflict("Robot already owns an active mission or claim is busy") from error
    return mission


def create_command(db, *, mission, mission_stage, source_station, target_station,
                   route_id, route_steps, target_marker=None):
    """Store one immutable stage intent; never publish it to the AGV mailbox."""
    if (mission.status != "ACTIVE" or mission.active_slot != 1 or mission.cancel_requested_at
            or mission_stage not in STAGES or source_station not in REQUIRED_STATIONS
            or target_station not in REQUIRED_STATIONS or source_station == target_station
            or not route_id or not isinstance(route_steps, list) or not route_steps):
        raise AgvMissionConflict("Invalid AGV command intent")
    existing = db.scalar(select(AgvMissionCommand).where(
        AgvMissionCommand.mission_id == mission.id,
        AgvMissionCommand.mission_stage == mission_stage))
    if existing:
        if (existing.source_station, existing.target_station, existing.route_id, existing.route_steps,
                existing.target_marker) != (source_station, target_station, route_id, route_steps, target_marker):
            raise AgvMissionConflict("Stage command already exists with a different route")
        return existing
    outstanding = db.scalar(select(AgvMissionCommand.command_id).where(
        AgvMissionCommand.mission_id == mission.id,
        AgvMissionCommand.status.in_(PENDING)).limit(1))
    if outstanding:
        raise AgvMissionConflict("Previous AGV command is unresolved")
    sequence = (db.scalar(select(func.max(AgvMissionCommand.command_sequence)).where(
        AgvMissionCommand.robot_id == mission.robot_id)) or 0) + 1
    command = AgvMissionCommand(
        command_id=str(uuid4()), mission_id=mission.id, task_id=mission.task_id,
        robot_id=mission.robot_id, map_id=mission.map_id,
        graph_version=mission.graph_version, mission_stage=mission_stage,
        source_station=source_station, target_station=target_station,
        route_id=route_id, route_steps=route_steps, target_marker=target_marker,
        command_sequence=sequence,
        status="REQUESTED")
    try:
        db.add(command)
        db.flush()
    except (IntegrityError, OperationalError) as error:
        db.rollback()
        existing = db.scalar(select(AgvMissionCommand).where(
            AgvMissionCommand.mission_id == mission.id,
            AgvMissionCommand.mission_stage == mission_stage))
        if existing and (existing.source_station, existing.target_station, existing.route_id, existing.route_steps,
                         existing.target_marker) == (source_station, target_station, route_id, route_steps, target_marker):
            return existing
        raise AgvMissionConflict("Concurrent AGV command creation rejected") from error
    return command


def claim_dispatch(db, *, command_id, task_id, robot_id, command_sequence):
    """Atomically claim one delivery attempt; commit before calling any transport."""
    result = db.execute(update(AgvMissionCommand).where(
        AgvMissionCommand.command_id == command_id,
        AgvMissionCommand.task_id == task_id,
        AgvMissionCommand.robot_id == robot_id,
        AgvMissionCommand.command_sequence == command_sequence,
        AgvMissionCommand.status == "REQUESTED",
        AgvMissionCommand.dispatch_claimed_at.is_(None),
        AgvMissionCommand.mission_id.in_(select(AgvMission.id).where(
            AgvMission.status == "ACTIVE", AgvMission.cancel_requested_at.is_(None)))).values(
                dispatch_claimed_at=_now()))
    return result.rowcount == 1


def advance_command(db, *, command_id, task_id, robot_id, command_sequence,
                    expected_status, new_status):
    """Atomically accept a correlated event; arrival/stop require separate evidence."""
    if new_status not in SAFE_TRANSITIONS.get(expected_status, ()):
        raise AgvMissionConflict("Unsupported AGV command transition")
    values = {"status": new_status}
    if new_status == "ACKNOWLEDGED":
        values["acknowledged_at"] = _now()
    if new_status == "EXECUTING":
        values["execution_started_at"] = _now()
    if new_status == "UNKNOWN":
        values["failure_details"] = "Execution outcome requires reconciliation"
    result = db.execute(update(AgvMissionCommand).where(
        AgvMissionCommand.command_id == command_id,
        AgvMissionCommand.task_id == task_id,
        AgvMissionCommand.robot_id == robot_id,
        AgvMissionCommand.command_sequence == command_sequence,
        AgvMissionCommand.status == expected_status,
        AgvMissionCommand.mission_id.in_(select(AgvMission.id).where(
            AgvMission.status == "ACTIVE", AgvMission.cancel_requested_at.is_(None)))).values(**values))
    if result.rowcount and new_status == "UNKNOWN":
        db.execute(update(AgvMission).where(
            AgvMission.id == select(AgvMissionCommand.mission_id).where(
                AgvMissionCommand.command_id == command_id).scalar_subquery(),
            AgvMission.active_slot == 1).values(status="UNKNOWN"))
    return result.rowcount == 1


def _verified_evidence(command, evidence, *, arrival):
    if not isinstance(evidence, dict):
        return False
    if any(evidence.get(key) != value for key, value in (
            ("command_id", command.command_id), ("task_id", command.task_id),
            ("robot_id", command.robot_id), ("command_sequence", command.command_sequence))):
        return False
    if evidence.get("stopped") is not True:
        return False
    if arrival:
        if (not command.target_marker
                or evidence.get("target_station") != command.target_station
                or evidence.get("current_station") != command.target_station
                or evidence.get("marker") != command.target_marker
                or evidence.get("physical_marker_verified") is not True):
            return False
    elif evidence.get("stopped_verified") is not True:
        return False
    try:
        observed = datetime.fromisoformat(evidence["timestamp"])
    except (KeyError, TypeError, ValueError):
        return False
    if observed.tzinfo:
        observed = observed.astimezone(timezone.utc).replace(tzinfo=None)
    lower = command.execution_started_at if arrival else command.cancel_requested_at
    return bool(lower and observed >= lower and observed <= _now())


def mark_uncertain(db, *, command_id, task_id, robot_id, command_sequence, reason):
    """Hold the robot claim after timeout/disconnect; no retry is implied."""
    if not reason:
        raise AgvMissionConflict("Uncertain execution needs a reason")
    result = db.execute(update(AgvMissionCommand).where(
        AgvMissionCommand.command_id == command_id,
        AgvMissionCommand.task_id == task_id,
        AgvMissionCommand.robot_id == robot_id,
        AgvMissionCommand.command_sequence == command_sequence,
        AgvMissionCommand.status.in_(PENDING[:-1])).values(
            status="UNKNOWN", failure_details=reason))
    if result.rowcount:
        db.execute(update(AgvMission).where(
            AgvMission.id == select(AgvMissionCommand.mission_id).where(
                AgvMissionCommand.command_id == command_id).scalar_subquery(),
            AgvMission.active_slot == 1).values(status="UNKNOWN"))
    return result.rowcount == 1


def expire_command(db, *, command_id, task_id, robot_id, command_sequence,
                   now, ack_timeout, execution_timeout):
    """Quarantine an overdue command; caller supplies measured deadlines."""
    command = db.get(AgvMissionCommand, command_id)
    if (command is None or (command.task_id, command.robot_id, command.command_sequence)
            != (task_id, robot_id, command_sequence)):
        return False
    if command.status in {"REQUESTED", "ACCEPTED"}:
        deadline = command.created_at
        limit = ack_timeout
        reason = "ACK_TIMEOUT"
    elif command.status in {"ACKNOWLEDGED", "EXECUTING"}:
        deadline = command.execution_started_at or command.acknowledged_at
        limit = execution_timeout
        reason = "EXECUTION_TIMEOUT"
    else:
        return False
    if limit <= 0 or deadline is None or (now - deadline).total_seconds() < limit:
        return False
    return mark_uncertain(db, command_id=command_id, task_id=task_id,
                          robot_id=robot_id, command_sequence=command_sequence,
                          reason=reason)


def verify_arrival(db, *, command_id, task_id, robot_id, command_sequence, evidence):
    """Only a marker-verified, stopped, correlated event can mark ARRIVED."""
    command = db.get(AgvMissionCommand, command_id)
    if (command is None or command.status != "EXECUTING"
            or (command.task_id, command.robot_id, command.command_sequence)
            != (task_id, robot_id, command_sequence)
            or not _verified_evidence(command, evidence, arrival=True)):
        return False
    result = db.execute(update(AgvMissionCommand).where(
        AgvMissionCommand.command_id == command_id,
        AgvMissionCommand.status == "EXECUTING",
        AgvMissionCommand.mission_id.in_(select(AgvMission.id).where(
            AgvMission.status == "ACTIVE", AgvMission.cancel_requested_at.is_(None)))).values(
                status="ARRIVED", arrival_evidence=evidence, completed_at=_now()))
    return result.rowcount == 1


def request_cancel(db, *, command_id, task_id, robot_id, command_sequence):
    """Block later stages; cancellation remains uncertain until stopped evidence."""
    command = db.get(AgvMissionCommand, command_id)
    if (command is None or command.status not in PENDING + ("ARRIVED",)
            or (command.task_id, command.robot_id, command.command_sequence)
            != (task_id, robot_id, command_sequence)):
        return False
    latest_sequence = db.scalar(select(func.max(AgvMissionCommand.command_sequence)).where(
        AgvMissionCommand.mission_id == command.mission_id))
    if latest_sequence != command_sequence:
        return False
    now = _now()
    result = db.execute(update(AgvMission).where(
        AgvMission.id == command.mission_id, AgvMission.active_slot == 1,
        AgvMission.cancel_requested_at.is_(None)).values(
            cancel_requested_at=now, status="UNKNOWN"))
    if result.rowcount:
        db.execute(update(AgvMissionCommand).where(
            AgvMissionCommand.command_id == command_id,
            AgvMissionCommand.status.in_(PENDING + ("ARRIVED",))).values(
                cancel_requested_at=now, status="UNKNOWN",
                failure_details="Cancellation pending verified stop"))
    return result.rowcount == 1


def verify_stopped(db, *, command_id, task_id, robot_id, command_sequence, evidence):
    command = db.get(AgvMissionCommand, command_id)
    if (command is None or command.status != "UNKNOWN" or not command.cancel_requested_at
            or (command.task_id, command.robot_id, command.command_sequence)
            != (task_id, robot_id, command_sequence)
            or not _verified_evidence(command, evidence, arrival=False)):
        return False
    result = db.execute(update(AgvMissionCommand).where(
        AgvMissionCommand.command_id == command_id,
        AgvMissionCommand.status == "UNKNOWN",
        AgvMissionCommand.cancel_requested_at.is_not(None)).values(
            status="STOPPED", stopped_evidence=evidence, completed_at=_now()))
    return result.rowcount == 1


def confirm_cancelled(db, *, command_id, task_id, robot_id, command_sequence):
    command = db.get(AgvMissionCommand, command_id)
    if (command is None or command.status != "STOPPED" or not command.stopped_evidence
            or (command.task_id, command.robot_id, command.command_sequence)
            != (task_id, robot_id, command_sequence)):
        return False
    result = db.execute(update(AgvMission).where(
        AgvMission.id == command.mission_id, AgvMission.status == "UNKNOWN",
        AgvMission.cancel_requested_at.is_not(None), AgvMission.active_slot == 1).values(
            status="CANCELLED", active_slot=None, completed_at=_now()))
    if result.rowcount:
        db.execute(update(AgvMissionCommand).where(
            AgvMissionCommand.command_id == command_id,
            AgvMissionCommand.status == "STOPPED").values(status="CANCELLED"))
    return result.rowcount == 1


def recover_unresolved_commands(db):
    """Run only after all workers are stopped; quarantine and never resend."""
    # shortcut: no cross-worker recovery lease exists; add one before online reconciliation.
    result = db.execute(update(AgvMissionCommand).where(
        AgvMissionCommand.status.in_(PENDING[:-1])).values(
            status="UNKNOWN", failure_details="Backend restarted before execution was verified"))
    db.execute(update(AgvMission).where(
        AgvMission.id.in_(select(AgvMissionCommand.mission_id).where(
            AgvMissionCommand.status == "UNKNOWN")),
        AgvMission.active_slot == 1).values(status="UNKNOWN"))
    return result.rowcount
