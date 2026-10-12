# Physical LiDAR verification — 2026-10-12

## Result: real LaserScan and Web Bridge PASS

Tested on Ubuntu / ROS 2 Jazzy in VMware at /home/huy/SLAM_KLTN after the user
corrected the wiring and transferred CP2102 from Windows into the VM.
The user confirmed seeing green scan points in the Ubuntu RViz window.
No robot base/motor node, SLAM, Nav2, Gazebo or fake odometry was started.

| Check | Actual result |
| --- | --- |
| USB | CP2102 10c4:ea60, serial 0001, /dev/ttyUSB0 |
| Permissions | root:dialout, 0660; huy is now in dialout |
| UART at 230400 | 46,628 bytes / 4.01 s, zero valid scan packets |
| UART at 115200 | 36,227 bytes / 4.02 s, 770/770 packets have valid CRC |
| SDK LD14P at 115200 | Communication normal, publisher exists, zero scan messages in 10 s |
| SDK LD14 at 115200 | Valid, continuously published LaserScan |
| ROS publisher | Exactly one: /ldlidar_publisher |
| ROS topic/frame | /scan, sensor_msgs/msg/LaserScan, laser_link |
| 30 s acceptance window | 172 received scans, 6.070 Hz after discovery |
| Received intervals | Largest gap 0.393 s; not a hard real-time guarantee |
| Timestamps | Strictly increasing; system time, use_sim_time=false |
| Points per scan | 382–384, with 187–224 valid ranges per scan in this window |
| Angular metadata | 0 to 6.283185 rad; last increment 0.0164481 rad |
| Range metadata | 0.1 to 8.0 m |
| Example measured ranges | 0.411, 0.390, 0.384, 0.403, 0.369, 0.383 m |
| RViz | Running, subscribed to /scan; user confirmed green points |
| Web Bridge | bridge_online=true, lidar_online=true, 6.111 Hz, scan age 61.3 ms |
| Physical TF/odom | No /odom, /tf, /tf_static or /clock publisher; mount not measured |
| Motion | No /cmd_vel publisher; no robot movement commanded |

A separate ros2 topic hz measurement converged to 6.008 Hz.
This is a short hardware check, not long-duration reliability or calibrated
mapping evidence. Ubuntu temporary evidence: /tmp/d200_acceptance.json,
/tmp/d200_real_launch.log, /tmp/d200_duplicate_check.log.

After a later VM reboot, the stack was restarted successfully. A fresh 12 s
check received 68 scans (5.614 Hz) with 383 points, 186 valid ranges, and Web
Bridge online. Two driver timeouts occurred during the slow VM startup.
A following 20 s check measured 5.842 Hz, maximum gap 0.636 s, with no further
timeouts (count stayed 2). The final backend heartbeat showed 5.923 Hz and
scan age 29.5 ms. Investigate VM scheduling/storage latency before relying on
this setup for physical navigation. These are observed delays; the precise
cause of each scan gap has not been isolated. Latest temporary evidence:
/tmp/d200_after_reboot.json and /tmp/d200_final_hz.log. Earlier files in /tmp
may be removed by reboot; the measurements above preserve their results.

## Root cause and model/profile distinction

Initially the user lacked serial permission; adding huy to dialout fixed
opening the port. Earlier probes then received invalid/repeating bytes or no
bytes. After the user's wiring correction, valid packets appeared at 115200,
matching the Windows LdsPointCloudViewer screenshot (LDS14, 115200, about
383 points/revolution).

The user identified the unit as LD14P. The tested stream matches the SDK's
LD14 processing profile (~2300 measurements/s), rather than its LD14P profile
(4000 measurements/s). At 115200, the LD14P parser accepts packet CRC but its
angle-span check drops measurements: a sample spans about 10.31 degrees at
2160 degrees/s, exceeding that profile's approximately 9.72-degree tolerance.
Selecting the existing LDLiDAR_LD14 profile fixes scan assembly without
patching the parser. The physical product revision/label has not been
independently verified; this is a verified stream configuration.

Official [D200/LD14P documentation](https://www.waveshare.com/wiki/D200_LiDAR_Kit)
specifies 230400; [LD14 documentation](https://www.waveshare.com/wiki/Triangulation_LiDAR_LD14)
specifies 115200. Do not assume these local defaults suit every D200 kit.
Profile and baudrate remain configurable for a differently verified unit.

## Files changed for this integration

- amr_hardware/launch/real_lidar.launch.py: driver-only launch, verified local
  defaults, configurable port/profile/baud/frame, system time, optional RViz
  and measured mount TF. Refuses startup if /scan already has a publisher.
- amr_hardware/config/real_lidar.rviz: bench view fixed to the LiDAR frame,
  best-effort subscription, no navigation tools.
- amr_hardware/setup.py and package.xml: install config and declare dependencies.
- amr_hardware/test/test_real_lidar_launch.py: missing/non-finite measurements,
  frame validation, no invented bench TF, duplicate scan guard and cleanup.
- amr_hardware/README.md and this report: evidence and operating commands.
- web_bridge/launch/web_bridge.launch.py: expose use_sim_time so the documented
  physical/simulation commands explicitly choose their clock source.
- Parent .gitmodules and ros2_ws/src/ldlidar_ros2 gitlink: record the driver in
  Windows, matching the dependency already present on Ubuntu.
- patches/ldlidar-sdk-pthread.patch: preserve the pre-existing Ubuntu SDK fix
  enabling pthread.h; also applied to Windows's nested SDK working tree.

Gazebo, SLAM/Nav2 configuration, Task Executor, FastAPI and React were not
changed by this integration; their earlier working-tree edits were preserved.
Generated build/install/log files are excluded from the published source.

## Build and test

On a fresh checkout only, initialize dependencies and apply the SDK patch once
(the current Windows and Ubuntu SDKs already have it):

```bash
cd ~/SLAM_KLTN
git submodule update --init --recursive
git -C ros2_ws/src/ldlidar_ros2/sdk apply --check "$PWD/patches/ldlidar-sdk-pthread.patch"
git -C ros2_ws/src/ldlidar_ros2/sdk apply "$PWD/patches/ldlidar-sdk-pthread.patch"
```

For an already patched SDK, check with git apply --reverse --check instead.
Pinned driver: 0f6101c93db0b4448cbe7a654826adcdee50622f.
Nested SDK: 6148cd3c33ae39adbd7e12faf82567fa8f8e7b0d.
A dirty submodule alone does not preserve the fix for a future clone.

```bash
source /opt/ros/jazzy/setup.bash
cd ~/SLAM_KLTN/ros2_ws
colcon build --symlink-install --packages-select ldlidar_ros2 amr_hardware web_bridge
source install/setup.bash
colcon test --packages-select amr_hardware web_bridge --event-handlers console_direct+
colcon test-result --test-result-base build/amr_hardware
colcon test-result --test-result-base build/web_bridge
```

Actually run: build PASS (3 packages); amr_hardware 22 tests PASS;
web_bridge 6 tests PASS. Live duplicate launch rejected with:
/scan already has a publisher: ldlidar_publisher.

Upstream driver lint remains FAIL: 5 of 8 CTest checks (copyright, cpplint,
flake8, lint_cmake, uncrustify). The aggregate counts 1,075 failures across
CTest summaries and individual lint diagnostics, not hardware tests.
No lint was disabled. Reproduce separately:

```bash
colcon test --packages-select ldlidar_ros2 --event-handlers console_direct+
colcon test-result --test-result-base build/ldlidar_ros2
```

## Run the verified physical unit

Close the Windows viewer. In VMware choose CP2102 and Connect (Disconnect
from host). Use a login session with dialout membership; no sudo ROS or
chmod 777. Stop Gazebo and any previous physical LiDAR launch first.

```bash
source /opt/ros/jazzy/setup.bash
source ~/SLAM_KLTN/ros2_ws/install/setup.bash
ls -l /dev/serial/by-id/
ros2 topic info /scan -v
ros2 launch amr_hardware real_lidar.launch.py rviz:=true
```

Before launch expect zero scan publishers (unknown topic is normal).
Defaults: LDLiDAR_LD14, 115200, laser_link, and the stable port
/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0.
Arguments port_name, frame_id, product_name and serial_baudrate can override
these for the actual connected unit.

In another sourced terminal:

```bash
ros2 topic info /scan -v
timeout 15 ros2 topic hz /scan
ros2 topic echo /scan --once --qos-reliability best_effort
```

Expect one publisher, about 6 Hz, laser_link and plausible finite ranges.
Timeout exit 124 is normal after 15 seconds. RViz should show green points;
Fixed Frame laser_link needs no invented robot TF.

If the existing backend is not already running, start in its own terminal:

```bash
cd ~/SLAM_KLTN/web/backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another sourced terminal:

```bash
ros2 launch web_bridge web_bridge.launch.py use_sim_time:=false
```

Then check:

```bash
curl -fsS http://127.0.0.1:8000/api/ros/state
```

Expect bridge_online=true, lidar_online=true, nonzero scan_rate_hz and fresh
last_scan_age_ms. tf_available=false, slam_online=false and map_status=WAITING
are correct for a stand-alone LiDAR.

## Physical mount and return to Gazebo

No physical mount measurements have been supplied. Default publish_mount_tf=false
publishes no TF. Once all measurements are known, supply:
publish_mount_tf:=true x:=... y:=... z:=... roll:=... pitch:=... yaw:=...
Use metres and radians; missing/non-finite measurements are rejected. Keep
the option false if a URDF or another node already owns this transform.
Neither the upstream viewer's z=0.18 m nor the Gazebo mount is a measurement.

The duplicate-publisher check is a startup graph snapshot, not a lock against
future processes. Do not start Gazebo/another driver afterwards on the same
ROS domain. Each TF and /scan must have only one authority.

Stop the physical launch and system-time Web Bridge with Ctrl-C, then:

```bash
ros2 topic info /scan -v
ros2 launch amr_sim simulation.launch.py vm_compat:=true
```

In another sourced terminal:

```bash
ros2 launch web_bridge web_bridge.launch.py use_sim_time:=true
```

The agent's current background sessions have PID files:
/tmp/d200_real_launch.pid, /tmp/d200_web_bridge.pid, /tmp/d200_backend.pid.
Inspect each PID with ps -fp PID before stopping the matching process;
a stale PID file does not prove process identity. The normal foreground
launches above stop with Ctrl-C.

## Still required before physical SLAM/Nav2

Measured base_link -> laser_link; calibrated physical encoders/wheel geometry;
real /odom and dynamic odom -> base_link; then SLAM's map -> odom, with system
time throughout. Existing consumers already use /scan and map/odom/base_link.
Validate footprint, scan orientation, timing and stopping behavior before a
separately authorized navigation test. Physical TF and real SLAM/Nav2 remain
NOT VERIFIED. No fake odometry was used.
