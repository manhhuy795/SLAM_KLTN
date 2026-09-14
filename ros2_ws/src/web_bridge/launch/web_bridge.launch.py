from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    backend_url = DeclareLaunchArgument(
        "backend_url",
        default_value="http://127.0.0.1:8000",
    )

    bridge = Node(
        package="web_bridge",
        executable="web_bridge",
        name="web_bridge",
        output="screen",
        parameters=[
            {
                "backend_url": LaunchConfiguration("backend_url"),
            }
        ],
    )

    return LaunchDescription([backend_url, bridge])
