import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    pkg_amr_sim = get_package_share_directory('amr_sim')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')

    vm_compat = DeclareLaunchArgument(
        'vm_compat',
        default_value='false',
        description='Use headless OGRE2 rendering for VMs without a display'
    )

    headless_args = PythonExpression([
        "'-s --headless-rendering' if '",
        LaunchConfiguration('vm_compat'),
        "' == 'true' else ''"
    ])

    render_engine = PythonExpression([
        "'ogre2' if '",
        LaunchConfiguration('vm_compat'),
        "' == 'true' else 'ogre'"
    ])

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
                '-r -v 3 ',
                headless_args,
                ' --render-engine ',
                render_engine,
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
        gazebo,
        bridge,
        lidar_tf,
        delayed_spawn
    ])
