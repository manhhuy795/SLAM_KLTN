import numpy as np

from amr_exploration.scoring import (
    euclidean_distance,
    normalize,
    score_candidates,
)


def test_euclidean_distance():
    distance = euclidean_distance(
        robot_xy=(0.0, 0.0),
        goal_xy=(3.0, 4.0),
    )

    assert distance == 5.0


def test_normalize_constant_values_returns_zero():
    values = np.array([
        2.0,
        2.0,
        2.0,
    ])

    result = normalize(values)

    assert np.allclose(
        result,
        [0.0, 0.0, 0.0],
    )


def test_normalize_values_to_zero_one_range():
    values = np.array([
        10.0,
        20.0,
        30.0,
    ])

    result = normalize(values)

    assert np.allclose(
        result,
        [0.0, 0.5, 1.0],
    )


def test_score_prefers_large_near_frontier():
    scores = score_candidates(
        gains=np.array([
            10.0,
            4.0,
        ]),
        distances=np.array([
            1.0,
            3.0,
        ]),
        failures=np.array([
            0.0,
            0.0,
        ]),
        w_gain=0.6,
        w_distance=0.3,
        w_failure=0.1,
    )

    assert scores[0] > scores[1]
