import unittest
from unittest.mock import Mock

from app.models.location import Location
from app.models.robot import Robot
from app.models.task import Task
from app.services.task_executor import TaskExecutor, TaskExecutorError


class RobotDispatchGuardTests(unittest.TestCase):
    def setUp(self):
        self.robot = Robot(id=7, robot_code="TEST-7", name="Test", robot_type="AMR", is_active=True)
        self.pickup = Location(id=11, code="P-11", name="Pickup", location_type="PICKUP",
                               x=1.0, y=2.0, yaw=0.0, is_active=True)
        self.delivery = Location(id=12, code="D-12", name="Delivery", location_type="DELIVERY",
                                 x=3.0, y=4.0, yaw=0.0, is_active=True)
        self.task = Task(id=21, task_code="T-21", product_id=1, robot_id=7,
                         pickup_location_id=11, dropoff_location_id=12,
                         status="WAITING", progress=0, is_paused=False,
                         cancel_requested=False)
        self.db = Mock()
        self.db.get.side_effect = self._get
        self.db.scalar.return_value = None
        self.nav = Mock()
        self.nav.get_status.return_value = {"state": "IDLE", "goal": None}
        self.nav.create_goal.return_value = {"state": "SENDING"}
        self.nav.create_cancel.return_value = {"state": "CANCELLED"}
        ros = Mock()
        ros.get_status.return_value = {
            "bridge_online": True, "nav2_online": True,
            "localization_available": True, "tf_available": True,
        }
        ros.get_pose.return_value = {"robot_id": 7}
        self.executor = TaskExecutor(self.nav, ros)

    def _get(self, model, key):
        if model is Robot and key == 7:
            return self.robot
        if model is Location:
            return {11: self.pickup, 12: self.delivery}.get(key)
        if model is Task and key == 21:
            return self.task
        return None

    def _assert_no_side_effects(self, status):
        self.assertEqual(self.task.status, status)
        self.nav.create_goal.assert_not_called()
        self.nav.create_cancel.assert_not_called()
        self.db.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_amr_start_cancel_and_completion_keep_existing_lifecycle(self):
        self.executor.start_pickup(self.db, self.task)
        self.assertEqual(self.task.status, "MOVING_TO_PICKUP")
        self.nav.create_goal.assert_called_once()

        self.nav.get_status.return_value = {
            "state": "NAVIGATING", "goal": {"task": {"id": 21}},
        }
        self.executor.cancel(self.db, self.task)
        self.assertEqual(self.task.status, "CANCELLED")
        self.nav.create_cancel.assert_called_once()

        self.nav.reset_mock()
        self.nav.get_status.return_value = {"state": "SUCCEEDED", "goal": None}
        self.task.status = "DELIVERY_CONFIRMED"
        self.executor.complete_delivery(self.db, self.task)
        self.assertEqual(self.task.status, "COMPLETED")
        self.assertEqual(self.task.progress, 100)
        self.nav.create_cancel.assert_not_called()

    def test_line_cannot_start_resume_or_advance_after_proof(self):
        self.robot.robot_type = "LINE"
        for method, status, paused in (
            ("start_pickup", "WAITING", False),
            ("resume", "MOVING_TO_PICKUP", True),
            ("resume", "TRANSPORTING", True),
            ("start_delivery", "PICKUP_CONFIRMED", False),
            ("complete_delivery", "DELIVERY_CONFIRMED", False),
            ("pause", "MOVING_TO_PICKUP", False),
            ("cancel", "WAITING", False),
        ):
            with self.subTest(method=method, status=status):
                self.task.status = status
                self.task.is_paused = paused
                with self.assertRaisesRegex(TaskExecutorError, "does not support AMR navigation"):
                    getattr(self.executor, method)(self.db, self.task)
                self._assert_no_side_effects(status)

    def test_missing_inactive_and_mismatched_robot_fail_before_goal(self):
        for robot_id, robot in ((None, self.robot), (99, self.robot), (7, None),
                                (7, Robot(id=7, robot_code="OFF", name="Off",
                                          robot_type="AMR", is_active=False))):
            with self.subTest(robot_id=robot_id, robot=robot):
                self.task.robot_id = robot_id
                self.robot = robot
                with self.assertRaises(TaskExecutorError):
                    self.executor.start_pickup(self.db, self.task)
                self._assert_no_side_effects("WAITING")

    def test_callback_checks_owner_type_and_stage_before_mutation(self):
        self.task.status = "MOVING_TO_PICKUP"
        status = {
            "state": "SUCCEEDED",
            "goal": {"task": {"id": 21, "robot_id": 7, "stage": "PICKUP"},
                     "location": {"id": 11}},
        }
        self.assertIsNone(self.executor.handle_navigation_status(
            self.db, {**status, "goal": {**status["goal"],
                                         "task": {"id": 21, "robot_id": 99,
                                                  "stage": "PICKUP"}}}))
        self.assertIsNone(self.executor.handle_navigation_status(
            self.db, {**status, "goal": {**status["goal"],
                                         "location": {"id": 12}}}))
        self.robot.robot_type = "LINE"
        self.assertIsNone(self.executor.handle_navigation_status(self.db, status))
        self._assert_no_side_effects("MOVING_TO_PICKUP")

        self.robot.robot_type = "AMR"
        result = self.executor.handle_navigation_status(self.db, status)
        self.assertIsNotNone(result)
        self.assertEqual(self.task.status, "ARRIVED_AT_PICKUP")


if __name__ == "__main__":
    unittest.main()
