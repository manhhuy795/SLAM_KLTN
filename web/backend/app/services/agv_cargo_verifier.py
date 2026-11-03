"""Mock-injectable cargo-presence evidence; never treats shape class as delivery proof."""

from datetime import datetime, timezone
from math import isfinite
import os

from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.agv_cargo_evidence import AgvCargoEvidence
from app.models.agv_mission import AgvMissionCommand
from app.models.robot import Robot
from app.models.task import Task


class CargoEvidenceError(ValueError):
    pass


class AgvCargoVerifier:
    def __init__(self, analyzer=None, *, hardware_validated=False):
        self.analyzer = analyzer
        self.hardware_validated = hardware_validated

    def automatic_proof_enabled(self):
        return (os.getenv("WRMS_AGV_CAMERA_AUTO_CONFIRM_ENABLED") == "1"
                and self.analyzer is not None and self.hardware_validated)

    def submit(self, db, *, capture_id, task_id, robot_id, command_id,
               station, image_ref, observed_at):
        """Persist one analyzed capture; caller commits. No Task state is changed."""
        if not all(isinstance(value, str) and value for value in
                   (capture_id, command_id, station, image_ref)):
            raise CargoEvidenceError("Capture identity and image reference are required")
        if (len(capture_id) > 64 or len(station) > 32 or len(image_ref) > 500
                or not isinstance(observed_at, datetime)):
            raise CargoEvidenceError("Capture fields are invalid")
        if observed_at.tzinfo:
            observed_at = observed_at.astimezone(timezone.utc).replace(tzinfo=None)
        existing = db.get(AgvCargoEvidence, capture_id)
        if existing:
            if (existing.task_id, existing.robot_id, existing.command_id,
                existing.station, existing.image_ref, existing.observed_at) != (
                    task_id, robot_id, command_id, station, image_ref, observed_at):
                raise CargoEvidenceError("Capture ID belongs to different evidence")
            return existing
        if self.analyzer is None:
            raise CargoEvidenceError("Camera analyzer is not configured")
        task = db.get(Task, task_id)
        robot = db.get(Robot, robot_id)
        command = db.get(AgvMissionCommand, command_id)
        if (task is None or robot is None or command is None or task.robot_id != robot_id
                or robot.robot_type != "LINE" or not robot.is_active
                or task.status != "ARRIVED_AT_DELIVERY"
                or (command.task_id, command.robot_id, command.mission_stage,
                    command.status, command.target_station) !=
                   (task_id, robot_id, "DELIVERY", "ARRIVED", station)
                or not command.arrival_evidence or not command.arrival_evidence.get("stopped")):
            raise CargoEvidenceError("Delivery arrival and robot ownership are not verified")
        if command.completed_at is None:
            raise CargoEvidenceError("Capture timestamp is invalid")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if observed_at < command.completed_at or observed_at > now:
            raise CargoEvidenceError("Capture is stale or from the future")
        result = self.analyzer.analyze(image_ref)
        if not isinstance(result, dict):
            raise CargoEvidenceError("Camera result is invalid")
        presence = result.get("presence")
        confidence = result.get("confidence")
        provenance = result.get("provenance")
        if (presence not in {"PRESENT", "ABSENT", "UNCERTAIN"}
                or type(confidence) not in {int, float} or not isfinite(confidence)
                or not 0 <= confidence <= 1
                or not isinstance(provenance, str) or not provenance or len(provenance) > 120):
            raise CargoEvidenceError("Camera presence result is invalid")
        evidence = AgvCargoEvidence(
            capture_id=capture_id, task_id=task_id, robot_id=robot_id,
            command_id=command_id, station=station, image_ref=image_ref,
            presence=presence, confidence=confidence, provenance=provenance,
            review_status="WAITING_FOR_REMOVAL" if presence == "PRESENT" else "MANUAL_REVIEW",
            observed_at=observed_at)
        try:
            db.add(evidence)
            db.flush()
        except (IntegrityError, OperationalError) as error:
            db.rollback()
            existing = db.get(AgvCargoEvidence, capture_id)
            if existing and (existing.task_id, existing.robot_id, existing.command_id,
                             existing.station, existing.image_ref, existing.observed_at) == (
                                 task_id, robot_id, command_id, station, image_ref, observed_at):
                return existing
            raise CargoEvidenceError("Concurrent or conflicting capture rejected") from error
        return evidence


agv_cargo_verifier = AgvCargoVerifier()
