import hashlib
import json
import queue
import threading
import time
from collections import deque
from math import atan2
from urllib.request import Request, urlopen

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformException, TransformListener


def quaternion_to_yaw(quaternion):
    return atan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0 - 2.0 * (quaternion.y ** 2 + quaternion.z ** 2),
    )


def ros_time_to_seconds(stamp):
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


class WebBridge(Node):
    def __init__(self):
        super().__init__("web_bridge")

        self.declare_parameter("backend_url", "http://127.0.0.1:8000")
        self.declare_parameter("robot_id", 1)
        self.declare_parameter("map_topic", "/map")
        self.declare_parameter("scan_topic", "/scan")
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("robot_base_frame", "base_link")
        self.declare_parameter("pose_publish_period_sec", 0.2)
        self.declare_parameter("heartbeat_period_sec", 1.0)
        self.declare_parameter("scan_stale_sec", 1.0)
        self.declare_parameter("map_stale_sec", 10.0)

        self.backend_url = str(self.get_parameter("backend_url").value).rstrip("/")
        self.robot_id = int(self.get_parameter("robot_id").value)
        self.map_topic = str(self.get_parameter("map_topic").value)
        self.scan_topic = str(self.get_parameter("scan_topic").value)
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

        self._outbox = queue.Queue(maxsize=16)
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
            "timestamp": time.time(),
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
