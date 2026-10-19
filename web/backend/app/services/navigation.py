from copy import deepcopy
from threading import Lock
from time import time


TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED", "REJECTED"}


class NavigationState:
    def __init__(self):
        self._lock = Lock()
        self._next_command_id = 1
        self._pending = None
        self._commands = {}
        self._path = None
        self._status = {
            "state": "IDLE",
            "nav2_online": False,
            "command_id": None,
            "goal": None,
            "distance_remaining": None,
            "current_pose": None,
            "navigation_time": None,
            "number_of_recoveries": 0,
            "error_code": 0,
            "error_message": "",
            "cancel_requested": False,
            "timestamp": None,
        }

    def create_goal(self, x, y, yaw, location=None, task=None, planning_point=None):
        from app.services.map_session import map_session
        with map_session.lock:
            context = map_session.guard()
            return self._create_goal(x, y, yaw, location, task, planning_point,
                                     context if context.get("enabled") else None)

    def _create_goal(self, x, y, yaw, location, task, planning_point, context):
        with self._lock:
            if self._status["state"] in {"SENDING", "NAVIGATING"}:
                raise ValueError("Navigation is already active")

            command_id = self._next_command_id
            self._next_command_id += 1
            goal = {"frame_id": "map", "x": x, "y": y, "yaw": yaw}
            if context:
                goal["map_context"] = {k: context.get(k) for k in ("session_id", "map_id", "map_hash")}
            if planning_point:
                goal["planning_point"] = deepcopy(planning_point)
            if location is not None:
                goal["location"] = deepcopy(location)
            if task is not None:
                goal["task"] = deepcopy(task)
            command = {
                "id": command_id,
                "command": "NAVIGATE_TO_POSE",
                **goal,
            }
            self._commands[command_id] = command
            self._pending = command
            self._path = None
            self._status = {
                **self._status,
                "state": "SENDING",
                "command_id": command_id,
                "goal": goal,
                "distance_remaining": None,
                "current_pose": None,
                "navigation_time": None,
                "number_of_recoveries": 0,
                "error_code": 0,
                "error_message": "",
                "cancel_requested": False,
                "timestamp": time(),
            }
            return deepcopy(self._status)

    def create_cancel(self):
        with self._lock:
            if self._status["state"] not in {"SENDING", "NAVIGATING"}:
                raise ValueError("Navigation is not active")

            if (
                self._pending is not None
                and self._pending["command"] == "NAVIGATE_TO_POSE"
                and not self._pending.get("claimed")
            ):
                # No bridge has taken the goal: do not send it to Nav2 at all.
                self._pending = None
                self._status["state"] = "CANCELLED"
                self._status["cancel_requested"] = False
                self._status["timestamp"] = time()
                return deepcopy(self._status)

            command_id = self._next_command_id
            self._next_command_id += 1
            command = {
                "id": command_id,
                "command": "CANCEL",
                "navigation_command_id": self._status["command_id"],
            }
            self._commands[command_id] = command
            self._pending = command
            self._status["cancel_requested"] = True
            self._status["timestamp"] = time()
            return deepcopy(self._status)

    def claim_pending(self):
        with self._lock:
            if self._pending is None or self._pending.get("claimed"):
                return None
            self._pending["claimed"] = True
            return deepcopy(self._pending)

    def set_status(self, command_id, data):
        with self._lock:
            command = self._commands.get(command_id)
            if command is None:
                raise KeyError("Navigation command not found")

            target_id = command.get("navigation_command_id", command_id)
            if target_id != self._status["command_id"]:
                raise KeyError("Navigation command is no longer active")
            if self._status["state"] in TERMINAL_STATES:
                return deepcopy(self._status)

            for key in (
                "state",
                "distance_remaining",
                "current_pose",
                "navigation_time",
                "number_of_recoveries",
                "error_code",
                "error_message",
                "cancel_requested",
            ):
                if key in data:
                    self._status[key] = data[key]

            if data.get("state") in TERMINAL_STATES:
                self._status["cancel_requested"] = False
                self._path = None
                self._pending = None

            self._status["timestamp"] = time()
            return deepcopy(self._status)

    def set_path(self, command_id, data):
        with self._lock:
            if command_id != self._status["command_id"]:
                raise KeyError("Navigation command is no longer active")
            if self._status["state"] in TERMINAL_STATES:
                raise KeyError("Navigation command has already finished")
            self._path = {
                "frame_id": data["frame_id"],
                "poses": data["poses"],
            }
            return deepcopy(self._path)

    def set_nav2_online(self, value):
        with self._lock:
            self._status["nav2_online"] = bool(value)
            return deepcopy(self._status)

    def get_status(self):
        with self._lock:
            return deepcopy(self._status)

    def get_path(self):
        with self._lock:
            return deepcopy(self._path)


navigation_state = NavigationState()
