"""Versioned Nav2 keepout masks; success requires both costmaps to confirm."""
import math
import time
from uuid import uuid4

import numpy as np
from nav_msgs.msg import OccupancyGrid
from nav2_msgs.msg import CostmapFilterInfo, Costmap
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from rclpy.time import Time
from rcl_interfaces.srv import GetParameters

from .navigation_safety import polygon_world


def rasterize(grid, objects, radius):
    if abs(grid["origin"]["yaw"])>1e-6:raise ValueError("Keepout requires origin yaw=0")
    width,height,res=grid["width"],grid["height"],grid["resolution"]
    ox,oy=grid["origin"]["x"],grid["origin"]["y"]
    mask=np.zeros((height,width),dtype=np.int8)
    # Filters run after inflation: include the full robot radius and cell diagonal.
    margin=radius+res*math.sqrt(2)
    for obj in objects:
        if obj["type"]!="NO_GO":continue
        points=polygon_world(obj)
        left=max(0,math.floor((min(x for x,y in points)-margin-ox)/res))
        right=min(width,math.ceil((max(x for x,y in points)+margin-ox)/res))
        bottom=max(0,math.floor((min(y for x,y in points)-margin-oy)/res))
        top=min(height,math.ceil((max(y for x,y in points)+margin-oy)/res))
        for start in range(bottom,top,128):
            end=min(top,start+128)
            x,y=np.meshgrid(ox+(np.arange(left,right)+.5)*res,oy+(np.arange(start,end)+.5)*res)
            inside=np.zeros(x.shape,dtype=bool);near=np.zeros(x.shape,dtype=bool)
            for (ax,ay),(bx,by) in zip(points,points[1:]+points[:1]):
                dx,dy=bx-ax,by-ay
                t=np.clip(((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy),0,1)
                near|=(x-ax-t*dx)**2+(y-ay-t*dy)**2<=margin*margin
                if dy:inside^=((ay>y)!=(by>y)) & (x<(bx-ax)*(y-ay)/dy+ax)
            mask[start:end,left:right][inside|near]=100
    return mask.ravel().tolist()


class Keepouts:
    def __init__(self,owner):
        self.owner=owner;self.node=owner.node
        self.qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE)
        self.info_pub=self.node.create_publisher(CostmapFilterInfo,"/web_bridge/keepout_info",self.qos)
        self.publisher=None;self.topic=None;self.applied=None;self.mask=None
        self.confirmed={}
        self.latest={}
        self.parameters={name:self.node.create_client(GetParameters,
            f"/{name}_costmap/{name}_costmap/get_parameters") for name in ("global","local")}
        self.subscriptions=[self.node.create_subscription(Costmap,f"/{name}_costmap/costmap_raw",
            lambda msg,n=name:self.latest.update({n:(msg,time.monotonic())}),self.qos) for name in ("global","local")]

    def enabled(self):
        try:
            for client in self.parameters.values():
                request=GetParameters.Request()
                request.names=["filters","keepout_filter.enabled","keepout_filter.override_lethal_cost",
                               "keepout_filter.filter_info_topic"]
                v=self.owner.call(client,request,2).values
                if ("keepout_filter" not in v[0].string_array_value or not v[1].bool_value
                    or v[2].bool_value or v[3].string_value!="/web_bridge/keepout_info"):return False
            return True
        except Exception:
            return False

    def fresh(self):
        return all(name in self.latest and time.monotonic()-self.latest[name][1]<3 for name in ("global","local"))

    def connected(self):
        if not self.topic:return False
        subscribers={(p.node_namespace,p.node_name) for p in self.node.get_subscriptions_info_by_topic(self.topic)}
        return {("/global_costmap","global_costmap"),("/local_costmap","local_costmap")}<=subscribers

    def matches(self,costmap,grid,mask,previous):
        meta=costmap.metadata
        if costmap.header.frame_id=="map" and (
            meta.size_x!=grid["width"] or meta.size_y!=grid["height"]
            or not math.isclose(meta.resolution,grid["resolution"],abs_tol=1e-7)
            or not math.isclose(meta.origin.position.x,grid["origin"]["x"],abs_tol=1e-6)
            or not math.isclose(meta.origin.position.y,grid["origin"]["y"],abs_tol=1e-6)):
            return False,0
        x,y=np.meshgrid(meta.origin.position.x+(np.arange(meta.size_x)+.5)*meta.resolution,
                        meta.origin.position.y+(np.arange(meta.size_y)+.5)*meta.resolution)
        if costmap.header.frame_id!="map":
            tf=self.node.tf_buffer.lookup_transform("map",costmap.header.frame_id,Time())
            q=tf.transform.rotation;yaw=math.atan2(2*q.w*q.z,1-2*q.z*q.z)
            x,y=math.cos(yaw)*x-math.sin(yaw)*y+tf.transform.translation.x,math.sin(yaw)*x+math.cos(yaw)*y+tf.transform.translation.y
        col=np.floor((x-grid["origin"]["x"])/grid["resolution"]).astype(int)
        row=np.floor((y-grid["origin"]["y"])/grid["resolution"]).astype(int)
        valid=(col>=0)&(row>=0)&(col<grid["width"])&(row<grid["height"])
        indices=row[valid]*grid["width"]+col[valid]
        actual=np.asarray(costmap.data).reshape(x.shape)[valid]
        expected=np.asarray(mask)[indices]==100
        if np.any(actual[expected]!=254):return False,int(expected.sum())
        if previous is not None:
            removed=(np.asarray(previous)[indices]==100)&~expected&(np.asarray(grid["data"])[indices]==0)
            if np.any(actual[removed]>=254):return False,int(expected.sum())
        return True,int(expected.sum())

    def apply(self,planning):
        self.applied=None;self.confirmed={}
        if not self.enabled():raise RuntimeError("Keepout filter must be enabled on BOTH costmaps")
        grid=self.owner.grid
        self.radius=self.owner.footprint_radius()
        mask=rasterize(grid,planning["objects"],self.radius)
        old_pub=self.publisher
        previous=self.mask if self.mask is not None and len(self.mask)==len(mask) else None
        self.topic="/web_bridge/keepout_mask/v"+uuid4().hex
        self.publisher=self.node.create_publisher(OccupancyGrid,self.topic,self.qos)
        msg=OccupancyGrid();msg.header.frame_id="map";msg.header.stamp=self.node.get_clock().now().to_msg()
        msg.info.width=grid["width"];msg.info.height=grid["height"];msg.info.resolution=grid["resolution"]
        msg.info.origin.position.x=grid["origin"]["x"];msg.info.origin.position.y=grid["origin"]["y"]
        msg.info.origin.orientation.w=1.;msg.info.map_load_time=msg.header.stamp;msg.data=mask
        self.publisher.publish(msg)
        self.mask=mask
        info=CostmapFilterInfo();info.header=msg.header;info.type=0;info.base=0.;info.multiplier=1.;info.filter_mask_topic=self.topic
        self.info_pub.publish(info)
        sent=self.node.get_clock().now().nanoseconds/1e9
        deadline=time.monotonic()+20
        try:
            while time.monotonic()<deadline and not self.owner.stop.is_set():
                checks={}
                if self.connected() and self.fresh():
                    for name in ("global","local"):
                        costmap=self.latest[name][0]
                        stamp=costmap.header.stamp.sec+costmap.header.stamp.nanosec/1e9
                        matched,count=self.matches(costmap,grid,mask,previous)
                        if matched and stamp>sent+1.0:checks[name]=count
                if len(checks)==2:
                    self.mask=mask;self.applied=planning["revision"];self.confirmed=checks
                    return
                time.sleep(.25)
            raise RuntimeError("Keepout not confirmed in BOTH global/local costmaps; navigation blocked")
        finally:
            if old_pub:self.node.destroy_publisher(old_pub)
