import hashlib
import json
import math
import queue
import threading
import time
from collections import deque
from math import atan2
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Path
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformException, TransformListener

from .time_utils import ros_time_to_seconds, transform_timestamp


def quaternion_to_yaw(quaternion):
    return atan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0 - 2.0 * (quaternion.y ** 2 + quaternion.z ** 2),
    )


class WebBridge(Node):
    def __init__(self):
        super().__init__("web_bridge")

        self.declare_parameter("backend_url", "http://127.0.0.1:8000")
        self.declare_parameter("robot_id", 1)
        self.declare_parameter("map_topic", "/map")
        self.declare_parameter("scan_topic", "/scan")
        self.declare_parameter("navigation_path_topic", "/plan")
        self.declare_parameter("nav2_action_name", "/navigate_to_pose")
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("robot_base_frame", "base_link")
        self.declare_parameter("pose_publish_period_sec", 0.2)
        self.declare_parameter("heartbeat_period_sec", 1.0)
        self.declare_parameter("scan_stale_sec", 1.0)
        self.declare_parameter("map_stale_sec", 10.0)
        self.declare_parameter("navigation_poll_period_sec", 0.2)

        self.backend_url = str(
            self.get_parameter("backend_url").value
        ).rstrip("/")
        self.robot_id = int(self.get_parameter("robot_id").value)
        self.map_topic = str(self.get_parameter("map_topic").value)
        self.scan_topic = str(self.get_parameter("scan_topic").value)
        self.navigation_path_topic = str(
            self.get_parameter("navigation_path_topic").value
        )
        self.nav2_action_name = str(
            self.get_parameter("nav2_action_name").value
        )
        self.map_frame = str(self.get_parameter("map_frame").value)
        self.robot_base_frame = str(
            self.get_parameter("robot_base_frame").value
        )
        self.pose_period = float(
            self.get_parameter("pose_publish_period_sec").value
        )
        self.heartbeat_period = float(
            self.get_parameter("heartbeat_period_sec").value
        )
        self.scan_stale_sec = float(
            self.get_parameter("scan_stale_sec").value
        )
        self.map_stale_sec = float(
            self.get_parameter("map_stale_sec").value
        )
        self.navigation_poll_period = float(
            self.get_parameter("navigation_poll_period_sec").value
        )

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        map_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.map_sub = self.create_subscription(
            OccupancyGrid,
            self.map_topic,
            self._map_callback,
            map_qos,
        )
        self.scan_sub = self.create_subscription(
            LaserScan,
            self.scan_topic,
            self._scan_callback,
            10,
        )
        self.path_sub = self.create_subscription(
            Path,
            self.navigation_path_topic,
            self._path_callback,
            10,
        )

        self.nav_client = ActionClient(
            self,
            NavigateToPose,
            self.nav2_action_name,
        )
        self._navigation_command = None
        self._navigation_goal_handle = None
        self._navigation_state = "IDLE"
        self._navigation_feedback = {}
        self._last_path_signature = None
        self._next_navigation_poll = 0.0
        self._next_navigation_status = 0.0

        self._latest_map = None
        self._latest_map_hash = None
        self._sent_map_hash = None
        self._queued_map_hash = None
        self._last_map_received = None
        self._last_scan_received = None
        self._scan_times = deque(maxlen=20)
        self._last_pose = None
        self._next_pose_publish = 0.0
        self._next_heartbeat = 0.0
        self._last_warning = 0.0

        self._outbox = queue.Queue(maxsize=32)
        self._stop_sender = threading.Event()
        self._sender = threading.Thread(
            target=self._send_loop,
            name="web-bridge-http",
            daemon=True,
        )
        self._sender.start()
        self._timer = self.create_timer(0.1, self._publish_updates)

    def _map_callback(self, message):
        origin = message.info.origin
        origin_yaw = quaternion_to_yaw(origin.orientation)
        data = [int(value) for value in message.data]
        digest = hashlib.sha1(
            json.dumps(
                {
                    "width": int(message.info.width),
                    "height": int(message.info.height),
                    "resolution": float(message.info.resolution),
                    "origin": [
                        float(origin.position.x),
                        float(origin.position.y),
                        origin_yaw,
                    ],
                    "frame_id": message.header.frame_id or self.map_frame,
                    "data": data,
                },
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        self._latest_map = {
            "width": int(message.info.width),
            "height": int(message.info.height),
            "resolution": float(message.info.resolution),
            "origin": {
                "x": float(origin.position.x),
                "y": float(origin.position.y),
                "yaw": origin_yaw,
            },
            "frame_id": message.header.frame_id or self.map_frame,
            "timestamp": ros_time_to_seconds(message.header.stamp),
            "map_hash": digest,
            "data": data,
        }
        self._latest_map_hash = digest
        self._last_map_received = time.monotonic()

    def _scan_callback(self, _message):
        now = time.monotonic()
        self._last_scan_received = now
        self._scan_times.append(now)

    def _path_callback(self, message):
        if self._navigation_command is None:
            return

        poses = [
            {
                "x": float(pose.pose.position.x),
                "y": float(pose.pose.position.y),
            }
            for pose in message.poses
        ]
        payload = {
            "command_id": self._navigation_command["id"],
            "frame_id": message.header.frame_id or self.map_frame,
            "poses": poses,
        }
        signature = json.dumps(payload, separators=(",", ":"))
        if signature == self._last_path_signature:
            return

        self._last_path_signature = signature
        self._enqueue("/api/ros/navigation/path", payload)

    def _lookup_pose(self):
        try:
            transform = self.tf_buffer.lookup_transform(
                self.map_frame,
                self.robot_base_frame,
                Time(),
            )
        except TransformException:
            return None

        translation = transform.transform.translation
        return {
            "robot_id": self.robot_id,
            "frame_id": self.map_frame,
            "timestamp": transform_timestamp(transform, time.time()),
            "x": float(translation.x),
            "y": float(translation.y),
            "yaw": quaternion_to_yaw(transform.transform.rotation),
        }

    def _scan_rate(self):
        if len(self._scan_times) < 2:
            return None
        elapsed = self._scan_times[-1] - self._scan_times[0]
        return (len(self._scan_times) - 1) / elapsed if elapsed > 0 else None

    def _publish_updates(self):
        now = time.monotonic()

        if (
            self._latest_map is not None
            and self._latest_map_hash != self._sent_map_hash
            and self._latest_map_hash != self._queued_map_hash
        ):
            self._queued_map_hash = self._latest_map_hash
            self._enqueue(
                "/api/ros/map",
                self._latest_map,
                self._map_result,
            )

        if now >= self._next_pose_publish:
            self._next_pose_publish = now + self.pose_period
            pose = self._lookup_pose()
            self._last_pose = pose
            if pose is not None:
                self._enqueue("/api/ros/pose", pose)

        if now >= self._next_heartbeat:
            self._next_heartbeat = now + self.heartbeat_period
            scan_age = None
            if self._last_scan_received is not None:
                scan_age = (now - self._last_scan_received) * 1000.0

            map_received = self._last_map_received is not None
            map_fresh = map_received and (
                now - self._last_map_received <= self.map_stale_sec
            )
            lidar_online = (
                self._last_scan_received is not None
                and now - self._last_scan_received <= self.scan_stale_sec
            )
            self._enqueue(
                "/api/ros/state",
                {
                    "bridge_online": True,
                    "nav2_online": self.nav_client.server_is_ready(),
                    "slam_online": map_fresh,
                    "map_status": "RECEIVED" if map_received else "WAITING",
                    "lidar_online": lidar_online,
                    "localization_available": self._last_pose is not None,
                    "tf_available": self._last_pose is not None,
                    "scan_rate_hz": self._scan_rate(),
                    "last_scan_age_ms": scan_age,
                    "timestamp": time.time(),
                },
            )

        if now >= self._next_navigation_poll:
            self._next_navigation_poll = (
                now + self.navigation_poll_period
            )
            self._poll_navigation_command()

        if (
            self._navigation_command is not None
            and now >= self._next_navigation_status
        ):
            self._next_navigation_status = now + 0.2
            self._queue_navigation_status()

    def _poll_navigation_command(self):
        if not self.nav_client.server_is_ready():
            return

        command = self._get_json("/api/ros/navigation/command")
        if not command:
            return

        if command["command"] == "NAVIGATE_TO_POSE":
            if self._navigation_command is not None:
                return
            self._navigation_command = command
            self._navigation_state = "SENDING"
            self._navigation_feedback = {}
            self._last_path_signature = None
            self._send_navigation_goal(command)
            return

        if command["command"] == "CANCEL":
            if self._navigation_goal_handle is None:
                self._post_navigation_terminal(
                    command["id"],
                    "FAILED",
                    0,
                    "No active Nav2 goal",
                )
                return
            cancel_future = (
                self._navigation_goal_handle.cancel_goal_async()
            )
            active_command_id = self._navigation_command["id"]
            cancel_future.add_done_callback(
                lambda future: self._cancel_response_callback(
                    future,
                    active_command_id,
                )
            )

    def _send_navigation_goal(self, command):
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = self.map_frame
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(command["x"])
        goal.pose.pose.position.y = float(command["y"])
        goal.pose.pose.orientation.z = math.sin(float(command["yaw"]) / 2.0)
        goal.pose.pose.orientation.w = math.cos(float(command["yaw"]) / 2.0)

        send_future = self.nav_client.send_goal_async(
            goal,
            feedback_callback=self._feedback_callback,
        )
        send_future.add_done_callback(self._goal_response_callback)

    def _goal_response_callback(self, future):
        command = self._navigation_command
        if command is None:
            return
        command_id = command["id"]
        try:
            goal_handle = future.result()
        except Exception as error:
            self._post_navigation_terminal(
                command_id,
                "FAILED",
                0,
                str(error),
            )
            return

        if not goal_handle.accepted:
            self._post_navigation_terminal(
                command_id,
                "REJECTED",
                0,
                "Nav2 rejected the goal",
            )
            return

        self._navigation_goal_handle = goal_handle
        self._navigation_state = "NAVIGATING"
        self._queue_navigation_status(force=True)
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._result_callback)

    def _feedback_callback(self, feedback_message):
        feedback = feedback_message.feedback
        current = feedback.current_pose.pose
        self._navigation_feedback = {
            "distance_remaining": self._finite_or_none(
                feedback.distance_remaining
            ),
            "current_pose": {
                "x": float(current.position.x),
                "y": float(current.position.y),
                "yaw": quaternion_to_yaw(current.orientation),
            },
            "navigation_time": (
                float(feedback.navigation_time.sec)
                + float(feedback.navigation_time.nanosec) * 1e-9
            ),
            "number_of_recoveries": max(
                0,
                int(feedback.number_of_recoveries),
            ),
        }

    def _cancel_response_callback(self, future, command_id):
        try:
            response = future.result()
            if not response.goals_canceling:
                self._post_navigation_terminal(
                    command_id,
                    "FAILED",
                    0,
                    "Nav2 did not accept cancel",
                )
        except Exception as error:
            self._post_navigation_terminal(
                command_id,
                "FAILED",
                0,
                str(error),
            )

    def _result_callback(self, future):
        command = self._navigation_command
        if command is None:
            return
        command_id = command["id"]
        try:
            result_wrapper = future.result()
            result = result_wrapper.result
            if result_wrapper.status == GoalStatus.STATUS_CANCELED:
                state = "CANCELLED"
            elif (
                result_wrapper.status == GoalStatus.STATUS_SUCCEEDED
                and int(result.error_code) == 0
            ):
                state = "SUCCEEDED"
            else:
                state = "FAILED"
            if state == "SUCCEEDED":
                self._navigation_feedback["distance_remaining"] = 0.0
            self._post_navigation_terminal(
                command_id,
                state,
                int(result.error_code),
                str(result.error_msg),
            )
        except Exception as error:
            self._post_navigation_terminal(
                command_id,
                "FAILED",
                0,
                str(error),
            )

    def _queue_navigation_status(self, force=False):
        if self._navigation_command is None:
            return

        if not force and self._navigation_state == "IDLE":
            return

        payload = {
            "command_id": self._navigation_command["id"],
            "state": self._navigation_state,
            "distance_remaining": self._navigation_feedback.get(
                "distance_remaining"
            ),
            "current_pose": self._navigation_feedback.get("current_pose"),
            "navigation_time": self._navigation_feedback.get(
                "navigation_time"
            ),
            "number_of_recoveries": self._navigation_feedback.get(
                "number_of_recoveries",
                0,
            ),
            "error_code": 0,
            "error_message": "",
        }
        self._enqueue(
            "/api/ros/navigation/command/"
            f"{self._navigation_command['id']}/status",
            payload,
        )

    def _post_navigation_terminal(
        self,
        command_id,
        state,
        error_code,
        error_message,
    ):
        payload = {
            "command_id": command_id,
            "state": state,
            "distance_remaining": self._navigation_feedback.get(
                "distance_remaining"
            ),
            "current_pose": self._navigation_feedback.get("current_pose"),
            "navigation_time": self._navigation_feedback.get(
                "navigation_time"
            ),
            "number_of_recoveries": self._navigation_feedback.get(
                "number_of_recoveries",
                0,
            ),
            "error_code": error_code,
            "error_message": error_message,
        }
        self._enqueue(
            "/api/ros/navigation/command/"
            f"{command_id}/status",
            payload,
        )
        self._navigation_state = state
        self._navigation_goal_handle = None
        self._navigation_command = None
        self._last_path_signature = None

    @staticmethod
    def _finite_or_none(value):
        value = float(value)
        return value if math.isfinite(value) else None

    def _map_result(self, success):
        if success:
            self._sent_map_hash = self._queued_map_hash
        self._queued_map_hash = None

    def _enqueue(self, endpoint, payload, callback=None):
        try:
            self._outbox.put_nowait((endpoint, payload, callback))
        except queue.Full:
            if callback is not None:
                callback(False)
            now = time.monotonic()
            if now - self._last_warning > 5.0:
                self._last_warning = now
                self.get_logger().warning(
                    "WRMS backend queue is full; dropping telemetry"
                )

    def _send_loop(self):
        while not self._stop_sender.is_set():
            try:
                endpoint, payload, callback = self._outbox.get(timeout=0.2)
            except queue.Empty:
                continue

            success = self._post_json(endpoint, payload)
            if callback is not None:
                callback(success)

    def _get_json(self, endpoint):
        try:
            with urlopen(
                self.backend_url + endpoint,
                timeout=0.2,
            ) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except (HTTPError, OSError, ValueError):
            return None

    def _post_json(self, endpoint, payload):
        request = Request(
            self.backend_url + endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=1.0) as response:
                response.read()
                return 200 <= response.status < 300
        except Exception as exc:
            now = time.monotonic()
            if now - self._last_warning > 5.0:
                self._last_warning = now
                self.get_logger().warning(
                    f"WRMS backend unavailable: {exc}"
                )
            return False

    def destroy_node(self):
        self._stop_sender.set()
        self._sender.join(timeout=1.5)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = WebBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
