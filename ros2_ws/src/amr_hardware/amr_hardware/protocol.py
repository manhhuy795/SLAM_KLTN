from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class EncoderPacket:
    boot_id: int
    sequence: int
    left_count: int
    right_count: int
    timestamp_ms: int


def velocity_command(sequence: int, left_mps: float, right_mps: float) -> str:
    if not all(math.isfinite(v) for v in (left_mps, right_mps)):
        raise ValueError("wheel targets must be finite")
    return f"VEL,{sequence},{left_mps:.6f},{right_mps:.6f}\n"


def stop_command(sequence: int) -> str:
    return f"STOP,{sequence}\n"


def emergency_stop_command(sequence: int, active: bool) -> str:
    return f"ESTOP,{sequence},{int(active)}\n"


def parse_encoder_packet(line: str) -> EncoderPacket:
    fields = line.strip().split(",")
    if len(fields) != 6 or fields[0] != "ENC":
        raise ValueError("expected ENC,boot_id,seq,left_count,right_count,timestamp_ms")

    try:
        if not all(re.fullmatch(r"-?[0-9]{1,10}", f) for f in fields[1:]):
            raise ValueError("invalid integer syntax")
        boot, sequence, left, right, timestamp = map(int, fields[1:])
    except ValueError as error:
        raise ValueError("encoder fields must be integers") from error

    if not all(0 <= v < 2**32 for v in (boot, sequence, timestamp)):
        raise ValueError("boot, sequence and timestamp must be uint32")
    if not all(-(2**31) <= v < 2**31 for v in (left, right)):
        raise ValueError("encoder counts must be int32")
    return EncoderPacket(boot, sequence, left, right, timestamp)


class LineBuffer:
    """Bounded framing for nonblocking serial reads; None marks an oversized line."""

    def __init__(self, limit=128):
        self.limit = limit
        self.pending = bytearray()
        self.discarding = False

    def feed(self, data):
        lines = []
        for byte in data:
            if byte == 10:
                if not self.discarding:
                    lines.append(bytes(self.pending))
                self.pending.clear()
                self.discarding = False
            elif not self.discarding:
                self.pending.append(byte)
                if len(self.pending) > self.limit:
                    lines.append(None)
                    self.pending.clear()
                    self.discarding = True
        return lines
