"""Rigid AGV local (+Y down) to ROS shared-map (+Y up) transform.

Anchors A,B,D are physically measured positions of original AGV test stations.
A->D defines AGV local +X. A->B verifies the clockwise +Y direction.
No scaling of odometry is allowed; measured distances are sanity checks.
"""
import math

AGV_WIDTH_M = 1.54
AGV_HEIGHT_M = 1.51
MAX_DISTANCE_ERROR_M = 0.15
MAX_B_RESIDUAL_M = 0.15


def validate_alignment(a, b, d):
    for p in (a, b, d):
        if not all(math.isfinite(p[k]) for k in ("x", "y")):
            raise ValueError("Anchor coordinates must be finite")
    dx, dy = d["x"] - a["x"], d["y"] - a["y"]
    distance = math.hypot(dx, dy)
    if abs(distance - AGV_WIDTH_M) > MAX_DISTANCE_ERROR_M:
        raise ValueError("A-D length must match AGV's measured 1.54 m line segment")
    theta = math.atan2(dy, dx)
    predicted_b = {
        "x": a["x"] + AGV_HEIGHT_M * math.sin(theta),
        "y": a["y"] - AGV_HEIGHT_M * math.cos(theta),
    }
    if math.hypot(predicted_b["x"] - b["x"], predicted_b["y"] - b["y"]) > MAX_B_RESIDUAL_M:
        raise ValueError("B must be on the +Y-down side of A-D at approximately 1.51 m")
    return theta


def transform_agv_pose(alignment, x, y, yaw_deg):
    theta = validate_alignment(alignment["a"], alignment["b"], alignment["d"])
    a = alignment["a"]
    return {
        "x": a["x"] + x * math.cos(theta) + y * math.sin(theta),
        "y": a["y"] + x * math.sin(theta) - y * math.cos(theta),
        "yaw": math.atan2(math.sin(theta - math.radians(yaw_deg)),
                          math.cos(theta - math.radians(yaw_deg))),
    }
