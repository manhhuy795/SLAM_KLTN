# AGV hardware integration handoff

Status: frontend read-only integration. No ESP32, webcam, movement, or camera proof was hardware-verified in this task. Automatic AGV dispatch and automatic camera confirmation remain disabled.

## Repository paths and roles

| Path | Verified role |
| --- | --- |
| `firmware/esp32_s3/agv_line_controller/agv_line_controller.ino` | ESP32-S3 Wi-Fi HTTP telemetry sender, local odometry, line sensors, encoder and MPU6050 processing, manual test-command consumer. |
| `firmware/esp32_s3/agv_line_controller/agv_secrets.example.h` | Example Wi-Fi SSID, backend telemetry URL and device token configuration; real secrets are local. |
| `web/backend/app/api/routes/agv.py` | Validates `LINE` robot and `X-AGV-Token`; receives telemetry and serves state, logs, CSV and manual commands. |
| `web/backend/app/services/agv_runtime.py` | In-memory AGV telemetry, freshness (2.5 s), trail, command mailbox and ACK state. State does not survive a backend restart. |
| `web/src/features/robots/agv/agv.js` | Frontend GET `/state`, manual command and CSV helpers. |
| `web/src/features/robots/agv/AgvTelemetryPanel.jsx` | LINE Telemetry and Diagnostics tab presentation; no independent poll or WebSocket. |
| `web/src/features/robots/agv/UsbCameraPreview.jsx` | Browser-local `getUserMedia` preview, camera selection and stream cleanup. |
| `web/src/features/robots/shared/RobotStatus.jsx` | Compact Dashboard cards; LINE connection freshness comes from AGV state. |
| `web/src/features/robots/shared/Robots.jsx` | Existing Robot Management page, selected robot and one LINE state poll/subscription; camera mounts only on its tab. |
| `web/src/App.jsx` | Existing page selection with `?page=robots&robot=LINE-01` deep link and browser history. |

## Telemetry contract and identity

The firmware posts JSON to **`POST /api/agv/{robot_code}/telemetry`** (example: `LINE-01`) at backend port **8000**. `agv_secrets.example.h` sets `AGV_TELEMETRY_URL` to `http://YOUR_UBUNTU_IP:8000/api/agv/LINE-01/telemetry`; the ESP32 needs a LAN-reachable backend IP, not `localhost`. FastAPI requires `X-AGV-Token` equal to the locally configured `WRMS_AGV_TOKEN`, then resolves `robot_code` to an existing `LINE` robot. The URL identifies the robot; the current telemetry body has no `robot_id` or command-correlated `command_id`.

| JSON field | Type | Unit / meaning |
| --- | --- | --- |
| `x`, `y` | finite float | metres, AGV-local odometry; **not** ROS map coordinates or verified station arrival |
| `yaw` | finite float | degrees, firmware orientation estimate using MPU6050 |
| `dist` | nonnegative float | metres, accumulated travelled distance |
| `speed` | finite float | cm/s, encoder-derived firmware speed |
| `line_mask` | integer 0–31 | five TCRT5000 line-sensor bits (L2, L1, C, R1, R2) |
| `line_err` | finite float | line-following error; physical unit is not specified in firmware contract |
| `ticks_l`, `ticks_r` | integer | cumulative left/right encoder ticks |
| `pwm_l`, `pwm_r` | integer −255…255 | left/right motor PWM command values, not measured RPM |
| `ack_id` | integer ≥ 0 | manual mailbox command receipt ID; ACK is not arrival or stopped evidence |
| `auto_loop` | boolean | manual A-B-C-D test loop state |
| `state` | nonempty string | firmware state label |

The read-only **`GET /api/agv/{robot_code}/state`** returns `connected`, `last_seen_age_ms`, `last_seen_ts`, `telemetry`, `trail`, command mailbox fields and an `agv_line_local` frame descriptor. Backend broadcasts `AGV_TELEMETRY_UPDATED` over the existing `/ws` connection. The UI treats telemetry as unavailable when `connected` is false. RPM, voltage, raw MPU6050 readings and battery percent are **not sent** by this payload; the UI displays `N/A` rather than deriving or simulating them.

## Camera

There is **no backend camera-stream or snapshot endpoint** in the inspected AGV routes. The existing preview uses browser `navigator.mediaDevices.getUserMedia` on `localhost` or HTTPS and accesses a webcam attached to the machine running the browser. The Camera tab stops its stream when the tab or Robot page unmounts. `POST /api/tasks/{task_id}/vision/captures` accepts a task-owned `image_ref` for classification review; it is not a live-video endpoint and the preview does not submit evidence. A camera on a separate backend host requires a verified stream service and placement decision before remote preview or automatic proof.

## Windows PowerShell read-only startup and checks

```powershell
Set-Location F:\SLAM_KLTN-agent-pilot\web\backend
$env:WRMS_AGV_ENABLE_COMMANDS = '0'
$env:WRMS_AGV_AUTO_DISPATCH_ENABLED = '0'
$env:WRMS_AGV_CAMERA_AUTO_CONFIRM_ENABLED = '0'
py -3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Set-Location F:\SLAM_KLTN-agent-pilot\web
npm.cmd run dev -- --host 127.0.0.1 --port 5173
Invoke-RestMethod http://127.0.0.1:8000/api/agv/LINE-01/state
node --test src/services/*.test.js src/features/robots/amr/*.test.js src/features/robots/agv/*.test.js src/features/map/*.test.js src/features/map/layers/*.test.js src/features/map/transforms/*.test.js
npm.cmd run test:visual
npm.cmd run build
git diff --check
```

The frontend defaults to `http://<browser-hostname>:8000/api` unless `VITE_API_BASE_URL` is set. Vite has no proxy. The example ESP32 URL must be changed to the real backend LAN IP before device telemetry can arrive, and `WRMS_AGV_TOKEN` must be set privately on the backend to match the device token. Do not put the token in the frontend or this document. The localhost startup command is for safe local UI checks; a device cannot reach that binding from Wi-Fi.

## Missing hardware/protocol capabilities

- No RPM, voltage, battery or raw IMU values in current telemetry; no physical station marker identity or verified stopped evidence.
- Manual M1–M4/A-B-C-D test commands do not implement the HOME/PICKUP/RACK_A–D mission route graph. The current ACK is not command-specific arrival proof.
- Device-side durable command deduplication, command-correlated station arrival, robust mission STOP/CANCEL confirmation, and restart reconciliation remain unverified. The manual `STOP` command is present but is not proof of a stopped robot.
- No verified camera placement or cargo-presence algorithm; MobileNetV3 shape classification alone cannot confirm delivery.
