"""Bench LiDAR only; never starts the robot base, SLAM or Nav2."""

import math
import os
import time

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch_ros.actions import Node


def mount_arguments(values):
    """Require every physical measurement instead of inventing a Gazebo mount."""
    if values["publish_mount_tf"] != "true":
        return None
    if not values["frame_id"] or values["frame_id"] == "base_link":
        raise ValueError("LiDAR frame must be nonempty and different from base_link")
    arguments = []
    for axis in ("x", "y", "z", "roll", "pitch", "yaw"):
        value = values[axis]
        if not value or not math.isfinite(float(value)):
            raise ValueError(f"Measured mount {axis} is required and must be finite")
        arguments.extend(["--" + axis, value])
    return arguments + ["--frame-id", "base_link", "--child-frame-id", values["frame_id"]]


def check_scan_source():
    import rclpy

    rclpy.init()
    node = rclpy.create_node("real_lidar_preflight")
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        publishers = node.get_publishers_info_by_topic("/scan")
        if publishers:
            names = ", ".join(p.node_name for p in publishers)
            raise RuntimeError(f"/scan already has a publisher: {names}. Stop it first.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


def launch_lidar(context):
    values = context.launch_configurations
    mount = mount_arguments(values)
    check_scan_source()
    actions = [Node(
        package="ldlidar_ros2", executable="ldlidar_ros2_node",
        name="ldlidar_publisher", output="screen",
        parameters=[{
            "product_name": values["product_name"],
            "port_name": values["port_name"],
            "serial_baudrate": int(values["serial_baudrate"]),
            "frame_id": values["frame_id"],
            "laser_scan_topic_name": "/scan",
            "point_cloud_2d_topic_name": "/pointcloud2d",
            "laser_scan_dir": True,
            "enable_angle_crop_func": False,
            "angle_crop_min": 135.0, "angle_crop_max": 225.0,
            "range_min": 0.1, "range_max": 8.0,
            "use_sim_time": False,
        }],
    )]
    if mount is not None:
        actions.append(Node(
            package="tf2_ros", executable="static_transform_publisher",
            name="real_lidar_mount", arguments=mount,
            parameters=[{"use_sim_time": False}],
        ))
    if values["rviz"] == "true":
        config = os.path.join(get_package_share_directory("amr_hardware"),
                              "config", "real_lidar.rviz")
        actions.append(Node(
            package="rviz2", executable="rviz2", name="real_lidar_rviz",
            arguments=["-d", config, "-f", values["frame_id"]],
            parameters=[{"use_sim_time": False}],
        ))
    return actions


def generate_launch_description():
    arguments = [
        # Verified stream: 115200 baud, ~2300 samples/s. LD14P profile drops it.
        DeclareLaunchArgument("product_name", default_value="LDLiDAR_LD14",
                              choices=["LDLiDAR_LD14", "LDLiDAR_LD14P"]),
        DeclareLaunchArgument("serial_baudrate", default_value="115200",
                              choices=["115200", "230400"]),
        DeclareLaunchArgument("port_name", default_value=(
            "/dev/serial/by-id/"
            "usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")),
        DeclareLaunchArgument("frame_id", default_value="laser_link"),
        DeclareLaunchArgument("rviz", default_value="false", choices=["true", "false"]),
        DeclareLaunchArgument("publish_mount_tf", default_value="false",
                              choices=["true", "false"]),
    ]
    arguments.extend(DeclareLaunchArgument(axis, default_value="")
                     for axis in ("x", "y", "z", "roll", "pitch", "yaw"))
    return LaunchDescription(arguments + [OpaqueFunction(function=launch_lidar)])
