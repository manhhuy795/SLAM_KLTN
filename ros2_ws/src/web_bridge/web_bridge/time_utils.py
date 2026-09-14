import math


def ros_time_to_seconds(stamp):
    if stamp is None:
        return None

    try:
        value = float(stamp.sec) + float(stamp.nanosec) * 1e-9
    except (AttributeError, TypeError, ValueError):
        return None

    if not math.isfinite(value) or value <= 0:
        return None

    return value


def transform_timestamp(transform, fallback):
    header = getattr(transform, "header", None)
    timestamp = ros_time_to_seconds(
        getattr(header, "stamp", None)
    )
    return timestamp if timestamp is not None else fallback
