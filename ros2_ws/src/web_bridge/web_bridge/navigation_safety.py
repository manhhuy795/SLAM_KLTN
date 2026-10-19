"""Conservative full-footprint checks in map meters; unknown cells are blocked."""
import math


def disk_cells(width, height, resolution, ox, oy, x, y, radius):
    if not all(math.isfinite(v) for v in (resolution,ox,oy,x,y,radius)) or resolution<=0 or radius<=0:
        raise ValueError("Invalid footprint/grid geometry")
    if x-radius<ox or y-radius<oy or x+radius>=ox+width*resolution or y+radius>=oy+height*resolution:
        raise ValueError("Robot footprint extends outside map")
    for row in range(math.floor((y-radius-oy)/resolution),math.floor((y+radius-oy)/resolution)+1):
        for col in range(math.floor((x-radius-ox)/resolution),math.floor((x+radius-ox)/resolution)+1):
            dx=max(ox+col*resolution-x,0,x-(ox+(col+1)*resolution))
            dy=max(oy+row*resolution-y,0,y-(oy+(row+1)*resolution))
            if dx*dx+dy*dy<=radius*radius:
                yield row*width+col


def polygon_world(obj):
    c,s=math.cos(obj["yaw"]),math.sin(obj["yaw"])
    return [(obj["x"]+c*p["x"]-s*p["y"],obj["y"]+s*p["x"]+c*p["y"]) for p in obj["vertices"]]


def near_polygon(x,y,polygon,radius):
    inside=False
    for (ax,ay),(bx,by) in zip(polygon,polygon[1:]+polygon[:1]):
        dx,dy=bx-ax,by-ay
        t=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy))) if dx or dy else 0
        if math.hypot(x-ax-t*dx,y-ay-t*dy)<=radius:return True
        if (ay>y)!=(by>y) and x<(bx-ax)*(y-ay)/(by-ay)+ax:inside=not inside
    return inside
