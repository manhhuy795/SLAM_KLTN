#include <Arduino.h>
#include <esp_system.h>
#include <errno.h>

// GPIO placeholders: replace only after the physical wiring is known.
constexpr int MOTOR_LEFT_PWM_PIN = -1;
constexpr int MOTOR_LEFT_DIR_PIN = -1;
constexpr int MOTOR_RIGHT_PWM_PIN = -1;
constexpr int MOTOR_RIGHT_DIR_PIN = -1;
constexpr int ENCODER_LEFT_A_PIN = -1;
constexpr int ENCODER_LEFT_B_PIN = -1;
constexpr int ENCODER_RIGHT_A_PIN = -1;
constexpr int ENCODER_RIGHT_B_PIN = -1;

constexpr uint32_t SERIAL_BAUDRATE = 115200;
constexpr uint32_t COMMAND_TIMEOUT_MS = 500;
constexpr uint32_t ENCODER_REPORT_INTERVAL_MS = 50;
constexpr float MAX_WHEEL_SPEED_MPS = 0.35F;  // Prototype; calibrate; match host limit.
constexpr bool ENABLE_OPEN_LOOP_BENCH_TEST = false;  // No calibrated velocity loop yet.
constexpr int LEFT_MOTOR_SIGN = 1;
constexpr int RIGHT_MOTOR_SIGN = 1;
constexpr int LEFT_ENCODER_SIGN = 1;
constexpr int RIGHT_ENCODER_SIGN = 1;
constexpr uint32_t PWM_FREQUENCY_HZ = 20000;  // Verify against driver datasheet.

// Unsigned arithmetic gives defined wrap; wire representation below is int32.
volatile uint32_t leftEncoderCount = 0;
volatile uint32_t rightEncoderCount = 0;
portMUX_TYPE encoderMux = portMUX_INITIALIZER_UNLOCKED;
uint32_t bootId = 0;
uint32_t lastCommandMs = 0;
uint32_t lastEncoderReportMs = 0;
uint32_t encoderSequence = 0;
bool emergencyStop = true;
bool pinsConfigured = false;
char inputLine[96];
size_t inputLength = 0;
bool discardLine = false;

void IRAM_ATTR onLeftEncoder() {
  portENTER_CRITICAL_ISR(&encoderMux);
  leftEncoderCount += LEFT_ENCODER_SIGN * (digitalRead(ENCODER_LEFT_A_PIN) ==
                              digitalRead(ENCODER_LEFT_B_PIN)
                          ? 1
                          : -1);
  portEXIT_CRITICAL_ISR(&encoderMux);
}

void IRAM_ATTR onRightEncoder() {
  portENTER_CRITICAL_ISR(&encoderMux);
  rightEncoderCount += RIGHT_ENCODER_SIGN * (digitalRead(ENCODER_RIGHT_A_PIN) ==
                               digitalRead(ENCODER_RIGHT_B_PIN)
                           ? 1
                           : -1);
  portEXIT_CRITICAL_ISR(&encoderMux);
}

void setMotor(int pwmPin, int dirPin, float targetMps) {
  if (!pinsConfigured || !ENABLE_OPEN_LOOP_BENCH_TEST) return;
  // ponytail: open-loop PWM for lifted-wheel bench tests only; add encoder PID
  // after counts/revolution, driver polarity and motor response are measured.
  const bool forward = targetMps >= 0.0F;
  const float magnitude = min(fabsf(targetMps) / MAX_WHEEL_SPEED_MPS, 1.0F);
  digitalWrite(dirPin, forward ? HIGH : LOW);
  analogWrite(pwmPin, static_cast<int>(255.0F * magnitude));
}

void stopMotors() {
  if (!pinsConfigured) return;
  analogWrite(MOTOR_LEFT_PWM_PIN, 0);
  analogWrite(MOTOR_RIGHT_PWM_PIN, 0);
}

bool parseUnsigned(const char* text, uint32_t& value) {
  if (text == nullptr || *text == '\0') return false;
  for (const char* p = text; *p; ++p) if (*p < '0' || *p > '9') return false;
  char* end = nullptr;
  errno = 0;
  const unsigned long parsed = strtoul(text, &end, 10);
  if (errno == ERANGE || parsed > UINT32_MAX || end == text || *end != '\0') return false;
  value = static_cast<uint32_t>(parsed);
  return true;
}

bool parseFloat(const char* text, float& value) {
  if (text == nullptr) return false;
  char* end = nullptr;
  value = strtof(text, &end);
  return end != text && *end == '\0' && isfinite(value);
}

bool handleLine(char* line) {
  if (*line == '\0' || *line == ',' || line[strlen(line) - 1] == ',' ||
      strstr(line, ",,") != nullptr) return false;
  char* save = nullptr;
  const char* type = strtok_r(line, ",", &save);
  const char* sequenceText = strtok_r(nullptr, ",", &save);
  uint32_t sequence;
  if (!parseUnsigned(sequenceText, sequence)) return false;

  if (strcmp(type, "VEL") == 0) {
    float leftTarget;
    float rightTarget;
    const char* leftText = strtok_r(nullptr, ",", &save);
    const char* rightText = strtok_r(nullptr, ",", &save);
    if (!parseFloat(leftText, leftTarget) ||
        !parseFloat(rightText, rightTarget) ||
        strtok_r(nullptr, ",", &save) != nullptr) {
      return false;
    }
    if (fabsf(leftTarget) > MAX_WHEEL_SPEED_MPS ||
        fabsf(rightTarget) > MAX_WHEEL_SPEED_MPS) return false;
    lastCommandMs = millis();
    if (!emergencyStop) {
      setMotor(MOTOR_LEFT_PWM_PIN, MOTOR_LEFT_DIR_PIN, LEFT_MOTOR_SIGN * leftTarget);
      setMotor(MOTOR_RIGHT_PWM_PIN, MOTOR_RIGHT_DIR_PIN, RIGHT_MOTOR_SIGN * rightTarget);
    }
    return true;
  }

  if (strcmp(type, "STOP") == 0) {
    if (strtok_r(nullptr, ",", &save) == nullptr) {
      stopMotors();
      lastCommandMs = millis();
      return true;
    }
    return false;
  }

  if (strcmp(type, "ESTOP") == 0) {
    const char* activeText = strtok_r(nullptr, ",", &save);
    if (activeText == nullptr || strtok_r(nullptr, ",", &save) != nullptr) {
      return false;
    }
    if (strcmp(activeText, "1") == 0) {
      emergencyStop = true;
      stopMotors();
      return true;
    } else if (strcmp(activeText, "0") == 0) {
      emergencyStop = false;
      stopMotors();  // A fresh VEL command is required after clearing.
      return true;
    }
  }
  return false;
}

void setupPins() {
  pinsConfigured = MOTOR_LEFT_PWM_PIN >= 0 && MOTOR_LEFT_DIR_PIN >= 0 &&
                   MOTOR_RIGHT_PWM_PIN >= 0 && MOTOR_RIGHT_DIR_PIN >= 0 &&
                   ENCODER_LEFT_A_PIN >= 0 && ENCODER_LEFT_B_PIN >= 0 &&
                   ENCODER_RIGHT_A_PIN >= 0 && ENCODER_RIGHT_B_PIN >= 0;
  if (!pinsConfigured) return;

  pinMode(MOTOR_LEFT_PWM_PIN, OUTPUT);
  pinMode(MOTOR_LEFT_DIR_PIN, OUTPUT);
  pinMode(MOTOR_RIGHT_PWM_PIN, OUTPUT);
  pinMode(MOTOR_RIGHT_DIR_PIN, OUTPUT);
  analogWriteFrequency(MOTOR_LEFT_PWM_PIN, PWM_FREQUENCY_HZ);
  analogWriteFrequency(MOTOR_RIGHT_PWM_PIN, PWM_FREQUENCY_HZ);
  pinMode(ENCODER_LEFT_A_PIN, INPUT_PULLUP);
  pinMode(ENCODER_LEFT_B_PIN, INPUT_PULLUP);
  pinMode(ENCODER_RIGHT_A_PIN, INPUT_PULLUP);
  pinMode(ENCODER_RIGHT_B_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(ENCODER_LEFT_A_PIN), onLeftEncoder, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENCODER_RIGHT_A_PIN), onRightEncoder, CHANGE);
  stopMotors();
}

void setup() {
  bootId = esp_random();  // Session identifier, not a security/authentication token.
  Serial.begin(SERIAL_BAUDRATE);
  setupPins();
  lastCommandMs = millis();
}

void loop() {
  if (millis() - lastCommandMs > COMMAND_TIMEOUT_MS) stopMotors();
  // Bounded parser work so a noisy serial sender cannot starve the watchdog.
  for (size_t budget = 0; budget < 256 && Serial.available(); ++budget) {
    const char character = static_cast<char>(Serial.read());
    if (character == '\n') {
      if (!discardLine) {
        inputLine[inputLength] = '\0';
        if (!handleLine(inputLine)) {
          emergencyStop = true;
          stopMotors();
        }
      }
      inputLength = 0;
      discardLine = false;
    } else if (discardLine || character == '\r') {
      continue;
    } else if (character != '\0' && inputLength < sizeof(inputLine) - 1) {
      inputLine[inputLength++] = character;
    } else {
      inputLength = 0;
      discardLine = true;
      emergencyStop = true;
      stopMotors();
    }
  }

  const uint32_t now = millis();
  if (now - lastCommandMs > COMMAND_TIMEOUT_MS) stopMotors();
  if (now - lastEncoderReportMs >= ENCODER_REPORT_INTERVAL_MS) {
    lastEncoderReportMs = now;
    portENTER_CRITICAL(&encoderMux);
    const int32_t left = static_cast<int32_t>(leftEncoderCount);
    const int32_t right = static_cast<int32_t>(rightEncoderCount);
    portEXIT_CRITICAL(&encoderMux);
    char output[96];
    const int length = snprintf(output, sizeof(output), "ENC,%lu,%lu,%ld,%ld,%lu\n",
                  static_cast<unsigned long>(bootId),
                  static_cast<unsigned long>(++encoderSequence),
                  static_cast<long>(left),
                  static_cast<long>(right),
                  static_cast<unsigned long>(now));
    // Do not let USB backpressure delay the independent motor watchdog.
    if (length > 0 && length < static_cast<int>(sizeof(output)) &&
        Serial.availableForWrite() >= length) Serial.write(
            reinterpret_cast<const uint8_t*>(output), length);
  }
}
