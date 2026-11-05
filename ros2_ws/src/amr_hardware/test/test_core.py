import math
import unittest

from amr_hardware.kinematics import (
    EncoderOdometry,
    encoder_delta,
    twist_to_wheel_velocities,
)
from amr_hardware.protocol import (
    emergency_stop_command,
    parse_encoder_packet,
    LineBuffer,
    stop_command,
    velocity_command,
)
from amr_hardware.safety import SafetyState


class KinematicsTest(unittest.TestCase):
    def make_odometry(self):
        return EncoderOdometry(
            wheel_radius=0.1,
            wheel_separation=0.5,
            ticks_per_revolution=100,
            max_ticks_per_second=10000,
        )

    def test_twist_to_wheel_velocity_and_limits(self):
        left, right = twist_to_wheel_velocities(1.0, 2.0, 0.25, 0.22, 1.0)
        self.assertAlmostEqual(left, 0.095)
        self.assertAlmostEqual(right, 0.345)

    def test_straight_odometry(self):
        odometry = self.make_odometry()
        self.assertIsNone(odometry.update(0, 0, 1000))
        update = odometry.update(100, 100, 2000)
        self.assertAlmostEqual(update.x, 2 * math.pi * 0.1)
        self.assertAlmostEqual(update.y, 0.0)
        self.assertAlmostEqual(update.yaw, 0.0)

    def test_measured_cpr_and_opposite_raw_encoder_direction(self):
        expected = 2 * math.pi * 0.0325
        for right_sign, right_count in ((1, 893), (-1, -893)):
            with self.subTest(right_sign=right_sign):
                odometry = EncoderOdometry(0.0325, 0.25, 893,
                                            right_encoder_sign=right_sign)
                odometry.update(0, 0, 1000)
                update = odometry.update(893, right_count, 2000)
                self.assertAlmostEqual(update.x, expected, places=6)
                self.assertAlmostEqual(update.y, 0.0)
                self.assertAlmostEqual(update.yaw, 0.0)
                self.assertEqual((update.delta_left, update.delta_right), (893, 893))

    def test_normalized_backward_and_turn(self):
        odometry = EncoderOdometry(0.0325, 0.25, 893,
                                    right_encoder_sign=-1)
        odometry.update(0, 0, 1000)
        backward = odometry.update(-100, 100, 2000)
        self.assertLess(backward.x, 0)
        self.assertLess(backward.linear_velocity, 0)
        turn = odometry.update(0, 200, 3000)
        self.assertEqual((turn.delta_left, turn.delta_right), (100, -100))
        self.assertNotEqual(turn.yaw, 0)
        self.assertAlmostEqual(turn.linear_velocity, 0.0)

    def test_encoder_signs_reject_non_integer_and_unsupported_values(self):
        for sign in (0, 2, -2, 1.0, True, "-1"):
            for parameter in ("left_encoder_sign", "right_encoder_sign"):
                with self.subTest(sign=sign, parameter=parameter), self.assertRaises(ValueError):
                    EncoderOdometry(0.0325, 0.25, 893, **{parameter: sign})

    def test_inverted_encoder_rollover_and_reset_rebaseline(self):
        odometry = EncoderOdometry(0.0325, 0.25, 893,
                                    right_encoder_sign=-1)
        odometry.update(2147483646, -2147483646, 1000)
        rollover = odometry.update(-2147483647, 2147483647, 1100)
        self.assertEqual((rollover.delta_left, rollover.delta_right), (3, 3))
        previous_x = rollover.x
        odometry.reset_encoder_reference()  # ESP32 boot change re-baselines raw counters.
        self.assertIsNone(odometry.update(0, 0, 10))
        self.assertEqual(odometry.x, previous_x)
        resumed = odometry.update(10, -10, 110)
        self.assertEqual((resumed.delta_left, resumed.delta_right), (10, 10))
        self.assertGreater(resumed.x, previous_x)

    def test_turn_in_place(self):
        odometry = self.make_odometry()
        odometry.update(0, 0, 1000)
        update = odometry.update(-25, 25, 2000)
        self.assertAlmostEqual(update.x, 0.0)
        self.assertAlmostEqual(update.y, 0.0)
        self.assertGreater(update.yaw, 0.0)

    def test_arc(self):
        odometry = self.make_odometry()
        odometry.update(0, 0, 1000)
        update = odometry.update(50, 100, 2000)
        angle = math.pi / 5
        radius = 0.75
        self.assertAlmostEqual(update.x, radius * math.sin(angle))
        self.assertAlmostEqual(update.y, radius * (1 - math.cos(angle)))
        self.assertAlmostEqual(update.yaw, angle)

    def test_counter_wrap_and_reset(self):
        self.assertEqual(encoder_delta(-2147483647, 2147483646, 32), 3)
        odometry = self.make_odometry()
        odometry.update(100, 100, 1000)
        with self.assertRaises(ValueError):
            odometry.update(1_000_000, 1_000_000, 1100)
        self.assertIsNotNone(odometry.update(1_000_010, 1_000_010, 1200))
        with self.assertRaises(ValueError):
            odometry.update(0, 0, 10)

    def test_clock_wrap_and_gear_ratio(self):
        odometry = EncoderOdometry(0.1, 0.5, 10, gear_ratio=10)
        odometry.update(0, 0, 2**32 - 500)
        update = odometry.update(100, 100, 500)
        self.assertAlmostEqual(update.linear_velocity, 0.2 * math.pi)

    def test_nonfinite_velocity_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                twist_to_wheel_velocities(value, 0, 0.25, 0.22, 1.0)
            with self.assertRaises(ValueError):
                velocity_command(1, 0, value)


class ProtocolAndSafetyTest(unittest.TestCase):
    def test_protocol(self):
        self.assertEqual(velocity_command(7, 0.1, -0.2), "VEL,7,0.100000,-0.200000\n")
        self.assertEqual(stop_command(8), "STOP,8\n")
        self.assertEqual(emergency_stop_command(9, True), "ESTOP,9,1\n")
        packet = parse_encoder_packet("ENC,99,3,-10,20,1234\n")
        self.assertEqual((packet.left_count, packet.right_count), (-10, 20))

        for malformed in (
            "",
            "ENC,1,2",
            "ENC,a,2,3,4",
            "ENC,-1,2,3,4",
            "STATUS,1,2,3,4",
            "ENC,99,1,2,3,4294967296",
            "ENC,99,1,2147483648,3,100",
            "ENC,99,1,2,3,1_000",
        ):
            with self.assertRaises(ValueError):
                parse_encoder_packet(malformed)

    def test_timeout_and_emergency_stop(self):
        safety = SafetyState(0.5)
        self.assertFalse(safety.accept_command(0))
        safety.set_emergency_stop(False)
        self.assertTrue(safety.accept_command(10.0))
        self.assertFalse(safety.consume_timeout(10.5))
        self.assertTrue(safety.consume_timeout(10.51))
        self.assertFalse(safety.consume_timeout(11.0))

        safety.set_emergency_stop(True)
        self.assertFalse(safety.accept_command(12.0))
        safety.set_emergency_stop(False)
        self.assertTrue(safety.accept_command(13.0))

    def test_split_combined_and_oversized_lines(self):
        buffer = LineBuffer(limit=32)
        self.assertEqual(buffer.feed(b"ENC,1,2,"), [])
        self.assertEqual(buffer.feed(b"3,4,5\nSTOP\n"), [b"ENC,1,2,3,4,5", b"STOP"])
        self.assertEqual(buffer.feed(b"x" * 100), [None])
        self.assertEqual(buffer.feed(b"VEL,1,1,1\nOK\n"), [b"OK"])


if __name__ == "__main__":
    unittest.main()
