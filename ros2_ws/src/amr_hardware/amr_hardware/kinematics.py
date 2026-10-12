from dataclasses import dataclass
import math


def clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def twist_to_wheel_velocities(
    linear: float,
    angular: float,
    wheel_separation: float,
    max_linear_velocity: float,
    max_angular_velocity: float,
    max_wheel_velocity: float = 0.35,
) -> tuple[float, float]:
    if not all(math.isfinite(v) for v in (linear, angular)):
        raise ValueError("cmd_vel must be finite")
    linear = clamp(linear, max_linear_velocity)
    angular = clamp(angular, max_angular_velocity)
    half_track = wheel_separation / 2.0
    left, right = linear - angular * half_track, linear + angular * half_track
    scale = max(1.0, abs(left) / max_wheel_velocity, abs(right) / max_wheel_velocity)
    return left / scale, right / scale


def encoder_delta(current: int, previous: int, counter_bits: int) -> int:
    modulus = 1 << counter_bits
    half = modulus >> 1
    return (current - previous + half) % modulus - half


@dataclass(frozen=True)
class OdometryUpdate:
    x: float
    y: float
    yaw: float
    linear_velocity: float
    angular_velocity: float
    delta_left: int
    delta_right: int


class EncoderOdometry:
    def __init__(
        self,
        wheel_radius: float,
        wheel_separation: float,
        ticks_per_revolution: float,
        gear_ratio: float = 1.0,
        counter_bits: int = 32,
        max_ticks_per_second: float = 20000.0,
    ):
        self.wheel_separation = wheel_separation
        self.counter_bits = counter_bits
        self.max_ticks_per_second = max_ticks_per_second
        self.meters_per_tick = (
            2.0 * math.pi * wheel_radius
            / (ticks_per_revolution * gear_ratio)
        )
        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self._previous = None

    def reset_encoder_reference(self):
        self._previous = None

    def update(
        self,
        left_count: int,
        right_count: int,
        timestamp_ms: int,
    ) -> OdometryUpdate | None:
        if self._previous is None:
            self._previous = (left_count, right_count, timestamp_ms)
            return None

        previous_left, previous_right, previous_time = self._previous
        elapsed_ms = (timestamp_ms - previous_time) % (2**32)
        if elapsed_ms == 0 or elapsed_ms >= 2**31:
            self._previous = (left_count, right_count, timestamp_ms)
            raise ValueError("encoder clock reset or duplicate timestamp")
        elapsed = elapsed_ms / 1000.0

        delta_left = encoder_delta(
            left_count, previous_left, self.counter_bits,
        )
        delta_right = encoder_delta(
            right_count, previous_right, self.counter_bits,
        )
        self._previous = (left_count, right_count, timestamp_ms)

        max_delta = self.max_ticks_per_second * elapsed
        if abs(delta_left) > max_delta or abs(delta_right) > max_delta:
            raise ValueError("implausible encoder delta; reset or corrupted packet")

        distance_left = delta_left * self.meters_per_tick
        distance_right = delta_right * self.meters_per_tick
        distance = (distance_left + distance_right) / 2.0
        delta_yaw = (
            distance_right - distance_left
        ) / self.wheel_separation
        middle_yaw = self.yaw + delta_yaw / 2.0
        half_angle = delta_yaw / 2.0
        chord = distance * (math.sin(half_angle) / half_angle if half_angle else 1.0)
        self.x += chord * math.cos(middle_yaw)
        self.y += chord * math.sin(middle_yaw)
        self.yaw = math.atan2(
            math.sin(self.yaw + delta_yaw),
            math.cos(self.yaw + delta_yaw),
        )
        return OdometryUpdate(
            x=self.x,
            y=self.y,
            yaw=self.yaw,
            linear_velocity=distance / elapsed,
            angular_velocity=delta_yaw / elapsed,
            delta_left=delta_left,
            delta_right=delta_right,
        )
