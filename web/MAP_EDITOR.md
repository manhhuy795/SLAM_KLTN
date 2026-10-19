# Map Editor — Planning Layer

Trên Ubuntu VM, mở http://192.168.192.134:5173 từ Windows.
Vào **Bản đồ & Sản phẩm → Bản đồ kho → Saved Map**, chọn map rồi bấm **Chỉnh sửa bản đồ**.

## Thao tác

- **Add Rack / Home / Pickup / Delivery / Charging**: chọn công cụ, bấm vị trí trên bản đồ.
- **Select / Move**: chọn hoặc kéo đối tượng. Bảng bên phải sửa tên, X/Y (m), Yaw (radian) và kích thước kệ.
- **Draw No-Go Zone**: bấm ít nhất ba đỉnh rồi **Hoàn tất vùng cấm**.
  Chọn polygon và kéo nút trắng, hoặc sửa tọa độ từng đỉnh để thay đổi hình/kích thước.
- **Pan**, kéo nền hoặc giữ nút chuột giữa để dịch khung nhìn; cuộn chuột hoặc nút +/− để zoom; **Fit map** để trở về toàn bản đồ.
- **Delete** xóa đối tượng khỏi bản nháp. **Save** lưu toàn bộ lớp; **Cancel** tải lại lớp trên server.
- Không đổi/xóa/upload map trong lúc chỉnh sửa. Lưu hoặc hủy trước.
  Rời trang/refresh khi có bản nháp sẽ hỏi xác nhận; chưa Save thì dữ liệu chưa được lưu.
- Hai cửa sổ cùng chỉnh sửa: lần lưu dùng phiên bản cũ trả 409, giữ bản nháp và báo lỗi; Cancel để tải lại phiên bản mới.

Ngoài bản đồ hoặc polygon không hợp lệ sẽ chặn Save. Điểm ở ô chiếm dụng/chưa biết hiện cảnh báo.
Ô trống cũng không chứng minh robot tiếp cận được.

## Lưu trữ và tọa độ

Bảng SQLite mới **planning_layers** liên kết SavedMap bằng map_id, không thêm/sửa Location hoặc Task.
Mỗi map có một danh sách đối tượng JSON, revision và updated_at; mỗi đối tượng có UUID, map_id,
type, name, x/y/yaw, width/height hoặc vertices, created_at và updated_at.

X/Y và Yaw theo hệ tọa độ ROS map. Đỉnh NO_GO là mét cục bộ quanh X/Y, xoay theo Yaw.
Kệ dùng X/Y làm tâm, width/height theo hai trục cục bộ của kệ.
Chuyển Canvas ↔ ROS áp dụng resolution, origin X/Y/Yaw và đảo chiều Y.
Zoom/pan chỉ tác động phép hiển thị; không thay đổi tọa độ đã lưu.

Metadata/planning ở web/backend/data/wrms.db. Ảnh/YAML/grid gốc vẫn nằm trong web/backend/data/maps/.
Backend tự tạo bảng mới khi khởi động; không cần seed/reset database.
Xóa Saved Map xóa luôn planning của map đó bằng khóa ngoại ON DELETE CASCADE.

## API

| Method | URL | Ý nghĩa |
|---|---|---|
| GET | /api/maps/{map_id}/planning | Tải lớp, revision 0 và objects [] nếu chưa lưu |
| PUT | /api/maps/{map_id}/planning | Lưu nguyên tử {revision, objects}; thêm/sửa/xóa đối tượng trong danh sách |
| DELETE | /api/maps/{map_id}/planning?revision=N | Xóa toàn bộ đối tượng, vẫn tăng revision |

PUT chỉ gửi id/type/name/x/y/yaw/width/height/vertices trong từng object.
map_id và timestamps do server gắn, không nhận từ client.
Response chứa revision mới, objects và warnings; WebSocket hiện có phát PLANNING_UPDATED.
Giới hạn 500 đối tượng/map, 128 đỉnh/polygon, tên 1–120 ký tự.
422: geometry/biên/tọa độ không hợp lệ; 409: phiên bản cũ; 404: map không tồn tại.
Mọi sửa/xóa cần revision để không âm thầm ghi đè dữ liệu.

## Kiểm thử trên Ubuntu

```bash
cd ~/SLAM_KLTN/web/backend
.venv/bin/python -m unittest discover -s tests -v
cd ..
node --test src/services/*.test.js
npm run build
```

Frontend phải đang chạy ở 5173 trước khi chạy browser test.
Playwright chỉ là công cụ kiểm thử ngoài repo:

```bash
npm install --prefix /tmp/import-map-browser playwright
/tmp/import-map-browser/node_modules/.bin/playwright install chromium
cd ~/SLAM_KLTN
PLAYWRIGHT_MODULE=/tmp/import-map-browser/node_modules/playwright node web/tests/map-editor.browser.cjs
PLAYWRIGHT_MODULE=/tmp/import-map-browser/node_modules/playwright node web/tests/import-map.browser.cjs
```

Browser test dùng backend/SQLite riêng và bản đồ tổng hợp, không gửi lệnh ROS.
Kiểm tra mọi loại đối tượng, kéo kệ/đỉnh polygon, nhập tọa độ/kích thước, zoom/pan,
ngoài biên, Save/Cancel, refresh/restart, tách map, conflict, WebSocket, grid không đổi,
Live read-only và quay lại Task/Dashboard. Ảnh/kết quả nằm trong thư mục in ra khi PASS.

## Giới hạn

Chỉ quy hoạch và hiển thị. NO_GO chưa đi vào Nav2 Costmap; điểm mới chưa được dùng cho Task/navigation.
Không sửa OccupancyGrid, firmware hoặc các API ROS/Nav2. Chưa kiểm chứng khả năng đi lại thực tế của robot.
