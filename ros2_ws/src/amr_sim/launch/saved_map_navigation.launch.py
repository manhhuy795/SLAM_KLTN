"""Localization + Nav2 for explicitly applied Saved Maps (Gazebo only)."""
import os
import yaml
import tempfile
from launch.actions import OpaqueFunction
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from nav2_common.launch import RewrittenYaml
from launch_ros.actions import Node


def setup(context):
    bringup=get_package_share_directory("nav2_bringup")
    rewrites={"use_sim_time":"true","allow_unknown":"false","consider_footprint":"true","tolerance":"0.0"}
    # Only this saved-map launch enables filters; the existing SLAM launch is unchanged.
    for name in ("global_costmap","local_costmap"):
        prefix=f"{name}.{name}.ros__parameters."
        rewrites.update({
                         prefix+"keepout_filter.plugin":"nav2_costmap_2d::KeepoutFilter",
                         prefix+"keepout_filter.enabled":"true",
                         prefix+"keepout_filter.filter_info_topic":"/web_bridge/keepout_info",
                         prefix+"keepout_filter.override_lethal_cost":"false"})
    config=RewrittenYaml(
        source_file=os.path.join(get_package_share_directory("amr_sim"),"config","nav2_params.yaml"),
        param_rewrites=rewrites,
        convert_types=True)
    config_path=config.perform(context)
    with open(config_path) as stream:parameters=yaml.safe_load(stream)
    for name in ("global_costmap","local_costmap"):
        parameters[name][name]["ros__parameters"]["filters"]=["keepout_filter"]
    with tempfile.NamedTemporaryFile(mode="w",suffix=".yaml",delete=False) as stream:
        yaml.safe_dump(parameters,stream);config=stream.name
    def include(name,args):
        return IncludeLaunchDescription(PythonLaunchDescriptionSource(
            os.path.join(bringup,"launch",name)),launch_arguments=args.items())
    common={"use_sim_time":"true","autostart":"false","use_composition":"False","params_file":config}
    bridge=IncludeLaunchDescription(PythonLaunchDescriptionSource(
        os.path.join(get_package_share_directory("web_bridge"),"launch","web_bridge.launch.py")),
        launch_arguments={"use_sim_time":"true","managed_maps":"true"}.items())
    return [
        Node(package="nav2_map_server",executable="map_server",name="map_server",
             parameters=[config,{"yaml_filename":"","use_sim_time":True}],output="screen"),
        Node(package="nav2_amcl",executable="amcl",name="amcl",
             parameters=[config,{"use_sim_time":True}],output="screen"),
        Node(package="nav2_lifecycle_manager",executable="lifecycle_manager",name="lifecycle_manager_localization",
             parameters=[{"use_sim_time":True,"autostart":True,"node_names":["map_server","amcl"]}],output="screen"),
        include("navigation_launch.py",common),bridge]


def generate_launch_description():
    return LaunchDescription([OpaqueFunction(function=setup)])
