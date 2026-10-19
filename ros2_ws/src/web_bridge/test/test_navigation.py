"""Action race regressions. Run with ROS 2 sourced; no Gazebo required."""

from concurrent.futures import Future
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

try:
    from action_msgs.msg import GoalStatus
    from web_bridge.web_bridge_node import WebBridge
except ModuleNotFoundError as error:
    if error.name not in {"rclpy", "action_msgs"}:
        raise
    WebBridge = None


def completed(value):
    future = Future()
    future.set_result(value)
    return future


@unittest.skipIf(WebBridge is None, "Requires sourced ROS 2 environment")
class NavigationCallbacksTest(unittest.TestCase):
    def setUp(self):
        self.bridge = WebBridge.__new__(WebBridge)
        self.bridge._navigation_command = {"id": 7}
        self.bridge._navigation_goal_handle = None
        self.bridge._navigation_state = "SENDING"
        self.bridge._navigation_feedback = {}
        self.bridge._cancel_requested = False
        self.bridge._cancel_in_flight = False
        self.bridge._enqueue = Mock()
        self.bridge.nav_client = Mock()
        self.bridge.nav_client.server_is_ready.return_value = True
        self.bridge._get_json = Mock(return_value={
            "command": "CANCEL", "id": 8, "navigation_command_id": 7,
        })
        self.result = Future()
        self.cancel = Future()
        self.handle = Mock(accepted=True)
        self.handle.get_result_async.return_value = self.result
        self.handle.cancel_goal_async.return_value = self.cancel

    def accept(self):
        self.bridge._goal_response_callback(completed(self.handle))

    def finish(self, status):
        self.result.set_result(SimpleNamespace(
            status=status, result=SimpleNamespace(error_code=0, error_msg=""),
        ))

    def test_cancel_while_sending_waits_for_handle_and_action_result(self):
        self.bridge._poll_navigation_command()
        self.assertTrue(self.bridge._cancel_requested)
        self.assertEqual(self.bridge._navigation_state, "SENDING")
        self.accept()
        self.handle.cancel_goal_async.assert_called_once()
        self.cancel.set_result(SimpleNamespace(goals_canceling=[object()]))
        self.assertIsNotNone(self.bridge._navigation_command)
        self.finish(GoalStatus.STATUS_CANCELED)
        self.assertIsNone(self.bridge._navigation_command)
        self.assertEqual(self.bridge._enqueue.call_args.args[1]["state"], "CANCELLED")

    def test_rejected_cancel_does_not_discard_running_goal(self):
        self.accept()
        self.bridge._poll_navigation_command()
        self.cancel.set_result(SimpleNamespace(goals_canceling=[]))
        self.assertIs(self.bridge._navigation_goal_handle, self.handle)
        self.assertEqual(self.bridge._navigation_state, "NAVIGATING")
        self.assertFalse(self.bridge._cancel_requested)
        self.finish(GoalStatus.STATUS_SUCCEEDED)
        self.assertEqual(self.bridge._enqueue.call_args.args[1]["state"], "SUCCEEDED")

    def test_late_cancel_response_cannot_clear_next_goal(self):
        self.accept()
        self.bridge._poll_navigation_command()
        self.finish(GoalStatus.STATUS_SUCCEEDED)
        self.bridge._navigation_command = {"id": 9}
        self.cancel.set_result(SimpleNamespace(goals_canceling=[]))
        self.assertEqual(self.bridge._navigation_command["id"], 9)

    def test_cancel_for_another_goal_is_ignored(self):
        self.bridge._get_json.return_value["navigation_command_id"] = 6
        self.accept()
        self.bridge._poll_navigation_command()
        self.handle.cancel_goal_async.assert_not_called()


if __name__ == "__main__":
    unittest.main()
