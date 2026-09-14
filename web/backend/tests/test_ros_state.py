import unittest

from app.services.ros_state import RosState


class RosStateTest(unittest.TestCase):
    def test_heartbeat_timeout_marks_ros_offline(self):
        state = RosState(heartbeat_timeout_sec=3.0)
        state.set_status({
            "bridge_online": True,
            "slam_online": True,
            "map_status": "RECEIVED",
            "lidar_online": True,
            "localization_available": True,
            "tf_available": True,
            "scan_rate_hz": 10.0,
            "last_scan_age_ms": 25.0,
            "timestamp": 100.0,
        })
        received_at = state._last_heartbeat_monotonic

        fresh = state.get_status(now=received_at + 2.9)
        self.assertTrue(fresh["bridge_online"])

        stale = state.get_status(now=received_at + 3.1)
        self.assertFalse(stale["bridge_online"])
        self.assertFalse(stale["slam_online"])
        self.assertFalse(stale["lidar_online"])
        self.assertFalse(stale["localization_available"])
        self.assertFalse(stale["tf_available"])
        self.assertEqual(stale["map_status"], "RECEIVED")
        self.assertIsNone(stale["scan_rate_hz"])


if __name__ == "__main__":
    unittest.main()
