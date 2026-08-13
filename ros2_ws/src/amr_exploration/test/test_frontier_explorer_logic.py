from types import SimpleNamespace

from amr_exploration.frontier_explorer_node import FrontierExplorerNode
from amr_exploration.state import ExplorerSession
from amr_exploration.blacklist import Blacklist

class FakeLogger:
    def debug(self, message):
        pass

    def info(self, message):
        pass

    def warn(self, message):
        pass


class FakeReadyExplorer:
    def __init__(self):
        self.enabled = True
        self.session = ExplorerSession()
        self.logger = FakeLogger()

    def get_logger(self):
        return self.logger

    def get_parameter(self, name):
        values = {
            'required_empty_checks': 3,
        }
        return SimpleNamespace(
            value=values[name]
        )

    def _selection_inputs_ready(self):
        return True

    def _get_robot_xy(self):
        return (0.0, 0.0)

    def _compute_best_candidate(self, robot_xy):
        assert robot_xy == (0.0, 0.0)
        return None


class FakeMissingTfExplorer(FakeReadyExplorer):
    def _get_robot_xy(self):
        return None

    def _compute_best_candidate(self, robot_xy):
        raise AssertionError(
            'Candidate selection must not run without TF'
        )


def test_valid_empty_selection_increments_empty_counter():
    explorer = FakeReadyExplorer()

    FrontierExplorerNode._exploration_tick(
        explorer
    )

    assert explorer.session.no_frontier_count == 1


def test_missing_tf_does_not_increment_empty_counter():
    explorer = FakeMissingTfExplorer()

    FrontierExplorerNode._exploration_tick(
        explorer
    )

    assert explorer.session.no_frontier_count == 0

class FakeNavClient:
    def __init__(self, ready=True):
        self.ready = ready

    def server_is_ready(self):
        return self.ready


class FakeReadinessExplorer:
    def __init__(
        self,
        *,
        has_map=True,
        has_costmap=True,
        costmap_time=100.0,
        nav_ready=True,
        map_frame='map',
        costmap_frame='map',
        ):
        self.latest_map = (
            SimpleNamespace(
                header=SimpleNamespace(
                    frame_id=map_frame
                )
            )
            if has_map
            else None
        )

        self.latest_costmap = (
            SimpleNamespace(
                header=SimpleNamespace(
                    frame_id=costmap_frame
                )
            )
            if has_costmap
            else None
        )

        self.latest_costmap_received_monotonic = (
            costmap_time
            if has_costmap
            else None
        )

        self.nav_client = FakeNavClient(
            nav_ready
        )

        self.logger = FakeLogger()

    def get_logger(self):
        return self.logger

    def get_parameter(self, name):
        values = {
            'max_costmap_age_sec': 2.0,
            'map_frame': 'map',
        }

        return SimpleNamespace(
            value=values[name]
        )


def test_selection_not_ready_without_map(
    monkeypatch,
):
    explorer = FakeReadinessExplorer(
        has_map=False
    )

    monkeypatch.setattr(
        'amr_exploration.frontier_explorer_node.time.monotonic',
        lambda: 101.0,
    )

    assert (
        FrontierExplorerNode._selection_inputs_ready(
            explorer
        )
        is False
    )


def test_selection_not_ready_without_costmap(
    monkeypatch,
):
    explorer = FakeReadinessExplorer(
        has_costmap=False
    )

    monkeypatch.setattr(
        'amr_exploration.frontier_explorer_node.time.monotonic',
        lambda: 101.0,
    )

    assert (
        FrontierExplorerNode._selection_inputs_ready(
            explorer
        )
        is False
    )


def test_selection_not_ready_with_stale_costmap(
    monkeypatch,
):
    explorer = FakeReadinessExplorer(
        costmap_time=95.0
    )

    monkeypatch.setattr(
        'amr_exploration.frontier_explorer_node.time.monotonic',
        lambda: 101.0,
    )

    assert (
        FrontierExplorerNode._selection_inputs_ready(
            explorer
        )
        is False
    )


def test_selection_not_ready_when_nav2_missing(
    monkeypatch,
):
    explorer = FakeReadinessExplorer(
        nav_ready=False
    )

    monkeypatch.setattr(
        'amr_exploration.frontier_explorer_node.time.monotonic',
        lambda: 101.0,
    )

    assert (
        FrontierExplorerNode._selection_inputs_ready(
            explorer
        )
        is False
    )


def test_selection_not_ready_with_wrong_frame(
    monkeypatch,
):
    explorer = FakeReadinessExplorer(
        costmap_frame='odom'
    )

    monkeypatch.setattr(
        'amr_exploration.frontier_explorer_node.time.monotonic',
        lambda: 101.0,
    )

    assert (
        FrontierExplorerNode._selection_inputs_ready(
            explorer
        )
        is False
    )


def test_selection_ready_when_all_inputs_valid(
    monkeypatch,
):
    explorer = FakeReadinessExplorer()

    monkeypatch.setattr(
        'amr_exploration.frontier_explorer_node.time.monotonic',
        lambda: 101.0,
    )

    assert (
        FrontierExplorerNode._selection_inputs_ready(
            explorer
        )
        is True
    )
class FakeTfBuffer:
    def lookup_transform(
        self,
        target_frame,
        source_frame,
        query_time,
    ):
        assert target_frame == 'map'
        assert source_frame == 'base_link'

        return SimpleNamespace(
            transform=SimpleNamespace(
                translation=SimpleNamespace(
                    x=1.25,
                    y=-0.40,
                    z=0.0,
                )
            )
        )


class FakeTfExplorer:
    def __init__(self):
        self.tf_buffer = FakeTfBuffer()
        self.logger = FakeLogger()

    def get_logger(self):
        return self.logger

    def get_parameter(self, name):
        values = {
            'map_frame': 'map',
            'robot_base_frame': 'base_link',
        }

        return SimpleNamespace(
            value=values[name]
        )


def test_get_robot_xy_from_tf():
    explorer = FakeTfExplorer()

    robot_xy = FrontierExplorerNode._get_robot_xy(
        explorer
    )

    assert robot_xy == (
        1.25,
        -0.40,
    )

class FakeMissingTfBuffer:
    def lookup_transform(
        self,
        target_frame,
        source_frame,
        query_time,
    ):
        from tf2_ros import TransformException

        raise TransformException(
            'TF temporarily unavailable'
        )


class FakeMissingTfLookupExplorer:
    def __init__(self):
        self.tf_buffer = FakeMissingTfBuffer()
        self.logger = FakeLogger()

    def get_logger(self):
        return self.logger

    def get_parameter(self, name):
        values = {
            'map_frame': 'map',
            'robot_base_frame': 'base_link',
        }

        return SimpleNamespace(
            value=values[name]
        )


def test_get_robot_xy_returns_none_when_tf_missing():
    explorer = FakeMissingTfLookupExplorer()

    robot_xy = FrontierExplorerNode._get_robot_xy(
        explorer
    )

    assert robot_xy is None

def make_grid_msg(
    data,
    width,
    height,
    resolution=1.0,
):
    return SimpleNamespace(
        data=data,
        info=SimpleNamespace(
            width=width,
            height=height,
            resolution=resolution,
            origin=SimpleNamespace(
                position=SimpleNamespace(
                    x=0.0,
                    y=0.0,
                )
            ),
        ),
    )


class FakeCandidateExplorer:
    def __init__(self):
        # Một vùng free 3x3 nằm giữa unknown.
        # Frontier sẽ là vòng ngoài của vùng free.
        self.latest_map = make_grid_msg(
            data=[
                -1, -1, -1, -1, -1,
                -1,  0,  0,  0, -1,
                -1,  0,  0,  0, -1,
                -1,  0,  0,  0, -1,
                -1, -1, -1, -1, -1,
            ],
            width=5,
            height=5,
        )

        # Costmap hoàn toàn an toàn.
        self.latest_costmap = make_grid_msg(
            data=[
                0, 0, 0, 0, 0,
                0, 0, 0, 0, 0,
                0, 0, 0, 0, 0,
                0, 0, 0, 0, 0,
                0, 0, 0, 0, 0,
            ],
            width=5,
            height=5,
        )

        self.blacklist = Blacklist(
            radius=0.4,
            failure_limit=2,
        )

        self.logger = FakeLogger()

    def get_logger(self):
        return self.logger

    def get_parameter(self, name):
        values = {
            'min_cluster_size': 1,
            'min_cluster_area_m2': 0.0,
            'candidate_search_radius': 1.0,
            'costmap_reject_threshold': 80,
            'w_gain': 0.6,
            'w_distance': 0.3,
            'w_failure': 0.1,
        }

        return SimpleNamespace(
            value=values[name]
        )


def test_compute_best_candidate_returns_valid_frontier():
    explorer = FakeCandidateExplorer()

    candidate = (
        FrontierExplorerNode._compute_best_candidate(
            explorer,
            robot_xy=(0.5, 0.5),
        )
    )

    assert candidate is not None

    assert candidate.x == 2.5
    assert candidate.y == 2.5

class FakeUnsafeCandidateExplorer(
    FakeCandidateExplorer
):
    def __init__(self):
        super().__init__()

        # Candidate hiện tại nằm tại cell giữa:
        # row=2, col=2 -> x=2.5, y=2.5
        #
        # Đặt cost = 100 để mô phỏng
        # vị trí không an toàn.
        self.latest_costmap = make_grid_msg(
            data=[
                0, 0,   0, 0, 0,
                0, 0,   0, 0, 0,
                0, 0, 100, 0, 0,
                0, 0,   0, 0, 0,
                0, 0,   0, 0, 0,
            ],
            width=5,
            height=5,
        )


def test_compute_best_candidate_rejects_high_costmap_cost():
    explorer = FakeUnsafeCandidateExplorer()

    candidate = (
        FrontierExplorerNode._compute_best_candidate(
            explorer,
            robot_xy=(0.5, 0.5),
        )
    )

    assert candidate is None


class FakeBlacklistedCandidateExplorer(
    FakeCandidateExplorer
):
    def __init__(self):
        super().__init__()

        # Candidate dự kiến tại (2.5, 2.5).
        # Ghi nhận thất bại đủ 2 lần để vùng này
        # trở thành blacklist.
        self.blacklist.record_failure(
            2.5,
            2.5,
        )

        self.blacklist.record_failure(
            2.5,
            2.5,
        )


def test_compute_best_candidate_rejects_blacklisted_area():
    explorer = FakeBlacklistedCandidateExplorer()

    candidate = (
        FrontierExplorerNode._compute_best_candidate(
            explorer,
            robot_xy=(0.5, 0.5),
        )
    )

    assert candidate is None


class FakeMultipleCandidateExplorer(
    FakeCandidateExplorer
):
    def __init__(self):
        super().__init__()

        # Có 2 vùng free tách biệt:
        #
        # A: vùng nhỏ 2x2 ở phía trên-trái
        # B: vùng lớn 3x3 ở phía dưới-phải
        #
        # Connected-components sẽ thấy A trước,
        # nhưng robot đứng gần B.
        self.latest_map = make_grid_msg(
            data=[
                -1, -1, -1, -1, -1, -1, -1, -1, -1,
                -1,  0,  0, -1, -1, -1, -1, -1, -1,
                -1,  0,  0, -1, -1, -1, -1, -1, -1,
                -1, -1, -1, -1, -1, -1, -1, -1, -1,
                -1, -1, -1, -1, -1, -1, -1, -1, -1,
                -1, -1, -1, -1, -1,  0,  0,  0, -1,
                -1, -1, -1, -1, -1,  0,  0,  0, -1,
                -1, -1, -1, -1, -1,  0,  0,  0, -1,
                -1, -1, -1, -1, -1, -1, -1, -1, -1,
            ],
            width=9,
            height=9,
        )

        # Toàn bộ costmap an toàn.
        self.latest_costmap = make_grid_msg(
            data=[0] * 81,
            width=9,
            height=9,
        )


def test_compute_best_candidate_uses_score_not_cluster_order():
    explorer = FakeMultipleCandidateExplorer()

    candidate = (
        FrontierExplorerNode._compute_best_candidate(
            explorer,
            robot_xy=(6.5, 6.5),
        )
    )

    assert candidate is not None

    # Candidate tốt nhất phải thuộc vùng B:
    # vừa lớn hơn vừa gần robot hơn.
    assert candidate.x == 6.5
    assert candidate.y == 6.5


class FakeFailurePenaltyExplorer(
    FakeCandidateExplorer
):
    def __init__(self):
        super().__init__()

        # Hai frontier có cùng kích thước
        # và cách robot một khoảng bằng nhau.
        #
        # A -> candidate (2.5, 2.5)
        # B -> candidate (6.5, 2.5)
        self.latest_map = make_grid_msg(
            data=[
                -1, -1, -1, -1, -1, -1, -1, -1, -1,
                -1,  0,  0, -1, -1, -1,  0,  0, -1,
                -1,  0,  0, -1, -1, -1,  0,  0, -1,
                -1, -1, -1, -1, -1, -1, -1, -1, -1,
                -1, -1, -1, -1, -1, -1, -1, -1, -1,
            ],
            width=9,
            height=5,
        )

        self.latest_costmap = make_grid_msg(
            data=[0] * 45,
            width=9,
            height=5,
        )

        # A thất bại 1 lần.
        # failure_limit = 2 nên A CHƯA bị blacklist.
        self.blacklist.record_failure(
            2.5,
            2.5,
        )


def test_compute_best_candidate_penalizes_previous_failure():
    explorer = FakeFailurePenaltyExplorer()

    assert explorer.blacklist.contains(
        2.5,
        2.5,
    ) is False

    assert explorer.blacklist.failure_count(
        2.5,
        2.5,
    ) == 1

    candidate = (
        FrontierExplorerNode._compute_best_candidate(
            explorer,
            robot_xy=(4.5, 2.5),
        )
    )

    assert candidate is not None

    # Hai candidate cùng gain và cùng khoảng cách.
    # B phải thắng vì A đã từng thất bại.
    assert candidate.x == 6.5
    assert candidate.y == 2.5


class RecordingLogger:
    def __init__(self):
        self.info_messages = []

    def debug(self, message):
        pass

    def warn(self, message):
        pass

    def info(self, message):
        self.info_messages.append(message)


class FakeCandidateTickExplorer(
    FakeReadyExplorer
):
    def __init__(self):
        super().__init__()
        self.logger = RecordingLogger()

    def _compute_best_candidate(
        self,
        robot_xy,
    ):
        return SimpleNamespace(
            x=1.25,
            y=2.50,
            cluster=SimpleNamespace(
                cell_count=12,
                area_m2=0.30,
            ),
        )


def test_tick_logs_selected_candidate():
    explorer = FakeCandidateTickExplorer()

    FrontierExplorerNode._exploration_tick(
        explorer
    )

    assert any(
        'Best frontier candidate' in message
        and 'x=1.25' in message
        and 'y=2.50' in message
        for message in explorer.logger.info_messages
    )
