"""Small LaserScan summaries; timestamps are local monotonic receipt times."""

from collections import deque
from math import isfinite


def scan_status(age_ms, stale_sec, offline_sec):
    if age_ms is None or age_ms > offline_sec * 1000:
        return "OFFLINE"
    return "STALE" if age_ms > stale_sec * 1000 else "ONLINE"


class ScanDiagnostics:
    def __init__(self, stale_sec=0.5, offline_sec=3.0):
        if not (isfinite(stale_sec) and isfinite(offline_sec)
                and 0 < stale_sec < offline_sec):
            raise ValueError("Require 0 < scan_stale_sec < scan_offline_sec")
        self.stale_sec = stale_sec
        self.offline_sec = offline_sec
        self.times = deque(maxlen=20)
        self.frame_id = None
        self.total = None
        self.valid = None
        self.nearest = None
        self.gap_ms = None
        self.max_gap_ms = None

    def receive(self, message, now):
        if self.times:
            gap = max(0.0, now - self.times[-1])
            self.gap_ms = gap * 1000
            self.max_gap_ms = max(self.max_gap_ms or 0.0, self.gap_ms)
            if gap > self.stale_sec:
                self.times.clear()  # Re-estimate Hz after an interruption.
        self.times.append(now)
        self.frame_id = message.header.frame_id
        self.total = len(message.ranges)
        self.valid = 0
        self.nearest = None
        for value in message.ranges:
            if isfinite(value) and message.range_min <= value <= message.range_max:
                self.valid += 1
                self.nearest = value if self.nearest is None else min(self.nearest, value)

    def snapshot(self, now):
        age = max(0.0, now - self.times[-1]) * 1000 if self.times else None
        status = scan_status(age, self.stale_sec, self.offline_sec)
        elapsed = self.times[-1] - self.times[0] if self.times else 0
        rate = (len(self.times) - 1) / elapsed if elapsed > 0 else None
        return {
            "lidar_online": status == "ONLINE",
            "lidar_status": status,
            "scan_rate_hz": rate if status == "ONLINE" else None,
            "last_scan_age_ms": age,
            "scan_frame_id": self.frame_id,
            "scan_points_valid": self.valid,
            "scan_points_total": self.total,
            "nearest_obstacle_m": self.nearest,
            "scan_gap_ms": self.gap_ms,
            "scan_max_gap_ms": self.max_gap_ms,
            "scan_stale_sec": self.stale_sec,
            "scan_offline_sec": self.offline_sec,
        }
