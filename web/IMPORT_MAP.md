# Import Map trên Ubuntu

Mở **Bản đồ & Sản phẩm → Bản đồ kho** (hoặc Tổng quan).
Nhập tên, chọn cặp ROS YAML và PGM/PNG rồi bấm **Upload Map**.
Tên ảnh trong trường `image` của YAML phải khớp tên ảnh tải lên.

- **Saved Map (server)**: chọn bản đồ đã lưu, xem khi ROS/robot offline, hoặc xóa sau xác nhận.
- **Live Map (ROS 2)**: xem map/pose/path hiện tại từ bridge. WebSocket live không thay thế Saved Map.
- Saved Map chỉ để xem; không nạp vào Nav2, không gửi goal và không ghép pose/path của phiên ROS khác.
- Bản đồ được chọn lưu chung trên server; chế độ xem Live/Saved là trạng thái riêng của trang, mặc định Live khi tải lại.
- Giữ resolution, origin x/y/yaw; đổi hàng ảnh từ trên xuống thành hàng OccupancyGrid từ dưới lên. Canvas hiển thị theo trục cục bộ của grid, tọa độ map dùng origin/yaw.
- YAML tối đa 64 KiB, ảnh 8-bit PGM/PNG tối đa 20 MiB và 4 triệu ô. Hỗ trợ mode trinary, scale, raw; không hỗ trợ ảnh động/16-bit hoặc YAML alias.

## Lưu trữ và API

Metadata/selection nằm trong bảng `saved_maps` của `web/backend/data/wrms.db`.
Mỗi bản đồ có thư mục UUID trong `web/backend/data/maps/`, chứa ảnh, YAML chuẩn hóa và `grid.json`.
Restart không xóa dữ liệu. Sao lưu cả SQLite và thư mục maps cùng lúc khi backend đã dừng.
Không chạy lại seed để cập nhật tính năng này; backend tự tạo bảng mới khi khởi động.

| Method | URL | Kết quả |
|---|---|---|
| POST | /api/maps | Multipart: name, yaml_file, image_file; 201 metadata |
| GET | /api/maps | Danh sách metadata |
| GET | /api/maps/selected | OccupancyGrid đã chọn hoặc null |
| GET | /api/maps/{id} | OccupancyGrid và metadata |
| POST | /api/maps/{id}/select | Chọn bản đồ trên server |
| DELETE | /api/maps/{id} | Xóa metadata và file, 204 |

Mutation phát sự kiện `SAVED_MAPS_UPDATED` trên WebSocket hiện có.
File sai trả 422, quá giới hạn trả 413, ID không tồn tại trả 404.
Chỉ đọc ảnh người dùng upload, không truy cập đường dẫn/URL trong YAML.

## Chạy website

Nếu server đang chạy, dùng phiên hiện có; không mở thêm cùng cổng.
Terminal 1:

```bash
cd ~/SLAM_KLTN/web/backend
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Terminal 2:

```bash
cd ~/SLAM_KLTN/web
npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
```

Từ Windows: http://192.168.192.134:5173
Địa chỉ này là IP VM tại lúc kiểm thử; nếu IP VM thay đổi cần cập nhật CORS theo cấu hình dự án.

## Kiểm thử

```bash
cd ~/SLAM_KLTN/web/backend
.venv/bin/python -m unittest discover -s tests -v
cd ..
node --test src/services/*.test.js
npm run build
```

Bản đồ mẫu **tổng hợp, không phải LiDAR thực tế**:
`web/backend/tests/fixtures/maps/import_demo.yaml` và `import_demo.pgm`.
Ảnh bất đối xứng 32 × 24, resolution 0.1, origin [-1.2, -0.8, 0.35] để kiểm tra hướng ảnh.

Browser test chạy Chromium headless trên Ubuntu; cần frontend đang chạy ở 5173.
Playwright chỉ cài trong /tmp, không thêm dependency cho ứng dụng:

```bash
mkdir -p /tmp/import-map-browser
npm install --prefix /tmp/import-map-browser playwright
/tmp/import-map-browser/node_modules/.bin/playwright install chromium
cd ~/SLAM_KLTN
PLAYWRIGHT_MODULE=/tmp/import-map-browser/node_modules/playwright node web/tests/import-map.browser.cjs
```

Test tạo backend/SQLite riêng, upload PGM và PNG qua UI, kiểm tra pixel canvas, origin,
tỷ lệ, WebSocket, Live/Saved, restart khi ROS offline, chọn/xóa và lỗi JavaScript.
Dữ liệu live tổng hợp chỉ gửi vào backend test. Thư mục bằng chứng/ảnh chụp được in khi PASS.

Map Editor và Planning Layer: xem [MAP_EDITOR.md](MAP_EDITOR.md).
