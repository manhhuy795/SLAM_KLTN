# ESP32-S3 motor controller skeleton

The Arduino sketch implements protocol v1 documented in
../../ros2_ws/src/amr_hardware/README.md: VEL/STOP/ESTOP and
ENC,boot_id,seq,left_count,right_count,timestamp_ms.

All eight GPIO constants are -1 placeholders; no final pins are assumed.
Startup is E-stopped. Motion PWM is additionally disabled by
ENABLE_OPEN_LOOP_BENCH_TEST=false. This is not a calibrated velocity controller.

Before using ESP32-S3 + GA25-370 motors:

1. Select the exact board, Arduino-ESP32 core and USB CDC/UART transport. Confirm
   Serial maps to the host port and baudrate matches ROS YAML.
2. Select a 12 V motor driver rated for measured stall current. This skeleton
   assumes PWM+DIR per motor: adapt for IN1/IN2/enable if needed. Verify the
   driver's coast/brake truth table and safe enable defaults.
3. Fit a physical E-stop/motor power isolation. Assign GPIO from actual wiring
   and board pinout. Verify encoder voltage levels, pull-ups and grounding.
4. Calibrate motor/encoder signs, decoded counts/revolution and gearbox ratio.
   A-pin CHANGE reads A/B but counts only A edges (x2, not x4).
5. Test with wheels lifted. Open-loop PWM is opt-in for bench tests only.
   Implement/tune encoder closed-loop speed control before autonomous driving.
6. Match host/firmware speed limits and choose PWM frequency from driver specs.
   Measure loaded wheel radius, separation, braking and timeout behaviour.
7. Test unplugged USB, ESP32 reset, ROS shutdown, malformed packets and E-stop
   under load before driving on the floor.

The parser is bounded and discards oversized lines through newline.
Malformed commands latch E-stop. USB output backpressure is checked before
writing to avoid deliberately blocking the motor watchdog. An independent
500 ms watchdog zeros PWM and handles millis wrap. Critical sections protect
encoder snapshots; unsigned counters wrap without signed arithmetic overflow.
Boot IDs from esp_random identify resets, not security/authentication.

PWM API reference:
https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html

Portable parser/watchdog checks (Python 3 + g++):

    cd ~/SLAM_KLTN
    python3 firmware/esp32_s3/test_skeleton.py

This compiles the actual sketch with stub GPIO/Serial/clock calls and checks
parsing, fragmented/oversized input, E-stop, encoder format and watchdog wrap.
**ESP32 target compilation, flashing, electrical behaviour, measured PWM,
encoder accuracy and physical motor tests remain PENDING.**
