import unittest
from unittest.mock import patch

from app.services.agv_runtime import AgvRuntime, status_from_firmware


def telemetry(**overrides):
    data = dict(x=0.0, y=0.0, yaw=90.0, dist=0.0, speed=0.0,
                line_mask=4, line_err=0.0, ticks_l=0, ticks_r=0,
                pwm_l=0, pwm_r=0, ack_id=0, auto_loop=False, state="STOPPED")
    data.update(overrides)
    return data


class AgvRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime = AgvRuntime()
        self.code = "LINE-01"

    def test_offline_motion_blocked(self):
        with self.assertRaisesRegex(ValueError, "offline"):
            self.runtime.command(self.code, "START")

    def test_accept_telemetry_and_trail(self):
        self.assertEqual(self.runtime.ingest(self.code, telemetry())["cmd_id"], 0)
        self.runtime.ingest(self.code, telemetry(x=0.10, ticks_l=697))
        state = self.runtime.get(self.code)
        self.assertTrue(state["connected"])
        self.assertEqual(len(state["trail"]), 2)
        self.assertEqual(state["telemetry"]["ticks_l"], 697)

    def test_command_ack(self):
        self.runtime.ingest(self.code, telemetry())
        issued = self.runtime.command(self.code, "MISSION:M1")
        pending = self.runtime.ingest(self.code, telemetry())
        self.assertEqual(pending["cmd"], "MISSION:M1")
        self.runtime.ingest(self.code, telemetry(ack_id=issued["cmd_id"]))
        state = self.runtime.get(self.code)
        self.assertIsNone(state["pending_command"])
        self.assertEqual(state["command_status"], "ACKNOWLEDGED")

    def test_wrong_ack_does_not_clear_pending(self):
        self.runtime.ingest(self.code, telemetry())
        issued = self.runtime.command(self.code, "START")
        self.runtime.ingest(self.code, telemetry(ack_id=issued["cmd_id"]-1))
        self.assertIsNotNone(self.runtime.get(self.code)["pending_command"])

    def test_stop_preempts_start(self):
        self.runtime.ingest(self.code, telemetry())
        self.runtime.command(self.code, "START")
        stopped = self.runtime.command(self.code, "STOP")
        self.assertEqual(self.runtime.ingest(self.code, telemetry())["cmd"], "STOP")
        self.assertEqual(self.runtime.command(self.code, "STOP")["cmd_id"], stopped["cmd_id"])

    def test_pending_rejects_non_stop(self):
        self.runtime.ingest(self.code, telemetry())
        self.runtime.command(self.code, "START")
        with self.assertRaisesRegex(ValueError, "pending"):
            self.runtime.command(self.code, "MISSION:M2")

    def test_age_timeout(self):
        self.runtime.ingest(self.code, telemetry())
        with patch("app.services.agv_runtime.monotonic", return_value=10**12):
            self.assertFalse(self.runtime.get(self.code)["connected"])

    def test_state_mapping(self):
        self.assertEqual(status_from_firmware("STOPPED"), "IDLE")
        self.assertEqual(status_from_firmware("RUNNING_FAST"), "MOVING")
        self.assertEqual(status_from_firmware("PAUSED_AT_STATION"), "PAUSED")
        self.assertEqual(status_from_firmware("LOST_LINE_STOP"), "ERROR")

    def test_multi_robot_mailboxes(self):
        self.runtime.ingest("LINE-01", telemetry())
        self.runtime.ingest("LINE-02", telemetry())
        self.runtime.command("LINE-01", "START")
        self.assertEqual(self.runtime.ingest("LINE-02", telemetry())["cmd_id"], 0)


if __name__ == "__main__":
    unittest.main()
