import math
import pytest
from web_bridge.navigation_safety import disk_cells, near_polygon, polygon_world


def test_disk_checks_interior_and_bounds():
    cells=list(disk_cells(20,20,.1,-1,-1,0,0,.22))
    assert 10*20+10 in cells and 10*20+12 in cells
    assert 10*20+13 not in cells
    with pytest.raises(ValueError):
        list(disk_cells(20,20,.1,-1,-1,.9,0,.22))


def test_rotated_polygon_and_footprint_clearance():
    obj=dict(x=2,y=3,yaw=math.pi/2,vertices=[dict(x=-1,y=-.5),dict(x=1,y=-.5),dict(x=1,y=.5),dict(x=-1,y=.5)])
    polygon=polygon_world(obj)
    assert near_polygon(2,3,polygon,0)
    assert near_polygon(2.7,3,polygon,.22)
    assert not near_polygon(2.8,3,polygon,.22)
    assert near_polygon(2,4,polygon,0)

def test_keepout_mask_rotates_polygons_and_expands_without_mutating_map():
    from copy import deepcopy
    from web_bridge.keepouts import rasterize
    grid=dict(width=40,height=40,resolution=.1,origin=dict(x=-2,y=-2,yaw=0),data=[0]*1600)
    before=deepcopy(grid)
    obj=dict(type="NO_GO",x=0,y=0,yaw=math.pi/2,
             vertices=[dict(x=-.6,y=-.1),dict(x=.6,y=-.1),dict(x=.6,y=.1),dict(x=-.6,y=.1)])
    mask=rasterize(grid,[obj],.22)
    assert mask[20*40+20]==100
    assert mask[26*40+20]==100
    assert mask[20*40+26]==0
    assert grid==before
    assert not any(rasterize(grid,[],.22))


def test_managed_checks_accept_ros_numpy_covariance():
    from types import SimpleNamespace as S
    import numpy as np
    from web_bridge.managed_maps import ManagedMaps
    manager=ManagedMaps.__new__(ManagedMaps)
    grid=dict(width=1,height=1,resolution=.05,origin=dict(x=0,y=0,yaw=0),data=[0],frame_id="map")
    manager.node=S(get_clock=lambda:S(now=lambda:S(nanoseconds=10_000_000_000)),
                   get_parameter=lambda _:S(value=True),_latest_map=grid,
                   _lookup_pose=lambda:dict(x=0,y=0),
                   _scan=S(snapshot=lambda _:dict(lidar_online=True,scan_points_valid=100)),
                   tf_buffer=S(lookup_transform=lambda *args:S(header=S(stamp=S(sec=10,nanosec=0)))))
    manager.last_clock=0;manager.clock_moved=0
    manager.states={n:None for n in ("map_server","amcl","planner_server","controller_server","bt_navigator")}
    manager.active_node=lambda _:True
    manager.active=dict(map_id="map",map_hash="hash");manager.grid=grid
    manager.amcl=S(pose=S(covariance=np.zeros(36)));manager.amcl_received=2;manager.loaded=1
    manager.error="";manager.request_id="request";manager.session_id="session"
    manager.read_json=lambda _:dict(revision=1)
    manager.keepouts=S(applied=1,connected=lambda:True,fresh=lambda:True,enabled=lambda:True,confirmed={},topic="mask")
    assert manager._checks()["ready"]
    manager.amcl.pose.covariance[0]=1
    assert not manager._checks()["ready"]
