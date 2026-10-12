# AMR hardware preparation (Phase 5)

Real mode: /cmd_vel (Twist) -> amr_hardware -> USB Serial -> ESP32-S3 -> motor driver.
Feedback: encoders -> Serial -> amr_hardware -> /odom + TF odom -> base_link.
Gazebo, Nav2, SLAM, Task Executor and Web are unchanged.
**Physical base/motor tests are PENDING.**

Physical LiDAR bench verification is now PASS; physical base/motor tests remain
pending. See [D200_CHECK.md](D200_CHECK.md) for measured results and commands.
Use `ros2 launch amr_hardware real_lidar.launch.py rviz:=true` for the verified
sensor stream (SDK LD14 profile, 115200 baud). This starts no robot base or TF
by default; do not run it alongside Gazebo.

## Serial protocol v1

ASCII, newline terminated, CRLF accepted. Default 115200 baud, 8N1.

| Direction | Packet | Units |
| --- | --- | --- |
| Host -> ESP32 | VEL,seq,left_mps,right_mps | Signed wheel ground speeds in m/s |
| Host -> ESP32 | STOP,seq | Zero PWM |
| Host -> ESP32 | ESTOP,seq,1 | Latch E-stop |
| Host -> ESP32 | ESTOP,seq,0 | Clear; stay stopped until fresh VEL |
| ESP32 -> host | ENC,boot_id,seq,left_count,right_count,timestamp_ms | Counts + MCU uptime |

Every packet ends in newline. Boot ID, sequence and uptime are uint32; counts are
signed int32 with modular wrap. Positive counts mean forward wheel travel.
Firmware generates a random boot ID on startup (reset indicator, not authentication).
Command sequence is diagnostic correlation, not an ACK. Duplicate/out-of-order
encoder sequences are ignored and never refresh the feedback watchdog.

Example feedback: ENC,42,1,0,0,1000 then ENC,42,2,100,100,2000.
These are test values, not measured GA25 specifications.

The host buffers fragmented USB input, limits lines to 128 bytes and consumes
at most 4096 bytes per tick so noise cannot starve the safety timer. Consecutive
malformed lines cause STOP, latched E-stop and reconnect. Boot change, clock
reset or implausible count jump stop the base and re-baseline counts while
preserving accumulated x/y/yaw. Sequence, count and millis wrap are supported.
Firmware must not zero counts without changing boot ID. Motion during connection
loss cannot be reconstructed; verify/relocalize before continuing.

## Geometry, timing and safety

left = v - w*separation/2; right = v + w*separation/2.
Chassis limits apply first, then both wheels scale together if a wheel exceeds
max_wheel_velocity, preserving curvature. Non-finite commands latch STOP.

metres/tick = 2*pi*wheel_radius/(encoder_ticks_per_revolution*gear_ratio).
Odometry uses exact arc integration; speed uses MCU uptime delta. ROS odometry
and TF share a host ROS-clock stamp taken on receipt. There is no MCU/host clock
synchronization in this prototype. Measure USB latency and covariance before
sensor fusion. Safety timers use monotonic wall time even if /clock is absent.

Startup and reconnect always latch E-stop and send STOP. Explicit clear is
accepted only with connected serial and fresh encoder data. No velocity is
replayed. Command timeout sends STOP; encoder timeout/reset, invalid command,
serial write failure and malformed feedback latch E-stop. Shutdown attempts STOP.
Stop the command publisher before clearing a fault.

Firmware must independently stop PWM after 500 ms without a valid command:
host STOP cannot be delivered after USB/host power failure.
Software E-stop does not replace physical E-stop or safe motor-enable circuitry.
Diagnostics reflect host latch/feedback state, not proof that physical PWM stopped.

## Topics and parameters

| Topic | Type | Direction |
| --- | --- | --- |
| /cmd_vel | geometry_msgs/msg/Twist | subscribe, depth 1 |
| /hardware/emergency_stop | std_msgs/msg/Bool | true stop / false clear |
| /odom | nav_msgs/msg/Odometry | publish after two valid samples |
| /tf | tf2_msgs/msg/TFMessage | publish odom -> base_link |
| /hardware/status | diagnostic_msgs/msg/DiagnosticArray | publish every 0.5 s |

Status includes serial connection/error, encoder freshness and last device
timestamp/boot ID, command age, host E-stop/fault, counts, targets and malformed
count. No new service or web endpoint. Parameters are startup-only; restart
after YAML edits (runtime edits are rejected).

| Parameter | Default | Meaning |
| --- | --- | --- |
| wheel_radius | 0.0325 m | Gazebo prototype, calibrate loaded radius |
| wheel_separation | 0.25 m | Gazebo prototype, calibrate track |
| encoder_ticks_per_revolution | 600 | Unmeasured test placeholder, NOT GA25 specification |
| gear_ratio | 1.0 | Multiply motor-shaft decoded ticks by ratio; use 1 for wheel ticks |
| encoder_counter_bits | 32 | 2..32; match firmware signed width |
| max_encoder_ticks_per_second | 20000 | Calibrate plausibility limit |
| max_linear_velocity | 0.22 m/s | Prototype chassis limit |
| max_angular_velocity | 1.0 rad/s | Prototype chassis limit |
| max_wheel_velocity | 0.35 m/s | Must not exceed firmware limit |
| cmd_vel_timeout / encoder_timeout | 0.5 / 0.5 s | Host watchdogs |
| serial_port / baudrate | /dev/ttyACM0 / 115200 | Prefer stable /dev/serial/by-id path |
| reconnect_interval | 1.0 s | Serial retry interval |
| max_malformed_packets | 5 | Consecutive invalid lines |
| cmd_vel_topic / odom_topic | /cmd_vel / /odom | Base topic names |
| odom_frame / base_frame | odom / base_link | Distinct TF frame names |

## Build/test on Ubuntu

    source /opt/ros/jazzy/setup.bash
    cd ~/SLAM_KLTN/ros2_ws
    rosdep install --from-paths src --ignore-src -r -y
    colcon build --symlink-install
    source install/setup.bash
    colcon test --event-handlers console_direct+
    colcon test-result --verbose
    python3 ~/SLAM_KLTN/firmware/esp32_s3/test_skeleton.py

ROS tests use real pyserial over Linux pseudo-terminals, inject mock ENC and
receive real Odometry/TF messages. They create a separate ROS domain automatically;
test /cmd_vel cannot reach Gazebo/hardware in the default domain. Firmware checks
require g++ and compile the .ino against host stubs, not the ESP32 target.

## Existing simulation

    source /opt/ros/jazzy/setup.bash
    source ~/SLAM_KLTN/ros2_ws/install/setup.bash
    ros2 launch amr_sim simulation.launch.py vm_compat:=true

Use existing SLAM/Nav2/Web commands. Do not launch amr_hardware on the same domain.

## Real base mode

Stop Gazebo first, configure measured hardware values and flash the configured
firmware. USB permission usually requires dialout group membership (log out/in
after changing groups). In a sourced Ubuntu terminal:

    ros2 launch amr_hardware hardware.launch.py params_file:=$HOME/SLAM_KLTN/ros2_ws/src/amr_hardware/config/hardware.yaml

Without ESP32, the node stays alive, reports serial_connected=false and retries;
it does not invent odometry. In another sourced terminal:

    ros2 topic echo /hardware/status

Only after encoder feedback is online and wheels are safely lifted:

    ros2 topic pub --once /hardware/emergency_stop std_msgs/msg/Bool '{data: false}'
    ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.05}}'

Ctrl-C stops the command publisher; host and firmware watchdogs must stop wheels.

    ros2 topic pub --once /hardware/emergency_stop std_msgs/msg/Bool '{data: true}'
    ros2 topic echo /odom
    ros2 run tf2_ros tf2_echo odom base_link

This launch starts only the base bridge. Physical LiDAR has a separate bench
launch documented in D200_CHECK.md. Real map -> odom, SLAM/Nav2 tuning and
autonomous navigation on hardware remain PENDING.
