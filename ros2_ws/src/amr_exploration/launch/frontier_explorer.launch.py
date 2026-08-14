import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory('amr_exploration')

    default_params = os.path.join(
        package_share,
        'config',
        'explorer_sim.yaml',
    )

    params_file = LaunchConfiguration('params_file')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Frontier explorer parameter YAML',
        ),
        Node(
            package='amr_exploration',
            executable='frontier_explorer',
            name='frontier_explorer',
            output='screen',
            parameters=[params_file],
        ),
    ])
