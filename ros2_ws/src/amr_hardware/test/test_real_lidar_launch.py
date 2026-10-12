import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


spec = importlib.util.spec_from_file_location(
    "real_lidar_launch",
    Path(__file__).parents[1] / "launch" / "real_lidar.launch.py",
)
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


def test_bench_does_not_invent_mount():
    assert launch.mount_arguments({"publish_mount_tf": "false"}) is None


@pytest.mark.parametrize("value", ["", "nan", "inf", "not-a-number"])
def test_mount_requires_all_finite_measurements(value):
    values = dict.fromkeys(("x", "y", "z", "roll", "pitch", "yaw"), "0")
    values.update(publish_mount_tf="true", frame_id="laser_link", z=value)
    with pytest.raises(ValueError):
        launch.mount_arguments(values)


def test_measured_mount_and_frame_are_preserved():
    values = dict(x="0.12", y="0.01", z="0.24", roll="0", pitch="0", yaw="1.57",
                  publish_mount_tf="true", frame_id="measured_laser")
    assert launch.mount_arguments(values) == [
        "--x", "0.12", "--y", "0.01", "--z", "0.24",
        "--roll", "0", "--pitch", "0", "--yaw", "1.57",
        "--frame-id", "base_link", "--child-frame-id", "measured_laser",
    ]
    values["frame_id"] = "base_link"
    with pytest.raises(ValueError):
        launch.mount_arguments(values)


@pytest.mark.parametrize("publishers", [[], [SimpleNamespace(node_name="gazebo_bridge")]])
def test_preflight_blocks_existing_scan_source_and_cleans_up(publishers):
    node = Mock()
    node.get_publishers_info_by_topic.return_value = publishers
    with patch("rclpy.init"), patch("rclpy.create_node", return_value=node), \
            patch("rclpy.shutdown") as shutdown, \
            patch.object(launch.time, "monotonic", side_effect=[0, 3]):
        if publishers:
            with pytest.raises(RuntimeError, match="gazebo_bridge"):
                launch.check_scan_source()
        else:
            launch.check_scan_source()
        node.destroy_node.assert_called_once()
        shutdown.assert_called_once()
