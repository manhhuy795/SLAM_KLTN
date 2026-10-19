"""Saved-map operations run off the ROS executor; no physical robot dispatch."""
import json
import math
import threading
import time
from uuid import uuid4
from urllib.request import urlopen

from geometry_msgs.msg import PoseWithCovarianceStamped
from lifecycle_msgs.srv import GetState
from nav2_msgs.srv import LoadMap, ManageLifecycleNodes, GetCostmap, GetCost
from rcl_interfaces.srv import GetParameters
from .keepouts import Keepouts
from .navigation_safety import disk_cells, polygon_world, near_polygon
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time


def same_grid(expected, actual):
    return (actual is not None and actual["frame_id"] == "map"
            and all(expected[k] == actual[k] for k in ("width","height","data"))
            and math.isclose(expected["resolution"],actual["resolution"],abs_tol=1e-7)
            and all(math.isclose(expected["origin"][k],actual["origin"][k],abs_tol=1e-6)
                    for k in ("x","y","yaw")))


class ManagedMaps:
    def __init__(self, node):
        self.node=node
        self.stop=threading.Event()
        self.lock=threading.RLock()
        self.session_id=uuid4().hex
        self.reported={"ready":False}
        self.report_time=0
        self.active=None
        self.grid=None
        self.request_id=None
        self.error=""
        self.state="WAITING"
        self.amcl=None
        self.amcl_received=0
        self.loaded=0
        self.startup_pending=False
        self.last_clock=0
        self.clock_moved=time.monotonic()
        self.states={name:node.create_client(GetState,"/"+name+"/get_state")
                     for name in ("map_server","amcl","planner_server","controller_server","bt_navigator",
                                  "global_costmap/global_costmap","local_costmap/local_costmap")}
        self.loader=node.create_client(LoadMap,"/map_server/load_map")
        self.startup=node.create_client(ManageLifecycleNodes,"/lifecycle_manager_navigation/manage_nodes")
        self.costmap=node.create_client(GetCostmap,"/global_costmap/get_costmap")
        self.cost=node.create_client(GetCost,"/global_costmap/get_cost_global_costmap")
        self.parameters=node.create_client(GetParameters,"/global_costmap/global_costmap/get_parameters")
        self.pose_pub=node.create_publisher(PoseWithCovarianceStamped,"/initialpose",10)
        self.amcl_sub=node.create_subscription(PoseWithCovarianceStamped,"/amcl_pose",self._amcl,10)
        self.keepouts=Keepouts(self)
        self.worker=threading.Thread(target=self._run,daemon=True)
        self.worker.start()

    def _amcl(self,msg):
        self.amcl=msg
        self.amcl_received=time.monotonic()

    def wait(self,future,seconds=8):
        event=threading.Event()
        future.add_done_callback(lambda _:event.set())
        if not event.wait(seconds):
            raise RuntimeError("ROS service/action timed out")
        return future.result()

    def call(self,client,request,seconds=8):
        if not client.wait_for_service(timeout_sec=1):
            raise RuntimeError(client.srv_name+" unavailable")
        return self.wait(client.call_async(request),seconds)

    def active_node(self,name):
        try:
            return self.call(self.states[name],GetState.Request(),2).current_state.id==3
        except Exception:
            return False

    def read_json(self,path):
        with urlopen(self.node.backend_url+path,timeout=3) as response:
            return json.load(response)

    def _checks(self):
        now=self.node.get_clock().now().nanoseconds
        if now!=self.last_clock:
            self.last_clock=now;self.clock_moved=time.monotonic()
        simulation=bool(self.node.get_parameter("use_sim_time").value) and now>0 and time.monotonic()-self.clock_moved<3
        states={name:self.active_node(name) for name in self.states}
        verified=self.active is not None and same_grid(self.grid,self.node._latest_map)
        covariance=self.amcl.pose.covariance if self.amcl else None
        localized=False
        try:
            tf=self.node.tf_buffer.lookup_transform("map","odom",Time())
            stamp=tf.header.stamp.sec+tf.header.stamp.nanosec/1e9
            scan=self.node._scan.snapshot(time.monotonic())
            localized=bool(verified and self.amcl_received>self.loaded and covariance is not None
                and max(covariance[0],covariance[7])<.25 and covariance[35]<.3
                and abs(now/1e9-stamp)<2.0 and scan.get("lidar_online")
                and (scan.get("scan_points_valid") or 0)>20 and self.node._lookup_pose())
        except Exception:
            pass
        nav2=all(states[n] for n in ("planner_server","controller_server","bt_navigator"))
        revision=None
        if self.active:
            revision=self.read_json("/api/maps/"+self.active["map_id"]+"/planning")["revision"]
        keepout_verified=self.keepouts.applied is not None and self.keepouts.applied==revision and self.keepouts.connected() and self.keepouts.fresh() and self.keepouts.enabled()
        ready=simulation and verified and localized and all(states.values()) and keepout_verified and not self.error
        return dict(enabled=True,ready=ready,state="READY" if ready else ("FAILED" if self.error else "UNLOCALIZED"),
                    request_id=self.request_id,session_id=self.session_id,
                    map_id=self.active["map_id"] if self.active else None,
                    map_hash=self.active["map_hash"] if self.active else None,
                    planning_revision=self.keepouts.applied,keepout_verified=keepout_verified,
                    keepout_cells=self.keepouts.confirmed,mask_topic=self.keepouts.topic,map_verified=verified,map_server_active=states["map_server"],
                    nav2_active=nav2,localization_valid=localized,environment="simulation",
                    error=self.error or ("" if ready else "Verify map/AMCL/Nav2 and explicitly apply the current planning keepouts"))

    def report(self):
        self.reported=self._checks()
        self.report_time=time.monotonic()
        self.node._post_json("/api/ros/map-session/status",self.reported)

    def _operate(self,command):
        with self.lock:
            self.request_id=command["id"]
            self.error=""
            if command["operation"]=="APPLY_KEEPOUTS":
                try:
                    if self.node._navigation_command is not None:raise RuntimeError("Cancel navigation first")
                    if (not self.active or command["map_id"]!=self.active["map_id"]
                        or command["map_hash"]!=self.active["map_hash"]):
                        raise RuntimeError("Load this map into Nav2 first")
                    status=self._checks()
                    if not all(status[k] for k in ("map_verified","localization_valid","nav2_active")):
                        raise RuntimeError("Map/localization/Nav2 unavailable")
                    self.keepouts.apply(command["planning"])
                except Exception as error:
                    self.keepouts.applied=None
                    self.error=str(error)
                self.report()
                return
            self.active=None
            self.keepouts.applied=None;self.keepouts.mask=None
            self.loaded=time.monotonic()
            self.startup_pending=True
            try:
                if not self.node.get_parameter("use_sim_time").value:
                    raise RuntimeError("Managed navigation is simulation-only")
                if self.node._navigation_command is not None:
                    raise RuntimeError("Navigation is active; cancel first")
                publishers=self.node.get_publishers_info_by_topic("/map")
                if any(p.node_name!="map_server" for p in publishers):
                    raise RuntimeError("Stop SLAM/other map publishers before loading a saved map")
                if not self.active_node("map_server"):
                    raise RuntimeError("Map Server must be active")
                self.grid=self.read_json("/api/maps/"+command["map_id"])
                if self.grid["map_hash"]!=command["map_hash"]:
                    raise RuntimeError("Saved map version changed")
                if abs(self.grid["origin"]["yaw"])>1e-6:
                    raise RuntimeError("Nav2 Jazzy requires origin yaw=0")
                request=LoadMap.Request();request.map_url=command["yaml_path"]
                result=self.call(self.loader,request)
                if result.result!=0:
                    raise RuntimeError("Map Server rejected file: "+str(result.result))
                # Both the service response and /map must match the original grid.
                message=result.map
                q=message.info.origin.orientation
                actual=dict(width=message.info.width,height=message.info.height,resolution=message.info.resolution,
                    frame_id=message.header.frame_id,origin=dict(x=message.info.origin.position.x,
                    y=message.info.origin.position.y,yaw=math.atan2(2*q.w*q.z,1-2*q.z*q.z)),data=list(message.data))
                if not same_grid(self.grid,actual):
                    raise RuntimeError("Map Server grid differs from Saved Map; navigation blocked")
                deadline=time.monotonic()+10
                while not same_grid(self.grid,self.node._latest_map):
                    if time.monotonic()>deadline:raise RuntimeError("/map confirmation timed out")
                    time.sleep(.1)
                self.active=command
                pose=command.get("initial_pose")
                if pose:
                    msg=PoseWithCovarianceStamped()
                    msg.header.frame_id="map";msg.header.stamp=self.node.get_clock().now().to_msg()
                    msg.pose.pose.position.x=pose["x"];msg.pose.pose.position.y=pose["y"]
                    msg.pose.pose.orientation.z=math.sin(pose["yaw"]/2)
                    msg.pose.pose.orientation.w=math.cos(pose["yaw"]/2)
                    msg.pose.covariance[0]=.04;msg.pose.covariance[7]=.04;msg.pose.covariance[35]=.04
                    self.pose_pub.publish(msg)
                    deadline=time.monotonic()+15
                    while self.amcl_received<=self.loaded or self.node._lookup_pose() is None:
                        if time.monotonic()>deadline:raise RuntimeError("AMCL did not confirm initial pose")
                        time.sleep(.1)
                if self.amcl_received>self.loaded:self.start_navigation()
            except Exception as error:
                self.error=str(error)
            self.report()

    def start_navigation(self):
        self.startup_pending=False
        if not self.active_node("bt_navigator"):
            request=ManageLifecycleNodes.Request();request.command=ManageLifecycleNodes.Request.STARTUP
            if not self.call(self.startup,request,40).success:
                self.error="Nav2 lifecycle startup failed"
                raise RuntimeError(self.error)

    def _run(self):
        while not self.stop.is_set():
            try:
                command=self.read_json("/api/ros/map-session/command")
                if command:self._operate(command)
                if self.startup_pending and self.active and not self.error and self.amcl_received>self.loaded:
                    self.start_navigation()
                self.report()
            except Exception as error:
                self.node.get_logger().warning("Map session: "+str(error))
            self.stop.wait(1)

    def footprint_radius(self):
        radii=[]
        for client in (self.parameters,self.keepouts.parameters["local"]):
            request=GetParameters.Request();request.names=["footprint","footprint_padding"]
            values=self.call(client,request).values
            points=json.loads(values[0].string_value);padding=values[1].double_value
            if len(points)<3 or padding<0:raise ValueError("Configured robot footprint unavailable")
            radius=max(math.hypot(abs(float(x))+padding,abs(float(y))+padding) for x,y in points)
            if not math.isfinite(radius) or radius<=0:raise ValueError("Invalid robot footprint")
            radii.append(radius)
        return max(radii)

    def validate_goal(self,command):
        context=command.get("map_context") or {}
        if not self.reported.get("ready") or time.monotonic()-self.report_time>4:
            raise ValueError("Map/localization not verified")
        if not self.active or any(context.get(k)!=v for k,v in
            (("session_id",self.session_id),("map_id",self.active["map_id"]),("map_hash",self.active["map_hash"]))):
            raise ValueError("Goal map/session does not match Nav2")
        layer=self.read_json("/api/maps/"+self.active["map_id"]+"/planning")
        point=command.get("planning_point")
        if point:
            target=next((p for p in layer["objects"] if p["id"]==point["id"]),None)
            if (point["revision"]!=layer["revision"] or point["map_id"]!=self.active["map_id"]
                or not target or target["type"] not in {"HOME","PICKUP","DELIVERY","CHARGING"}
                or any(command[k]!=target[k] for k in ("x","y","yaw"))):
                raise ValueError("Planning point changed; select it again")
        x,y,yaw=(float(command[k]) for k in ("x","y","yaw"))
        if not all(math.isfinite(v) for v in (x,y,yaw)):raise ValueError("Invalid goal")
        radius=self.footprint_radius()
        if radius>self.keepouts.radius+1e-6:raise ValueError("Robot footprint changed; reapply keepouts")
        if layer["revision"]!=self.keepouts.applied:raise ValueError("Planning changed; apply keepouts first")
        grid=self.grid
        cells=disk_cells(grid["width"],grid["height"],grid["resolution"],
                         grid["origin"]["x"],grid["origin"]["y"],x,y,radius)
        if any(grid["data"][i]!=0 for i in cells):
            raise ValueError("Goal footprint overlaps occupied/unknown map cells")
        if any(near_polygon(x,y,polygon_world(o),radius) for o in layer["objects"] if o["type"]=="NO_GO"):
            raise ValueError("Goal footprint overlaps a NO-GO zone")
        costmap=self.call(self.costmap,GetCostmap.Request()).map
        meta=costmap.metadata
        if costmap.header.frame_id!="map":raise ValueError("Global costmap frame mismatch")
        cells=disk_cells(meta.size_x,meta.size_y,meta.resolution,meta.origin.position.x,
                         meta.origin.position.y,x,y,radius)
        if any(costmap.data[i]>=253 for i in cells):
            raise ValueError("Robot footprint is blocked in current costmap")
        request=GetCost.Request();request.use_footprint=True
        request.x=x;request.y=y;request.theta=yaw
        cost=self.call(self.cost,request).cost
        if not math.isfinite(cost) or cost<0 or cost>=253:
            raise ValueError("Nav2 rejected goal footprint")
        # Recheck after service calls; a stale preflight must never dispatch motion.
        if not self._checks()["ready"]:raise ValueError("Localization changed during goal validation")

    def dispatch(self,command):
        def run():
            try:
                with self.lock:
                    self.validate_goal(command)
                    if self.node._cancel_requested:
                        self.node._post_navigation_terminal(command["id"],"CANCELLED",0,"Cancelled before dispatch")
                    elif not self.stop.is_set():
                        self.node._send_navigation_goal(command)
            except Exception as error:
                state="CANCELLED" if self.node._cancel_requested else "REJECTED"
                self.node._post_navigation_terminal(command["id"],state,0,str(error))
        threading.Thread(target=run,daemon=True).start()

    def close(self):
        self.stop.set()
        self.worker.join(timeout=2)
