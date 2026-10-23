"""Thread-safe in-memory telemetry and command mailbox for hardware-tested AGV."""
from collections import deque
from threading import Lock
from time import monotonic, time
import secrets

ONLINE_TIMEOUT_SEC = 2.5
PENDING_TIMEOUT_SEC = 15.0
MAP_WIDTH_M = 1.54
MAP_HEIGHT_M = 1.51

COMMANDS = {
    "start": "START",
    "stop": "STOP",
    "test_forward": "TEST_FORWARD",
    "reset_odom": "RESET_ODOM",
    "calibrate_gyro": "CALIBRATE_GYRO",
    "mission_next": "MISSION:NEXT",
    "auto_loop_on": "AUTO_LOOP:ON",
    "auto_loop_off": "AUTO_LOOP:OFF",
    "turn_left_90": "TURN_LEFT_90",
    "turn_right_90": "TURN_RIGHT_90",
    "turn_180": "TURN_180",
}


def status_from_firmware(value):
    if value in {"STOPPED", "AT_STATION"}:
        return "IDLE"
    if value in {"PAUSED_AT_STATION"}:
        return "PAUSED"
    if value.startswith("LOST_") or value in {"COMM_LOSS_STOP"}:
        return "ERROR"
    return "MOVING"


class AgvRuntime:
    def __init__(self):
        self._lock = Lock()
        self._robots = {}

    def _entry(self, code):
        entry = self._robots.get(code)
        if entry is None:
            entry = {
                "last_seen": None,
                "last_seen_wall": None,
                "telemetry": None,
                "trail": deque(maxlen=1000),
                "logs": deque(maxlen=5000),
                "pending": None,
                "last_ack_id": 0,
                "last_command": None,
                "command_status": "NONE",
                "next_id": secrets.randbelow(900_000_000) + 1_000_000,
            }
            self._robots[code] = entry
        return entry

    def _expire(self, entry, now):
        pending = entry["pending"]
        if pending and now - pending["created_at"] > PENDING_TIMEOUT_SEC:
            entry["last_command"] = pending["cmd"]
            entry["command_status"] = "TIMEOUT"
            entry["pending"] = None

    def ingest(self, code, telemetry):
        now = monotonic()
        data = dict(telemetry)
        with self._lock:
            entry = self._entry(code)
            self._expire(entry, now)
            entry["telemetry"] = data
            entry["last_seen"] = now
            entry["last_seen_wall"] = time()
            entry["last_ack_id"] = data["ack_id"]

            trail = entry["trail"]
            point = [round(data["x"], 3), round(data["y"], 3)]
            if not trail or (point[0]-trail[-1][0])**2 + (point[1]-trail[-1][1])**2 >= 0.0004:
                trail.append(point)

            entry["logs"].append({"timestamp": entry["last_seen_wall"], **data})
            pending = entry["pending"]
            if pending and data["ack_id"] == pending["id"]:
                if pending["cmd"] == "RESET_ODOM":
                    trail.clear()
                    trail.append(point)
                entry["last_command"] = pending["cmd"]
                entry["command_status"] = "ACKNOWLEDGED"
                entry["pending"] = None

            pending = entry["pending"]
            return {
                "status": "ok",
                "cmd": pending["cmd"] if pending else None,
                "cmd_id": pending["id"] if pending else 0,
            }

    def command(self, code, cmd):
        now = monotonic()
        with self._lock:
            entry = self._entry(code)
            self._expire(entry, now)
            connected = (entry["last_seen"] is not None
                         and now - entry["last_seen"] <= ONLINE_TIMEOUT_SEC)
            if cmd != "STOP" and not connected:
                raise ValueError("AGV offline: cannot send motion command")
            pending = entry["pending"]
            if pending and pending["cmd"] == "STOP" and cmd == "STOP":
                return {"cmd_id": pending["id"], "cmd": "STOP", "status": "pending"}
            if pending and cmd != "STOP":
                raise ValueError("Another AGV command is pending acknowledgement")
            entry["next_id"] += 1
            if entry["next_id"] >= 2_000_000_000:
                entry["next_id"] = 1_000_000
            entry["pending"] = {
                "id": entry["next_id"],
                "cmd": cmd,
                "created_at": now,
            }
            entry["last_command"] = cmd
            entry["command_status"] = "PENDING"
            return {"cmd_id": entry["next_id"], "cmd": cmd, "status": "pending"}

    def online(self, code):
        with self._lock:
            entry = self._robots.get(code)
            return bool(entry and entry["last_seen"] is not None
                        and monotonic() - entry["last_seen"] <= ONLINE_TIMEOUT_SEC)

    def get(self, code, commands_enabled=False):
        now = monotonic()
        with self._lock:
            entry = self._entry(code)
            self._expire(entry, now)
            seen = entry["last_seen"]
            age = None if seen is None else round((now - seen) * 1000)
            return {
                "robot_code": code,
                "connected": age is not None and age <= ONLINE_TIMEOUT_SEC * 1000,
                "last_seen_age_ms": age,
                "last_seen_ts": entry["last_seen_wall"],
                "telemetry": dict(entry["telemetry"]) if entry["telemetry"] else None,
                "trail": list(entry["trail"]),
                "pending_command": (
                    {"id": entry["pending"]["id"], "cmd": entry["pending"]["cmd"]}
                    if entry["pending"] else None
                ),
                "last_ack_id": entry["last_ack_id"],
                "last_command": entry["last_command"],
                "command_status": entry["command_status"],
                "commands_enabled": commands_enabled,
                "map": {"width": MAP_WIDTH_M, "height": MAP_HEIGHT_M,
                        "frame_id": "agv_line_local", "x_right": True, "y_down": True},
            }

    def logs(self, code, limit=200):
        with self._lock:
            return list(self._entry(code)["logs"])[-limit:]

    def clear_logs(self, code):
        with self._lock:
            self._entry(code)["logs"].clear()


agv_runtime = AgvRuntime()
