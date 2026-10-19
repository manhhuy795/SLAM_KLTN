import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    pkg_amr_sim = get_package_share_directory('amr_sim')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')

    vm_compat = DeclareLaunchArgument(
        'vm_compat',
        default_value='false',
        description='Use software OpenGL and X11 for the OGRE2 lidar in VMware'
    )

    vmware_software_rendering = SetEnvironmentVariable(
        'LIBGL_ALWAYS_SOFTWARE',
        '1',
        condition=IfCondition(LaunchConfiguration('vm_compat')),
    )
    vmware_x11 = SetEnvironmentVariable(
        'QT_QPA_PLATFORM',
        'xcb',
        condition=IfCondition(LaunchConfiguration('vm_compat')),
    )

    world_file = os.path.join(
        pkg_amr_sim,
        'worlds',
        'warehouse.sdf'
    )

    model_file = os.path.join(
        pkg_amr_sim,
        'models',
        'amr',
        'model.sdf'
    )

    bridge_config = os.path.join(
        pkg_amr_sim,
        'config',
        'bridge.yaml'
    )

    # Gazebo
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                pkg_ros_gz_sim,
                'launch',
                'gz_sim.launch.py'
            )
        ),
        launch_arguments={
            'gz_args': [
                # Server-only OGRE2/EGL publishes intermittent all-inf scans
                # on VMware SVGA3D. The X11-backed GUI renderer is reliable.
                '-r -v 3 --render-engine ogre2',
                f' {world_file}'
            ]
        }.items(),
    )

    # ROS 2 <-> Gazebo bridge
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_bridge',
        output='screen',
        parameters=[
            {
                'config_file': bridge_config
            }
        ]
    )

    # Static transform: base_link -> laser_link
    lidar_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='lidar_static_tf',
        output='screen',
        arguments=[
            '--x', '0.18',
            '--y', '0.0',
            '--z', '0.15',
            '--yaw', '0.0',
            '--pitch', '0.0',
            '--roll', '0.0',
            '--frame-id', 'base_link',
            '--child-frame-id', 'laser_link'
        ]
    )

    # Spawn AMR
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        output='screen',
        arguments=[
            '--world', 'warehouse',
            '--file', model_file,
            '--name', 'amr',
            '-x', '0',
            '-y', '0',
            '-z', '0.02'
        ]
    )

    # Wait for Gazebo before spawning
    delayed_spawn = TimerAction(
        period=3.0,
        actions=[spawn_robot]
    )

    return LaunchDescription([
        vm_compat,
        vmware_software_rendering,
        vmware_x11,
        gazebo,
        bridge,
        lidar_tf,
        delayed_spawn
    ])
