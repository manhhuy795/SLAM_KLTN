# AGV line controller -> WRMS

This firmware is adapted from the **hardware-tested** upload `test_05_web_telemetry_odometry.cpp`.
Motor direction, encoder decode, TCRT5000, MPU6050, PD line following, mission distances,
PWM and 100 Hz loop are intentionally preserved. The former Python `server.py`
is replaced by FastAPI routes in `web/backend/app/api/routes/agv.py` (port 8000).

## Configure
Copy `agv_secrets.example.h` to `agv_secrets.h` locally. Fill a 2.4 GHz Wi-Fi SSID,
password, Ubuntu host IP and `WRMS_AGV_TOKEN`. Never commit secrets. Use a LAN-reachable
host (Bridged VM or suitable forwarding), not localhost. The firmware polls/POSTs
`/api/agv/LINE-01/telemetry` and retains the original `cmd/cmd_id` response contract.

Backend:
```sh
export WRMS_AGV_TOKEN="replace-with-a-long-random-device-token"
export WRMS_AGV_ENABLE_COMMANDS=0
cd web/backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend at port 5173 shows the AGV card in the dashboard, robot-local rectangular
map, line sensors, encoder ticks, PWM, odometry and CSV export. Once you have
validated read-only telemetry and stop behaviour on lifted wheels, set
`WRMS_AGV_ENABLE_COMMANDS=1` and restart backend to enable remote commands.

Important: firmware is single-device hardware-tested code, not Nav2's AMR
serial firmware. Never flash it to the AMR controller.

## Boundaries and limitations
- `LINE-01` uses its **local** frame, +Y downward and yaw in degrees. Those
  coordinates are NOT valid as a ROS `map` pose. Do not overlay them on SLAM.
- The in-memory AGV log and mailbox do not persist across backend restarts.
  Restart while stationary; sending STOP after restart requires live firmware.
- Original firmware command ACK indicates command was received, not motion
  completion. A physical emergency-stop circuit is essential.
- Original firmware is hardware-verified by the project owner; **these new
  integration changes still require a full bench and floor regression test**.
- The original ESP32 code does not enforce a network-loss motor watchdog. Do not
  regard web connectivity as a safety interlock.
