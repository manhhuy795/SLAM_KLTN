from copy import deepcopy
from threading import Lock


class RosState:
    def __init__(self):
        self._lock = Lock()
        self._status = {
            "bridge_online": False,
            "slam_online": False,
            "map_status": "WAITING",
            "lidar_online": False,
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
            return deepcopy(self._status)

    def get_status(self):
        with self._lock:
            return deepcopy(self._status)

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
