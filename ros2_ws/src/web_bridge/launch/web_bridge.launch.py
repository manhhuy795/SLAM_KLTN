import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def launch_bridge(context):
    config_file = os.path.join(
        get_package_share_directory("web_bridge"),
        "config",
        "bridge.yaml",
    )
    parameters = [config_file, {
        "use_sim_time": LaunchConfiguration("use_sim_time").perform(context) == "true",
    }]
    backend_url = LaunchConfiguration("backend_url").perform(context)

    if backend_url:
        parameters.append({"backend_url": backend_url})

    return [
        Node(
            package="web_bridge",
            executable="web_bridge",
            name="web_bridge",
            output="screen",
            parameters=parameters,
        )
    ]


def generate_launch_description():
    backend_url = DeclareLaunchArgument(
        "backend_url",
        default_value="",
        description="Optional override for the backend URL in bridge.yaml",
    )

    return LaunchDescription([
        backend_url,
        DeclareLaunchArgument(
            "use_sim_time",
            default_value="true",
            choices=["true", "false"],
            description="Use Gazebo /clock for goal stamps and TF",
        ),
        OpaqueFunction(function=launch_bridge),
    ])
