import unittest

from web_bridge.time_utils import (
    ros_time_to_seconds,
    transform_timestamp,
)


class Stamp:
    def __init__(self, sec, nanosec):
        self.sec = sec
        self.nanosec = nanosec


class Header:
    def __init__(self, stamp):
        self.stamp = stamp


class Transform:
    def __init__(self, stamp):
        self.header = Header(stamp)


class RosTimeUtilsTest(unittest.TestCase):
    def test_ros_time_is_converted_to_seconds(self):
        self.assertEqual(
            ros_time_to_seconds(Stamp(12, 500000000)),
            12.5,
        )
        self.assertEqual(
            transform_timestamp(Transform(Stamp(4, 250000000)), 99.0),
            4.25,
        )

    def test_invalid_ros_time_uses_fallback(self):
        self.assertEqual(
            transform_timestamp(Transform(Stamp(0, 0)), 99.0),
            99.0,
        )
        self.assertIsNone(ros_time_to_seconds(None))


if __name__ == "__main__":
    unittest.main()
