import unittest
from time import monotonic

from app.services.ros_state import RosState


class AmrHardwareTelemetryTest(unittest.TestCase):
    def test_source_isolation_and_freshness(self):
        state = RosState()
        hardware = dict(robot_id=1, source="HARDWARE",
                        diagnostics=dict(serial_connected=True, encoder_online=True,
                                         emergency_stop=True, left_encoder_count=12,
                                         right_encoder_count=13, fault_reason="", serial_error=""),
                        odometry=dict(frame_id="odom", child_frame_id="base_link",
                                      x=0.1, y=0.2, yaw=0.0,
                                      linear_mps=0.0, angular_radps=0.0),
                        status_age_ms=0.0, odom_age_ms=0.0)
        self.assertEqual(state.get_amr_telemetry(1, "HARDWARE")["state"], "OFFLINE")
        self.assertEqual(state.set_amr_telemetry(hardware)["state"], "ONLINE")
        self.assertEqual(state.get_amr_telemetry(1, "SIMULATION")["state"], "OFFLINE")
        state._amr_telemetry[(1, "HARDWARE")] = (
            hardware, monotonic() - 3, 100.0)
        stale = state.get_amr_telemetry(1, "HARDWARE")
        self.assertEqual(stale["state"], "STALE")
        self.assertEqual(stale["odometry_state"], "STALE")
        state.set_amr_telemetry({**hardware, "status_age_ms": 6000})
        self.assertEqual(state.get_amr_telemetry(1, "HARDWARE")["odometry_state"], "OFFLINE")
        state.set_amr_telemetry({**hardware, "diagnostics": {
            **hardware["diagnostics"], "encoder_online": False}})
        self.assertEqual(state.get_amr_telemetry(1, "HARDWARE")["odometry_state"], "OFFLINE")
        state._amr_telemetry[(1, "HARDWARE")] = (
            hardware, monotonic() - 6, 100.0)
        self.assertEqual(state.get_amr_telemetry(1, "HARDWARE")["state"], "OFFLINE")


if __name__ == "__main__":
    unittest.main()
