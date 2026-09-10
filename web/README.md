# WRMS Website Testbed

Warehouse Robot Management System ở chế độ testbed/simulation.

Phạm vi hiện tại là website và backend mô phỏng dữ liệu robot, task, sản phẩm,
location, cảnh báo và lịch sử. Chưa có robot thật trong vòng test này.

## Phạm vi

Đã hỗ trợ:

- Dashboard realtime qua REST + WebSocket.
- Robot status simulation bằng API PATCH.
- CRUD sản phẩm và location/kệ.
- Tạo task và quản lý lifecycle:

  ```text
  WAITING
  → MOVING_TO_PICKUP
  → ARRIVED_AT_PICKUP
  → PICKUP_CONFIRMED
  → TRANSPORTING
  → ARRIVED_AT_DELIVERY
  → DELIVERY_CONFIRMED
  → COMPLETED
  ```

- `FAILED` và `CANCELLED`.
- Pickup/delivery proof với `image_path`, không upload file thật.
- Alert lifecycle `NEW → ACKNOWLEDGED → RESOLVED`.
- Group/count alert lặp.
- EventLog và History filter.
- WebSocket dùng chung cho robot, task, alert và event.
- Safe Stop là software request; không phải physical E-STOP.

Không thuộc scope hiện tại:

- ROS2, MQTT.
- PID, encoder, motor, line sensor và firmware.
- AprilTag, camera stream và upload ảnh thật.
- Authentication/session operator thật.

## Cấu trúc

```text
autonomous-warehouse-robot/
├── README.md
└── web/
    ├── backend/
    │   ├── app/
    │   │   ├── api/routes/
    │   │   ├── models/
    │   │   ├── schemas/
    │   │   └── services/
    │   ├── data/wrms.db
    │   ├── init_db.py
    │   └── seed.py
    ├── src/
    ├── package.json
    └── vite.config.js
```

## Yêu cầu

- Python 3.11+
- Node.js và npm
- Các package Python hiện có của project: FastAPI, Uvicorn, SQLAlchemy, Pydantic

Không cần robot hoặc thiết bị phần cứng để chạy testbed.

## Chạy backend

```powershell
cd F:\autonomous-warehouse-robot\web\backend
py -3.11 init_db.py
py -3.11 seed.py
py -3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend mặc định dùng SQLite tại:

```text
web/backend/data/wrms.db
```

## Chạy frontend

Mở terminal khác:

```powershell
cd F:\autonomous-warehouse-robot\web
npm install
npm run dev
```

Frontend mặc định gọi:

```text
REST:      http://127.0.0.1:8000/api
WebSocket: ws://127.0.0.1:8000/ws
```

Có thể đổi endpoint bằng Vite env mà không cần sửa code:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000/api
VITE_WS_URL=ws://127.0.0.1:8000/ws
```

Nếu không khai báo `.env.local`, frontend tự dùng hai giá trị localhost ở trên.

Build production:

```powershell
npm run build
```

## API chính

### Products

```text
GET    /api/products
GET    /api/products/{product_id}
POST   /api/products
PATCH  /api/products/{product_id}
DELETE /api/products/{product_id}
```

Ví dụ tạo sản phẩm:

```json
{
  "product_code": "P-TEST-01",
  "name": "Test product",
  "status": "AVAILABLE",
  "default_rack_id": 2,
  "image_path": "/proofs/product.jpg"
}
```

`default_rack_id` phải trỏ tới location loại `RACK` đang hoạt động.

### Locations / racks

```text
GET    /api/locations
GET    /api/locations/{location_id}
POST   /api/locations
PATCH  /api/locations/{location_id}
DELETE /api/locations/{location_id}
```

Location đang được product, task hoặc line segment tham chiếu sẽ không bị xóa
hoặc deactivate.

### Robot simulation

```text
PATCH /api/robots/{robot_id}/status
```

Ví dụ:

```json
{
  "online": true,
  "state": "MOVING",
  "battery_percent": 86,
  "voltage": 12.1,
  "x": 3.2,
  "y": 2.4,
  "yaw": 0.4,
  "line_segment_id": 2,
  "localization_quality": "GOOD"
}
```

Sau khi commit, backend broadcast `ROBOT_STATUS_UPDATED`. Dashboard, Robots và
WarehouseMap nhận dữ liệu qua WebSocket.

### Tasks

```text
GET    /api/tasks
POST   /api/tasks
GET    /api/tasks/{task_id}
PATCH  /api/tasks/{task_id}/status
PATCH  /api/tasks/{task_id}/pause
PATCH  /api/tasks/{task_id}/resume
PATCH  /api/tasks/{task_id}/cancel
```

Status lifecycle chỉ được chuyển theo đúng thứ tự. `FAILED` có thể xảy ra từ
trạng thái đang chạy; `COMPLETED` đặt progress bằng 100.

### Task proof

```text
POST /api/tasks/{task_id}/proofs
GET  /api/tasks/{task_id}/proofs
```

Giá trị hợp lệ:

```text
proof_type:          PICKUP, DELIVERY
verification_status: PENDING, AUTO_VERIFIED, MANUAL_CONFIRMED, FAILED
```

Chỉ lưu `image_path`. Proof được xác nhận tại đúng lifecycle state sẽ tự cập
nhật `PICKUP_CONFIRMED` hoặc `DELIVERY_CONFIRMED`.

### Alerts và History

```text
GET  /api/alerts
POST /api/alerts
PATCH /api/alerts/{alert_id}/acknowledge
PATCH /api/alerts/{alert_id}/resolve

GET /api/history
GET /api/operators
```

Alert có cùng `group_key` và chưa `RESOLVED` sẽ được tăng `occurrence_count`.

### Robot commands và Safe Stop

```text
POST  /api/robots/{robot_id}/commands
PATCH /api/robots/{robot_id}/commands/{command_id}/ack
POST  /api/robots/safe-stop
```

Safe Stop chỉ tạo command cho robot đang `is_active` và `online`. Backend không
coi robot đã dừng nếu chưa có acknowledgement.

### WebSocket

```text
ws://127.0.0.1:8000/ws
```

Message có dạng:

```json
{
  "type": "TASK_UPDATED",
  "data": {}
}
```

Các event chính:

```text
ROBOT_STATUS_UPDATED
TASK_UPDATED
ALERT_UPDATED
EVENT_CREATED
COMMAND_CREATED
COMMAND_ACKNOWLEDGED
COMMAND_FAILED
```

Frontend chỉ fetch REST lần đầu; các thay đổi sau đó đi qua một WebSocket dùng
chung. Không có polling API 5 giây.

## End-to-end test flow

1. Seed database.
2. Tạo product và rack, hoặc dùng dữ liệu seed.
3. Tạo task với product, delivery location và robot.
4. PATCH robot thành online và cập nhật tọa độ/trạng thái.
5. Chuyển task qua lifecycle.
6. Tạo pickup proof với `AUTO_VERIFIED`.
7. Chuyển tới delivery và tạo delivery proof.
8. Chuyển task thành `COMPLETED`.
9. Kiểm tra `/api/history?task_id={task_id}`.
10. Mở frontend để quan sát Dashboard, Robots, WarehouseMap, Alerts và
    History cập nhật realtime.

## Kiểm tra nhanh

```powershell
cd F:\autonomous-warehouse-robot\web
py -3.11 -m compileall -q backend/app
npm run build
```

Smoke test hiện có kiểm tra product/location CRUD, robot status, WebSocket,
task lifecycle, proof, alert grouping và History/EventLog trên SQLite tạm.

## Trạng thái hiện tại

Website đã đủ cho phạm vi testbed/simulation và có thể dừng mở rộng phần web.
Các bước tiếp theo, nếu cần robot thật, là một project tích hợp riêng cho
firmware/hardware, ROS2 hoặc MQTT; không nằm trong website testbed này.
