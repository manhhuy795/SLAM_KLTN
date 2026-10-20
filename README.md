# SLAM_KLTN — chạy demo trên Ubuntu

Repo chứa FastAPI, React, ROS 2 Web Bridge, Gazebo/Nav2 và bộ dữ liệu demo.
Không cần SQLite hoặc thư mục build từ máy của tác giả. Các lệnh dưới chạy từ thư mục clone;
không có đường dẫn /home/huy hoặc IP cố định.

## 1. Cài công cụ

Môi trường đã kiểm thử: Ubuntu 24.04 Desktop, Python 3.12, Node.js 22, ROS 2 Jazzy.
Chỉ xem web/quy hoạch thì không cần ROS hoặc robot.

~~~bash
sudo apt update
sudo apt install -y git curl build-essential python3-venv python3-pip
git clone https://github.com/manhhuy795/SLAM_KLTN.git
cd SLAM_KLTN
~~~

Node phải đáp ứng [yêu cầu Vite](https://vite.dev/guide/) (Node 22.12+ hoặc 24+).
Nếu chưa có Node phù hợp, cài qua [nvm](https://github.com/nvm-sh/nvm):
~~~bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh -o /tmp/slam-kltn-install-nvm.sh
bash /tmp/slam-kltn-install-nvm.sh
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm install
nvm use
~~~
Repo có .nvmrc chọn Node 22. Lệnh tải dependencies cần Internet.

## 2. Chuẩn bị web và dữ liệu (chạy một lần)

Từ thư mục SLAM_KLTN, khi backend chưa chạy:
~~~bash
bash scripts/setup_web.sh
~~~

Lệnh này tạo venv, cài requirements, khởi tạo SQLite, seed dữ liệu mẫu có sẵn,
import hai Saved Map, npm ci và build frontend.

- **San Demo 4 A0 - Final**: 2,38 × 1,68 m; mặc định trên database mới.
  Có HOME, PICKUP, A1…D2 và KE_A…KE_D, đủ 14 đối tượng.
- **SIMULATION ONLY - warehouse.sdf geometry**: 12 × 8 m, đúng world Gazebo trong repo.
  Có SIM Destination và SIM Keepout để kiểm tra Nav2.

Importer nhận diện map theo hash, chạy lại không nhân đôi map/đối tượng hoặc đổi lựa chọn đã có.
Nếu quy hoạch hiện có khác bộ mẫu, importer báo lỗi và giữ nguyên; không xóa database để xử lý lỗi này.
Chỉ cần thêm dữ liệu vào môi trường đã cài đặt:
~~~bash
cd web/backend
.venv/bin/python import_demo.py
.venv/bin/python import_demo.py --dataset simulation
~~~
Chạy khi backend đã dừng, sau đó khởi động lại backend để mọi trình duyệt tải trạng thái mới.

## 3. Mở web — hai terminal

Mỗi terminal bắt đầu ở thư mục clone SLAM_KLTN.

Terminal 1:
~~~bash
cd web/backend
export WRMS_CORS_ORIGINS="http://$(hostname -I | awk '{print $1}'):5173"
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
~~~

Terminal 2:
~~~bash
cd web
npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
~~~

Trên Ubuntu mở http://localhost:5173. Từ Windows/máy khác cùng mạng:
chạy hostname -I trên Ubuntu rồi mở http://IP_UBUNTU:5173.
Trình duyệt cũng cần truy cập cổng backend 8000.
WRMS_CORS_ORIGINS ở Terminal 1 cho phép trình duyệt truy cập qua IP của Ubuntu.
Nếu máy có nhiều card mạng, thay bằng IP đang dùng; có thể khai báo nhiều origin cách nhau bởi dấu phẩy.
Nếu báo Address already in use, kiểm tra ss -ltnp trước khi mở thêm dịch vụ.

Mở Tổng quan hoặc Bản đồ & Sản phẩm: bản đồ sân demo xuất hiện cùng 14 đối tượng.
Chọn đối tượng để xem tọa độ; Chỉnh sửa bản đồ → Save để lưu, refresh vẫn còn.
Không cần ROS cho các chức năng này. Offline/UNLOCALIZED trong bảng Nav2 không phải lỗi import.

## 4. Gazebo + Nav2 (tùy chọn)

Cài [ROS 2 Jazzy cho Ubuntu 24.04](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)
trước; sau đó chạy từ thư mục repo:
~~~bash
sudo apt update
sudo apt install -y ros-dev-tools ros-jazzy-ros-gz ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-slam-toolbox
source /opt/ros/jazzy/setup.bash
~~~

Nếu máy chưa có cấu hình rosdep, chạy sudo rosdep init một lần. Tiếp theo:
~~~bash
rosdep update
rosdep install --from-paths ros2_ws/src/amr_sim ros2_ws/src/web_bridge --ignore-src -r -y --rosdistro jazzy
cd ros2_ws
colcon build --packages-select amr_sim web_bridge --symlink-install
~~~

Không cần tải/build submodule LiDAR để chạy demo simulation. Phần cứng thật có hướng dẫn riêng
trong ros2_ws/src/amr_hardware/README.md.

Giữ backend/frontend đang chạy. Mỗi terminal ROS bắt đầu ở thư mục repo.
Terminal 3, mở trên desktop Ubuntu (Gazebo dùng cửa sổ đồ họa):
~~~bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=76 GZ_PARTITION=slam_stage3 GZ_IP=127.0.0.1
ros2 launch amr_sim simulation.launch.py vm_compat:=true
~~~
Đợi robot và dữ liệu scan/odom xuất hiện; có thể kiểm tra ở terminal ROS:
~~~bash
ros2 topic echo /odom --once --field pose.pose.position
ros2 topic echo /scan --once --field header
~~~

Terminal 4:
~~~bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=76 GZ_PARTITION=slam_stage3 GZ_IP=127.0.0.1
ros2 launch amr_sim saved_map_navigation.launch.py
~~~
Không mở SLAM Toolbox/bridge khác song song với luồng Saved Map này.
Nếu lifecycle khởi động timeout trên VM: đợi máy ổn định, Ctrl+C terminal 4 rồi chạy lại.
Không khởi động một launch thứ hai khi launch cũ chưa thoát.

Trên web:
1. Chọn Saved Map **SIMULATION ONLY - warehouse.sdf geometry**.
2. Xác nhận đã đối chiếu môi trường; nhập initial pose (0,0,0) chỉ khi robot vừa spawn mặc định.
3. Nạp bản đồ vào Nav2, đợi map/localization hợp lệ.
4. Áp dụng vùng cấm, đợi READY và xác nhận phiên bản.
5. Chọn SIM Destination → Đi tới điểm. Mong đợi path tránh vùng đỏ và SUCCEEDED.
6. Có thể Hủy điều hướng khi đang chạy để kiểm tra CANCELLED.
7. Chọn lại San Demo 4 A0 - Final để trở về bản đồ chính của web.

Chọn Saved Map chỉ đổi bản đồ đang xem; không tự load vào Nav2 hoặc gửi goal.
Sân demo 2,38 × 1,68 m không khớp world Gazebo 12 × 8 m; không dùng initial pose/map của môi trường này cho môi trường kia.

## 5. Test

~~~bash
cd web/backend
.venv/bin/python -m unittest discover -s tests -v
cd ..
node --test src/services/*.test.js
npm run build
cd ../ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
colcon test --packages-select amr_sim web_bridge --event-handlers console_direct+
colcon test-result --test-result-base build/web_bridge
colcon test-result --test-result-base build/amr_sim
~~~
amr_sim chưa đăng ký unit test riêng. Các browser/simulation tests và opt-in robot motion được mô tả
trong [web/NAV2_SAVED_MAP.md](web/NAV2_SAVED_MAP.md).

## Dữ liệu, giới hạn và dừng hệ thống

- demo/final chứa YAML/PGM, payload quy hoạch gốc và hai CSV; demo/simulation là fixture từ collision boxes của warehouse.sdf, không phải khảo sát LiDAR.
- Chưa có RACK_STOP: A1…D2 dùng PICKUP, giữ nguyên tên/tọa độ; yaw mặc định 0.
  A1, B2, C1, D2 trùng ô vật cản trong PGM final. Không tự sửa tọa độ hoặc coi các điểm là an toàn.
  Bốn kệ dùng đúng kích thước tham khảo; đường line không được thêm vào occupancy hoặc keepout.
- Runtime nằm ở web/backend/data/wrms.db và web/backend/data/maps/. Dữ liệu phát sinh trên mỗi máy
  không đồng bộ qua Git. Khi cần backup, dừng backend rồi sao lưu cả thư mục data.
- Sau khi cài đặt, ứng dụng dùng dữ liệu local; không chứa mật khẩu, địa chỉ SSH hay database của tác giả.
- Trước shutdown: hủy goal và đợi CANCELLED/robot dừng, Ctrl+C Nav2, Gazebo, backend, frontend rồi shutdown Ubuntu.
- Chưa nghiệm thu robot thật hoặc phục hồi tự động goal đang chạy khi backend bị tắt.
