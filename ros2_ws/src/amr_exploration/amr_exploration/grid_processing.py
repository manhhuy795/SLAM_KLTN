from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass(frozen=True)
class FrontierCluster:
    label: int
    cell_count: int
    area_m2: float
    centroid_row: float
    centroid_col: float
    cells: tuple[tuple[int, int], ...] = field(
        default_factory=tuple,
        compare=False,
        repr=False,
    )



@dataclass(frozen=True)
class Candidate:
    row: int
    col: int
    x: float
    y: float
    cluster: FrontierCluster


def occupancy_to_array(
    data,
    width: int,
    height: int,
) -> np.ndarray:
    """
    Chuyển OccupancyGrid dạng 1 chiều thành ma trận 2 chiều.
    """
    array = np.asarray(data, dtype=np.int16)

    expected_size = width * height

    if array.size != expected_size:
        raise ValueError(
            f'OccupancyGrid size mismatch: '
            f'{array.size} != {width}x{height}'
        )

    return array.reshape((height, width))


def frontier_mask(
    grid: np.ndarray,
    free_value: int = 0,
    unknown_value: int = -1,
) -> np.ndarray:
    """
    Frontier là ô free nằm cạnh ít nhất một ô unknown.
    """
    free = grid == free_value

    unknown = (
        grid == unknown_value
    ).astype(np.uint8)

    kernel = np.ones(
        (3, 3),
        dtype=np.uint8,
    )

    unknown_neighbor = cv2.dilate(
        unknown,
        kernel,
        iterations=1,
    ).astype(bool)

    return free & unknown_neighbor


def grid_to_world(
    row: int,
    col: int,
    resolution: float,
    origin_x: float,
    origin_y: float,
) -> tuple[float, float]:
    """
    Chuyển hàng/cột của bản đồ sang tọa độ x,y theo mét.
    """
    x = origin_x + (col + 0.5) * resolution
    y = origin_y + (row + 0.5) * resolution

    return x, y


def world_to_grid(
    x: float,
    y: float,
    resolution: float,
    origin_x: float,
    origin_y: float,
) -> tuple[int, int]:
    """
    Chuyển tọa độ x,y theo mét về hàng/cột của bản đồ.
    """
    col = int(
        np.floor(
            (x - origin_x) / resolution
        )
    )

    row = int(
        np.floor(
            (y - origin_y) / resolution
        )
    )

    return row, col


def extract_clusters(
    mask: np.ndarray,
    resolution: float,
    min_cluster_size: int,
    min_cluster_area_m2: float,
) -> list[FrontierCluster]:
    """
    Gom các ô frontier nằm gần nhau thành từng cụm.
    """
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8),
        connectivity=8,
    )

    clusters = []

    # label = 0 là background nên bỏ qua
    for label in range(1, count):
        cell_count = int(
            stats[label, cv2.CC_STAT_AREA]
        )

        area_m2 = (
            cell_count
            * resolution
            * resolution
        )

        if cell_count < min_cluster_size:
            continue

        if area_m2 < min_cluster_area_m2:
            continue

        centroid_col, centroid_row = centroids[label]

        cell_coordinates = np.argwhere(
            labels == label
        )

        cells = tuple(
            (
                int(row),
                int(col),
            )
            for row, col in cell_coordinates
        )

        clusters.append(
            FrontierCluster(
                cells=cells,
                label=label,
                cell_count=cell_count,
                area_m2=area_m2,
                centroid_row=float(centroid_row),
                centroid_col=float(centroid_col),
            )
        )

    return clusters


def select_candidate_near_centroid(
    cluster: FrontierCluster,
    map_grid: np.ndarray,
    resolution: float,
    origin_x: float,
    origin_y: float,
    search_radius_m: float,
) -> Candidate | None:
    """
    Tìm ô free gần tâm của cụm frontier nhất.

    Nếu tâm cụm không phải ô free thì mở rộng vùng tìm kiếm
    dần dần cho tới giới hạn search_radius_m.
    """
    center_row = int(
        round(cluster.centroid_row)
    )

    center_col = int(
        round(cluster.centroid_col)
    )

    if cluster.cells:
        valid_cells = [
            (row, col)
            for row, col in cluster.cells
            if (
                0 <= row < map_grid.shape[0]
                and 0 <= col < map_grid.shape[1]
                and map_grid[row, col] == 0
            )
        ]

        if not valid_cells:
            return None

        row, col = min(
            valid_cells,
            key=lambda cell: (
                (cell[0] - cluster.centroid_row) ** 2
                +
                (cell[1] - cluster.centroid_col) ** 2
            ),
        )

        x, y = grid_to_world(
            row=row,
            col=col,
            resolution=resolution,
            origin_x=origin_x,
            origin_y=origin_y,
        )

        return Candidate(
            row=row,
            col=col,
            x=x,
            y=y,
            cluster=cluster,
        )

    max_radius_cells = max(
        0,
        int(
            np.ceil(
                search_radius_m / resolution
            )
        ),
    )

    height, width = map_grid.shape

    for radius in range(max_radius_cells + 1):

        row_min = max(
            0,
            center_row - radius,
        )

        row_max = min(
            height,
            center_row + radius + 1,
        )

        col_min = max(
            0,
            center_col - radius,
        )

        col_max = min(
            width,
            center_col + radius + 1,
        )

        search_area = map_grid[
            row_min:row_max,
            col_min:col_max
        ]

        rows, cols = np.where(
            search_area == 0
        )

        if rows.size == 0:
            continue

        # Chuyển tọa độ trong cửa sổ nhỏ
        # về tọa độ trên toàn bản đồ.
        rows = rows + row_min
        cols = cols + col_min

        # Nếu có nhiều ô free thì lấy ô gần tâm cụm nhất.
        distances = (
            (rows - cluster.centroid_row) ** 2
            +
            (cols - cluster.centroid_col) ** 2
        )

        best_index = int(
            np.argmin(distances)
        )

        row = int(rows[best_index])
        col = int(cols[best_index])

        x, y = grid_to_world(
            row=row,
            col=col,
            resolution=resolution,
            origin_x=origin_x,
            origin_y=origin_y,
        )

        return Candidate(
            row=row,
            col=col,
            x=x,
            y=y,
            cluster=cluster,
        )

    return None

def sample_costmap_cost(
    x: float,
    y: float,
    cost_grid: np.ndarray,
    resolution: float,
    origin_x: float,
    origin_y: float,
) -> int | None:
    """
    Lấy giá trị costmap tại tọa độ x, y.

    Trả None nếu tọa độ nằm ngoài costmap.
    """
    row, col = world_to_grid(
        x=x,
        y=y,
        resolution=resolution,
        origin_x=origin_x,
        origin_y=origin_y,
    )

    height, width = cost_grid.shape

    if (
        row < 0
        or col < 0
        or row >= height
        or col >= width
    ):
        return None

    return int(
        cost_grid[row, col]
    )
