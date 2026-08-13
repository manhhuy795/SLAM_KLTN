import math

import numpy as np


def euclidean_distance(
    robot_xy: tuple[float, float],
    goal_xy: tuple[float, float],
) -> float:
    """
    Tính khoảng cách đường thẳng từ robot tới goal.
    """
    return math.hypot(
        goal_xy[0] - robot_xy[0],
        goal_xy[1] - robot_xy[1],
    )


def normalize(
    values: np.ndarray,
) -> np.ndarray:
    """
    Chuẩn hóa mảng giá trị về khoảng 0.0 -> 1.0.

    Nếu tất cả giá trị giống nhau thì trả về toàn số 0.
    """
    values = np.asarray(
        values,
        dtype=float,
    )

    if values.size == 0:
        return values

    minimum = float(np.min(values))
    maximum = float(np.max(values))

    if maximum <= minimum:
        return np.zeros_like(
            values,
            dtype=float,
        )

    return (
        (values - minimum)
        / (maximum - minimum)
    )


def score_candidates(
    gains: np.ndarray,
    distances: np.ndarray,
    failures: np.ndarray,
    w_gain: float,
    w_distance: float,
    w_failure: float,
) -> np.ndarray:
    """
    Chấm điểm các candidate.

    Điểm cao khi:
    - vùng khám phá lớn;
    - khoảng cách nhỏ;
    - ít thất bại trước đó.
    """
    normalized_gain = normalize(gains)
    normalized_distance = normalize(distances)
    normalized_failure = normalize(failures)

    return (
        w_gain * normalized_gain
        - w_distance * normalized_distance
        - w_failure * normalized_failure
    )
