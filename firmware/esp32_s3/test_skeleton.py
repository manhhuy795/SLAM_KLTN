"""Compile/run the actual .ino with host stubs; NOT an ESP32 build or hardware test."""

from pathlib import Path
import subprocess
import tempfile


ARDUINO_STUB = r"""
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
using std::min;
using std::isfinite;
#define IRAM_ATTR
#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define CHANGE 3
using portMUX_TYPE = int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL_ISR(p) ((void)(p))
#define portEXIT_CRITICAL_ISR(p) ((void)(p))
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
uint32_t testNow = 0;
int stopWrites = 0;
uint32_t millis() { return testNow; }
void pinMode(int, int) {}
void digitalWrite(int, int) {}
int digitalRead(int) { return 0; }
int digitalPinToInterrupt(int pin) { return pin; }
void attachInterrupt(int, void (*)(), int) {}
void analogWriteFrequency(int, uint32_t) {}
void analogWrite(int, int duty) { if (duty == 0) ++stopWrites; }
struct TestSerial {
  std::string input, output;
  void begin(uint32_t) {}
  int available() { return input.size(); }
  int read() { int c = input.front(); input.erase(0, 1); return c; }
  int availableForWrite() { return 4096; }
  void write(const uint8_t* data, size_t n) { output.append((const char*)data, n); }
} Serial;
"""

CHECK = r"""
#include <cassert>
#include "sketch.ino"
bool command(const char* text) {
  char line[96];
  snprintf(line, sizeof(line), "%s", text);
  return handleLine(line);
}
int main() {
  setup();
  assert(!pinsConfigured && emergencyStop);
  assert(command("ESTOP,1,0") && !emergencyStop);
  assert(command("VEL,2,0.1,-0.2"));
  for (const char* bad : {"", "VEL,2,,0.1", "VEL,2,nan,0.1",
       "VEL,2,0.1,0.2,extra", "VEL,2,0.9,0", "STOP,4294967296",
       "STOP,-1", "ESTOP,3,2", "VEL,2,0.1,0.2,"}) assert(!command(bad));
  Serial.input = "VEL,2,0.";
  loop();
  Serial.input = "1,0.1\n";
  loop();
  assert(!emergencyStop && inputLength == 0);
  Serial.input = std::string(110, 'x') + "ESTOP,1,0\n";
  loop();
  assert(emergencyStop); // Do not execute a valid suffix of an oversized line.
  assert(command("ESTOP,3,0") && !emergencyStop);
  Serial.input = "bad\n";
  loop();
  assert(emergencyStop);
  pinsConfigured = true; // Only the stub GPIO/PWM implementation runs here.
  lastCommandMs = 10;
  testNow = 511;
  int before = stopWrites;
  loop();
  assert(stopWrites >= before + 2);
  assert(Serial.output.find("ENC,123,") != std::string::npos);
  lastCommandMs = UINT32_MAX - 100;
  testNow = 500; // millis() wrap still times out.
  before = stopWrites;
  loop();
  assert(stopWrites >= before + 2);
  puts("PASS: firmware host parser/framing/watchdog checks (hardware pending)");
}
"""


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="amr-firmware-") as directory:
        root = Path(directory)
        (root / "Arduino.h").write_text(ARDUINO_STUB)
        (root / "esp_system.h").write_text(
            "#pragma once\n#include <cstdint>\nuint32_t esp_random() { return 123; }\n"
        )
        sketch = Path(__file__).parent / "amr_motor_controller/amr_motor_controller.ino"
        (root / "sketch.ino").write_text(sketch.read_text())
        (root / "check.cpp").write_text(CHECK)
        binary = root / "check"
        subprocess.run([
            "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(root), str(root / "check.cpp"), "-o", str(binary),
        ], check=True)
        subprocess.run([str(binary)], check=True)
