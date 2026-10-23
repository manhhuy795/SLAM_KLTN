# SLAM_KLTN — chạy demo trên Ubuntu

Repo chứa FastAPI, React, ROS 2 Web Bridge, Gazebo/Nav2 và bộ dữ liệu demo.
Không cần SQLite hoặc thư mục build từ máy của tác giả. Các lệnh dưới chạy từ thư mục clone;
không có đường dẫn /home/huy hoặc IP cố định.

## Hướng dẫn chạy full WRMS (nhánh tích hợp AGV)

**Tình trạng:** mô phỏng AMR/ROS 2 + WRMS chạy theo luồng đã có; hai file AGV gốc đã được kiểm tra phần cứng bởi chủ dự án, nhưng **tích hợp AGV → WRMS, hiển thị chung bản đồ và AMR thật chưa được nghiệm thu end-to-end**. [Pull Request #1](https://github.com/manhhuy795/SLAM_KLTN/pull/1) còn Draft; `main` chưa có phần tích hợp này.

Một sân kho vật lý, **một Saved Map WRMS**: `AMR-01` dùng LiDAR/ROS 2, `LINE-01` dùng cảm biến dò line/encoder/MPU6050. AGV có frame nội bộ A–B–C–D 1,54 × 1,51 m, còn bản đồ sân demo WRMS 2,38 × 1,68 m. **Không coi đó là hai bản đồ kho độc lập, cũng không tự đồng nhất tọa độ hai robot.**

### Clone đúng phiên bản có AGV (lần đầu)

~~~bash
git clone https://github.com/manhhuy795/SLAM_KLTN.git
cd SLAM_KLTN
git fetch origin
git switch --track origin/feat/wrms-agv-hardware-telemetry-20261023
bash scripts/setup_web.sh
~~~

`setup_web.sh` yêu cầu Python, Node.js đúng phiên bản (mục 1–2). Nếu đã có repo/branch local, dùng `git switch feat/wrms-agv-hardware-telemetry-20261023` và `git pull --ff-only`; **không reset, xóa DB hoặc ghi đè dữ liệu đã có**.

### Các tiến trình khi demo (4 terminal + ESP32)

| Thành phần | Cổng/topic | Cách khởi động |
| --- | --- | --- |
| Terminal 1: FastAPI, SQLite, AGV API | :8000 | Mục 3 + 6.2 |
| Terminal 2: React dashboard | :5173 | Mục 3 |
| Terminal 3: Gazebo AMR simulation | /scan, /odom | Mục 4 |
| Terminal 4: Nav2 Saved Map + AMCL + Web Bridge | ROS 2 / port 8000 | Mục 4 |
| ESP32-S3 AGV **thật** | Wi-Fi → HTTP :8000 | Flash `agv_line_controller.ino` theo mục 6.1 |

**Quan trọng:** Gazebo/Nav2 ở mục 4 dùng world **12 × 8 m**; AGV thật dùng sa bàn **2,38 × 1,68 m**. Hai chế độ này có thể gửi dữ liệu về cùng Web nhưng **không phải hai robot thật cùng được định vị trên một map**. Để demo cả hai robot **thật** trên một map, AMR thật còn cần bring-up TF/odom/localization/Nav2 ngoài bench LiDAR đã ghi nhận; xem mục 7.

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


## 6. Chạy WRMS + AGV dò line thật

### 6.1 ESP32-S3 firmware và mạng

Firmware AGV đã chuyển vào `firmware/esp32_s3/agv_line_controller/agv_line_controller.ino`. **Không dùng** `server.py` standalone cổng 5000 nữa, cũng **không nạp firmware AGV vào ESP32 của AMR**.

~~~bash
cd ~/SLAM_KLTN
cp firmware/esp32_s3/agv_line_controller/agv_secrets.example.h \
   firmware/esp32_s3/agv_line_controller/agv_secrets.h
nano firmware/esp32_s3/agv_line_controller/agv_secrets.h
hostname -I
~~~

Cấu hình trong `agv_secrets.h` (giữ nguyên tên macro):

~~~cpp
#pragma once
#define AGV_WIFI_SSID "WIFI_2_4GHZ"
#define AGV_WIFI_PASSWORD "MAT_KHAU_WIFI"
#define AGV_TELEMETRY_URL "http://IP_UBUNTU:8000/api/agv/LINE-01/telemetry"
#define AGV_DEVICE_TOKEN "TOKEN_DAI_NGAU_NHIEN"
~~~

`IP_UBUNTU` là IP mà ESP32 cùng LAN **định tuyến được đến**, không phải `localhost`. Nếu Backend chạy trong VMware NAT, dùng Bridged hoặc port forwarding đã kiểm tra; firewall phải cho phép kết nối nội bộ tới :8000. Máy truy cập Web cũng phải tới được :5173 và :8000. Không commit `agv_secrets.h` (đã thêm vào .gitignore), không công khai token. Dùng Arduino IDE + board ESP32-S3 đúng, upload `agv_line_controller.ino` rồi kiểm tra Serial Monitor 115200 và telemetry; làm lại kiểm tra an toàn với bánh nâng khỏi sàn vì URL/header tích hợp là phần mới.

### 6.2 Full Web/AGV — hai terminal Ubuntu

**Terminal 1**, từ repo, cấu hình token trùng firmware, mặc định chưa bật lệnh từ Web:

~~~bash
cd ~/SLAM_KLTN/web/backend
export WRMS_CORS_ORIGINS="http://$(hostname -I | awk '{print $1}'):5173"
export WRMS_AGV_TOKEN="TOKEN_DAI_NGAU_NHIEN"
export WRMS_AGV_ENABLE_COMMANDS=0
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
~~~

**Terminal 2**:

~~~bash
cd ~/SLAM_KLTN/web
npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
~~~

Mở `http://IP_UBUNTU:5173`. Vào **Tổng quan → AGV LINE-01** xem thông số encoder, MPU6050 yaw, x/y, cảm biến TCRT5000, PWM, tốc độ, trạng thái, ACK, lệnh chờ và CSV. ESP32 tự POST `/api/agv/LINE-01/telemetry` mỗi khoảng 150 ms theo firmware. Backend phản hồi `cmd`, `cmd_id`; không cần khởi động Web Bridge/ROS để có telemetry AGV.

**Terminal kiểm tra** (một terminal khác, không mở thêm service):

~~~bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/robots
curl -fsS http://127.0.0.1:8000/api/agv/LINE-01/state
curl -f http://127.0.0.1:8000/api/agv/LINE-01/export_csv -o agv_telemetry.csv
~~~

`/state` phải có `connected:true` khi ESP32 gửi đều. Khi không nhận được: kiểm tra Wi-Fi 2.4 GHz, địa chỉ Ubuntu/VM, log Serial, header `X-AGV-Token`, firewall và HTTP status. API trả `401` nếu token sai, `503` nếu Backend chưa có `WRMS_AGV_TOKEN`, `404` nếu chưa seed `LINE-01` và `422` nếu schema payload sai. Khởi tạo DB bằng mục 2, **không xóa DB để sửa lỗi**.

Khi đã đối chiếu dữ liệu và thử dừng an toàn, **tắt robot/chỉ để bánh nâng**, dừng Terminal 1 và đổi `WRMS_AGV_ENABLE_COMMANDS=1` trong lần chạy Backend tiếp theo nếu cần điều khiển qua Web. Mục tiêu ban đầu là **read-only telemetry**. Lệnh Web hiện chưa xác thực người vận hành; chỉ sử dụng trên LAN tin cậy có giới hạn truy cập. `ack_id` không bảo đảm hoàn thành chuyển động; **STOP qua mạng không thay thế E-stop vật lý**. Firmware AGV gốc chưa có watchdog bắt buộc dừng động cơ khi mất mạng. Mailbox và log telemetry trong RAM, mất khi restart Backend.

### 6.3 Cả hai robot trên **một Saved Map**

Chọn **Saved Map → San Demo 4 A0 - Final** (2,38 × 1,68 m) trong WRMS. Trong mục bản đồ có các ô **A(x,y), B(x,y), D(x,y)** cho AGV. Hãy đo và nhập vị trí ba mốc trên **bản đồ kho chung**; không tự nhập A=(0,0), B=(0,1.51), D=(1.54,0) nếu gốc map thật không trùng gốc firmware.

- Backend lưu telemetry AGV trong hệ A–B–C–D **+Y xuống, yaw độ**; không dùng trực tiếp nó như pose ROS `map`.
- Frontend áp dụng phép tịnh tiến/đổi hướng và kiểm tra độ dài A–D xấp xỉ 1,54 m, A–B xấp xỉ 1,51 m. Nếu chưa có mốc đúng, map hash sai, pose ngoài bản đồ hoặc thiết bị offline thì **không vẽ marker AGV sai**.
- Mốc hiệu chuẩn hiện lưu ở **localStorage từng trình duyệt** và gắn với map hash, chưa dùng DB để đồng bộ giữa các máy.
- Màn hình nhỏ A–B–C–D trong AGV telemetry là **bảng chẩn đoán local**, không phải bản đồ kho thứ hai.
- Marker **AMR thật** chỉ có nghĩa khi ROS có pose/map localization hợp lệ; không suy diễn từ việc nhận được `/scan`.

## 7. Chạy AMR thật (bench), không trộn với Gazebo

**LiDAR thật** từng được kiểm tra với profile `LDLiDAR_LD14`, 115200 baud và `/scan` khoảng 6 Hz; xem [báo cáo D200](ros2_ws/src/amr_hardware/D200_CHECK.md). Điều hướng Nav2 trên AMR thật **chưa được nghiệm thu end-to-end**.

**Dừng Gazebo/Nav2 simulation** trước khi chạy ROS LiDAR/base trên cùng ROS domain. Với checkout mới, cần submodule của LiDAR; file patch SDK chỉ áp dụng **một lần**, khi kiểm tra `apply --check` thành công:

~~~bash
cd ~/SLAM_KLTN
git submodule update --init --recursive
git -C ros2_ws/src/ldlidar_ros2/sdk apply --check "$PWD/patches/ldlidar-sdk-pthread.patch"
git -C ros2_ws/src/ldlidar_ros2/sdk apply "$PWD/patches/ldlidar-sdk-pthread.patch"
source /opt/ros/jazzy/setup.bash
cd ros2_ws
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy
colcon build --packages-select ldlidar_ros2 amr_hardware web_bridge --symlink-install
source install/setup.bash
~~~

Nếu patch đã áp dụng, **không áp dụng lại**; xem hướng dẫn trong `D200_CHECK.md`. Mở Backend/Frontend theo mục 3 (đặt token theo mục 6 nếu có AGV). Sau đó mở **terminal ROS LiDAR** (kiểm tra port thật với `ls -l /dev/serial/by-id` hoặc `ls /dev/ttyUSB*`):

~~~bash
cd ~/SLAM_KLTN
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
ros2 launch amr_hardware real_lidar.launch.py port_name:=/dev/ttyUSB0 rviz:=true
~~~

**Terminal Web Bridge ROS thật**:

~~~bash
cd ~/SLAM_KLTN
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
ros2 launch web_bridge web_bridge.launch.py use_sim_time:=false
~~~

**Kiểm tra cảm biến**:

~~~bash
ros2 topic echo /scan --once --field header
ros2 topic hz /scan
~~~

Đối với **base AMR thật**, cần hoàn thành cấu hình firmware `amr_motor_controller.ino`, encoder, motor driver, tham số `hardware.yaml` và E-stop trước. Chỉ chạy node khi phần cứng phù hợp:

~~~bash
ros2 launch amr_hardware hardware.launch.py \
  params_file:=$HOME/SLAM_KLTN/ros2_ws/src/amr_hardware/config/hardware.yaml
~~~

Lệnh trên **không tự khởi động SLAM/Nav2 thật**. Không chạy `amr_hardware` trùng Gazebo với cùng `/odom` và không chạy hai publisher `/scan` cùng lúc. Xem [AMR hardware README](ros2_ws/src/amr_hardware/README.md).

## 8. Kiểm thử full stack và dừng hệ thống

Sau khi hoàn tất setup và có hai terminal Web:

~~~bash
cd ~/SLAM_KLTN/web/backend
.venv/bin/python -m unittest discover -s tests -v
cd ../
node --test src/services/*.test.js
npm run build
cd ../ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
colcon test --packages-select amr_sim web_bridge --event-handlers console_direct+
colcon test-result --test-result-base build/web_bridge
~~~

**Checklist:** Backend health 200; SQLite có `AMR-01` và `LINE-01`; ESP32 telemetry cập nhật/không bị stale; Serial khớp Dashboard; căn chỉnh A/B/D trên map thực; mô phỏng Nav2 dùng **map SIMULATION ONLY** đúng world 12 × 8 m, nhận `/scan`/`/odom`, có localization/path/goal và cancel; không đánh đồng mô phỏng AMR với phần cứng AMR. Nếu chạy hai robot thật cùng sân, cần kiểm tra riêng vùng tránh va chạm, nhiệm vụ và E-stop trước demo.

**Shutdown an toàn:** dừng robot thật bằng cơ cấu an toàn vật lý nếu cần → hủy goal và xác nhận robot dừng → Ctrl+C Nav2/Web Bridge → Ctrl+C Gazebo → Ctrl+C Backend → Ctrl+C Frontend. **Không tắt Web rồi mặc định AGV đã dừng**, vì firmware có chế độ chạy nội bộ khi mất Wi-Fi.
