"""Read-only conversion of ROS diagnostics and odometry for WRMS."""

import math


def parse_hardware_status(message):
    status = next((item for item in message.status if item.name == "amr_hardware/base"), None)
    if status is None:
        return None
    values = {item.key: item.value for item in status.values}

    def boolean(key):
        value = values.get(key)
        return value == "true" if value in {"true", "false"} else None

    encoder_online = boolean("encoder_online")
    def count(key):
        try:
            return int(values[key]) if encoder_online else None
        except (KeyError, ValueError):
            return None

    return {
        "serial_connected": boolean("serial_connected"),
        "encoder_online": encoder_online,
        "emergency_stop": boolean("emergency_stop"),
        "left_encoder_count": count("left_encoder_count"),
        "right_encoder_count": count("right_encoder_count"),
        "fault_reason": values.get("fault_reason", "")[:256],
        "serial_error": values.get("serial_error", "")[:256],
    }


def parse_odometry(message, odom_frame="odom", base_frame="base_link"):
    if message.header.frame_id != odom_frame or message.child_frame_id != base_frame:
        return None
    pose = message.pose.pose
    twist = message.twist.twist
    q = pose.orientation
    values = (pose.position.x, pose.position.y, q.x, q.y, q.z, q.w,
              twist.linear.x, twist.angular.z)
    if not all(math.isfinite(value) for value in values):
        return None
    yaw = math.atan2(2 * (q.w * q.z + q.x * q.y),
                     1 - 2 * (q.y * q.y + q.z * q.z))
    return {"frame_id": "odom", "child_frame_id": "base_link",
            "x": float(pose.position.x), "y": float(pose.position.y), "yaw": yaw,
            "linear_mps": float(twist.linear.x),
            "angular_radps": float(twist.angular.z)}
