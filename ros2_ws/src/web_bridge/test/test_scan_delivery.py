import queue
import unittest
from unittest.mock import Mock, patch

from test_scan_diagnostics import scan
from web_bridge.scan_diagnostics import ScanDiagnostics

try:
    from web_bridge.web_bridge_node import WebBridge
except ModuleNotFoundError as error:
    if error.name not in {"rclpy", "action_msgs"}:
        raise
    WebBridge = None


@unittest.skipIf(WebBridge is None, "Requires sourced ROS 2 environment")
class ScanDeliveryTest(unittest.TestCase):
    def bridge(self):
        bridge = WebBridge.__new__(WebBridge)
        bridge._scan = ScanDiagnostics()
        bridge._outbox = queue.Queue()
        bridge._stop_sender = Mock()
        bridge._stop_sender.is_set.side_effect = [False, True]
        bridge._post_json = Mock(return_value=True)
        return bridge

    def test_callback_uses_monotonic_receipt_time(self):
        bridge = self.bridge()
        with patch("web_bridge.web_bridge_node.time.monotonic", return_value=20):
            bridge._scan_callback(scan())
        self.assertEqual(bridge._scan.snapshot(20.5)["last_scan_age_ms"], 500)

    def test_queue_delay_cannot_report_old_scan_online(self):
        bridge = self.bridge()
        bridge._scan.receive(scan(), 0)
        with patch("web_bridge.web_bridge_node.time.monotonic", return_value=0.1):
            bridge._enqueue("/api/ros/state", bridge._scan.snapshot(0.1))
        with patch("web_bridge.web_bridge_node.time.monotonic", return_value=0.7):
            bridge._send_loop()
        payload = bridge._post_json.call_args.args[1]
        self.assertEqual(payload["lidar_status"], "STALE")
        self.assertFalse(payload["lidar_online"])
        self.assertAlmostEqual(payload["last_scan_age_ms"], 700)
        self.assertAlmostEqual(payload["bridge_queue_age_ms"], 600)
        self.assertNotIn("_queued_at", payload)

    def test_expired_queued_status_is_not_sent_after_reconnect(self):
        bridge = self.bridge()
        with patch("web_bridge.web_bridge_node.time.monotonic", return_value=0):
            bridge._enqueue("/api/ros/state", bridge._scan.snapshot(0))
        with patch("web_bridge.web_bridge_node.time.monotonic", return_value=4):
            bridge._send_loop()
        bridge._post_json.assert_not_called()
