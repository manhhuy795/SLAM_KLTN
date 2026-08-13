import time

import rclpy

from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid

from rclpy.action import ActionClient
from rclpy.node import Node

from std_srvs.srv import SetBool

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

    def _exploration_tick(
        self,
    ) -> None:

        if not self.enabled:
            return

        if (
            self.session.state
            is not ExplorerState.IDLE
        ):
            return

        # Task 5:
        # chưa tìm frontier
        # chưa gửi goal.
        #
        # Task 6 sẽ implement phần này.

        self.get_logger().debug(
            'Explorer IDLE - ready for frontier selection'
        )

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
