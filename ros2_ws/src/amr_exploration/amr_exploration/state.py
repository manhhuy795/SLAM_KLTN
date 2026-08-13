from dataclasses import dataclass
from enum import Enum, auto


class ExplorerState(Enum):
    IDLE = auto()
    NAVIGATING = auto()
    DONE = auto()


@dataclass
class ExplorerSession:
    state: ExplorerState = ExplorerState.IDLE
    active_goal_xy: tuple[float, float] | None = None
    no_frontier_count: int = 0

    def start_navigation(
        self,
        goal_xy: tuple[float, float],
    ) -> None:
        if self.state is not ExplorerState.IDLE:
            raise RuntimeError(
                'Can only start navigation from IDLE'
            )

        self.active_goal_xy = goal_xy
        self.state = ExplorerState.NAVIGATING

    def navigation_succeeded(self) -> None:
        self.active_goal_xy = None
        self.no_frontier_count = 0
        self.state = ExplorerState.IDLE

    def navigation_failed(self) -> None:
        self.active_goal_xy = None
        self.state = ExplorerState.IDLE

    def record_empty_check(
        self,
        required_empty_checks: int,
    ) -> bool:
        if self.state is not ExplorerState.IDLE:
            return False

        self.no_frontier_count += 1

        if self.no_frontier_count >= required_empty_checks:
            self.state = ExplorerState.DONE
            return True

        return False

    def record_candidate_found(self) -> None:
        self.no_frontier_count = 0

    def reset(self) -> None:
        self.state = ExplorerState.IDLE
        self.active_goal_xy = None
        self.no_frontier_count = 0
