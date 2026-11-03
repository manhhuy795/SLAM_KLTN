# README_for_test_AGV — Test nhanh AGV LINE-01

**Mục tiêu:** ESP32-S3 gửi telemetry qua Wi-Fi lên **WRMS → Robot → LINE-01 → Telemetry**; thử webcam ở tab **Camera**. **AGV dùng driver L298N.** Chưa kiểm thử mission tự động.

## 1. Clone và chạy Web (Windows)

Cần Git, Python 3.11+, Node.js 22.12+ hoặc 24+.

```powershell
git clone -b ai/team-pilot --single-branch https://github.com/manhhuy795/SLAM_KLTN.git
cd SLAM_KLTN\web\backend
py -3.11 -m pip install -r requirements.txt
py -3.11 init_db.py
py -3.11 seed.py

# Mở backend cho ESP32 truy cập qua LAN; chỉ dùng trên mạng tin cậy.
$env:WRMS_AGV_TOKEN = "THAY_BANG_TOKEN_BI_MAT"
$env:WRMS_AGV_ENABLE_COMMANDS = "0"
$env:WRMS_AGV_AUTO_DISPATCH_ENABLED = "0"
$env:WRMS_AGV_CAMERA_AUTO_CONFIRM_ENABLED = "0"
py -3.11 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**PowerShell khác** (đứng tại thư mục `SLAM_KLTN`):

```powershell
cd web
npm.cmd ci
npm.cmd run dev -- --host 0.0.0.0 --port 5173
```

Mở `http://localhost:5173`. Kiểm tra API bằng `http://localhost:8000/docs`.

## 2. Cấu hình ESP32-S3 (L298N)

File firmware: `firmware/esp32_s3/agv_line_controller/agv_line_controller.ino`.

Sao chép `agv_secrets.example.h` thành `agv_secrets.h` **trong cùng thư mục firmware**, sửa:

```cpp
#pragma once
#define AGV_WIFI_SSID "TEN_WIFI_2_4GHZ"
#define AGV_WIFI_PASSWORD "MAT_KHAU_WIFI"
#define AGV_TELEMETRY_URL "http://IP_LAPTOP:8000/api/agv/LINE-01/telemetry"
#define AGV_DEVICE_TOKEN "THAY_BANG_TOKEN_BI_MAT"
```

- Xem `IP_LAPTOP` bằng `ipconfig` (IPv4 card Wi-Fi/LAN); **không dùng `localhost` trên ESP32**.
- Token phải trùng `WRMS_AGV_TOKEN`. Không commit `agv_secrets.h`.
- ESP32 và laptop phải liên lạc được qua mạng; cho phép cổng TCP 8000 trên Windows Firewall trong mạng riêng.
- **Kiểm tra lại dây nối và GPIO trước khi nạp firmware**: code hiện dùng L298N, I²C MPU6050 SDA=4/SCL=5. Nâng bánh khỏi sàn hoặc ngắt nguồn motor khi thử truyền dữ liệu lần đầu.

## 3. Files to edit so ESP32-S3 syncs with WRMS

| File | Change required |
|---|---|
| `firmware/esp32_s3/agv_line_controller/agv_secrets.h` | **Create** by copying `agv_secrets.example.h`. Set Wi-Fi SSID/password, `AGV_TELEMETRY_URL=http://LAPTOP_IP:8000/api/agv/LINE-01/telemetry`, and `AGV_DEVICE_TOKEN` equal to backend `WRMS_AGV_TOKEN`. Never commit secrets. |
| `firmware/esp32_s3/agv_line_controller/agv_line_controller.ino` | Already uses **L298N**. Check GPIO against wiring before flashing: L298N ENA/IN1/IN2/IN3/IN4/ENB = 6/7/15/16/17/18; MPU6050 SDA/SCL = 4/5; encoders = 10-13; TCRT5000 = 48/47/21/20/19. Change only if actual wiring differs. |
| `web/backend/app/api/routes/agv.py` | **No edit for first test.** POST `/api/agv/LINE-01/telemetry` already accepts the firmware JSON and checks `X-AGV-Token`. Only update if adding new fields to the agreed contract. |
| `web/src/features/robots/agv/AgvTelemetryPanel.jsx` | **No edit for first test.** Displays telemetry from FastAPI; update alongside backend only for new fields. |
| `web/src/features/robots/agv/UsbCameraPreview.jsx` | **No edit for browser-local USB camera.** Webcam plugs into the PC opening the browser. |

**Sync rule:** `AGV_DEVICE_TOKEN` (ESP32) = `WRMS_AGV_TOKEN` (FastAPI). Backend binds to `0.0.0.0:8000`, and firmware uses the laptop's LAN IPv4, **not localhost**. No API or React edits needed for the current JSON keys: `x,y,yaw,dist,speed,line_mask,line_err,ticks_l,ticks_r,pwm_l,pwm_r,ack_id,auto_loop,state`.

## 4. Test telemetry và camera

1. Mở **Robot → LINE-01 → Telemetry**. Trạng thái phải thành ONLINE khi ESP32 gửi liên tục.
2. Xem encoder (`ticks_l/r`), odometry (`x`, `y`, `yaw`), tốc độ (`speed`), cảm biến line (`line_mask`) và PWM (`pwm_l/r`).
3. Kiểm tra API:

```powershell
Invoke-RestMethod http://localhost:8000/api/agv/LINE-01/state
```

Kết quả cần `connected: true`. Rút nguồn ESP32: trạng thái phải OFFLINE sau khoảng 2,5 giây.

4. Cắm webcam vào **máy đang mở trình duyệt**, vào **Robot → LINE-01 → Camera**, cấp quyền truy cập webcam. Camera hiện dùng browser `getUserMedia()`, **không phải stream từ ESP32 hoặc server**.

**Chưa có trong telemetry hiện tại:** điện áp pin, RPM từng động cơ, gia tốc/gyro raw; Web hiển thị `N/A` là bình thường.

## 5. Nếu không hoạt động

| Hiện tượng | Kiểm tra |
|---|---|
| OFFLINE / không nhận telemetry | Wi-Fi 2.4 GHz, IPv4 laptop, firewall, log Serial 115200 |
| HTTP 401 | Token ESP32 khác `WRMS_AGV_TOKEN` |
| HTTP 404 | Chưa seed robot `LINE-01` |
| HTTP 422 | JSON gửi không đúng schema |
| HTTP 503 | Backend chưa đặt `WRMS_AGV_TOKEN` |
| Camera không lên | Webcam phải cắm trên máy mở trình duyệt; cấp quyền camera tại `localhost`/HTTPS |

**An toàn:** Giữ `WRMS_AGV_ENABLE_COMMANDS=0`; không thử điều khiển motor từ Web trước khi kiểm tra phần cứng và phương án dừng khẩn cấp. `ACK` không chứng minh robot đã đến trạm hay dừng hẳn.
