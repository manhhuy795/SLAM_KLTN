import unittest

from pydantic import ValidationError
from app.schemas.ros import RosStatusPayload
from app.services.ros_state import RosState


class RosStateTest(unittest.TestCase):
    def test_scan_age_advances_without_new_heartbeat_and_recovers(self):
        state = RosState()
        payload = {
            "bridge_online": True, "lidar_online": True, "lidar_status": "ONLINE",
            "last_scan_age_ms": 100, "scan_rate_hz": 6,
            "scan_stale_sec": 0.5, "scan_offline_sec": 3,
        }
        state.set_status(payload)
        received = state._last_heartbeat_monotonic
        for elapsed, expected in ((0.3, "ONLINE"), (0.5, "STALE"), (2.95, "OFFLINE")):
            value = state.get_status(now=received + elapsed)
            self.assertEqual(value["lidar_status"], expected)
            self.assertEqual(value["lidar_online"], expected == "ONLINE")
            self.assertAlmostEqual(value["last_scan_age_ms"], 100 + elapsed * 1000)
        state.set_status(payload)
        self.assertEqual(state.get_status()["lidar_status"], "ONLINE")
        self.assertEqual(payload["last_scan_age_ms"], 100)

    def test_diagnostics_are_optional_and_invalid_values_rejected(self):
        legacy = dict(slam_online=False, map_status="WAITING", lidar_online=True,
                      localization_available=False, tf_available=False)
        self.assertIsNone(RosStatusPayload(**legacy).lidar_status)
        for fields in (
            {"nearest_obstacle_m": float('nan')}, {"scan_gap_ms": float('inf')},
            {"scan_points_valid": 3, "scan_points_total": 2},
            {"scan_points_total": -1}, {"scan_stale_sec": 0.5},
            {"scan_stale_sec": 3, "scan_offline_sec": 1},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                RosStatusPayload(**legacy, **fields)

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
