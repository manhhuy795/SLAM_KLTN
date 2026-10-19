import json
from types import SimpleNamespace
import unittest

from web_bridge.scan_diagnostics import ScanDiagnostics


def scan(ranges=(0.3, 1.0), frame="laser_link"):
    return SimpleNamespace(
        header=SimpleNamespace(frame_id=frame, stamp=None),
        ranges=ranges, range_min=0.1, range_max=8.0,
    )


class ScanDiagnosticsTest(unittest.TestCase):
    def test_startup_and_freshness_boundaries_and_recovery(self):
        diagnostics = ScanDiagnostics()
        self.assertEqual(diagnostics.snapshot(0)["lidar_status"], "OFFLINE")
        diagnostics.receive(scan(), 10)
        for now, expected in ((10.5, "ONLINE"), (10.501, "STALE"),
                              (13.0, "STALE"), (13.001, "OFFLINE")):
            with self.subTest(now=now):
                value = diagnostics.snapshot(now)
                self.assertEqual(value["lidar_status"], expected)
                self.assertEqual(value["lidar_online"], expected == "ONLINE")
        diagnostics.receive(scan(frame="sim_laser"), 20)
        value = diagnostics.snapshot(20)
        self.assertEqual(value["lidar_status"], "ONLINE")
        self.assertEqual(value["scan_frame_id"], "sim_laser")
        self.assertIsNone(value["scan_rate_hz"])

    def test_six_hz_and_interruption_are_receipt_measurements(self):
        diagnostics = ScanDiagnostics()
        for index in range(40):
            diagnostics.receive(scan(), index / 6)
        value = diagnostics.snapshot(6.5)
        self.assertAlmostEqual(value["scan_rate_hz"], 6)
        self.assertAlmostEqual(value["scan_gap_ms"], 1000 / 6)
        diagnostics.receive(scan(), 7.14)
        value = diagnostics.snapshot(7.14)
        self.assertAlmostEqual(value["scan_max_gap_ms"], 640)
        self.assertIsNone(value["scan_rate_hz"])
        diagnostics.receive(scan(), 7.14 + 1 / 6)
        self.assertAlmostEqual(diagnostics.snapshot(7.4)["scan_rate_hz"], 6)

    def test_filter_ranges_and_inclusive_limits(self):
        diagnostics = ScanDiagnostics()
        diagnostics.receive(scan([float('nan'), float('inf'), -float('inf'),
                                  -1, 0.099, 0.1, 0.2, 8, 8.001]), 0)
        value = diagnostics.snapshot(0.02)
        self.assertEqual(value["scan_points_total"], 9)
        self.assertEqual(value["scan_points_valid"], 3)
        self.assertEqual(value["nearest_obstacle_m"], 0.1)
        self.assertEqual(value["last_scan_age_ms"], 20)
        self.assertNotIn("ranges", value)
        json.dumps(value, allow_nan=False)

    def test_empty_or_all_invalid_scan_has_no_nearest_obstacle(self):
        for ranges in ([], [float('inf'), float('nan'), 9]):
            diagnostics = ScanDiagnostics()
            diagnostics.receive(scan(ranges), 0)
            value = diagnostics.snapshot(0)
            self.assertEqual(value["scan_points_valid"], 0)
            self.assertIsNone(value["nearest_obstacle_m"])
            self.assertTrue(value["lidar_online"])
            json.dumps(value, allow_nan=False)

    def test_configurable_thresholds(self):
        diagnostics = ScanDiagnostics(stale_sec=1, offline_sec=2)
        diagnostics.receive(scan(), 0)
        self.assertEqual(diagnostics.snapshot(0.64)["lidar_status"], "ONLINE")
        self.assertEqual(diagnostics.snapshot(1.01)["lidar_status"], "STALE")
        self.assertEqual(diagnostics.snapshot(2.01)["lidar_status"], "OFFLINE")
        for stale, offline in ((0, 3), (3, 1), (1, 1), (float('nan'), 3), (1, float('inf'))):
            with self.subTest(stale=stale, offline=offline):
                with self.assertRaises(ValueError):
                    ScanDiagnostics(stale, offline)


if __name__ == "__main__":
    unittest.main()
