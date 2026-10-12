import math
import time

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import TransformStamped, Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rcl_interfaces.msg import SetParametersResult
from std_msgs.msg import Bool
from tf2_ros import TransformBroadcaster

from .kinematics import EncoderOdometry, twist_to_wheel_velocities
from .protocol import (
    emergency_stop_command,
    LineBuffer,
    parse_encoder_packet,
    stop_command,
    velocity_command,
)
from .safety import SafetyState

try:
    import serial
except ImportError:  # The node stays alive and reports the missing dependency.
    serial = None


def quaternion_from_yaw(yaw: float) -> tuple[float, float]:
    return math.sin(yaw / 2.0), math.cos(yaw / 2.0)


class HardwareBridgeNode(Node):
    def __init__(self, **kwargs):
        super().__init__("amr_hardware", **kwargs)

        self.wheel_radius = self._positive("wheel_radius", 0.0325)
        self.wheel_separation = self._positive("wheel_separation", 0.25)
        self.ticks_per_revolution = self._positive(
            "encoder_ticks_per_revolution", 600.0,
        )
        self.gear_ratio = self._positive("gear_ratio", 1.0)
        self.counter_bits = int(self.declare_parameter(
            "encoder_counter_bits", 32,
        ).value)
        self.max_ticks_per_second = self._positive(
            "max_encoder_ticks_per_second", 20000.0,
        )
        self.max_linear_velocity = self._positive(
            "max_linear_velocity", 0.22,
        )
        self.max_angular_velocity = self._positive(
            "max_angular_velocity", 1.0,
        )
        self.max_wheel_velocity = self._positive("max_wheel_velocity", 0.35)
        self.cmd_vel_timeout = self._positive("cmd_vel_timeout", 0.5)
        self.encoder_timeout = self._positive("encoder_timeout", 0.5)
        self.serial_port = self.declare_parameter(
            "serial_port", "/dev/ttyACM0",
        ).value
        self.baudrate = int(self.declare_parameter(
            "baudrate", 115200,
        ).value)
        self.reconnect_interval = self._positive(
            "reconnect_interval", 1.0,
        )
        self.max_malformed_packets = int(self.declare_parameter(
            "max_malformed_packets", 5,
        ).value)
        self.cmd_vel_topic = self.declare_parameter(
            "cmd_vel_topic", "/cmd_vel",
        ).value
        self.odom_topic = self.declare_parameter(
            "odom_topic", "/odom",
        ).value
        self.odom_frame = self.declare_parameter(
            "odom_frame", "odom",
        ).value
        self.base_frame = self.declare_parameter(
            "base_frame", "base_link",
        ).value
        if not 2 <= self.counter_bits <= 32 or self.max_malformed_packets < 1:
            raise ValueError(
                "encoder_counter_bits must be 2..32 and "
                "max_malformed_packets must be >= 1"
            )
        if self.baudrate <= 0 or not self.serial_port:
            raise ValueError("baudrate must be positive and serial_port nonempty")
        if not self.odom_frame or not self.base_frame or self.odom_frame == self.base_frame:
            raise ValueError("odom_frame and base_frame must be distinct and nonempty")

        self.odometry = EncoderOdometry(
            self.wheel_radius,
            self.wheel_separation,
            self.ticks_per_revolution,
            self.gear_ratio,
            self.counter_bits,
            self.max_ticks_per_second,
        )
        self.safety = SafetyState(self.cmd_vel_timeout)
        self.connection = None
        self.connection_error = ""
        self.fault_reason = "startup: clear emergency stop after encoder is online"
        self.rx = LineBuffer()
        self.last_packet = None
        self.sequence = 0
        self.malformed_packets = 0
        self.last_encoder_time = None
        self.left_count = 0
        self.right_count = 0
        self.left_target = 0.0
        self.right_target = 0.0

        self.odom_publisher = self.create_publisher(
            Odometry, self.odom_topic, 20,
        )
        self.status_publisher = self.create_publisher(
            DiagnosticArray, "/hardware/status", 10,
        )
        self.tf_broadcaster = TransformBroadcaster(self)
        self.create_subscription(
            Twist, self.cmd_vel_topic, self._on_cmd_vel, 1,
        )
        self.create_subscription(
            Bool, "/hardware/emergency_stop", self._on_emergency_stop, 10,
        )
        # Safety must keep ticking even if someone sets use_sim_time with no /clock.
        wall_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(0.01, self._read_serial, clock=wall_clock)
        self.create_timer(0.05, self._watchdog, clock=wall_clock)
        self.create_timer(self.reconnect_interval, self._connect, clock=wall_clock)
        self.create_timer(0.5, self._publish_status, clock=wall_clock)
        self.add_on_set_parameters_callback(lambda params: SetParametersResult(
            successful=False, reason="Hardware parameters require a node restart",
        ))
        self._connect()

    def _positive(self, name, default):
        value = float(self.declare_parameter(name, default).value)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and positive")
        return value

    def _next_sequence(self):
        self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        return self.sequence

    def _connect(self):
        if self.connection is not None or serial is None:
            return
        try:
            self.connection = serial.Serial(
                self.serial_port,
                self.baudrate,
                timeout=0,
                write_timeout=0.1,
                exclusive=True,
            )
            self.connection.reset_input_buffer()
            self.connection_error = ""
            self.rx = LineBuffer()
            self.last_packet = None
            self.last_encoder_time = None
            self.malformed_packets = 0
            self.odometry.reset_encoder_reference()
            self.safety.set_emergency_stop(True)
            self.fault_reason = "connected: clear emergency stop after encoder is online"
            self.left_target = self.right_target = 0.0
            self._write(stop_command(self._next_sequence()))
            self._write(emergency_stop_command(
                self._next_sequence(), self.safety.emergency_stop,
            ))
            if self.connection is None:
                return
            self.get_logger().info(
                f"Connected to {self.serial_port} at {self.baudrate} baud"
            )
        except Exception as error:
            if self.connection is not None:
                self._disconnect(error)
            message = str(error)
            if message != self.connection_error:
                self.get_logger().warning(
                    f"Serial connection unavailable: {message}"
                )
            self.connection_error = message

    def _disconnect(self, reason):
        connection, self.connection = self.connection, None
        self.connection_error = str(reason)
        self.last_encoder_time = None
        self.last_packet = None
        self.odometry.reset_encoder_reference()
        self.safety.set_emergency_stop(True)
        self.fault_reason = "serial disconnected; clear required after reconnect"
        self.left_target = self.right_target = 0.0
        self.safety.motion_command_active = False
        if connection is not None:
            try:
                connection.write(
                    stop_command(self._next_sequence()).encode("ascii")
                )
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass
        self.get_logger().error(f"Serial disconnected: {reason}")

    def _write(self, line):
        if self.connection is None:
            return False
        try:
            data = line.encode("ascii")
            if self.connection.write(data) != len(data):
                raise OSError("short serial write")
            return True
        except Exception as error:
            self._disconnect(error)
            return False

    def _send_stop(self):
        self.left_target = self.right_target = 0.0
        self.safety.motion_command_active = False
        self._write(stop_command(self._next_sequence()))

    def _on_cmd_vel(self, message):
        now = time.monotonic()
        if self.connection is None or not self._encoder_online(now):
            self._send_stop()
            return
        if not all(math.isfinite(v) for v in (message.linear.x, message.angular.z)):
            self._fault("non-finite cmd_vel")
            return
        if not self.safety.accept_command(now):
            self._send_stop()
            return
        self.left_target, self.right_target = twist_to_wheel_velocities(
            message.linear.x,
            message.angular.z,
            self.wheel_separation,
            self.max_linear_velocity,
            self.max_angular_velocity,
            self.max_wheel_velocity,
        )
        self._write(velocity_command(
            self._next_sequence(), self.left_target, self.right_target,
        ))

    def _on_emergency_stop(self, message):
        active = bool(message.data)
        if not active and not self._encoder_online(time.monotonic()):
            self._fault("cannot clear emergency stop without fresh encoder feedback")
            return
        self._send_stop()
        self.safety.set_emergency_stop(active)
        self.fault_reason = "operator emergency stop" if active else ""
        self._write(emergency_stop_command(self._next_sequence(), active))
        if active:
            self.get_logger().error("Software emergency stop active")
        else:
            self.get_logger().warning(
                "Software emergency stop cleared; waiting for a new cmd_vel"
            )

    def _watchdog(self):
        if self.last_encoder_time is not None and not self._encoder_online(time.monotonic()):
            self.last_encoder_time = None
            self.odometry.reset_encoder_reference()
            self._fault("encoder timeout")
        if self.safety.consume_timeout(time.monotonic()):
            self.get_logger().warning("cmd_vel timeout; stopping motors")
            self._send_stop()

    def _encoder_online(self, now):
        return (
            self.connection is not None and self.last_encoder_time is not None
            and now - self.last_encoder_time <= self.encoder_timeout
        )

    def _fault(self, reason):
        self.safety.set_emergency_stop(True)
        self.fault_reason = reason
        self._send_stop()
        self._write(emergency_stop_command(self._next_sequence(), True))
        self.get_logger().error(reason)

    def _read_serial(self):
        if self.connection is None:
            return
        try:
            # Bounded work prevents a noisy device from starving safety callbacks.
            raw_data = self.connection.read(min(self.connection.in_waiting, 4096))
            for raw in self.rx.feed(raw_data):
                try:
                    if raw is None:
                        raise ValueError("serial line exceeds 128 bytes")
                    packet = parse_encoder_packet(raw.decode("ascii"))
                    bound = 1 << (self.counter_bits - 1)
                    if not all(-bound <= n < bound for n in (packet.left_count, packet.right_count)):
                        raise ValueError("count outside configured counter width")
                except (UnicodeDecodeError, ValueError) as error:
                    self.malformed_packets += 1
                    self.get_logger().warning(f"Malformed serial packet: {error}")
                    if self.malformed_packets >= self.max_malformed_packets:
                        self._fault("too many malformed packets")
                        self._disconnect("too many malformed packets")
                        return
                    continue

                self.malformed_packets = 0
                if self.last_packet is not None:
                    if packet.boot_id != self.last_packet.boot_id:
                        self._fault("ESP32 reset detected")
                        self.odometry.reset_encoder_reference()
                    else:
                        delta_seq = (packet.sequence - self.last_packet.sequence) % (2**32)
                        if not 0 < delta_seq < 2**31:
                            continue  # Duplicate/stale packets never refresh the watchdog.
                self.last_packet = packet
                self.left_count = packet.left_count
                self.right_count = packet.right_count
                try:
                    update = self.odometry.update(
                        packet.left_count, packet.right_count, packet.timestamp_ms,
                    )
                except ValueError as error:
                    self.last_encoder_time = None
                    self._fault(str(error))
                    continue
                self.last_encoder_time = time.monotonic()
                if update is not None:
                    self._publish_odometry(update)
        except Exception as error:
            self._disconnect(error)

    def _publish_odometry(self, update):
        stamp = self.get_clock().now().to_msg()
        z, w = quaternion_from_yaw(update.yaw)

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self.odom_frame
        odom.child_frame_id = self.base_frame
        odom.pose.pose.position.x = update.x
        odom.pose.pose.position.y = update.y
        odom.pose.pose.orientation.z = z
        odom.pose.pose.orientation.w = w
        odom.twist.twist.linear.x = update.linear_velocity
        odom.twist.twist.angular.z = update.angular_velocity
        self.odom_publisher.publish(odom)

        transform = TransformStamped()
        transform.header.stamp = stamp
        transform.header.frame_id = self.odom_frame
        transform.child_frame_id = self.base_frame
        transform.transform.translation.x = update.x
        transform.transform.translation.y = update.y
        transform.transform.rotation.z = z
        transform.transform.rotation.w = w
        self.tf_broadcaster.sendTransform(transform)

    def _publish_status(self):
        now = time.monotonic()
        command_age = (
            now - self.safety.last_command_time
            if self.safety.last_command_time is not None else math.inf
        )
        encoder_age = (
            now - self.last_encoder_time
            if self.last_encoder_time is not None else math.inf
        )
        connected = self.connection is not None
        encoder_online = connected and encoder_age <= self.encoder_timeout
        if self.safety.emergency_stop:
            level, message = DiagnosticStatus.ERROR, "emergency stop active"
        elif not connected:
            level, message = DiagnosticStatus.ERROR, "serial disconnected"
        elif not encoder_online:
            level, message = DiagnosticStatus.WARN, "encoder timeout"
        else:
            level, message = DiagnosticStatus.OK, "hardware online"

        status = DiagnosticStatus(
            level=level,
            name="amr_hardware/base",
            hardware_id=self.serial_port,
            message=message,
            values=[
                KeyValue(key="serial_connected", value=str(connected).lower()),
                KeyValue(key="encoder_online", value=str(encoder_online).lower()),
                KeyValue(key="encoder_age_s", value=f"{encoder_age:.3f}"),
                KeyValue(key="cmd_vel_age_s", value=f"{command_age:.3f}"),
                KeyValue(
                    key="emergency_stop",
                    value=str(self.safety.emergency_stop).lower(),
                ),
                KeyValue(key="left_encoder_count", value=str(self.left_count)),
                KeyValue(key="right_encoder_count", value=str(self.right_count)),
                KeyValue(key="left_target_mps", value=f"{self.left_target:.6f}"),
                KeyValue(key="right_target_mps", value=f"{self.right_target:.6f}"),
                KeyValue(
                    key="malformed_packets",
                    value=str(self.malformed_packets),
                ),
                KeyValue(key="serial_error", value=self.connection_error),
                KeyValue(key="fault_reason", value=self.fault_reason),
                KeyValue(key="last_encoder_timestamp_ms", value=(
                    str(self.last_packet.timestamp_ms) if self.last_packet else "none"
                )),
                KeyValue(key="boot_id", value=(
                    str(self.last_packet.boot_id) if self.last_packet else "none"
                )),
            ],
        )
        diagnostics = DiagnosticArray()
        diagnostics.header.stamp = self.get_clock().now().to_msg()
        diagnostics.status = [status]
        self.status_publisher.publish(diagnostics)

    def shutdown_hardware(self):
        self._send_stop()
        connection, self.connection = self.connection, None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def main(args=None):
    rclpy.init(args=args)
    node = HardwareBridgeNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            node.shutdown_hardware()
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        except KeyboardInterrupt:
            pass
