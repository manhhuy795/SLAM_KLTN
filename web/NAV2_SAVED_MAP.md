# Saved Map → Nav2 (ROS 2 Jazzy / Gazebo)

Chỉ chạy trên simulation. Map/Planning Layer được giữ nguyên; không tự gửi goal khi chọn hoặc chỉnh đối tượng.

## Sử dụng

Vào Bản đồ & Sản phẩm → Bản đồ kho → Saved Map:
1. Chọn map đúng môi trường Gazebo, xác nhận đã đối chiếu.
2. Nhập initial pose đã biết trong frame map nếu cần. (0,0,0) chỉ đúng khi robot vừa spawn ở world warehouse mặc định.
3. Bấm Nạp bản đồ vào Nav2; đợi Map Server, Localization và Nav2 hợp lệ.
4. Lưu quy hoạch và bấm Áp dụng vùng cấm, kể cả danh sách vùng cấm rỗng. Đợi xác nhận phiên bản hiện tại.
5. Chọn HOME/PICKUP/DELIVERY/CHARGING, bấm Đi tới điểm; theo dõi path, robot, status và distance. Hủy điều hướng dùng luồng cancel cũ.

Map đang xem độc lập với map Nav2. Kệ chỉ là quy hoạch, không tự thành vật cản Nav2. Live Map vẫn chỉ đọc.

## Khởi chạy trên Ubuntu VM

Kiểm tra cổng trước; không khởi chạy trùng dịch vụ:
```bash
ss -ltnp | grep -E ':8000|:5173'
```
Terminal 1:
```bash
cd /home/huy/SLAM_KLTN/web/backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Terminal 2:
```bash
cd /home/huy/SLAM_KLTN/web
npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
```
Terminal 3 trên desktop Ubuntu:
```bash
source /opt/ros/jazzy/setup.bash
source /home/huy/SLAM_KLTN/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=76
export GZ_PARTITION=slam_stage3
export GZ_IP=127.0.0.1
ros2 launch amr_sim simulation.launch.py vm_compat:=true
```
Terminal 4, không chạy SLAM Toolbox/bridge khác song song:
```bash
source /opt/ros/jazzy/setup.bash
source /home/huy/SLAM_KLTN/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=76
export GZ_PARTITION=slam_stage3
export GZ_IP=127.0.0.1
ros2 launch amr_sim saved_map_navigation.launch.py
```
Từ Windows: http://192.168.192.134:5173 (đổi IP nếu VM nhận IP khác).

## API và dữ liệu

- GET /api/ros/map-session: map thực dùng, hash, lifecycle/localization, revision keepout, lỗi/xác nhận.
- POST /api/ros/map-session/apply: {map_id, operation:"LOAD_MAP", initial_pose?:{x,y,yaw}}.
- Cùng endpoint với {map_id, operation:"APPLY_KEEPOUTS", planning_revision}.
- GET /api/ros/map-session/command và POST /api/ros/map-session/status: bridge nhận thao tác/trả kết quả.
- POST /api/ros/navigation/goal thêm {x,y,yaw,map_id,planning_point_id,planning_revision}; server lấy tọa độ từ điểm đã lưu.
- Event MAP_SESSION_UPDATED; status/path/cancel dùng API và event cũ.

Goal manual/location/task cũng qua guard của managed bridge. Kiểm tra map/session/revision, AMCL/TF/scan, footprint của cả global/local, tường/unknown/NO-GO và costmap trước NavigateToPose.

Mask riêng dùng KeepoutFilter trên cả hai costmap. Mỗi lần apply có topic mới, transient-local QoS. Mask mở rộng theo bán kính bao footprint đã padding + đường chéo ô lưới vì filter chạy sau inflation. Xác nhận yêu cầu đúng subscription phiên bản mới, dữ liệu costmap được publish mới và lethal cost tương ứng. Xóa mask cũng kiểm tra giải phóng ô cũ; vật cản thật tại ô đó có thể khiến xác nhận thất bại an toàn.

Jazzy không hỗ trợ origin yaw khác 0 trong luồng costmap này: từ chối nạp, giữ nguyên map để xem/chỉnh. Tham chiếu: https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_costmap_2d/plugins/costmap_filters/keepout_filter.cpp

## Kiểm thử

```bash
cd /home/huy/SLAM_KLTN/web/backend
.venv/bin/python -m unittest discover -s tests -v
cd /home/huy/SLAM_KLTN/web
node --test src/services/*.test.js
npm run build
source /opt/ros/jazzy/setup.bash
cd /home/huy/SLAM_KLTN/ros2_ws
colcon build --packages-select amr_sim web_bridge --symlink-install
source install/setup.bash
colcon test --packages-select amr_sim web_bridge --event-handlers console_direct+
colcon test-result --test-result-base build/web_bridge
colcon test-result --test-result-base build/amr_sim
```
amr_sim hiện không đăng ký unit test riêng; không trộn kết quả cũ của package vendor vào kết quả hai package này.

Browser regression dùng backend/SQLite tạm riêng:
```bash
npm install --prefix /tmp/import-map-browser playwright@1.64.1 --no-audit --no-fund
/tmp/import-map-browser/node_modules/.bin/playwright install chromium
cd /home/huy/SLAM_KLTN/web
export PLAYWRIGHT_MODULE=/tmp/import-map-browser/node_modules/playwright
node tests/import-map.browser.cjs
node tests/map-editor.browser.cjs
```
Integration test sau CÓ điều khiển robot Gazebo và lưu map kiểm thử để xem. Chỉ chạy với warehouse.sdf, domain 76, robot vừa spawn (0,0,0). Map được dựng từ collision boxes của world, KHÔNG phải khảo sát LiDAR:
```bash
mkdir -p /tmp/nav2-map-check
python3 /home/huy/SLAM_KLTN/ros2_ws/src/amr_sim/test/make_warehouse_map.py --output /tmp/nav2-map-check/gazebo_geometry
cd /home/huy/SLAM_KLTN/web
export PLAYWRIGHT_MODULE=/tmp/import-map-browser/node_modules/playwright
export NAV2_SIMULATION_TEST=1
export NAV2_INITIAL_POSE='{"x":0,"y":0,"yaw":0}'
export NAV2_TEST_MAP_PREFIX=/tmp/nav2-map-check/gazebo_geometry
export NAV2_TEST_ARTIFACT_DIR=/tmp/nav2-map-check/evidence
node tests/nav2-saved-map.browser.cjs
```
PASS: map/localization xác nhận; cả hai costmap có lethal mask; path tránh polygon; robot tới đích SUCCEEDED. Ảnh/JSON trong evidence. Không chạy lại với initial pose cũ sau khi robot di chuyển.

## Giới hạn

- Chưa nghiệm thu phần cứng; cần map thực, calibration/footprint/TF và xác minh localization độc lập.
- Vùng tròn bao footprint có thể từ chối lối hẹp mà hình chữ nhật xoay có thể đi qua.
- Map/planning lưu bền; phiên Nav2 trong RAM được bridge xác nhận lại. Restart backend kiểm thử khi robot đã dừng; chưa phục hồi tự động nhiệm vụ đang chạy.
- Không chuyển đổi/xóa dữ liệu Location hoặc Task. Không commit/push build, install, log, dist hay file tạm.

## Dừng hệ thống

Khi chạy các terminal ở trên: hủy goal trên web và đợi CANCELLED (hoặc đợi SUCCEEDED), rồi Ctrl+C lần lượt ở terminal Nav2, Gazebo, backend và frontend. Đợi tiến trình thoát rồi shutdown Ubuntu bằng menu hệ thống. Sau lần khởi động mới phải nạp map, xác nhận initial pose và áp dụng vùng cấm lại; không dùng initial pose của lần chạy trước nếu robot đã spawn lại.

## Các file của Giai đoạn 3

- Backend: thêm app/services/map_session.py, app/api/routes/map_session.py, tests/test_map_session.py; nối vào app/main.py, app/services/navigation.py, app/api/routes/ros.py, app/api/routes/maps.py, app/schemas/ros.py.
- ROS bridge: thêm web_bridge/managed_maps.py, web_bridge/navigation_safety.py, web_bridge/keepouts.py và test/test_navigation_safety.py; sửa web_bridge/web_bridge_node.py, launch/web_bridge.launch.py, package.xml.
- Simulation: thêm amr_sim/launch/saved_map_navigation.launch.py và amr_sim/test/make_warehouse_map.py; dùng cấu hình Nav2 hiện có qua launch override.
- Web: thêm src/UI/SavedMapNavigation.jsx; nối vào WarehouseMap.jsx, MapEditor.jsx, SlamMap.jsx, SavedMapControls.jsx, NavigationPanel.jsx, src/services/api.js và src/styles/dashboard.css.
- Browser tests: thêm tests/nav2-saved-map.browser.cjs; sửa tests/map-editor.browser.cjs để scroll canvas vào viewport trước thao tác chuột.
- Tài liệu: web/NAV2_SAVED_MAP.md. Những thay đổi chưa commit từ các giai đoạn trước được giữ nguyên.

## Kết quả nghiệm thu trên VM (19/10/2026)

- 3A/3B/3C: PASS simulation. Chạy lại sau shutdown/reboot: map và localization hợp lệ, mask 496 ô trên mỗi costmap, path tránh vùng cấm và NavigateToPose SUCCEEDED.
- Backend: 31 tests PASS; frontend: 11 tests PASS; npm run build PASS.
- ROS: build amr_sim/web_bridge PASS; web_bridge 18 tests PASS (amr_sim chưa đăng ký unit test).
- Browser Import Map/Map Editor regression PASS; cancel trả CANCELLED, WebSocket/path/distance realtime PASS.
- Tắt filter local cố ý: apply FAILED đúng; khôi phục filter: apply PASS. Xóa vùng cấm giải phóng mask; goal trong vùng cấm/vật cản bị từ chối.
- Restart backend khi idle: map/planning giữ nguyên. Nav2 offline: goal bị chặn HTTP 409. Sau shutdown VM: SQLite quick_check=ok; Task/Location/map/planning gốc không đổi so với baseline.
- Bằng chứng JSON/ảnh/log: /home/huy/.local/state/nav2-map-stage3/. Không đưa dữ liệu kiểm thử hoặc build artifacts vào Git.
