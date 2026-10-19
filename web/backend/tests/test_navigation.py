import unittest

from app.services.navigation import NavigationState


class NavigationStateTests(unittest.TestCase):
    def test_goal_is_claimed_once_and_terminal_state_clears_path(self):
        state = NavigationState()

        created = state.create_goal(1.0, 2.0, 0.5)
        command = state.claim_pending()

        self.assertEqual(command["id"], created["command_id"])
        self.assertIsNone(state.claim_pending())

        state.set_status(command["id"], {"state": "NAVIGATING"})
        state.set_path(command["id"], {
            "frame_id": "map",
            "poses": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 2.0}],
        })
        state.set_status(command["id"], {"state": "SUCCEEDED"})

        self.assertEqual(state.get_status()["state"], "SUCCEEDED")
        self.assertIsNone(state.get_path())

    def test_location_metadata_is_kept_with_goal(self):
        state = NavigationState()
        status = state.create_goal(0.5, 0.0, 0.0, {
            "id": 4, "code": "RACK-TEST", "name": "Rack test Nav2",
        })
        self.assertEqual(status["goal"]["location"]["code"], "RACK-TEST")
        command = state.claim_pending()
        self.assertEqual(command["location"]["id"], 4)

    def test_task_metadata_is_kept_with_goal(self):
        state = NavigationState()
        status = state.create_goal(
            0.5,
            0.0,
            0.0,
            task={"id": 7, "code": "T-0007", "robot_id": 1},
        )
        self.assertEqual(status["goal"]["task"]["id"], 7)
        self.assertEqual(state.claim_pending()["task"]["code"], "T-0007")

    def test_cancel_targets_active_goal(self):
        state = NavigationState()
        goal = state.create_goal(1.0, 0.0, 0.0)
        state.claim_pending()
        state.set_status(goal["command_id"], {"state": "NAVIGATING"})

        cancel = state.create_cancel()
        self.assertEqual(cancel["command_id"], goal["command_id"])
        self.assertEqual(state.claim_pending()["command"], "CANCEL")

        state.set_status(goal["command_id"], {"state": "CANCELLED"})
        state.set_status(goal["command_id"], {"state": "FAILED"})
        self.assertEqual(state.get_status()["state"], "CANCELLED")

    def test_cancel_before_bridge_claim_never_dispatches_goal(self):
        state = NavigationState()
        state.create_goal(0.5, 0.0, 0.0)
        self.assertEqual(state.create_cancel()["state"], "CANCELLED")
        self.assertIsNone(state.claim_pending())
        # A new goal can be sent immediately; the old one never reached ROS.
        next_goal = state.create_goal(1.0, 0.0, 0.0)
        self.assertEqual(state.claim_pending()["id"], next_goal["command_id"])

    def test_rejected_cancel_keeps_goal_active_and_allows_retry(self):
        state = NavigationState()
        goal = state.create_goal(0.5, 0.0, 0.0)
        state.claim_pending()
        state.create_cancel()
        state.claim_pending()
        status = state.set_status(goal["command_id"], {
            "state": "NAVIGATING",
            "cancel_requested": False,
            "error_message": "Nav2 did not accept cancel",
        })
        self.assertFalse(status["cancel_requested"])
        with self.assertRaises(ValueError):
            state.create_goal(2.0, 0.0, 0.0)
        self.assertTrue(state.create_cancel()["cancel_requested"])

    def test_late_path_does_not_restore_finished_navigation(self):
        state = NavigationState()
        goal = state.create_goal(0.5, 0.0, 0.0)
        state.set_status(goal["command_id"], {"state": "SUCCEEDED"})
        with self.assertRaises(KeyError):
            state.set_path(goal["command_id"], {
                "frame_id": "map", "poses": [{"x": 0.5, "y": 0.0}],
            })
        self.assertIsNone(state.get_path())


if __name__ == "__main__":
    unittest.main()
