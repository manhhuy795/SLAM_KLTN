from dataclasses import dataclass
import math


@dataclass
class FailedRegion:
    x: float
    y: float
    radius: float
    failures: int = 0
    active: bool = False


class Blacklist:
    def __init__(
        self,
        radius: float,
        failure_limit: int,
    ):
        self.radius = radius
        self.failure_limit = failure_limit
        self._regions: list[FailedRegion] = []

    def _find_region(
        self,
        x: float,
        y: float,
    ) -> FailedRegion | None:
        for region in self._regions:
            distance = math.hypot(
                x - region.x,
                y - region.y,
            )

            if distance <= region.radius:
                return region

        return None

    def record_failure(
        self,
        x: float,
        y: float,
    ) -> bool:
        region = self._find_region(
            x,
            y,
        )

        if region is None:
            region = FailedRegion(
                x=x,
                y=y,
                radius=self.radius,
            )

            self._regions.append(
                region
            )

        region.failures += 1

        if region.failures >= self.failure_limit:
            region.active = True

        return region.active

    def contains(
        self,
        x: float,
        y: float,
    ) -> bool:
        for region in self._regions:
            if not region.active:
                continue

            distance = math.hypot(
                x - region.x,
                y - region.y,
            )

            if distance <= region.radius:
                return True

        return False

    def failure_count(
        self,
        x: float,
        y: float,
    ) -> int:
        region = self._find_region(
            x,
            y,
        )

        if region is None:
            return 0

        return region.failures

    def clear(self) -> None:
        self._regions.clear()
