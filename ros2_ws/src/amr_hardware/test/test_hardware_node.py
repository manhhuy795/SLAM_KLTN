"""Real pyserial over Linux PTY + ROS topics. No physical motors are connected."""

import os
import pty
import time
import unittest
from unittest.mock import patch

from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.parameter import Parameter
from std_msgs.msg import Bool
from tf2_msgs.msg import TFMessage

from amr_hardware.node import HardwareBridgeNode


class HardwareNodeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = Context()
        # Never exercise /cmd_vel in the simulation/default domain.
        rclpy.init(context=cls.context, domain_id=101 + os.getpid() % 80)

    @classmethod
    def tearDownClass(cls):
        cls.context.shutdown()

    def drain(self):
        try:
            while True:
                self.writes += os.read(self.master, 4096).decode("ascii")
        except BlockingIOError:
            pass

    def spin_until(self, predicate, timeout=8.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.executor.spin_once(timeout_sec=0.01)
            self.drain()
            if predicate():
                return True
        return False

    def setUp(self):
        self.master, self.slave = pty.openpty()
        os.set_blocking(self.master, False)
        self.writes = ""
        self.node = HardwareBridgeNode(context=self.context, parameter_overrides=[
            Parameter("serial_port", value=os.ttyname(self.slave)),
            Parameter("cmd_vel_timeout", value=0.3),
            Parameter("encoder_timeout", value=5.0),
            Parameter("wheel_radius", value=0.1),
            Parameter("wheel_separation", value=0.5),
            Parameter("encoder_ticks_per_revolution", value=100.0),
        ])
        self.probe = rclpy.create_node("hardware_test_probe", context=self.context)
        self.odom, self.status, self.tf = [], [], []
        self.probe.create_subscription(Odometry, "/odom", self.odom.append, 10)
        self.probe.create_subscription(
            DiagnosticArray, "/hardware/status", self.status.append, 10,
        )
        self.probe.create_subscription(TFMessage, "/tf", self.tf.append, 10)
        self.cmd = self.probe.create_publisher(Twist, "/cmd_vel", 1)
        self.estop = self.probe.create_publisher(Bool, "/hardware/emergency_stop", 10)
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)
        self.executor.add_node(self.probe)
        self.assertTrue(self.spin_until(
            lambda: self.cmd.get_subscription_count() == 1
            and self.estop.get_subscription_count() == 1
            and self.node.odom_publisher.get_subscription_count() == 1
        ))

    def tearDown(self):
        self.node.shutdown_hardware()
        self.executor.shutdown()
        self.node.destroy_node()
        self.probe.destroy_node()
        os.close(self.master)
        os.close(self.slave)

    def feedback(self, line=b"ENC,99,1,0,0,1000\n"):
        os.write(self.master, line)
        self.assertTrue(self.spin_until(lambda: self.node.last_encoder_time is not None))

    def arm(self):
        self.feedback()
        self.estop.publish(Bool(data=False))
        self.assertTrue(self.spin_until(lambda: not self.node.safety.emergency_stop))

    def send_velocity(self):
        message = Twist()
        message.linear.x, message.angular.z = 0.1, 0.2
        self.cmd.publish(message)
        self.assertTrue(self.spin_until(lambda: "VEL," in self.writes))

    def test_serial_to_odom_and_real_tf_watchdog_estop(self):
        self.arm()
        self.send_velocity()
        self.assertIn(",0.050000,0.150000\n", self.writes)
        os.write(self.master, b"ENC,99,2,100,")
        self.node._read_serial()
        self.assertEqual(self.node.malformed_packets, 0)
        os.write(self.master, b"100,2000\n")
        self.assertTrue(self.spin_until(lambda: bool(self.odom) and bool(self.tf)))
        self.assertAlmostEqual(self.odom[-1].pose.pose.position.x, 0.2 * 3.141592653589793)
        transform = self.tf[-1].transforms[0]
        self.assertEqual(transform.header.frame_id, "odom")
        self.assertEqual(transform.child_frame_id, "base_link")
        self.assertAlmostEqual(transform.transform.translation.x, self.odom[-1].pose.pose.position.x)
        self.assertEqual(transform.header.stamp, self.odom[-1].header.stamp)
        self.assertTrue(self.spin_until(lambda: not self.node.safety.motion_command_active))
        self.assertTrue(self.writes.splitlines()[-1].startswith("STOP,"))
        self.estop.publish(Bool(data=True))
        self.assertTrue(self.spin_until(lambda: self.node.safety.emergency_stop))
        self.writes = ""
        self.node._on_cmd_vel(Twist())
        self.drain()
        self.assertNotIn("VEL,", self.writes)
        self.assertTrue(self.spin_until(lambda: any(
            value.key == "emergency_stop" and value.value == "true"
            for msg in self.status for value in msg.status[0].values
        )))

    def test_reconnect_and_reset_latch_stop_preserve_pose(self):
        self.arm()
        self.feedback(b"ENC,99,2,10,10,2000\n")
        self.assertTrue(self.spin_until(lambda: bool(self.odom)))
        x = self.node.odometry.x
        os.write(self.master, b"ENC,100,1,0,0,10\n")
        self.assertTrue(self.spin_until(lambda: self.node.safety.emergency_stop))
        self.assertEqual(self.node.odometry.x, x)
        self.assertIn("reset", self.node.fault_reason)
        self.node._disconnect("test cable removal")
        self.node._connect()
        self.assertIsNotNone(self.node.connection)
        self.assertTrue(self.node.safety.emergency_stop)
        self.assertIsNone(self.node.last_encoder_time)
        self.node._on_emergency_stop(Bool(data=False))
        self.assertTrue(self.node.safety.emergency_stop)
        self.arm()
        self.send_velocity()
        self.assertEqual(self.node.odometry.x, x)

    def test_malformed_feedback_timeout_and_duplicate_packets(self):
        self.arm()
        old_time = self.node.last_encoder_time
        os.write(self.master, b"ENC,99,1,0,0,1000\n")
        self.node._read_serial()
        self.assertEqual(self.node.last_encoder_time, old_time)
        self.node.last_encoder_time = time.monotonic() - 6
        self.node._watchdog()
        self.assertTrue(self.node.safety.emergency_stop)
        self.assertEqual(self.node.fault_reason, "encoder timeout")
        os.write(self.master, b"invalid\n" * self.node.max_malformed_packets)
        self.assertTrue(self.spin_until(lambda: self.node.connection is None))
        self.assertTrue(self.node.safety.emergency_stop)
        self.assertIn("malformed", self.node.connection_error)

    def test_failed_connect_short_write_nonfinite_and_shutdown(self):
        self.node._disconnect("test")
        with patch("amr_hardware.node.serial.Serial", side_effect=OSError("missing")):
            self.node._connect()
        self.assertIsNone(self.node.connection)
        self.node._connect()
        self.arm()
        message = Twist()
        message.linear.x = float("nan")
        self.node._on_cmd_vel(message)
        self.assertTrue(self.node.safety.emergency_stop)
        with patch.object(self.node.connection, "write", return_value=0):
            self.node._send_stop()
        self.assertIsNone(self.node.connection)
        self.node._connect()
        self.node.shutdown_hardware()
        self.drain()
        self.assertIsNone(self.node.connection)
        self.assertTrue(self.writes.splitlines()[-1].startswith("STOP,"))


if __name__ == "__main__":
    unittest.main()
