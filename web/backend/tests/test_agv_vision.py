import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import tasks as task_routes
from app.db.deps import get_db
from app.main import app
from app.models.agv_mission import AgvMission, AgvMissionCommand
from app.models.agv_vision import AgvClassRackPolicy, AgvVisionCapture, AgvVisionJob
from app.models.location import Location
from app.models.product import Product
from app.models.task import Task
from app.schemas.task import (AgvPickupTaskCreate, AgvPolicyUpdate,
                              AgvVisionCaptureCreate, AgvVisionReview, TaskProofCreate)
from app.services.agv_vision import AgvPickupClassifier
from tests import test_agv_mission_store as mission_tests


class MockShapeClassifier:
    def __init__(self, scores=None):
        self.scores = scores or {"cylinder": 0.90, "rectangular_box": 0.08,
                                 "triangular_prism": 0.02}
        self.calls = 0

    def predict_image(self, _image_ref):
        self.calls += 1
        return {"success": True, "predicted_class": max(self.scores, key=self.scores.get),
                "confidence": max(self.scores.values()),
                "class_probabilities": self.scores, "model_version": "mock-shape-v1"}


class AgvVisionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = mission_tests.AgvMissionStoreTests(
            "test_claim_is_durable_idempotent_and_one_active_per_robot")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.engine = self.fixture.engine
        self.adapter, _, self.transport = self.fixture.adapter()
        self.classifier = MockShapeClassifier()
        self.vision = AgvPickupClassifier(self.classifier)
        self.flags = patch.dict("os.environ", {
            "WRMS_AGV_AUTO_DISPATCH_ENABLED": "1",
            "WRMS_AGV_POLICY_TOKEN": "policy-test-token",
            "WRMS_AGV_VISION_TOKEN": "vision-test-token",
        })
        self.flags.start()
        self.addCleanup(self.flags.stop)
        self.adapter_patch = patch.object(task_routes, "agv_mission_adapter", self.adapter)
        self.adapter_patch.start()
        self.addCleanup(self.adapter_patch.stop)
        self.vision_patch = patch.object(task_routes, "agv_pickup_classifier", self.vision)
        self.vision_patch.start()
        self.addCleanup(self.vision_patch.stop)

    def create_task(self, db):
        return task_routes.create_agv_pickup_task(
            AgvPickupTaskCreate(robot_id=self.fixture.robot_id),
            BackgroundTasks(), db)

    def policy(self, db, mapping=None):
        return task_routes.update_agv_class_rack_policy(
            AgvPolicyUpdate(map_id="test-map", operator_id=self.fixture.operator_id,
                mapping=mapping or dict.fromkeys(("cylinder", "rectangular_box",
                                                  "triangular_prism"), "RACK_A"),
                min_confidence=0.8, min_margin=0.2, expected_revision=None),
            "policy-test-token", db)

    def arrive_at_pickup(self, db, task_id):
        task_routes.start_task(task_id, BackgroundTasks(), db)
        mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task_id))
        command = db.scalar(select(AgvMissionCommand).where(
            AgvMissionCommand.mission_id == mission.id,
            AgvMissionCommand.mission_stage == "PICKUP"))
        self.adapter.acknowledge(db, **self.fixture.identity(command))
        self.adapter.executing(db, **self.fixture.identity(command))
        self.adapter.arrival(db, **self.fixture.identity(command),
                             evidence=self.fixture.evidence(command))
        return command

    def capture(self, db, task_id, capture_id="capture-1"):
        return task_routes.capture_agv_pickup_shape(task_id,
            AgvVisionCaptureCreate(capture_id=capture_id, robot_id=self.fixture.robot_id,
                                   image_ref="mock://pickup-frame"),
            "vision-test-token", db)

    def review(self, db, task_id, approve=True, capture_id="capture-1"):
        return task_routes.review_agv_pickup_shape(task_id,
            AgvVisionReview(capture_id=capture_id, operator_id=self.fixture.operator_id,
                            approve=approve), BackgroundTasks(), "policy-test-token", db)

    def test_same_task_is_unassigned_then_reviewed_and_dispatched_once(self):
        with Session(self.engine) as db:
            created = self.create_task(db)
            task_id = created["id"]
            self.assertIsNone(created["product_id"])
            self.assertIsNone(created["dropoff_location_id"])
            self.assertIsNone(task_routes.get_task(task_id, db)["dropoff_location_code"])
            self.assertIsNone(next(row for row in task_routes.get_tasks(db)
                                   if row["id"] == task_id)["dropoff_location_id"])
            job = db.get(AgvVisionJob, task_id)
            self.assertEqual((job.status, db.get(Task, task_id).product_id,
                              db.get(Task, task_id).dropoff_location_id),
                             ("PENDING", None, None))
            self.policy(db)
            self.arrive_at_pickup(db, task_id)
            with self.assertRaises(HTTPException):
                task_routes.create_task_proof(task_id, TaskProofCreate(
                    proof_type="PICKUP", image_path="mock://proof",
                    verification_status="MANUAL_CONFIRMED",
                    confirmed_by=self.fixture.operator_id), BackgroundTasks(), db)
            self.assertEqual(db.get(Task, task_id).status, "ARRIVED_AT_PICKUP")
            capture = self.capture(db, task_id)
            self.assertEqual(capture["predicted_class"], "cylinder")
            review_queue = task_routes.get_agv_vision_review(task_id, db)
            self.assertEqual(review_queue["captures"][0]["review_status"], "REVIEW")
            self.assertEqual(review_queue["captures"][0]["image_ref"], "mock://pickup-frame")
            self.assertEqual(self.capture(db, task_id), capture)
            self.assertEqual(self.classifier.calls, 1)
            approved = self.review(db, task_id)
            self.assertEqual(approved["rack_code"], "RACK_A")
            self.assertEqual(self.review(db, task_id), approved)
            self.assertEqual(db.get(AgvVisionJob, task_id).status, "ASSIGNED")
            self.assertEqual(task_routes.get_task(task_id, db)["dropoff_location_code"], "RACK_A")
            self.assertEqual(len(self.transport.sent), 1)  # Classification and review do not dispatch.
            task_routes.create_task_proof(task_id, TaskProofCreate(
                proof_type="PICKUP", image_path="mock://proof",
                verification_status="MANUAL_CONFIRMED",
                confirmed_by=self.fixture.operator_id), BackgroundTasks(), db)
            mission = db.scalar(select(AgvMission).where(AgvMission.task_id == task_id))
            delivery = db.scalar(select(AgvMissionCommand).where(
                AgvMissionCommand.mission_id == mission.id,
                AgvMissionCommand.mission_stage == "DELIVERY"))
            self.assertEqual((db.get(Task, task_id).status, delivery.target_station),
                             ("TRANSPORTING", "RACK_A"))
            self.assertEqual(len(self.transport.sent), 2)
            self.adapter.acknowledge(db, **self.fixture.identity(delivery))
            self.adapter.executing(db, **self.fixture.identity(delivery))
            self.adapter.arrival(db, **self.fixture.identity(delivery),
                                 evidence=self.fixture.evidence(delivery))
            self.assertEqual(db.get(Task, task_id).status, "ARRIVED_AT_DELIVERY")
            task_routes.create_task_proof(task_id, TaskProofCreate(
                proof_type="DELIVERY", image_path="mock://delivery-proof",
                verification_status="MANUAL_CONFIRMED",
                confirmed_by=self.fixture.operator_id), BackgroundTasks(), db)
            self.assertEqual(db.get(Task, task_id).status, "COMPLETED")
            returning = db.scalar(select(AgvMissionCommand).where(
                AgvMissionCommand.mission_id == mission.id,
                AgvMissionCommand.mission_stage == "RETURN_PICKUP"))
            self.assertIsNotNone(returning)
            self.assertEqual(len(self.transport.sent), 3)
            self.adapter.acknowledge(db, **self.fixture.identity(returning))
            self.assertEqual(returning.status, "ACKNOWLEDGED")

    def test_missing_policy_invalid_mapping_and_ambiguous_prediction_reject(self):
        with Session(self.engine) as db:
            task_id = self.create_task(db)["id"]
            self.arrive_at_pickup(db, task_id)
            with self.assertRaises(HTTPException):
                self.capture(db, task_id)
            self.assertEqual(db.get(AgvVisionJob, task_id).status, "PENDING")
            with self.assertRaises(HTTPException):
                self.policy(db, {"cylinder": "RACK_A"})
            self.policy(db)
            self.classifier.scores = {"cylinder": 0.5, "rectangular_box": 0.5,
                                      "triangular_prism": 0.0}
            with self.assertRaises(HTTPException):
                self.capture(db, task_id)
            self.assertEqual(db.query(AgvVisionCapture).count(), 0)
            self.assertEqual(db.get(AgvVisionJob, task_id).status, "PENDING")

    def test_missing_or_invalid_classifier_result_never_assigns_rack(self):
        with Session(self.engine) as db:
            task_id = self.create_task(db)["id"]
            self.policy(db)
            self.arrive_at_pickup(db, task_id)
            for result in (None, {"success": False},
                           {"success": True, "predicted_class": "unknown",
                            "confidence": 0.9,
                            "class_probabilities": {"unknown": 1.0},
                            "model_version": "mock"},
                           *({"success": True, "predicted_class": "cylinder",
                              "confidence": nonfinite,
                              "class_probabilities": {"cylinder": 0.9,
                                                      "rectangular_box": 0.08,
                                                      "triangular_prism": 0.02},
                              "model_version": "mock"}
                             for nonfinite in (float("nan"), float("inf"), -float("inf")))):
                with patch.object(self.classifier, "predict_image", return_value=result):
                    with self.assertRaises(HTTPException):
                        self.capture(db, task_id)
            self.assertEqual(db.get(AgvVisionJob, task_id).status, "PENDING")
            self.assertIsNone(task_routes.get_task(task_id, db)["dropoff_location_id"])
            self.assertEqual(len(self.transport.sent), 1)

    def test_review_rejection_allows_new_capture_without_duplicate_assignment(self):
        with Session(self.engine) as db:
            task_id = self.create_task(db)["id"]
            self.policy(db)
            self.arrive_at_pickup(db, task_id)
            self.capture(db, task_id)
            self.assertIsNone(self.review(db, task_id, approve=False)["rack_location_id"])
            self.assertEqual(db.get(AgvVisionJob, task_id).status, "PENDING")
            self.capture(db, task_id, capture_id="capture-2")
            self.review(db, task_id, capture_id="capture-2")
            with self.assertRaises(HTTPException):
                self.review(db, task_id, capture_id="capture-1")
            self.assertEqual(db.get(AgvVisionJob, task_id).status, "ASSIGNED")

    def test_capture_requires_pickup_and_rejects_wrong_robot_or_stale_policy(self):
        with Session(self.engine) as db:
            task_id = self.create_task(db)["id"]
            self.policy(db)
            with self.assertRaises(HTTPException):
                self.capture(db, task_id)
            self.arrive_at_pickup(db, task_id)
            with self.assertRaises(HTTPException):
                task_routes.capture_agv_pickup_shape(task_id,
                    AgvVisionCaptureCreate(capture_id="bad-owner",
                        robot_id=self.fixture.other_robot_id, image_ref="mock://frame"),
                    "vision-test-token", db)
            self.capture(db, task_id)
            self.assertEqual(db.query(AgvVisionCapture).count(), 1)
            task_routes.update_agv_class_rack_policy(AgvPolicyUpdate(
                map_id="test-map", operator_id=self.fixture.operator_id,
                mapping=dict.fromkeys(("cylinder", "rectangular_box",
                                      "triangular_prism"), "RACK_A"),
                min_confidence=0.85, min_margin=0.25, expected_revision=1),
                "policy-test-token", db)
            with self.assertRaises(HTTPException):
                self.review(db, task_id)
            self.assertEqual(db.get(AgvVisionJob, task_id).status, "REVIEW")
            self.assertIsNone(task_routes.get_task(task_id, db)["dropoff_location_id"])

    def test_stale_concurrent_review_cannot_assign_twice(self):
        with Session(self.engine) as db:
            task_id = self.create_task(db)["id"]
            self.policy(db)
            self.arrive_at_pickup(db, task_id)
            self.capture(db, task_id)
        with Session(self.engine) as first, Session(self.engine) as second:
            second.get(AgvVisionJob, task_id)
            second.get(AgvVisionCapture, "capture-1")
            self.review(first, task_id)
            with self.assertRaises(HTTPException):
                self.review(second, task_id, approve=False)
            with Session(self.engine) as check:
                job = check.get(AgvVisionJob, task_id)
                self.assertEqual(job.status, "ASSIGNED")
                self.assertIsNotNone(job.assigned_rack_id)

    def test_existing_task_response_contract_remains_nonnullable(self):
        with Session(self.engine) as db:
            self.assertIsNone(db.get(AgvClassRackPolicy, "test-map"))
            with self.assertRaises(HTTPException):
                task_routes.update_agv_class_rack_policy(AgvPolicyUpdate(
                    map_id="test-map", operator_id=self.fixture.operator_id,
                    mapping=dict.fromkeys(("cylinder", "rectangular_box",
                                          "triangular_prism"), "RACK_A"),
                    min_confidence=0.8, min_margin=0.2), None, db)
            existing = task_routes.get_task(self.fixture.task_ids[0], db)
            self.assertEqual(existing["dropoff_location_code"], "RACK_A")

    def test_http_unassigned_task_and_vision_review_contract(self):
        def fixture_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = fixture_db
        self.addCleanup(app.dependency_overrides.pop, get_db, None)
        client = TestClient(app)
        self.assertEqual(client.post("/api/tasks", json={
            "robot_id": self.fixture.robot_id}).status_code, 422)
        created = client.post("/api/tasks/agv", json={"robot_id": self.fixture.robot_id})
        self.assertEqual(created.status_code, 201, created.text)
        task_id = created.json()["id"]
        self.assertIsNone(created.json()["product_id"])
        self.assertIsNone(created.json()["dropoff_location_id"])
        with Session(self.engine) as db:
            task = db.get(Task, task_id)
            self.assertIsNone(task.product_id)
            self.assertIsNone(task.dropoff_location_id)
        self.assertIsNone(client.get(f"/api/tasks/{task_id}").json()["dropoff_location_code"])
        self.assertIsNone(next(row for row in client.get("/api/tasks").json()
                               if row["id"] == task_id)["dropoff_location_id"])

        policy = {"map_id": "test-map", "operator_id": self.fixture.operator_id,
                  "mapping": dict.fromkeys(("cylinder", "rectangular_box",
                                            "triangular_prism"), "RACK_A"),
                  "min_confidence": 0.8, "min_margin": 0.2}
        url = "/api/tasks/agv/class-rack-policy"
        self.assertEqual(client.put(url, json=policy).status_code, 403)
        self.assertEqual(client.put(url, json=policy, headers={
            "X-WRMS-Policy-Token": "policy-test-token"}).status_code, 200)
        capture_url = f"/api/tasks/{task_id}/vision/captures"
        capture = {"capture_id": "http-capture", "robot_id": self.fixture.robot_id,
                   "image_ref": "mock://pickup-frame"}
        self.assertEqual(client.post(capture_url, json=capture).status_code, 403)
        with Session(self.engine) as db:
            self.arrive_at_pickup(db, task_id)
        captured = client.post(capture_url, json=capture, headers={
            "X-WRMS-Vision-Token": "vision-test-token"})
        self.assertEqual(captured.status_code, 201, captured.text)
        self.assertEqual(captured.json()["review_status"], "REVIEW")
        review_url = f"/api/tasks/{task_id}/vision/review"
        review = {"capture_id": "http-capture", "operator_id": self.fixture.operator_id,
                  "approve": True}
        self.assertEqual(client.post(review_url, json=review).status_code, 403)
        reviewed = client.post(review_url, json=review, headers={
            "X-WRMS-Policy-Token": "policy-test-token"})
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()["rack_code"], "RACK_A")
        self.assertEqual(client.get(f"/api/tasks/{task_id}").json()["dropoff_location_code"],
                         "RACK_A")
        self.assertEqual(len(self.transport.sent), 1)


if __name__ == "__main__":
    unittest.main()
