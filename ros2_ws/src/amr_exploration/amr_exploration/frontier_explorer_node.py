import time

import rclpy

from action_msgs.msg import GoalStatus

from .grid_processing import (
    extract_clusters,
    frontier_mask,
    occupancy_to_array,
    sample_costmap_cost,
    select_candidate_near_centroid,
)

from .scoring import (
    euclidean_distance,
    score_candidates,
)

from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid

from rclpy.time import Time
from rclpy.action import ActionClient
from rclpy.node import Node

from std_srvs.srv import SetBool

from tf2_ros import TransformException
from tf2_ros import Buffer
from tf2_ros import TransformListener

from .blacklist import Blacklist
from .state import ExplorerSession
from .state import ExplorerState


class FrontierExplorerNode(Node):

    def __init__(self):
        super().__init__('frontier_explorer')

        # =========================
        # Parameters
        # =========================

        self.declare_parameter(
            'map_topic',
            '/map',
        )

        self.declare_parameter(
            'global_costmap_topic',
            '/global_costmap/costmap',
        )

        self.declare_parameter(
            'map_frame',
            'map',
        )

        self.declare_parameter(
            'robot_base_frame',
            'base_link',
        )

        self.declare_parameter(
            'exploration_period_sec',
            3.0,
        )

        self.declare_parameter(
            'max_costmap_age_sec',
            2.0,
        )

        self.declare_parameter(
            'min_cluster_size',
            8,
        )

        self.declare_parameter(
            'min_cluster_area_m2',
            0.02,
        )

        self.declare_parameter(
            'candidate_search_radius',
            0.35,
        )

        self.declare_parameter(
            'costmap_reject_threshold',
            80,
        )

        self.declare_parameter(
            'blacklist_radius',
            0.40,
        )

        self.declare_parameter(
            'failure_limit',
            2,
        )

        self.declare_parameter(
            'goal_timeout_sec',
            120.0,
        )

        self.declare_parameter(
            'max_exploration_time_sec',
            1800.0,
        )

        self.declare_parameter(
            'required_empty_checks',
            3,
        )

        self.declare_parameter(
            'w_gain',
            0.6,
        )

        self.declare_parameter(
            'w_distance',
            0.3,
        )

        self.declare_parameter(
            'w_failure',
            0.1,
        )

        # =========================
        # Internal state
        # =========================

        self.session = ExplorerSession()

        self.enabled = False

        self.latest_map = None
        self.latest_costmap = None

        self.active_goal_handle = None
        self.goal_started_monotonic = None
        self.goal_cancel_requested = False

        self.latest_map_received_monotonic = None
        self.latest_costmap_received_monotonic = None

        self.blacklist = Blacklist(
            radius=float(
                self.get_parameter(
                    'blacklist_radius'
                ).value
            ),
            failure_limit=int(
                self.get_parameter(
                    'failure_limit'
                ).value
            ),
        )

        # =========================
        # TF
        # =========================

        self.tf_buffer = Buffer()

        self.tf_listener = TransformListener(
            self.tf_buffer,
            self,
        )

        # =========================
        # Nav2 Action Client
        # =========================

        self.nav_client = ActionClient(
            self,
            NavigateToPose,
            '/navigate_to_pose',
        )

        # =========================
        # Subscribers
        # =========================

        map_topic = str(
            self.get_parameter(
                'map_topic'
            ).value
        )

        costmap_topic = str(
            self.get_parameter(
                'global_costmap_topic'
            ).value
        )

        self.map_sub = self.create_subscription(
            OccupancyGrid,
            map_topic,
            self._map_callback,
            10,
        )

        self.costmap_sub = self.create_subscription(
            OccupancyGrid,
            costmap_topic,
            self._costmap_callback,
            10,
        )

        # =========================
        # Enable / disable service
        # =========================

        self.enable_service = self.create_service(
            SetBool,
            '~/set_enabled',
            self._set_enabled_callback,
        )

        # =========================
        # Exploration timer
        # =========================

        period = float(
            self.get_parameter(
                'exploration_period_sec'
            ).value
        )

        self.timer = self.create_timer(
            period,
            self._exploration_tick,
        )

        self.get_logger().info(
            'Frontier Explorer initialized'
        )

        self.get_logger().info(
            'Explorer starts DISABLED'
        )

    # =============================
    # Callbacks only cache data
    # =============================

    def _map_callback(
        self,
        msg: OccupancyGrid,
    ) -> None:

        self.latest_map = msg

        self.latest_map_received_monotonic = (
            time.monotonic()
        )

    def _costmap_callback(
        self,
        msg: OccupancyGrid,
    ) -> None:

        self.latest_costmap = msg

        self.latest_costmap_received_monotonic = (
            time.monotonic()
        )

    # =============================
    # Enable / disable
    # =============================

    def _set_enabled_callback(
        self,
        request,
        response,
    ):

        self.enabled = bool(
            request.data
        )

        if (
            self.enabled
            and
            self.session.state
            is ExplorerState.DONE
        ):
            self.session.reset()
            self.blacklist.clear()

        if self.enabled:
            response.message = (
                'Frontier exploration enabled'
            )
        else:
            if (
                self.session.state
                is ExplorerState.NAVIGATING
                and self.active_goal_handle
                is not None
                and not self.goal_cancel_requested
            ):
                self.goal_cancel_requested = True
                self.active_goal_handle.cancel_goal_async()

            response.message = (
                'Frontier exploration disabled'
            )

        response.success = True

        self.get_logger().info(
            response.message
        )

        return response

    # =============================
    # Main timer
    # =============================
    def _selection_inputs_ready(
        self,
        ) -> bool:

        if self.latest_map is None:
            self.get_logger().debug(
                'Waiting for /map'
            )
            return False

        if self.latest_costmap is None:
            self.get_logger().debug(
                'Waiting for global costmap'
            )
            return False

        if (
            self.latest_costmap_received_monotonic
            is None
        ):
            return False

        max_costmap_age_sec = float(
            self.get_parameter(
                'max_costmap_age_sec'
            ).value
        )

        costmap_age = (
            time.monotonic()
            -
            self.latest_costmap_received_monotonic
        )

        if costmap_age > max_costmap_age_sec:
            self.get_logger().debug(
                'Global costmap is stale'
            )
            return False

        if not self.nav_client.server_is_ready():
            self.get_logger().debug(
                'Nav2 NavigateToPose server not ready'
            )
            return False

        expected_frame = str(
            self.get_parameter(
                'map_frame'
            ).value
        )

        map_frame = (
            self.latest_map.header.frame_id
        )

        costmap_frame = (
            self.latest_costmap.header.frame_id
        )

        if map_frame != expected_frame:
            self.get_logger().warn(
                f'Unexpected map frame: '
                f'{map_frame}, expected {expected_frame}'
            )
            return False

        if costmap_frame != expected_frame:
            self.get_logger().warn(
                f'Unexpected costmap frame: '
                f'{costmap_frame}, expected {expected_frame}'
            )
            return False

        return True


    def _get_robot_xy(
        self,
        ) -> tuple[float, float] | None:

        map_frame = str(
            self.get_parameter(
                'map_frame'
            ).value
        )

        robot_base_frame = str(
            self.get_parameter(
                'robot_base_frame'
            ).value
        )

        try:
            transform = self.tf_buffer.lookup_transform(
                map_frame,
                robot_base_frame,
                Time(),
            )

        except TransformException as exc:
            self.get_logger().debug(
                f'TF unavailable: {exc}'
            )
            return None

        translation = (
            transform.transform.translation
        )

        return (
            float(translation.x),
            float(translation.y),
        )

    def _compute_best_candidate(
        self,
        robot_xy: tuple[float, float],
        ):
        map_msg = self.latest_map
        map_info = map_msg.info

        resolution = float(
            map_info.resolution
        )

        origin_x = float(
            map_info.origin.position.x
        )

        origin_y = float(
            map_info.origin.position.y
        )

        map_grid = occupancy_to_array(
            data=map_msg.data,
            width=int(map_info.width),
            height=int(map_info.height),
        )

        costmap_msg = self.latest_costmap
        costmap_info = costmap_msg.info

        costmap_resolution = float(
            costmap_info.resolution
        )

        costmap_origin_x = float(
            costmap_info.origin.position.x
        )

        costmap_origin_y = float(
            costmap_info.origin.position.y
        )

        costmap_grid = occupancy_to_array(
            data=costmap_msg.data,
            width=int(costmap_info.width),
            height=int(costmap_info.height),
        )

        costmap_reject_threshold = int(
            self.get_parameter(
                'costmap_reject_threshold'
            ).value
        )

        mask = frontier_mask(
            map_grid
        )

        clusters = extract_clusters(
            mask=mask,
            resolution=resolution,
            min_cluster_size=int(
                self.get_parameter(
                    'min_cluster_size'
                ).value
            ),
            min_cluster_area_m2=float(
                self.get_parameter(
                    'min_cluster_area_m2'
                ).value
            ),
        )

        if not clusters:
            return None

        search_radius_m = float(
            self.get_parameter(
                'candidate_search_radius'
            ).value
        )

        candidates = []

        for cluster in clusters:
            candidate = select_candidate_near_centroid(
                cluster=cluster,
                map_grid=map_grid,
                resolution=resolution,
                origin_x=origin_x,
                origin_y=origin_y,
                search_radius_m=search_radius_m,
            )

            if candidate is None:
                continue

            cost = sample_costmap_cost(
                x=candidate.x,
                y=candidate.y,
                cost_grid=costmap_grid,
                resolution=costmap_resolution,
                origin_x=costmap_origin_x,
                origin_y=costmap_origin_y,
            )

            # Ngoài costmap -> không đủ thông tin
            # để coi candidate là an toàn.
            if cost is None:
                continue

            # Cost cao -> candidate không an toàn.
            if cost >= costmap_reject_threshold:
                continue

            if self.blacklist.contains(
                candidate.x,
                candidate.y,
            ):
                continue

            candidates.append(
                candidate
            )

        if not candidates:
            return None

        gains = []
        distances = []
        failures = []

        for candidate in candidates:
            gains.append(
                candidate.cluster.area_m2
            )

            distances.append(
                euclidean_distance(
                    robot_xy=robot_xy,
                    goal_xy=(
                        candidate.x,
                        candidate.y,
                    ),
                )
            )

            failures.append(
                self.blacklist.failure_count(
                    candidate.x,
                    candidate.y,
                )
            )

        scores = score_candidates(
            gains=gains,
            distances=distances,
            failures=failures,
            w_gain=float(
                self.get_parameter(
                    'w_gain'
                ).value
            ),
            w_distance=float(
                self.get_parameter(
                    'w_distance'
                ).value
            ),
            w_failure=float(
                self.get_parameter(
                    'w_failure'
                ).value
            ),
        )

        best_index = int(
            scores.argmax()
        )

        return candidates[
            best_index
        ]
    
    def _build_navigation_goal(
        self,
        candidate,
        ) -> NavigateToPose.Goal:

        map_frame = str(
            self.get_parameter(
                'map_frame'
            ).value
        )

        goal = NavigateToPose.Goal()

        goal.pose.header.frame_id = map_frame

        goal.pose.pose.position.x = float(
            candidate.x
        )

        goal.pose.pose.position.y = float(
            candidate.y
        )

        goal.pose.pose.position.z = 0.0

        goal.pose.pose.orientation.x = 0.0
        goal.pose.pose.orientation.y = 0.0
        goal.pose.pose.orientation.z = 0.0
        goal.pose.pose.orientation.w = 1.0

        return goal

    def _send_navigation_goal(
        self,
        candidate,
    ) -> None:

        goal = self._build_navigation_goal(
            candidate
        )

        goal_future = (
            self.nav_client.send_goal_async(
                goal
            )
        )

        self.session.start_navigation(
            (
                float(candidate.x),
                float(candidate.y),
            )
        )

        # Bước 7.4 sẽ thay callback tạm này
        # bằng xử lý accepted / rejected.
        goal_future.add_done_callback(
            self._goal_response_callback
        )

    def _goal_response_callback(
        self,
        future,
        ) -> None:

        goal_handle = future.result()

        if not goal_handle.accepted:
            failed_goal = (
                self.session.active_goal_xy
            )

            if failed_goal is not None:
                self.blacklist.record_failure(
                    failed_goal[0],
                    failed_goal[1],
                )

            self.session.navigation_failed()
            self._clear_navigation_tracking()

            self.get_logger().warn(
                'Navigation goal rejected by Nav2'
            )

            return

        self.get_logger().info(
            'Navigation goal accepted by Nav2'
        )

        self.active_goal_handle = goal_handle
        self.goal_started_monotonic = time.monotonic()
        self.goal_cancel_requested = False

        result_future = (
            goal_handle.get_result_async()
        )

        result_future.add_done_callback(
            self._navigation_result_callback
        )

    def _clear_navigation_tracking(
        self,
    ) -> None:
        self.active_goal_handle = None
        self.goal_started_monotonic = None
        self.goal_cancel_requested = False

    def _navigation_result_callback(
        self,
        future,
    ) -> None:

        result = future.result()
        status = result.status

        goal_xy = self.session.active_goal_xy

        if status == GoalStatus.STATUS_SUCCEEDED:
            self.session.navigation_succeeded()
            self._clear_navigation_tracking()

            self.get_logger().info(
                'Navigation goal succeeded'
            )

            return

        # ABORTED / CANCELED hoặc trạng thái thất bại khác
        if goal_xy is not None:
            self.blacklist.record_failure(
                goal_xy[0],
                goal_xy[1],
            )

        self.session.navigation_failed()
        self._clear_navigation_tracking()

        if status == GoalStatus.STATUS_ABORTED:
            self.get_logger().warn(
                'Navigation goal aborted'
            )

        elif status == GoalStatus.STATUS_CANCELED:
            self.get_logger().warn(
                'Navigation goal canceled'
            )

        else:
            self.get_logger().warn(
                f'Navigation failed with status {status}'
            )

    def _check_navigation_timeout(
        self,
    ) -> bool:

        if (
            self.session.state
            is not ExplorerState.NAVIGATING
        ):
            return False

        if self.active_goal_handle is None:
            return False

        if self.goal_started_monotonic is None:
            return False

        if self.goal_cancel_requested:
            return True

        goal_timeout_sec = float(
            self.get_parameter(
                'goal_timeout_sec'
            ).value
        )

        elapsed = (
            time.monotonic()
            - self.goal_started_monotonic
        )

        if elapsed <= goal_timeout_sec:
            return False

        self.goal_cancel_requested = True

        self.active_goal_handle.cancel_goal_async()

        self.get_logger().warn(
            'Navigation goal timeout - '
            'cancel requested'
        )

        return True

    def _exploration_tick(self,) -> None:

        if not self.enabled:
            return

        if self.session.state is ExplorerState.NAVIGATING:
            self._check_navigation_timeout()
            return

        if self.session.state is not ExplorerState.IDLE:
            return

        # Thiếu map/costmap/Nav2/frame...
        # thì chỉ chờ vòng timer tiếp theo.
        if not self._selection_inputs_ready():
            return

        # Không lấy được TF robot thì cũng chỉ chờ.
        robot_xy = self._get_robot_xy()

        if robot_xy is None:
            return

        candidate = self._compute_best_candidate(
            robot_xy
        )

        # Chỉ tới đây mới được kết luận
        # "không có candidate hợp lệ".
        if candidate is None:
            required_empty_checks = int(
                self.get_parameter(
                    'required_empty_checks'
                ).value
            )

            done = self.session.record_empty_check(
                required_empty_checks
            )

            if done:
                self.get_logger().info(
                    'Exploration complete: '
                    'no valid frontier candidates'
                )

            return

        self.session.record_candidate_found()

        self.get_logger().info(
            'Best frontier candidate: '
            f'x={candidate.x:.2f}, '
            f'y={candidate.y:.2f}, '
            f'cells={candidate.cluster.cell_count}, '
            f'area={candidate.cluster.area_m2:.3f} m^2'
        )

        self._send_navigation_goal(candidate)

        # Task 6 chỉ chọn và log candidate.
        # Task 7 mới gửi NavigateToPose.
    def destroy_node(self):

        self.nav_client.destroy()

        super().destroy_node()


def main(args=None):

    rclpy.init(args=args)

    node = FrontierExplorerNode()

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    finally:
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
