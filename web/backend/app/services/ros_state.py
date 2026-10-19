from copy import deepcopy
from threading import Lock
from time import monotonic


class RosState:
    def __init__(self, heartbeat_timeout_sec=3.0):
        self._lock = Lock()
        self.heartbeat_timeout_sec = heartbeat_timeout_sec
        self._last_heartbeat_monotonic = None
        self._status = {
            "bridge_online": False,
            "nav2_online": False,
            "slam_online": False,
            "map_status": "WAITING",
            "lidar_online": False,
            "lidar_status": "OFFLINE",
            "localization_available": False,
            "tf_available": False,
            "scan_rate_hz": None,
            "last_scan_age_ms": None,
            "timestamp": None,
        }
        self._map = None
        self._pose = None

    def set_status(self, data):
        with self._lock:
            self._status = dict(data)
            self._last_heartbeat_monotonic = monotonic()
            return deepcopy(self._status)

    def get_status(self, now=None):
        with self._lock:
            status = deepcopy(self._status)
            current_time = monotonic() if now is None else now
            heartbeat_missing = self._last_heartbeat_monotonic is None
            heartbeat_expired = (
                not heartbeat_missing
                and current_time - self._last_heartbeat_monotonic
                > self.heartbeat_timeout_sec
            )

            status["heartbeat_age_ms"] = (
                None if heartbeat_missing else
                max(0.0, current_time - self._last_heartbeat_monotonic) * 1000
            )
            status["heartbeat_timeout_sec"] = self.heartbeat_timeout_sec
            if not heartbeat_missing and status.get("last_scan_age_ms") is not None:
                status["last_scan_age_ms"] += status["heartbeat_age_ms"]
            if status.get("scan_stale_sec") is not None:
                age = status.get("last_scan_age_ms")
                if age is None or age > status["scan_offline_sec"] * 1000:
                    lidar_status = "OFFLINE"
                elif age > status["scan_stale_sec"] * 1000:
                    lidar_status = "STALE"
                else:
                    lidar_status = "ONLINE"
                status["lidar_status"] = lidar_status
                status["lidar_online"] = lidar_status == "ONLINE"
                if not status["lidar_online"]:
                    status["scan_rate_hz"] = None

            if heartbeat_missing or heartbeat_expired:
                status.update({
                    "bridge_online": False,
                    "nav2_online": False,
                    "slam_online": False,
                    "lidar_online": False,
                    "lidar_status": "OFFLINE",
                    "localization_available": False,
                    "tf_available": False,
                    "scan_rate_hz": None,
                    "last_scan_age_ms": None,
                })

            return status

    def set_map(self, data):
        with self._lock:
            changed = (
                self._map is None
                or self._map.get("map_hash") != data["map_hash"]
            )
            self._map = dict(data)
            return changed, deepcopy(self._map)

    def get_map(self):
        with self._lock:
            return deepcopy(self._map)

    def set_pose(self, data):
        with self._lock:
            self._pose = dict(data)
            return deepcopy(self._pose)

    def get_pose(self):
        with self._lock:
            return deepcopy(self._pose)


ros_state = RosState()
