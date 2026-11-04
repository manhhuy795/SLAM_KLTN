import unittest
from types import SimpleNamespace as Item
from unittest.mock import Mock, patch

from web_bridge.hardware_telemetry import parse_hardware_status, parse_odometry

try:
    from web_bridge.web_bridge_node import WebBridge
except ModuleNotFoundError as error:
    if error.name not in {"rclpy", "action_msgs", "diagnostic_msgs", "nav_msgs"}:
        raise
    WebBridge = None


class HardwareTelemetryConversionTest(unittest.TestCase):
    def test_diagnostics_preserve_latched_stop_and_real_encoder_evidence(self):
        def diagnostic(encoder_online):
            values = dict(serial_connected="true", encoder_online=encoder_online,
                          emergency_stop="true", left_encoder_count="123",
                          right_encoder_count="-45", fault_reason="encoder timeout")
            return Item(status=[Item(name="amr_hardware/base", values=[
                Item(key=key, value=value) for key, value in values.items()])])
        self.assertEqual(parse_hardware_status(diagnostic("true"))["left_encoder_count"], 123)
        offline = parse_hardware_status(diagnostic("false"))
        self.assertIsNone(offline["left_encoder_count"])
        self.assertTrue(offline["emergency_stop"])
        self.assertEqual(offline["fault_reason"], "encoder timeout")
        self.assertIsNone(parse_hardware_status(Item(status=[])))

    def test_odometry_rejects_wrong_frame_and_nonfinite_values(self):
        message = Item(header=Item(frame_id="odom"), child_frame_id="base_link",
            pose=Item(pose=Item(position=Item(x=1.0, y=2.0),
                                orientation=Item(x=0.0, y=0.0, z=0.0, w=1.0))),
            twist=Item(twist=Item(linear=Item(x=0.1), angular=Item(z=0.2))))
        self.assertEqual(parse_odometry(message)["linear_mps"], 0.1)
        message.header.frame_id = "map"
        self.assertIsNone(parse_odometry(message))
        message.header.frame_id = "odom"
        message.pose.pose.position.x = float("nan")
        self.assertIsNone(parse_odometry(message))


@unittest.skipIf(WebBridge is None, "Requires sourced ROS 2 environment")
class TelemetryOnlyBridgeTest(unittest.TestCase):
    def test_hardware_mode_never_polls_navigation(self):
        bridge = WebBridge.__new__(WebBridge)
        bridge.telemetry_only = True
        bridge.telemetry_source = "HARDWARE"
        bridge.robot_id = 1
        bridge._latest_hardware_status = {"serial_connected": True}
        bridge._last_hardware_status = 9.5
        bridge._latest_odom = None
        bridge._last_odom = None
        bridge._last_telemetry_sent = (None, None)
        bridge._next_telemetry_publish = 0
        bridge._enqueue = Mock()
        bridge._poll_navigation_command = Mock()
        with patch("web_bridge.web_bridge_node.time.monotonic", return_value=10):
            bridge._publish_updates()
        bridge._poll_navigation_command.assert_not_called()
        endpoint, payload = bridge._enqueue.call_args.args
        self.assertEqual(endpoint, "/api/ros/hardware-telemetry")
        self.assertEqual(payload["source"], "HARDWARE")


if __name__ == "__main__":
    unittest.main()
