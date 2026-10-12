import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory("amr_hardware"),
        "config",
        "hardware.yaml",
    )
    params_file = LaunchConfiguration("params_file")

    return LaunchDescription([
        DeclareLaunchArgument(
            "params_file",
            default_value=default_params,
            description="Physical AMR hardware parameters",
        ),
        Node(
            package="amr_hardware",
            executable="hardware_node",
            name="amr_hardware",
            output="screen",
            parameters=[params_file],
        ),
    ])
