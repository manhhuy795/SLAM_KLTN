import numpy as np

from amr_exploration.grid_processing import (
    extract_clusters,
    frontier_mask,
    grid_to_world,
    occupancy_to_array,
    select_candidate_near_centroid,
    world_to_grid,
)

def test_occupancy_to_array_uses_current_width_height():
    data = [0, 0, -1, 100, 0, -1]

    grid = occupancy_to_array(
        data,
        width=3,
        height=2,
    )

    assert grid.shape == (2, 3)
    assert grid[0, 2] == -1
    assert grid[1, 0] == 100


def test_frontier_is_free_cell_adjacent_to_unknown():
    grid = np.array([
        [0,   0,  0],
        [0,   0, -1],
        [100, 0, -1],
    ], dtype=np.int16)

    mask = frontier_mask(grid)

    assert mask[0, 2]
    assert mask[1, 1]
    assert mask[2, 1]

    assert not mask[1, 2]
    assert not mask[2, 0]


def test_grid_world_round_trip():
    x, y = grid_to_world(
        row=2,
        col=3,
        resolution=0.05,
        origin_x=-1.0,
        origin_y=-2.0,
    )

    row, col = world_to_grid(
        x=x,
        y=y,
        resolution=0.05,
        origin_x=-1.0,
        origin_y=-2.0,
    )

    assert (row, col) == (2, 3)

def test_extract_clusters_removes_small_components():
    mask = np.zeros((8, 8), dtype=bool)

    # Cụm lớn gồm 4 ô
    mask[1:3, 1:3] = True

    # Một frontier đơn lẻ, quá nhỏ
    mask[5, 5] = True

    clusters = extract_clusters(
        mask,
        resolution=0.05,
        min_cluster_size=3,
        min_cluster_area_m2=0.005,
    )

    assert len(clusters) == 1
    assert clusters[0].cell_count == 4


def test_candidate_search_expands_from_centroid_until_free_cell():
    # Ban đầu toàn bộ là vùng chưa biết
    map_grid = np.full(
        (7, 7),
        -1,
        dtype=np.int16,
    )

    # Chỉ có một ô thực sự đi được
    map_grid[3, 1] = 0

    # Frontier gồm 3 ô
    mask = np.zeros(
        (7, 7),
        dtype=bool,
    )

    mask[3, 1:4] = True

    clusters = extract_clusters(
        mask,
        resolution=0.05,
        min_cluster_size=1,
        min_cluster_area_m2=0.0,
    )

    cluster = clusters[0]

    candidate = select_candidate_near_centroid(
        cluster=cluster,
        map_grid=map_grid,
        resolution=0.05,
        origin_x=0.0,
        origin_y=0.0,
        search_radius_m=0.20,
    )

    assert candidate is not None
    assert map_grid[
        candidate.row,
        candidate.col
    ] == 0

from amr_exploration.grid_processing import sample_costmap_cost


def test_sample_costmap_cost_returns_cell_value():
    cost_grid = np.array([
        [0, 10, 20],
        [30, 40, 50],
        [60, 70, 80],
    ], dtype=np.int16)

    cost = sample_costmap_cost(
        x=1.5,
        y=1.5,
        cost_grid=cost_grid,
        resolution=1.0,
        origin_x=0.0,
        origin_y=0.0,
    )

    assert cost == 40


def test_sample_costmap_cost_returns_none_outside_map():
    cost_grid = np.zeros(
        (3, 3),
        dtype=np.int16,
    )

    cost = sample_costmap_cost(
        x=10.0,
        y=10.0,
        cost_grid=cost_grid,
        resolution=1.0,
        origin_x=0.0,
        origin_y=0.0,
    )

    assert cost is None

def test_candidate_for_ring_frontier_must_lie_on_frontier():
    # Unknown toàn bản đồ.
    grid = np.full(
        (11, 11),
        -1,
        dtype=np.int8,
    )

    # Một vùng free hình vuông.
    # Frontier của vùng này sẽ tạo thành một "vòng"
    # bao quanh tâm (5, 5).
    grid[2:9, 2:9] = 0

    mask = frontier_mask(
        grid
    )

    clusters = extract_clusters(
        mask=mask,
        resolution=0.05,
        min_cluster_size=1,
        min_cluster_area_m2=0.0,
    )

    assert len(clusters) == 1

    cluster = clusters[0]

    candidate = select_candidate_near_centroid(
        cluster=cluster,
        map_grid=grid,
        resolution=0.05,
        origin_x=0.0,
        origin_y=0.0,
        search_radius_m=1.0,
    )

    assert candidate is not None

    # Candidate phải thực sự nằm trên frontier
    # của cluster, không được rơi vào vùng free
    # ở giữa vòng frontier.
    assert bool(
        mask[
            candidate.row,
            candidate.col,
        ]
    )