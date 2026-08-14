from types import SimpleNamespace
from action_msgs.msg import GoalStatus

from nav2_msgs.action import NavigateToPose

from amr_exploration.frontier_explorer_node import FrontierExplorerNode
from amr_exploration.state import (
    ExplorerSession,
    ExplorerState,
)
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

    # Candidate phải là một cell thật sự thuộc frontier,
    # không được rơi vào centroid (2.5, 2.5).
    assert (
        candidate.row,
        candidate.col,
    ) in candidate.cluster.cells

    assert (
        candidate.x,
        candidate.y,
    ) != (2.5, 2.5)

class FakeUnsafeCandidateExplorer(
    FakeCandidateExplorer
):
    def __init__(self):
        super().__init__()

        # Candidate frontier được chọn:
        # row=1, col=2 -> x=2.5, y=1.5
        #
        # Đặt cost = 100 để mô phỏng
        # vị trí không an toàn.
        self.latest_costmap = make_grid_msg(
            data=[
                0, 0,   0, 0, 0,
                0, 0, 100, 0, 0,
                0, 0,   0, 0, 0,
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
        # Candidate frontier tại (2.5, 1.5).
        self.blacklist.record_failure(
            2.5,
            1.5,
        )

        self.blacklist.record_failure(
            2.5,
            1.5,
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
    # Candidate phải thuộc vùng B,
    # không quan trọng cell frontier nào trong B.
    assert candidate.cluster.cell_count == 8

    assert candidate.row >= 5
    assert candidate.col >= 5


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
            1.5,
            1.5,
        )


def test_compute_best_candidate_penalizes_previous_failure():
    explorer = FakeFailurePenaltyExplorer()

    assert explorer.blacklist.contains(
        1.5,
        1.5,
    ) is False

    assert explorer.blacklist.failure_count(
        1.5,
        1.5,
    ) == 1

    candidate = (
        FrontierExplorerNode._compute_best_candidate(
            explorer,
            robot_xy=(4.0, 1.5),
        )
    )

    assert candidate is not None

    # Hai candidate cùng gain và cùng khoảng cách.
    # B phải thắng vì A đã từng thất bại.
    assert candidate.x == 6.5
    assert candidate.y == 1.5


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

    def _send_navigation_goal(
        self,
        candidate,
    ):
        pass

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

class FakeNavigationTickExplorer(
    FakeCandidateTickExplorer
):
    def __init__(self):
        super().__init__()
        self.sent_candidates = []

    def _send_navigation_goal(
        self,
        candidate,
    ):
        self.sent_candidates.append(
            candidate
        )


def test_tick_sends_selected_candidate_to_navigation():
    explorer = FakeNavigationTickExplorer()

    FrontierExplorerNode._exploration_tick(
        explorer
    )

    assert len(
        explorer.sent_candidates
    ) == 1

    candidate = explorer.sent_candidates[0]

    assert candidate.x == 1.25
    assert candidate.y == 2.50

class FakeClockTime:
    def to_msg(self):
        return SimpleNamespace(
            sec=123,
            nanosec=456,
        )


class FakeClock:
    def now(self):
        return FakeClockTime()


class FakeGoalBuilderExplorer:
    def get_parameter(self, name):
        values = {
            'map_frame': 'map',
        }

        return SimpleNamespace(
            value=values[name]
        )

    def get_clock(self):
        return FakeClock()


def test_build_navigation_goal_uses_candidate_pose():
    explorer = FakeGoalBuilderExplorer()

    candidate = SimpleNamespace(
        x=1.25,
        y=2.50,
    )

    goal = FrontierExplorerNode._build_navigation_goal(
        explorer,
        candidate,
    )

    assert isinstance(
        goal,
        NavigateToPose.Goal,
    )

    assert goal.pose.header.frame_id == 'map'

    assert goal.pose.pose.position.x == 1.25
    assert goal.pose.pose.position.y == 2.50
    assert goal.pose.pose.position.z == 0.0

    assert goal.pose.pose.orientation.x == 0.0
    assert goal.pose.pose.orientation.y == 0.0
    assert goal.pose.pose.orientation.z == 0.0
    assert goal.pose.pose.orientation.w == 1.0

class FakeGoalFuture:
    def __init__(self):
        self.callback = None

    def add_done_callback(
        self,
        callback,
    ):
        self.callback = callback


class FakeNavigateClient:
    def __init__(self):
        self.sent_goals = []
        self.future = FakeGoalFuture()

    def send_goal_async(
        self,
        goal,
    ):
        self.sent_goals.append(
            goal
        )
        return self.future


class FakeSendGoalExplorer:
    def __init__(self):
        self.session = ExplorerSession()
        self.nav_client = FakeNavigateClient()
        self.logger = FakeLogger()

    def get_logger(self):
        return self.logger

    def get_parameter(self, name):
        values = {
            'map_frame': 'map',
        }

        return SimpleNamespace(
            value=values[name]
        )

    def _build_navigation_goal(
        self,
        candidate,
        ):
        return FrontierExplorerNode._build_navigation_goal(
            self,
            candidate,
        )

    def _goal_response_callback(
        self,
        future,
        ):
        pass


def test_send_navigation_goal_sends_action_and_enters_navigating():
    explorer = FakeSendGoalExplorer()

    candidate = SimpleNamespace(
        x=1.25,
        y=2.50,
    )

    FrontierExplorerNode._send_navigation_goal(
        explorer,
        candidate,
    )

    assert explorer.session.state is ExplorerState.NAVIGATING

    assert explorer.session.active_goal_xy == (
        1.25,
        2.50,
    )

    assert len(
        explorer.nav_client.sent_goals
    ) == 1

    goal = explorer.nav_client.sent_goals[0]

    assert goal.pose.header.frame_id == 'map'
    assert goal.pose.pose.position.x == 1.25
    assert goal.pose.pose.position.y == 2.50

    assert (
        explorer.nav_client.future.callback
        is not None
    )


class FakeActionResultFuture:
    def __init__(self):
        self.callback = None

    def add_done_callback(
        self,
        callback,
    ):
        self.callback = callback


class FakeGoalHandle:
    def __init__(
        self,
        accepted,
    ):
        self.accepted = accepted
        self.result_future = FakeActionResultFuture()

    def get_result_async(self):
        return self.result_future


class FakeGoalResponseFuture:
    def __init__(
        self,
        goal_handle,
    ):
        self.goal_handle = goal_handle

    def result(self):
        return self.goal_handle


class FakeGoalResponseExplorer:
    def __init__(self):
        self.session = ExplorerSession()
        self.session.start_navigation(
            (1.25, 2.50)
        )

        self.blacklist = Blacklist(
            radius=0.4,
            failure_limit=2,
        )

        self.logger = FakeLogger()
        self.active_goal_handle = None
        self.goal_started_monotonic = None
        self.goal_cancel_requested = True

    def get_logger(self):
        return self.logger

    def _navigation_result_callback(
        self,
        future,
    ):
        pass

    def _clear_navigation_tracking(
        self,
    ):
        return FrontierExplorerNode._clear_navigation_tracking(
            self
        )


def test_goal_rejected_returns_to_idle_and_records_failure():
    explorer = FakeGoalResponseExplorer()

    goal_handle = FakeGoalHandle(
        accepted=False
    )

    future = FakeGoalResponseFuture(
        goal_handle
    )

    FrontierExplorerNode._goal_response_callback(
        explorer,
        future,
    )

    assert explorer.session.state is ExplorerState.IDLE
    assert explorer.session.active_goal_xy is None

    assert explorer.blacklist.failure_count(
        1.25,
        2.50,
    ) == 1


def test_goal_accepted_keeps_navigating_and_waits_for_result():
    explorer = FakeGoalResponseExplorer()

    goal_handle = FakeGoalHandle(
        accepted=True
    )

    future = FakeGoalResponseFuture(
        goal_handle
    )

    FrontierExplorerNode._goal_response_callback(
        explorer,
        future,
    )

    assert (
        explorer.session.state
        is ExplorerState.NAVIGATING
    )

    assert (
        explorer.session.active_goal_xy
        == (1.25, 2.50)
    )

    assert (
        goal_handle.result_future.callback
        is not None
    )

    assert explorer.blacklist.failure_count(
        1.25,
        2.50,
    ) == 0

class FakeNavigationResultFuture:
    def __init__(
        self,
        status,
    ):
        self.status = status

    def result(self):
        return SimpleNamespace(
            status=self.status
        )


class FakeNavigationResultExplorer:
    def __init__(self):
        self.session = ExplorerSession()

        self.session.start_navigation(
            (1.25, 2.50)
        )

        self.blacklist = Blacklist(
            radius=0.4,
            failure_limit=2,
        )

        self.logger = FakeLogger()
        self.active_goal_handle = object()
        self.goal_started_monotonic = 100.0
        self.goal_cancel_requested = True

    def _clear_navigation_tracking(
        self,
    ):
        return FrontierExplorerNode._clear_navigation_tracking(
            self
        )

    def get_logger(self):
        return self.logger


def test_navigation_success_returns_to_idle_without_failure():
    explorer = FakeNavigationResultExplorer()

    future = FakeNavigationResultFuture(
        GoalStatus.STATUS_SUCCEEDED
    )

    FrontierExplorerNode._navigation_result_callback(
        explorer,
        future,
    )

    assert explorer.session.state is ExplorerState.IDLE
    assert explorer.session.active_goal_xy is None

    assert explorer.blacklist.failure_count(
        1.25,
        2.50,
    ) == 0


def test_navigation_aborted_records_failure_and_returns_idle():
    explorer = FakeNavigationResultExplorer()

    future = FakeNavigationResultFuture(
        GoalStatus.STATUS_ABORTED
    )

    FrontierExplorerNode._navigation_result_callback(
        explorer,
        future,
    )

    assert explorer.session.state is ExplorerState.IDLE
    assert explorer.session.active_goal_xy is None

    assert explorer.blacklist.failure_count(
        1.25,
        2.50,
    ) == 1


def test_navigation_canceled_records_failure_and_returns_idle():
    explorer = FakeNavigationResultExplorer()

    future = FakeNavigationResultFuture(
        GoalStatus.STATUS_CANCELED
    )

    FrontierExplorerNode._navigation_result_callback(
        explorer,
        future,
    )

    assert explorer.session.state is ExplorerState.IDLE
    assert explorer.session.active_goal_xy is None

    assert explorer.blacklist.failure_count(
        1.25,
        2.50,
    ) == 1

class FakeCancelableGoalHandle:
    def __init__(self):
        self.cancel_calls = 0

    def cancel_goal_async(self):
        self.cancel_calls += 1
        return SimpleNamespace()


class FakeTimeoutExplorer:
    def __init__(
        self,
        *,
        started_at=100.0,
        timeout=10.0,
    ):
        self.session = ExplorerSession()
        self.session.start_navigation(
            (1.25, 2.50)
        )

        self.active_goal_handle = (
            FakeCancelableGoalHandle()
        )

        self.goal_started_monotonic = (
            started_at
        )

        self.goal_cancel_requested = False
        self.timeout = timeout
        self.logger = FakeLogger()

    def get_logger(self):
        return self.logger

    def get_parameter(self, name):
        values = {
            'goal_timeout_sec': self.timeout,
        }

        return SimpleNamespace(
            value=values[name]
        )


def test_navigation_before_timeout_does_not_cancel(
    monkeypatch,
):
    explorer = FakeTimeoutExplorer(
        started_at=100.0,
        timeout=10.0,
    )

    monkeypatch.setattr(
        'amr_exploration.frontier_explorer_node.time.monotonic',
        lambda: 105.0,
    )

    timed_out = (
        FrontierExplorerNode._check_navigation_timeout(
            explorer
        )
    )

    assert timed_out is False
    assert (
        explorer.active_goal_handle.cancel_calls
        == 0
    )


def test_navigation_timeout_requests_cancel(
    monkeypatch,
):
    explorer = FakeTimeoutExplorer(
        started_at=100.0,
        timeout=10.0,
    )

    monkeypatch.setattr(
        'amr_exploration.frontier_explorer_node.time.monotonic',
        lambda: 111.0,
    )

    timed_out = (
        FrontierExplorerNode._check_navigation_timeout(
            explorer
        )
    )

    assert timed_out is True
    assert (
        explorer.active_goal_handle.cancel_calls
        == 1
    )

    assert explorer.goal_cancel_requested is True

    # Vẫn NAVIGATING cho tới khi Nav2 trả
    # result CANCELED.
    assert (
        explorer.session.state
        is ExplorerState.NAVIGATING
    )


def test_timeout_does_not_send_cancel_twice(
    monkeypatch,
):
    explorer = FakeTimeoutExplorer(
        started_at=100.0,
        timeout=10.0,
    )

    monkeypatch.setattr(
        'amr_exploration.frontier_explorer_node.time.monotonic',
        lambda: 111.0,
    )

    FrontierExplorerNode._check_navigation_timeout(
        explorer
    )

    FrontierExplorerNode._check_navigation_timeout(
        explorer
    )

    assert (
        explorer.active_goal_handle.cancel_calls
        == 1
    )

def test_goal_accepted_stores_handle_and_starts_timeout(
    monkeypatch,
):
    explorer = FakeGoalResponseExplorer()

    goal_handle = FakeGoalHandle(
        accepted=True
    )

    future = FakeGoalResponseFuture(
        goal_handle
    )

    monkeypatch.setattr(
        'amr_exploration.frontier_explorer_node.time.monotonic',
        lambda: 123.0,
    )

    FrontierExplorerNode._goal_response_callback(
        explorer,
        future,
    )

    assert (
        explorer.active_goal_handle
        is goal_handle
    )

    assert (
        explorer.goal_started_monotonic
        == 123.0
    )

    assert (
        explorer.goal_cancel_requested
        is False
    )

class FakeNavigatingTickExplorer:
    def __init__(self):
        self.enabled = True

        self.session = ExplorerSession()
        self.session.start_navigation(
            (1.25, 2.50)
        )

        self.timeout_checks = 0

    def _check_navigation_timeout(
        self,
    ):
        self.timeout_checks += 1
        return False


def test_tick_checks_timeout_while_navigating():
    explorer = FakeNavigatingTickExplorer()

    FrontierExplorerNode._exploration_tick(
        explorer
    )

    assert explorer.timeout_checks == 1

    assert (
        explorer.session.state
        is ExplorerState.NAVIGATING
    )
def test_navigation_success_clears_goal_tracking():
    explorer = FakeNavigationResultExplorer()

    future = FakeNavigationResultFuture(
        GoalStatus.STATUS_SUCCEEDED
    )

    FrontierExplorerNode._navigation_result_callback(
        explorer,
        future,
    )

    assert explorer.active_goal_handle is None
    assert explorer.goal_started_monotonic is None
    assert explorer.goal_cancel_requested is False

def test_navigation_aborted_clears_goal_tracking():
    explorer = FakeNavigationResultExplorer()

    future = FakeNavigationResultFuture(
        GoalStatus.STATUS_ABORTED
    )

    FrontierExplorerNode._navigation_result_callback(
        explorer,
        future,
    )

    assert explorer.active_goal_handle is None
    assert explorer.goal_started_monotonic is None
    assert explorer.goal_cancel_requested is False


def test_navigation_canceled_clears_goal_tracking():
    explorer = FakeNavigationResultExplorer()

    future = FakeNavigationResultFuture(
        GoalStatus.STATUS_CANCELED
    )

    FrontierExplorerNode._navigation_result_callback(
        explorer,
        future,
    )

    assert explorer.active_goal_handle is None
    assert explorer.goal_started_monotonic is None
    assert explorer.goal_cancel_requested is False

def test_goal_rejected_clears_navigation_tracking():
    explorer = FakeGoalResponseExplorer()

    # Giả lập còn dữ liệu tracking cũ.
    explorer.active_goal_handle = object()
    explorer.goal_started_monotonic = 100.0
    explorer.goal_cancel_requested = True

    goal_handle = FakeGoalHandle(
        accepted=False
    )

    future = FakeGoalResponseFuture(
        goal_handle
    )

    FrontierExplorerNode._goal_response_callback(
        explorer,
        future,
    )

    assert explorer.session.state is ExplorerState.IDLE
    assert explorer.session.active_goal_xy is None

    assert explorer.active_goal_handle is None
    assert explorer.goal_started_monotonic is None
    assert explorer.goal_cancel_requested is False

def test_disable_while_navigating_requests_cancel():
    explorer = FakeTimeoutExplorer()

    request = SimpleNamespace(
        data=False
    )
    response = SimpleNamespace()

    FrontierExplorerNode._set_enabled_callback(
        explorer,
        request,
        response,
    )

    assert explorer.enabled is False
    assert response.success is True
    assert (
        response.message
        == 'Frontier exploration disabled'
    )

    assert (
        explorer.active_goal_handle.cancel_calls
        == 1
    )

    assert explorer.goal_cancel_requested is True

    # Giữ NAVIGATING cho tới khi Nav2
    # trả result CANCELED.
    assert (
        explorer.session.state
        is ExplorerState.NAVIGATING
    )
