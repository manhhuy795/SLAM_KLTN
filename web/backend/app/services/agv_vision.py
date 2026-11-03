"""Mock-injectable pickup classification; never dispatches a robot."""

from datetime import datetime, timezone
from math import isfinite

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.agv_mission import AgvMission, AgvMissionCommand
from app.models.agv_vision import AgvClassRackPolicy, AgvVisionCapture, AgvVisionJob
from app.models.location import Location
from app.models.operator import Operator
from app.models.robot import Robot
from app.models.saved_map import SavedMap
from app.models.task import Task


CLASSES = frozenset({"cylinder", "rectangular_box", "triangular_prism"})
RACKS = frozenset({"RACK_A", "RACK_B", "RACK_C", "RACK_D"})


class AgvVisionError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def configure_policy(db, *, map_id, mapping, min_confidence, min_margin, expected_revision=None):
    """Store an explicit per-map policy; no class has a default rack."""
    saved_map = db.get(SavedMap, map_id)
    if saved_map is None or not saved_map.is_selected:
        raise AgvVisionError("A selected map is required")
    if (not isinstance(mapping, dict) or set(mapping) != CLASSES
            or any(value not in RACKS for value in mapping.values())):
        raise AgvVisionError("Policy must map each supported class to a rack")
    if (type(min_confidence) not in (int, float) or type(min_margin) not in (int, float)
            or not isfinite(min_confidence) or not isfinite(min_margin)
            or not 0 < min_confidence <= 1 or not 0 < min_margin <= 1):
        raise AgvVisionError("Policy confidence and margin must be explicit and valid")
    for rack_code in set(mapping.values()):
        rack = db.scalar(select(Location).where(Location.code == rack_code))
        if rack is None or rack.location_type != "RACK" or not rack.is_active:
            raise AgvVisionError("Policy rack is missing or inactive")
    policy = db.get(AgvClassRackPolicy, map_id)
    if policy is None:
        if expected_revision not in (None, 0):
            raise AgvVisionError("Policy revision changed")
        policy = AgvClassRackPolicy(map_id=map_id, revision=1, mapping=dict(mapping),
                                    min_confidence=min_confidence, min_margin=min_margin,
                                    updated_at=_now())
        db.add(policy)
        try:
            db.flush()
        except (IntegrityError, OperationalError) as error:
            db.rollback()
            raise AgvVisionError("Concurrent policy update rejected") from error
        return policy
    if expected_revision != policy.revision:
        raise AgvVisionError("Policy revision changed")
    result = db.execute(update(AgvClassRackPolicy).where(
        AgvClassRackPolicy.map_id == map_id,
        AgvClassRackPolicy.revision == expected_revision).values(
            revision=expected_revision + 1, mapping=dict(mapping),
            min_confidence=min_confidence, min_margin=min_margin, updated_at=_now()))
    if result.rowcount != 1:
        raise AgvVisionError("Concurrent policy update rejected")
    db.refresh(policy)
    return policy


def _verified_pickup(db, task, job):
    robot = db.get(Robot, job.robot_id)
    saved_map = db.get(SavedMap, job.map_id)
    if (task.robot_id != job.robot_id or robot is None or robot.robot_type != "LINE"
            or not robot.is_active or saved_map is None or not saved_map.is_selected
            or task.status != "ARRIVED_AT_PICKUP"):
        raise AgvVisionError("LINE task has no verified pickup arrival")
    mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task.id))
    if mission is None or mission.robot_id != robot.id or mission.map_id != job.map_id:
        raise AgvVisionError("LINE mission ownership is invalid")
    command = db.scalar(select(AgvMissionCommand).where(
        AgvMissionCommand.mission_id == mission.id,
        AgvMissionCommand.mission_stage == "PICKUP"))
    if command is None and mission.handoff_command_id:
        command = db.get(AgvMissionCommand, mission.handoff_command_id)
    if (command is None or command.status != "ARRIVED" or not command.arrival_evidence
            or command.robot_id != robot.id or command.target_station != "PICKUP"):
        raise AgvVisionError("Pickup arrival evidence is missing")


def _validated_prediction(result, policy):
    if not isinstance(result, dict) or result.get("success") is not True:
        raise AgvVisionError("Classification failed")
    scores = result.get("class_probabilities")
    if (not isinstance(scores, dict) or set(scores) != CLASSES
            or any(type(score) not in (int, float) or not isfinite(score)
                   or not 0 <= score <= 1 for score in scores.values())
            or abs(sum(scores.values()) - 1) > 0.01):
        raise AgvVisionError("Classification probabilities are invalid")
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    label, confidence = ordered[0]
    if (result.get("predicted_class") != label
            or type(result.get("confidence")) not in (int, float)
            or not isfinite(result["confidence"])
            or not 0 <= result["confidence"] <= 1
            or abs(result["confidence"] - confidence) > 0.01
            or confidence < policy.min_confidence
            or confidence - ordered[1][1] < policy.min_margin):
        raise AgvVisionError("Classification is missing or ambiguous")
    version = result.get("model_version")
    if not isinstance(version, str) or not version or len(version) > 120:
        raise AgvVisionError("Classifier model version is required")
    return label, confidence, scores, version


class AgvPickupClassifier:
    def __init__(self, classifier=None):
        self.classifier = classifier

    def capture(self, db, *, task_id, robot_id, capture_id, image_ref):
        """Persist one valid shape result for operator review; caller commits."""
        if (not isinstance(capture_id, str) or not capture_id or len(capture_id) > 64
                or not isinstance(image_ref, str) or not image_ref or len(image_ref) > 500):
            raise AgvVisionError("Capture identity and image reference are required")
        existing = db.get(AgvVisionCapture, capture_id)
        if existing:
            if (existing.task_id, existing.robot_id, existing.image_ref) != (
                    task_id, robot_id, image_ref):
                raise AgvVisionError("Capture ID belongs to different evidence")
            return existing
        if self.classifier is None:
            raise AgvVisionError("Pickup classifier is not configured")
        task = db.get(Task, task_id)
        job = db.get(AgvVisionJob, task_id)
        if task is None or job is None or job.robot_id != robot_id or job.status != "PENDING":
            raise AgvVisionError("Pickup classification is unavailable")
        _verified_pickup(db, task, job)
        policy = db.get(AgvClassRackPolicy, job.map_id)
        if policy is None:
            raise AgvVisionError("Class-to-rack policy is not configured")
        label, confidence, scores, version = _validated_prediction(
            self.classifier.predict_image(image_ref), policy)
        changed = db.execute(update(AgvVisionJob).where(
            AgvVisionJob.task_id == task_id, AgvVisionJob.robot_id == robot_id,
            AgvVisionJob.status == "PENDING").values(
                status="REVIEW", active_capture_id=capture_id))
        if changed.rowcount != 1:
            raise AgvVisionError("Another capture is awaiting review")
        capture = AgvVisionCapture(capture_id=capture_id, task_id=task_id,
            robot_id=robot_id, image_ref=image_ref, predicted_class=label,
            confidence=confidence, probabilities=dict(scores), model_version=version,
            policy_revision=policy.revision, review_status="REVIEW")
        try:
            db.add(capture)
            db.flush()
        except (IntegrityError, OperationalError) as error:
            db.rollback()
            raise AgvVisionError("Concurrent capture rejected") from error
        return capture

    def review(self, db, *, task_id, capture_id, operator_id, approve):
        """Operator accepts a shape and assigns a rack to the same Task."""
        task = db.get(Task, task_id)
        job = db.get(AgvVisionJob, task_id)
        capture = db.get(AgvVisionCapture, capture_id)
        operator = db.get(Operator, operator_id)
        if (task is None or job is None or capture is None or operator is None
                or not operator.is_active or capture.task_id != task_id
                or capture.robot_id != job.robot_id):
            raise AgvVisionError("Vision review ownership is invalid")
        if (capture.review_status == "ACCEPTED" and approve
                and capture.confirmed_by == operator_id and job.status == "ASSIGNED"):
            return capture, db.get(Location, job.assigned_rack_id)
        if (job.status != "REVIEW" or job.active_capture_id != capture_id
                or capture.review_status != "REVIEW"):
            raise AgvVisionError("Vision review is stale or duplicated")
        _verified_pickup(db, task, job)
        if not approve:
            changed = db.execute(update(AgvVisionJob).where(
                AgvVisionJob.task_id == task_id, AgvVisionJob.status == "REVIEW",
                AgvVisionJob.active_capture_id == capture_id).values(
                    status="PENDING", active_capture_id=None))
            if changed.rowcount != 1:
                raise AgvVisionError("Concurrent review rejected")
            capture.review_status = "REJECTED"
            capture.confirmed_by = operator_id
            capture.reviewed_at = _now()
            return capture, None
        policy = db.get(AgvClassRackPolicy, job.map_id)
        if policy is None or policy.revision != capture.policy_revision:
            raise AgvVisionError("Class-to-rack policy changed; capture again")
        rack_code = policy.mapping.get(capture.predicted_class)
        rack = db.scalar(select(Location).where(Location.code == rack_code))
        if rack is None or rack.location_type != "RACK" or not rack.is_active:
            raise AgvVisionError("Assigned rack is missing or inactive")
        if task.dropoff_location_id is not None:
            raise AgvVisionError("Task destination was already assigned")
        changed = db.execute(update(AgvVisionJob).where(
            AgvVisionJob.task_id == task_id, AgvVisionJob.status == "REVIEW",
            AgvVisionJob.active_capture_id == capture_id).values(
                status="ASSIGNED", assigned_rack_id=rack.id, assigned_at=_now()))
        if changed.rowcount != 1:
            raise AgvVisionError("Concurrent rack assignment rejected")
        task.dropoff_location_id = rack.id
        capture.review_status = "ACCEPTED"
        capture.confirmed_by = operator_id
        capture.reviewed_at = _now()
        return capture, rack


agv_pickup_classifier = AgvPickupClassifier()
