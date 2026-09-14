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


if __name__ == "__main__":
    unittest.main()
