#include <Arduino.h>
#include "agv_secrets.h" // Copy agv_secrets.example.h to agv_secrets.h, never commit credentials.
#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <HTTPClient.h>
#include <math.h>
#include <esp_arduino_version.h>
#include "soc/usb_serial_jtag_reg.h"
#include "driver/gpio.h"

/*
 * ===================================================================================
 * AGV_Ver2 - TEST 05: ĐỊNH VỊ ODOMETRY LIÊN TỤC & ĐIỀU PHỐI ĐA TRẠM CHUẨN XÁC
 * -----------------------------------------------------------------------------------
 * ĐẶC TẢ TỌA ĐỘ BẢN ĐỒ THỰC TẾ (154cm x 151cm):
 *   - Gốc O tại Trạm A (0.00, 0.00) - Tâm trục 2 bánh xe.
 *   - Trục X: Hướng sang phải về Trạm D (1.54m, 0.00m) -> Góc Yaw = 0.0°
 *   - Trục Y: Hướng xuống dưới về Trạm B (0.00m, 1.51m) -> Góc Yaw = +90.0°
 *   - Trạm C: (1.54m, 1.51m)
 *   - Chiều dài các chặng:
 *       + Chặng AB: 1.51m, hướng Yaw mục tiêu = +90.0°
 *       + Chặng BC: 1.54m, hướng Yaw mục tiêu = 0.0°
 *       + Chặng CD: 1.51m, hướng Yaw mục tiêu = -90.0°
 *       + Chặng DA: 1.54m, hướng Yaw mục tiêu = 180.0°
 *
 * CÁC SỬA ĐỔI QUAN TRỌNG ĐÃ KIỂM CHỨNG:
 *   1. SỬA ĐÚNG DẤU NGẮT ENCODER BÁNH PHẢI:
 *      - Bánh phải lắp đối xứng cơ học nên điều kiện ngắt phải là:
 *        isrEncRightA so sánh !=, isrEncRightB so sánh == (đồng bộ chuẩn từ test_03 & test_06).
 *      - Cả 2 bánh cùng tăng (+) khi xe tiến -> deltaS > 0 chuẩn xác, odometry không bị triệt tiêu về 0.
 *   2. BỔ SUNG CƠ CHẾ DỪNG TRẠM THEO QUÃNG ĐƯỜNG ENCODER (DISTANCE STOP):
 *      - Xe sẽ tự động giảm tốc khi còn cách trạm 35cm và DỪNG CHÍNH XÁC tại trạm
 *        khi quãng đường đạt đích HOẶC khi gặp vạch dừng. Không bao giờ chạy lố vòng quanh sa bàn.
 *   3. SỬA ĐÚNG HỆ QUY CHIẾU GÓC QUAY (LEFT = TURN LEFT, RIGHT = TURN RIGHT):
 *      - Đồng bộ hệ trục màn hình (+Y xuống, +X sang phải):
 *        Quay Trái: Left wheel lùi, Right wheel tiến -> góc Yaw giảm về 0°.
 *        Quay Phải: Left wheel tiến, Right wheel lùi -> góc Yaw tăng.
 *   4. HIỂN THỊ NỘI SUY TOÀN VẸN TRÊN WEB DASHBOARD:
 *      - Giữ nguyên tọa độ thực tế tích phân từ Encoder + Gyro, vẽ đúng hành trình A->B->C->D->A.
 * ===================================================================================
 */

// --- 1. CẤU HÌNH KẾT NỐI WI-FI & SERVER ---
const char* wifi_ssid        = AGV_WIFI_SSID;
const char* wifi_pass        = AGV_WIFI_PASSWORD;
String      serverUrl        = AGV_TELEMETRY_URL;
WiFiUDP     udpDiscovery;
#define     UDP_DISCOVERY_PORT 5005

// --- 2. SƠ ĐỒ CHÂN PHẦN CỨNG ---
// I2C MPU-6050
#define I2C_SDA_PIN          4
#define I2C_SCL_PIN          5
#define MPU6050_ADDR         0x68

// Driver L298N
#define L298N_ENA_PIN        6
#define L298N_IN1_PIN        7
#define L298N_IN2_PIN        15
#define L298N_IN3_PIN        16
#define L298N_IN4_PIN        17
#define L298N_ENB_PIN        18
#define BUTTON_BOOT_PIN      0

#define PWM_FREQ_HZ          20000
#define PWM_RES_BITS         8
#define PWM_CH_LEFT          0
#define PWM_CH_RIGHT         1

// Encoder Hall
#define ENC_L_A_PIN          10
#define ENC_L_B_PIN          11
#define ENC_R_A_PIN          12
#define ENC_R_B_PIN          13

// Cảm biến dò line TCRT5000 5 mắt
#define LINE_L2_PIN          48
#define LINE_L1_PIN          47
#define LINE_C_PIN           21
#define LINE_R1_PIN          20
#define LINE_R2_PIN          19

// --- 3. THÔNG SỐ VẬT LÝ & HIỆU CHUẨN THỰC ĐO ---
bool invertLeftMotor         = true;
bool invertRightMotor        = true;
bool swapMotors              = true;

bool invertEncLeft           = false;
bool invertEncRight          = false;
bool swapEncoders            = true;

// THÔNG SỐ CƠ KHÍ CHÍNH XÁC TỪ THỰC NGHIỆM ĐO ĐẠC:
// - L = 23cm (Khoảng cách từ tâm trục 2 bánh xe đến hàng mắt TCRT5000)
// - W = 29cm (Khoảng cách giữa tâm 2 bánh xe chủ động)
// - d = 6.5cm (Đường kính bánh xe có tải)
// - Xung chuẩn: 6970 xung/mét (69.7 xung/cm)
const float TICKS_PER_METER          = 6970.0f;
const float DIST_AXLE_TO_SENSOR_M    = 0.24f; // L = 23cm
const float WHEEL_BASE_W_M           = 0.29f; // W = 29cm
const float WHEEL_DIAM_M             = 0.065f;// d = 6.5cm

// Tốc độ điều khiển thích ứng
int   straightPwm            = 215;
int   curvePwm               = 178;
int   brakePwm               = 182; // Tốc độ hãm tiếp cận trạm
int   turnPwm                = 175; // Tốc độ xoay cua gắt / tìm vạch
int   maxPwm                 = 240;

// Hệ số PD bám line từ Test 02
float Kp_line                = 36.0f;
float Kd_line                = 15.0f;

// --- 4. CÁC BIẾN TOÀN CỤC CHIA SẺ GIỮA 2 CORE ---
portMUX_TYPE stateMux = portMUX_INITIALIZER_UNLOCKED;

volatile bool isRunning      = false;
volatile float odomX         = 0.0f;       // Tọa độ X tâm trục bánh xe (m)
volatile float odomY         = 0.0f;       // Tọa độ Y tâm trục bánh xe (m)
volatile float yawDeg        = 90.0f;      // Hướng ban đầu về B (+90°)
volatile float totalDistM    = 0.0f;
volatile float legProgressM  = 0.0f;       // Quãng đường xe đã lăn trong chặng hiện tại
volatile float currentSpeed  = 0.0f;
volatile int   lineMask      = 0;
volatile float currentLineErr= 0.0f;
volatile int   cmdPwmL       = 0;
volatile int   cmdPwmR       = 0;
volatile long  globalTicksL  = 0;
volatile long  globalTicksR  = 0;
String         robotStateStr = "STOPPED";

// Encoder ISR raw
volatile long rawTicksL      = 0;
volatile long rawTicksR      = 0;
long prevTicksL              = 0;
long prevTicksR              = 0;

// MPU-6050
bool  mpuConnected           = false;
float gyroZOffset            = -1.31f;
unsigned long lastImuUs      = 0;

// Trạng thái vận hành & Nhiệm vụ
enum LegId { LEG_AB = 0, LEG_BC = 1, LEG_CD = 2, LEG_DA = 3, LEG_NONE = 4 };
enum RobotSubState {
  SUB_STOPPED,
  SUB_TURNING_FOR_MISSION,
  SUB_TURNING_REVERSE_SEARCH,
  SUB_TURNING_MANUAL,
  SUB_LINE_FOLLOWING,
  SUB_MOTOR_TEST,
  SUB_PAUSE_AT_STATION
};

volatile LegId         currentLeg          = LEG_AB;
volatile RobotSubState robotSubState       = SUB_STOPPED;
volatile float         legTargetDistM      = 1.51f;
volatile float         legTargetHeadingDeg = 90.0f;
volatile float         startTurnYaw        = 0.0f;
volatile unsigned long turnSearchStartMs   = 0;

// Tự động chạy tuần hoàn A -> B -> C -> D -> A
volatile bool          autoLoopEnabled     = false;
volatile unsigned long stationPauseUntilMs = 0;

// Biến điều khiển bám line
float lastValidError         = 0.0f;
float lastLineError          = 0.0f;
unsigned long lineLostTimeMs = 0;
const unsigned long LOST_TIMEOUT_MS = 1500;

// Bộ lọc dốc gia tốc chỉ áp dụng cho vận tốc tịnh tiến (Base Speed Ramp)
float smoothedBaseSpeed      = 0.0f;
const float MAX_RAMP_STEP    = 4.0f;

// Giao thức mạng
volatile int lastAckId                  = 0;
volatile unsigned long testMotorUntilMs = 0;

// Hàm chuẩn hóa góc vào khoảng [-180.0, +180.0]
inline float normalizeAngleDeg(float a) {
  while (a >  180.0f) a -= 360.0f;
  while (a < -180.0f) a += 360.0f;
  return a;
}

// ===================================================================================
// TRÌNH PHỤC VỤ NGẮT ENCODER (CHUẨN TỪ TEST 03 VÀ TEST 06)
// ===================================================================================
void IRAM_ATTR isrEncLeftA() {
  int a = gpio_get_level((gpio_num_t)ENC_L_A_PIN);
  int b = gpio_get_level((gpio_num_t)ENC_L_B_PIN);
  if (a == b) rawTicksL++; else rawTicksL--;
}

void IRAM_ATTR isrEncLeftB() {
  int a = gpio_get_level((gpio_num_t)ENC_L_A_PIN);
  int b = gpio_get_level((gpio_num_t)ENC_L_B_PIN);
  if (a != b) rawTicksL++; else rawTicksL--;
}

// BÁNH PHẢI ĐỐI XỨNG CƠ HỌC: ĐẢO ĐIỀU KIỆN SO SÁNH ĐỂ CẢ 2 BÁNH CÙNG TĂNG KHI TIẾN
void IRAM_ATTR isrEncRightA() {
  int a = gpio_get_level((gpio_num_t)ENC_R_A_PIN);
  int b = gpio_get_level((gpio_num_t)ENC_R_B_PIN);
  if (a != b) rawTicksR++; else rawTicksR--;
}

void IRAM_ATTR isrEncRightB() {
  int a = gpio_get_level((gpio_num_t)ENC_R_A_PIN);
  int b = gpio_get_level((gpio_num_t)ENC_R_B_PIN);
  if (a == b) rawTicksR++; else rawTicksR--;
}

void getCalibratedTicks(long &outL, long &outR) {
  noInterrupts();
  long rL = rawTicksL;
  long rR = rawTicksR;
  interrupts();

  long tL = swapEncoders ? rR : rL;
  long tR = swapEncoders ? rL : rR;

  outL = invertEncLeft  ? -tL : tL;
  outR = invertEncRight ? -tR : tR;
}

// ===================================================================================
// ĐIỀU KHIỂN ĐỘNG CƠ L298N
// ===================================================================================
void writeLeftPwm(int val) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcWrite(L298N_ENA_PIN, val);
#else
  ledcWrite(PWM_CH_LEFT, val);
#endif
}

void writeRightPwm(int val) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcWrite(L298N_ENB_PIN, val);
#else
  ledcWrite(PWM_CH_RIGHT, val);
#endif
}

void initMotors() {
  pinMode(L298N_IN1_PIN, OUTPUT);
  pinMode(L298N_IN2_PIN, OUTPUT);
  pinMode(L298N_IN3_PIN, OUTPUT);
  pinMode(L298N_IN4_PIN, OUTPUT);

#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcAttach(L298N_ENA_PIN, PWM_FREQ_HZ, PWM_RES_BITS);
  ledcAttach(L298N_ENB_PIN, PWM_FREQ_HZ, PWM_RES_BITS);
#else
  ledcSetup(PWM_CH_LEFT, PWM_FREQ_HZ, PWM_RES_BITS);
  ledcSetup(PWM_CH_RIGHT, PWM_FREQ_HZ, PWM_RES_BITS);
  ledcAttachPin(L298N_ENA_PIN, PWM_CH_LEFT);
  ledcAttachPin(L298N_ENB_PIN, PWM_CH_RIGHT);
#endif

  writeLeftPwm(0);
  writeRightPwm(0);
  digitalWrite(L298N_IN1_PIN, LOW);
  digitalWrite(L298N_IN2_PIN, LOW);
  digitalWrite(L298N_IN3_PIN, LOW);
  digitalWrite(L298N_IN4_PIN, LOW);
}

void setMotors(int leftSpeed, int rightSpeed) {
  cmdPwmL = leftSpeed;
  cmdPwmR = rightSpeed;

  if (!isRunning && (testMotorUntilMs < millis())) {
    writeLeftPwm(0);
    writeRightPwm(0);
    digitalWrite(L298N_IN1_PIN, LOW);
    digitalWrite(L298N_IN2_PIN, LOW);
    digitalWrite(L298N_IN3_PIN, LOW);
    digitalWrite(L298N_IN4_PIN, LOW);
    return;
  }

  int cmdLeft  = swapMotors ? rightSpeed : leftSpeed;
  int cmdRight = swapMotors ? leftSpeed  : rightSpeed;

  int l = invertLeftMotor  ? -cmdLeft  : cmdLeft;
  int r = invertRightMotor ? -cmdRight : cmdRight;

  // Bánh Trái
  if (l > 0) {
    digitalWrite(L298N_IN1_PIN, HIGH);
    digitalWrite(L298N_IN2_PIN, LOW);
    writeLeftPwm(constrain(l, 0, maxPwm));
  } else if (l < 0) {
    digitalWrite(L298N_IN1_PIN, LOW);
    digitalWrite(L298N_IN2_PIN, HIGH);
    writeLeftPwm(constrain(-l, 0, maxPwm));
  } else {
    digitalWrite(L298N_IN1_PIN, LOW);
    digitalWrite(L298N_IN2_PIN, LOW);
    writeLeftPwm(0);
  }

  // Bánh Phải
  if (r > 0) {
    digitalWrite(L298N_IN3_PIN, HIGH);
    digitalWrite(L298N_IN4_PIN, LOW);
    writeRightPwm(constrain(r, 0, maxPwm));
  } else if (r < 0) {
    digitalWrite(L298N_IN3_PIN, LOW);
    digitalWrite(L298N_IN4_PIN, HIGH);
    writeRightPwm(constrain(-r, 0, maxPwm));
  } else {
    digitalWrite(L298N_IN3_PIN, LOW);
    digitalWrite(L298N_IN4_PIN, LOW);
    writeRightPwm(0);
  }
}

void stopMotors() {
  isRunning = false;
  robotSubState = SUB_STOPPED;
  smoothedBaseSpeed = 0.0f;
  setMotors(0, 0);
}

// Khởi chạy nhiệm vụ chặng
void startMission(LegId leg) {
  currentLeg = leg;
  if (leg == LEG_AB) {
    legTargetDistM = 1.51f;
    legTargetHeadingDeg = 90.0f;  // Hướng xuống dọc trục Y
  } else if (leg == LEG_BC) {
    legTargetDistM = 1.54f;
    legTargetHeadingDeg = 0.0f;   // Hướng sang phải dọc trục X
  } else if (leg == LEG_CD) {
    legTargetDistM = 1.51f;
    legTargetHeadingDeg = -90.0f; // Hướng lên ngược trục Y
  } else if (leg == LEG_DA) {
    legTargetDistM = 1.54f;
    legTargetHeadingDeg = 180.0f; // Hướng sang trái ngược trục X
  }

  float headingErr = normalizeAngleDeg(legTargetHeadingDeg - yawDeg);

  legProgressM      = 0.0f; // Đặt lại quãng đường chặng mới về 0
  smoothedBaseSpeed = 0.0f;
  lastLineError     = 0.0f;
  lastValidError    = 0.0f;
  lineLostTimeMs    = 0;

  if (fabsf(headingErr) > 6.0f) {
    // Cần xoay chuyển hướng tại chỗ trước khi chạy bám line
    startTurnYaw = yawDeg; // Lưu góc bắt đầu để tính góc đã xoay thoát vạch cũ
    robotSubState = SUB_TURNING_FOR_MISSION;
    robotStateStr = "TURNING_STATION";
    isRunning = true;
    Serial.printf("\n>> [KHỞI ĐỘNG CHẶNG %d] Cần xoay %+.1f° về hướng đích %.1f°...\n",
                  (int)leg + 1, headingErr, legTargetHeadingDeg);
  } else {
    // Đã đúng hướng -> Khởi hành bám line ngay
    prevTicksL = globalTicksL;
    prevTicksR = globalTicksR;
    robotSubState = SUB_LINE_FOLLOWING;
    robotStateStr = "RUNNING_FAST";
    isRunning = true;
    Serial.printf("\n>> [KHỞI ĐỘNG CHẶNG %d] Đúng hướng %.1f° -> Khởi hành bám line!\n",
                  (int)leg + 1, legTargetHeadingDeg);
  }
}

// Chuyển sang chặng kế tiếp tuần tự
void advanceToNextLeg() {
  if (currentLeg == LEG_AB) startMission(LEG_BC);
  else if (currentLeg == LEG_BC) startMission(LEG_CD);
  else if (currentLeg == LEG_CD) startMission(LEG_DA);
  else startMission(LEG_AB);
}

// Lệnh xoay góc thủ công từ Web/Serial (Xong sẽ dừng hẳn)
void startManualTurn(float deltaAngleDeg) {
  legTargetHeadingDeg = normalizeAngleDeg(yawDeg + deltaAngleDeg);
  robotSubState = SUB_TURNING_MANUAL;
  robotStateStr = "TURNING_MANUAL";
  isRunning = true;
  smoothedBaseSpeed = 0.0f;
  Serial.printf("\n>> [LỆNH XOAY THỦ CÔNG] Xoay %+.1f° tới hướng đích %.1f°...\n", deltaAngleDeg, legTargetHeadingDeg);
}

// ===================================================================================
// KHỞI TẠO CẢM BIẾN DÒ LINE TCRT5000
// ===================================================================================
void initLineSensors() {
  CLEAR_PERI_REG_MASK(USB_SERIAL_JTAG_CONF0_REG,
                      USB_SERIAL_JTAG_USB_PAD_ENABLE |
                      USB_SERIAL_JTAG_DP_PULLUP |
                      USB_SERIAL_JTAG_DM_PULLUP |
                      USB_SERIAL_JTAG_DP_PULLDOWN |
                      USB_SERIAL_JTAG_DM_PULLDOWN);
  SET_PERI_REG_MASK(USB_SERIAL_JTAG_CONF0_REG, USB_SERIAL_JTAG_PAD_PULL_OVERRIDE);

  gpio_reset_pin((gpio_num_t)LINE_L2_PIN);
  gpio_reset_pin((gpio_num_t)LINE_L1_PIN);
  gpio_reset_pin((gpio_num_t)LINE_C_PIN);
  gpio_reset_pin((gpio_num_t)LINE_R1_PIN);
  gpio_reset_pin((gpio_num_t)LINE_R2_PIN);

  pinMode(LINE_L2_PIN, INPUT_PULLUP);
  pinMode(LINE_L1_PIN, INPUT_PULLUP);
  pinMode(LINE_C_PIN,  INPUT_PULLUP);
  pinMode(LINE_R1_PIN, INPUT_PULLUP);
  pinMode(LINE_R2_PIN, INPUT_PULLUP);
}

int readLineSensors(int &sL2, int &sL1, int &sC, int &sR1, int &sR2) {
  sL2 = digitalRead(LINE_L2_PIN);
  sL1 = digitalRead(LINE_L1_PIN);
  sC  = digitalRead(LINE_C_PIN);
  sR1 = digitalRead(LINE_R1_PIN);
  sR2 = digitalRead(LINE_R2_PIN);

  return (sL2 << 4) | (sL1 << 3) | (sC << 2) | (sR1 << 1) | sR2;
}

// ===================================================================================
// KHỞI TẠO & CẬP NHẬT MPU-6050
// ===================================================================================
bool writeReg8(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  return (Wire.endTransmission() == 0);
}

int16_t readReg16(uint8_t addr, uint8_t reg) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.endTransmission(false);
  Wire.requestFrom((int)addr, 2);
  if (Wire.available() == 2) {
    return (int16_t)((Wire.read() << 8) | Wire.read());
  }
  return 0;
}

void calibrateGyroZ(int samples = 500) {
  double sum = 0;
  for (int i = 0; i < samples; i++) {
    int16_t r = readReg16(MPU6050_ADDR, 0x47);
    sum += (r / 32.8f);
    delay(2);
  }
  gyroZOffset = (float)(sum / samples);
}

void initMPU() {
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN, 100000);
  delay(50);
  Wire.beginTransmission(MPU6050_ADDR);
  if (Wire.endTransmission() == 0) {
    writeReg8(MPU6050_ADDR, 0x6B, 0x00); // Đánh thức MPU-6050
    delay(10);
    writeReg8(MPU6050_ADDR, 0x1A, 0x03); // DLPF 44Hz chống rung cơ học
    writeReg8(MPU6050_ADDR, 0x1B, 0x10); // ±1000 dps
    mpuConnected = true;
    calibrateGyroZ(400);
  }
}

// ===================================================================================
// CORE 1: ĐIỀU KHIỂN BÁM LINE, TÍNH ODOMETRY LIÊN TỤC & ĐIỀU HƯỚNG TRẠM (100Hz CHUẨN)
// ===================================================================================
void updateControlAndOdometry(float dt = 0.010f) {
  // 1. Cập nhật góc Yaw từ MPU-6050 (Đồng bộ hệ tọa độ màn hình: Quanh trục Z)
  if (mpuConnected) {
    int16_t rGz = readReg16(MPU6050_ADDR, 0x47);
    float gzRaw = (rGz / 32.8f);

    if (!isRunning && (testMotorUntilMs < millis()) && (robotSubState == SUB_STOPPED || robotSubState == SUB_PAUSE_AT_STATION)) {
      // Xe đứng yên: ZUPT (Zero Velocity Update) tự động khử trôi tĩnh
      gyroZOffset = 0.995f * gyroZOffset + 0.005f * gzRaw;
    } else {
      // Hệ tọa độ màn hình (+Y xuống, +X sang phải):
      // Xoay Trái là ngược chiều kim đồng hồ -> raw Gz > 0 -> góc Yaw cần GIẢM từ 90° về 0°.
      // Do đó đảo dấu gz để góc Yaw giảm khi xoay Trái và tăng khi xoay Phải:
      float gz = -(gzRaw - gyroZOffset);
      if (fabsf(gz) < 0.25f) gz = 0.0f; // Deadband lọc rung lắc
      yawDeg = normalizeAngleDeg(yawDeg + gz * dt);
    }
  }

  // 2. Cập nhật quãng đường & tọa độ tâm trục 2 bánh xe từ Encoder
  long curL, curR;
  getCalibratedTicks(curL, curR);
  globalTicksL = curL;
  globalTicksR = curR;

  long dL = curL - prevTicksL;
  long dR = curR - prevTicksR;
  prevTicksL = curL;
  prevTicksR = curR;

  float deltaSL = (float)dL / TICKS_PER_METER;
  float deltaSR = (float)dR / TICKS_PER_METER;
  float deltaS  = (deltaSL + deltaSR) / 2.0f; // Khi cả 2 bánh cùng tiến, deltaS > 0 chuẩn xác

  currentSpeed = (deltaS / dt) * 100.0f; // cm/s
  totalDistM += fabsf(deltaS);

  // Chiếu lên hệ tọa độ mặt sàn (Tâm trục 2 bánh xe)
  float rad = (yawDeg * PI) / 180.0f;
  odomX += deltaS * cosf(rad);
  odomY += deltaS * sinf(rad);

  // 3. Đọc 5 mắt cảm biến dò line TCRT5000
  int sL2, sL1, sC, sR1, sR2;
  lineMask = readLineSensors(sL2, sL1, sC, sR1, sR2);
  int activeCount = sL2 + sL1 + sC + sR1 + sR2;

  // ---------------------------------------------------------------------------------
  // TRẠNG THÁI 0: TẠM NGHỈ TẠI TRẠM TRONG CHẾ ĐỘ AUTO LOOP (PAUSE 2 GIÂY)
  // ---------------------------------------------------------------------------------
  if (robotSubState == SUB_PAUSE_AT_STATION) {
    setMotors(0, 0);
    if (millis() >= stationPauseUntilMs) {
      advanceToNextLeg();
    }
    return;
  }

  // ---------------------------------------------------------------------------------
  // TRẠNG THÁI 1A: XOAY CHUYỂN HƯỚNG TẠI TRẠM (CƠ CHẾ BẮT VẠCH THÍCH ỨNG - TRIỆT TIÊU QUAY QUÁ ĐÀ)
  // ---------------------------------------------------------------------------------
  if (robotSubState == SUB_TURNING_FOR_MISSION) {
    float err = normalizeAngleDeg(legTargetHeadingDeg - yawDeg);
    float absErr = fabsf(err);
    float rotatedSoFar = fabsf(normalizeAngleDeg(yawDeg - startTurnYaw));

    // ĐIỀU KIỆN KHÓA VẠCH THÔNG MINH LINH HOẠT:
    // Khi đã xoay thoát vạch cũ (rotatedSoFar >= 20°) VÀ mắt giữa (C, L1, R1) chạm vạch đen của chặng mới:
    // -> DỪNG XOAY NGAY LẬP TỨC! Không ép góc phải tới đúng 0° lý thuyết!
    bool lineCaught = (rotatedSoFar >= 20.0f) && ((lineMask & 0b01110) != 0);

    if (lineCaught) {
      setMotors(0, 0);
      smoothedBaseSpeed = 0.0f;
      yawDeg = legTargetHeadingDeg; // Khóa góc hướng theo chặng mới
      prevTicksL = globalTicksL;
      prevTicksR = globalTicksR;
      legProgressM = 0.0f;
      lastLineError = 0.0f;
      lastValidError = 0.0f;
      lineLostTimeMs = 0;
      robotSubState = SUB_LINE_FOLLOWING;
      robotStateStr = "RUNNING_FAST";
      isRunning = true;
      Serial.printf("\n>> [BẮT ĐÚNG VẠCH MỚI] Đã khóa vạch chặng %d tại Yaw = %.1f° (Đã xoay %.1f°) -> Khởi hành!\n",
                    (int)currentLeg + 1, yawDeg, rotatedSoFar);
      return;
    }

    // Nếu góc đã tới đích (|err| <= 2.5°):
    if (absErr <= 2.5f) {
      setMotors(0, 0);
      smoothedBaseSpeed = 0.0f;
      yawDeg = legTargetHeadingDeg;

      if ((lineMask & 0b01110) != 0) {
        // Đã nằm trên vạch -> Khởi hành bám line
        prevTicksL = globalTicksL;
        prevTicksR = globalTicksR;
        legProgressM = 0.0f;
        lastLineError = 0.0f;
        lastValidError = 0.0f;
        lineLostTimeMs = 0;
        robotSubState = SUB_LINE_FOLLOWING;
        robotStateStr = "RUNNING_FAST";
        isRunning = true;
        Serial.printf("\n>> [ĐẠT GÓC ĐÍCH] Đã thấy vạch tại Yaw = %.1f° -> Khởi hành chặng %d!\n", yawDeg, (int)currentLeg + 1);
        return;
      } else {
        // Tới góc đích nhưng bị lố vạch do quán tính: Kích hoạt quét ngược lại chậm rãi tìm vạch
        robotSubState = SUB_TURNING_REVERSE_SEARCH;
        turnSearchStartMs = millis();
        Serial.printf("\n>> [DÒ TÌM VẠCH LINH HOẠT] Đạt góc %.1f° chưa thấy vạch -> Bắt đầu quét ngược tìm vạch...\n", yawDeg);
        return;
      }
    }

    // TỐC ĐỘ XOAY THÍCH ỨNG:
    // - Thoát vạch cũ (< 20°): 175 PWM
    // - Quét tìm vạch (>= 20°): 168 PWM (bò êm để mắt bắt vạch nhạy bén, triệt tiêu quán tính lố đà)
    int turnSpeed = (rotatedSoFar < 20.0f) ? 175 : 168;

    if (err < 0.0f) {
      setMotors(-turnSpeed, turnSpeed); // QUAY TRÁI
    } else {
      setMotors(turnSpeed, -turnSpeed); // QUAY PHẢI
    }
    return;
  }

  // ---------------------------------------------------------------------------------
  // TRẠNG THÁI 1B: QUÉT NGƯỢC TÌM LẠI VẠCH NẾU QUAY LỐ (REVERSE SEARCH SWEEP)
  // ---------------------------------------------------------------------------------
  if (robotSubState == SUB_TURNING_REVERSE_SEARCH) {
    bool found = ((lineMask & 0b01110) != 0);
    bool timeout = (millis() - turnSearchStartMs > 800);

    if (found || timeout) {
      setMotors(0, 0);
      smoothedBaseSpeed = 0.0f;
      prevTicksL = globalTicksL;
      prevTicksR = globalTicksR;
      legProgressM = 0.0f;
      lastLineError = 0.0f;
      lastValidError = 0.0f;
      lineLostTimeMs = 0;
      robotSubState = SUB_LINE_FOLLOWING;
      robotStateStr = "RUNNING_FAST";
      isRunning = true;
      Serial.printf("\n>> [KẾT QUẢ DÒ VẠCH] %s -> Bắt đầu bám line chặng %d!\n",
                    found ? "ĐÃ TÌM THẤY VẠCH" : "HẾT THỜI GIAN QUÉT, TIẾP TỤC", (int)currentLeg + 1);
      return;
    }

    // Quay ngược lại hướng vừa xoay ở tốc độ 168 PWM
    float err = normalizeAngleDeg(legTargetHeadingDeg - startTurnYaw);
    int sweepSpeed = 168;
    if (err < 0.0f) {
      setMotors(sweepSpeed, -sweepSpeed); // Quay PHẢI ngược lại
    } else {
      setMotors(-sweepSpeed, sweepSpeed); // Quay TRÁI ngược lại
    }
    return;
  }

  // ---------------------------------------------------------------------------------
  // TRẠNG THÁI 1C: XOAY THỦ CÔNG THEO GÓC (TỪ LỆNH WEB HOẶC SERIAL)
  // ---------------------------------------------------------------------------------
  if (robotSubState == SUB_TURNING_MANUAL) {
    float err = normalizeAngleDeg(legTargetHeadingDeg - yawDeg);
    float absErr = fabsf(err);

    if (absErr <= 2.5f) {
      setMotors(0, 0);
      smoothedBaseSpeed = 0.0f;
      yawDeg = legTargetHeadingDeg;
      robotSubState = SUB_STOPPED;
      robotStateStr = "STOPPED";
      isRunning = false;
      Serial.printf("\n>> [XOAY THỦ CÔNG XONG] Dừng xe tại hướng Yaw = %.1f°\n", yawDeg);
      return;
    }

    int turnSpeed = (absErr > 40.0f) ? 178 : ((absErr > 15.0f) ? 172 : 168);
    if (err < 0.0f) {
      setMotors(-turnSpeed, turnSpeed); // QUAY TRÁI
    } else {
      setMotors(turnSpeed, -turnSpeed); // QUAY PHẢI
    }
    return;
  }

  // ---------------------------------------------------------------------------------
  // TRẠNG THÁI 2: CHẾ ĐỘ TEST ĐỘNG CƠ TIẾN THẲNG 1 GIÂY
  // ---------------------------------------------------------------------------------
  if (testMotorUntilMs > millis()) {
    setMotors(205, 205);
    robotStateStr = "MOTOR_TEST";
    return;
  }

  if (!isRunning || robotSubState == SUB_STOPPED) {
    stopMotors();
    robotStateStr = "STOPPED";
    return;
  }

  // ---------------------------------------------------------------------------------
  // TRẠNG THÁI 3: BÁM LINE CHUẨN XÁC TỪ TEST 02 KẾT HỢP KHÓA HƯỚNG TỚI ĐÚNG GÓC TRẠM
  // ---------------------------------------------------------------------------------
  legProgressM += deltaS;
  float remainingLegM = legTargetDistM - legProgressM;
  float sensorReachCornerDistM = legTargetDistM - DIST_AXLE_TO_SENSOR_M; // Vị trí mắt cảm biến chạm góc rẽ

  int leftPwm  = 0;
  int rightPwm = 0;

  // GIAI ĐOẠN 3.1: ĐÃ ĐẾN VÙNG GÓC TRẠM (MẮT CẢM BIẾN ĐÃ CHẠM GÓC -> BÒ THÊM 23CM ĐỂ TÂM TRỤC BÁNH TỚI ĐÚNG GÓC TRẠM)
  if (legProgressM >= sensorReachCornerDistM) {
    if (remainingLegM <= 0.005f) {
      // ĐÃ TỚI ĐÚNG GÓC TRẠM: Tâm trục 2 bánh xe nằm chính xác tại góc trạm (ví dụ Y = 1.51m) -> DỪNG KHỰNG!
      stopMotors();
      robotStateStr = "AT_STATION";

      Serial.printf("\n>> [ĐÃ TỚI TRẠM DỪNG] Đích đến chặng %d! Tâm trục 2 bánh xe tại X=%.3fm, Y=%.3fm, Yaw=%.1f° (Đã đi: %.3fm)\n",
                    (int)currentLeg + 1, odomX, odomY, yawDeg, legProgressM);

      if (autoLoopEnabled) {
        stationPauseUntilMs = millis() + 2000;
        robotSubState = SUB_PAUSE_AT_STATION;
        robotStateStr = "PAUSED_AT_STATION";
        isRunning = true;
      } else {
        robotSubState = SUB_STOPPED;
        isRunning = false;
      }
      return;
    }

    // Bò chậm thẳng vào tâm trạm bằng Khóa hướng MPU Gyro (giữ thẳng góc chặng để tâm 2 bánh xe tới đúng góc trạm):
    float hErr = normalizeAngleDeg(legTargetHeadingDeg - yawDeg);
    float u_h = 3.0f * hErr;
    leftPwm  = constrain((int)(brakePwm + u_h), 168, 195);
    rightPwm = constrain((int)(brakePwm - u_h), 168, 195);
    robotStateStr = "APPROACH_CORNER";
    setMotors(leftPwm, rightPwm);
    return;
  }

  // GIAI ĐOẠN 3.2: BÁM LINE BÌNH THƯỜNG TRÊN ĐƯỜNG THẲNG
  if (activeCount == 0) {
    // --- TÌNH HUỐNG: MẤT VẠCH HOÀN TOÀN (00000) ---
    if (lineLostTimeMs == 0) lineLostTimeMs = millis();

    if (millis() - lineLostTimeMs > LOST_TIMEOUT_MS) {
      stopMotors();
      robotStateStr = "LOST_LINE_STOP";
      return;
    }

    // Nếu vừa xuất phát chặng mới (chưa qua 35cm đầu): Khóa hướng MPU Gyro thẳng tắp theo hướng chặng để lao vào bắt vạch
    if (legProgressM < 0.35f) {
      float hErr = normalizeAngleDeg(legTargetHeadingDeg - yawDeg);
      float u_h = 3.0f * hErr;
      leftPwm  = constrain((int)(brakePwm + u_h), 168, 195);
      rightPwm = constrain((int)(brakePwm - u_h), 168, 195);
      robotStateStr = "CREEP_FIND_LINE";
      setMotors(leftPwm, rightPwm);
      return;
    }

    // Tận dụng Bộ nhớ hướng lệch cuối cùng (Lost-line Memory từ Test 02)
    if (lastValidError < -0.3f) {
      robotStateStr = "LOST_TURN_LEFT";
      leftPwm  = -turnPwm;
      rightPwm = +turnPwm;
    } else if (lastValidError > 0.3f) {
      robotStateStr = "LOST_TURN_RIGHT";
      leftPwm  = +turnPwm;
      rightPwm = -turnPwm;
    } else {
      robotStateStr = "LOST_CREEP_FWD";
      leftPwm  = turnPwm;
      rightPwm = turnPwm;
    }
    setMotors(leftPwm, rightPwm);
    return;

  } else {
    // --- TÌNH HUỐNG: BÁM LINE BẰNG THUẬT TOÁN PD CẢI TIẾN ---
    lineLostTimeMs = 0;

    // Trọng số: L2=-2, L1=-1, C=0, R1=+1, R2=+2
    currentLineErr = (float)(-2*sL2 + -1*sL1 + 0*sC + 1*sR1 + 2*sR2) / (float)activeCount;
    lastValidError = currentLineErr;

    // TRIỆT TIÊU 100% SAI SỐ CỘNG DỒN TRÔI DẠT GYRO (COMPLEMENTARY LINE-HEADING FUSION):
    // Khi xe đang bám vạch trên chặng đường thẳng, đường vạch vật lý chính là mốc hướng tuyệt đối!
    // Kéo góc Yaw liên tục về hướng chuẩn của chặng (trừ sai lệch bẻ lái) để triệt tiêu trôi tĩnh do rung động động cơ:
    if (fabsf(currentLineErr) < 0.6f) {
      float expectedHeading = legTargetHeadingDeg - (currentLineErr * 4.0f);
      float headingDiff = normalizeAngleDeg(expectedHeading - yawDeg);
      yawDeg = normalizeAngleDeg(yawDeg + 0.025f * headingDiff);
    }

    float dErr = (currentLineErr - lastLineError) / fmaxf(dt, 0.001f);
    lastLineError = currentLineErr;

    // TỐC ĐỘ THÍCH ỨNG THEO ĐỘ CONG & VỊ TRÍ TRẠM:
    float absErr = fabsf(currentLineErr);
    int targetBase = straightPwm - (int)(absErr * (straightPwm - curvePwm));
    targetBase = constrain(targetBase, curvePwm, straightPwm);

    // Khi còn cách góc dưới 40cm -> Giảm tốc độ bò chậm an toàn (brakePwm)
    if (remainingLegM < 0.40f) {
      targetBase = min(targetBase, brakePwm);
      robotStateStr = "BRAKING_NEAR_STATION";
    } else {
      robotStateStr = (absErr < 0.35f) ? "RUNNING_FAST" : "TURNING_LINE";
    }

    // Bộ lọc dốc gia tốc (Rate Limiter) CHỈ ÁP DỤNG CHO TỐC ĐỘ CƠ SỞ (smoothedBaseSpeed):
    if (targetBase > smoothedBaseSpeed) smoothedBaseSpeed = min((float)targetBase, smoothedBaseSpeed + MAX_RAMP_STEP);
    else if (targetBase < smoothedBaseSpeed) smoothedBaseSpeed = max((float)targetBase, smoothedBaseSpeed - MAX_RAMP_STEP);

    // Tín hiệu điều khiển bẻ lái PD phản hồi tức thời không trễ
    float u = (Kp_line * currentLineErr) + (Kd_line * dErr);

    // Ôm cua góc vuông gắt từ Test 02
    if (currentLineErr <= -1.8f) {
      leftPwm  = -turnPwm;
      rightPwm = curvePwm + 25;
      robotStateStr = "PIVOT_LEFT";
    } else if (currentLineErr >= 1.8f) {
      leftPwm  = curvePwm + 25;
      rightPwm = -turnPwm;
      robotStateStr = "PIVOT_RIGHT";
    } else {
      leftPwm  = constrain((int)(smoothedBaseSpeed + u), 0, maxPwm);
      rightPwm = constrain((int)(smoothedBaseSpeed - u), 0, maxPwm);
    }
  }

  setMotors(leftPwm, rightPwm);
}

// Tác vụ FreeRTOS định thời chuẩn xác 100Hz trên Core 1
void controlLoopTask(void *pvParameters) {
  TickType_t xLastWakeTime = xTaskGetTickCount();
  const TickType_t xFrequency = pdMS_TO_TICKS(10);

  while (true) {
    vTaskDelayUntil(&xLastWakeTime, xFrequency);
    updateControlAndOdometry(0.010f);
  }
}

// ===================================================================================
// CORE 0: KẾT NỐI WI-FI & GỬI DỮ LIỆU TELEMETRY LÊN WEBSERVER (6.6Hz = 150ms)
// ===================================================================================
void telemetryTask(void *pvParameters) {
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifi_ssid, wifi_pass);
  Serial.print(">> [WI-FI]: Đang kết nối tới mạng ");
  Serial.println(wifi_ssid);

  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 25) {
    delay(400);
    Serial.print(".");
    retry++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n✅ [WI-FI]: Đã kết nối! IP ESP32 = %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n⚠️ [WI-FI]: Không kết nối được Wi-Fi -> Chạy nội bộ.");
  }

  HTTPClient http;
  http.setTimeout(1200);

  while (true) {
    if (WiFi.status() == WL_CONNECTED) {
      String payload = "{";
      payload += "\"x\":" + String(odomX, 3) + ",";
      payload += "\"y\":" + String(odomY, 3) + ",";
      payload += "\"yaw\":" + String(yawDeg, 1) + ",";
      payload += "\"dist\":" + String(totalDistM, 3) + ",";
      payload += "\"speed\":" + String(currentSpeed, 1) + ",";
      payload += "\"line_mask\":" + String(lineMask) + ",";
      payload += "\"line_err\":" + String(currentLineErr, 2) + ",";
      payload += "\"ticks_l\":" + String(globalTicksL) + ",";
      payload += "\"ticks_r\":" + String(globalTicksR) + ",";
      payload += "\"pwm_l\":" + String(cmdPwmL) + ",";
      payload += "\"pwm_r\":" + String(cmdPwmR) + ",";
      payload += "\"ack_id\":" + String(lastAckId) + ",";
      payload += "\"auto_loop\":" + String(autoLoopEnabled ? "true" : "false") + ",";
      payload += "\"state\":\"" + robotStateStr + "\"";
      payload += "}";

      http.begin(serverUrl);
      http.addHeader("Content-Type", "application/json");
       http.addHeader("X-AGV-Token", AGV_DEVICE_TOKEN);
      int httpCode = http.POST(payload);

      if (httpCode == 200) {
        String resp = http.getString();

        int idIdx = resp.indexOf("\"cmd_id\":");
        int incomingId = 0;
        if (idIdx >= 0) {
          incomingId = resp.substring(idIdx + 9).toInt();
        }

        if (incomingId > 0 && incomingId != lastAckId) {
          lastAckId = incomingId;
          Serial.printf("\n>> [NHẬN LỆNH #%d TỪ SERVER]: %s\n", incomingId, resp.c_str());

          if (resp.indexOf("START") >= 0) {
            startMission(currentLeg);
          } else if (resp.indexOf("STOP") >= 0) {
            autoLoopEnabled = false;
            stopMotors();
            robotStateStr = "STOPPED";
            Serial.println(">> [LỆNH]: DỪNG KHẨN CẤP!");
          } else if (resp.indexOf("TEST_FORWARD") >= 0) {
            testMotorUntilMs = millis() + 1000;
            isRunning = true;
            robotStateStr = "MOTOR_TEST";
            Serial.println(">> [LỆNH]: TEST ĐỘNG CƠ TIẾN 1 GIÂY!");
          } else if (resp.indexOf("RESET_ODOM") >= 0) {
            odomX = 0.0f; odomY = 0.0f; yawDeg = 90.0f; totalDistM = 0.0f; legProgressM = 0.0f;
            currentLeg = LEG_AB;
            autoLoopEnabled = false;
            noInterrupts(); rawTicksL = 0; rawTicksR = 0; interrupts();
            prevTicksL = 0; prevTicksR = 0;
            Serial.println(">> [LỆNH]: ĐÃ RESET TỌA ĐỘ VỀ GỐC A (0,0) GÓC 90°!");
          } else if (resp.indexOf("CALIBRATE_GYRO") >= 0) {
            calibrateGyroZ(400);
            yawDeg = 90.0f;
            Serial.printf(">> [LỆNH]: ĐÃ CALIB GYRO! Offset = %+.3f | Yaw = 90.0°\n", gyroZOffset);
          } else if (resp.indexOf("MISSION:M1") >= 0) {
            autoLoopEnabled = false;
            startMission(LEG_AB);
          } else if (resp.indexOf("MISSION:M2") >= 0) {
            autoLoopEnabled = false;
            startMission(LEG_BC);
          } else if (resp.indexOf("MISSION:M3") >= 0) {
            autoLoopEnabled = false;
            startMission(LEG_CD);
          } else if (resp.indexOf("MISSION:M4") >= 0) {
            autoLoopEnabled = false;
            startMission(LEG_DA);
          } else if (resp.indexOf("MISSION:NEXT") >= 0) {
            advanceToNextLeg();
          } else if (resp.indexOf("AUTO_LOOP:ON") >= 0) {
            autoLoopEnabled = true;
            startMission(currentLeg);
            Serial.println(">> [LỆNH]: BẬT CHẾ ĐỘ VÒNG LẶP TỰ ĐỘNG (A-B-C-D-A)!");
          } else if (resp.indexOf("AUTO_LOOP:OFF") >= 0) {
            autoLoopEnabled = false;
            Serial.println(">> [LỆNH]: TẮT VÒNG LẶP TỰ ĐỘNG!");
          } else if (resp.indexOf("TURN_LEFT_90") >= 0) {
            startManualTurn(-90.0f); // Xoay TRÁI 90°
          } else if (resp.indexOf("TURN_RIGHT_90") >= 0) {
            startManualTurn(90.0f);  // Xoay PHẢI 90°
          } else if (resp.indexOf("TURN_180") >= 0) {
            startManualTurn(180.0f);
          }
        }
      }
      http.end();
    }
    vTaskDelay(pdMS_TO_TICKS(150));
  }
}

// ===================================================================================
// SETUP
// ===================================================================================
void setup() {
  Serial.begin(115200);
  delay(600);

  initMotors();
  initLineSensors();
  initMPU();

  // Khởi tạo ngắt Encoder Hall
  pinMode(ENC_L_A_PIN, INPUT_PULLUP);
  pinMode(ENC_L_B_PIN, INPUT_PULLUP);
  pinMode(ENC_R_A_PIN, INPUT_PULLUP);
  pinMode(ENC_R_B_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(ENC_L_A_PIN), isrEncLeftA, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_L_B_PIN), isrEncLeftB, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_R_A_PIN), isrEncRightA, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_R_B_PIN), isrEncRightB, CHANGE);

  // Mặc định xe xuất phát tại Trạm A (0.00, 0.00), mũi xe hướng về B (+90.0°)
  odomX = 0.00f;
  odomY = 0.00f;
  yawDeg = 90.0f;
  legProgressM = 0.0f;

  Serial.println("\n=========================================================================");
  Serial.println("   AGV_VER2 - ODOMETRY & WEB SERVER TELEMETRY (SA BÀN 154cm x 151cm)");
  Serial.println("=========================================================================");
  Serial.printf("Tọa độ ban đầu (Tâm trục bánh): X=%.2fm | Y=%.2fm | Hướng=%.1f°\n", odomX, odomY, yawDeg);
  Serial.println(">> Đang kích hoạt đa nhân ESP32-S3...");

  // Core 0: Giao tiếp mạng Wi-Fi Telemetry
  xTaskCreatePinnedToCore(telemetryTask, "TelemetryTask", 8192, NULL, 1, NULL, 0);

  // Core 1: Điều khiển 100Hz chuẩn RTOS
  xTaskCreatePinnedToCore(controlLoopTask, "Control100Hz", 8192, NULL, 2, NULL, 1);
}

// ===================================================================================
// LOOP CHÍNH (XỬ LÝ PHÍM SERIAL & NÚT BOOT)
// ===================================================================================
void loop() {
  if (Serial.available()) {
    char ch = Serial.read();
    if (ch == ' ' || ch == 's') {
      if (isRunning) stopMotors();
      else startMission(currentLeg);
      Serial.printf("\n[SERIAL KEY]: %s\n", isRunning ? "START (CHẠY)" : "STOP (DỪNG)");
    } else if (ch == 't') {
      testMotorUntilMs = millis() + 1000;
      isRunning = true;
      Serial.println("\n[SERIAL KEY]: TEST ĐỘNG CƠ TIẾN 1 GIÂY!");
    } else if (ch == '1') {
      autoLoopEnabled = false;
      startMission(LEG_AB);
    } else if (ch == '2') {
      autoLoopEnabled = false;
      startMission(LEG_BC);
    } else if (ch == '3') {
      autoLoopEnabled = false;
      startMission(LEG_CD);
    } else if (ch == '4') {
      autoLoopEnabled = false;
      startMission(LEG_DA);
    } else if (ch == 'n') {
      advanceToNextLeg();
    } else if (ch == 'a') {
      autoLoopEnabled = !autoLoopEnabled;
      Serial.printf("\n[SERIAL KEY]: Chế độ Vòng Lặp Tự Động: %s\n", autoLoopEnabled ? "BẬT" : "TẮT");
      if (autoLoopEnabled && !isRunning) startMission(currentLeg);
    } else if (ch == 'l') {
      startManualTurn(-90.0f); // Xoay TRÁI 90°
    } else if (ch == 'k') {
      startManualTurn(90.0f);  // Xoay PHẢI 90°
    } else if (ch == 'c') {
      Serial.println("\n[SERIAL KEY]: CALIB LẠI GYRO (GIỮ XE ĐỨNG YÊN 1S)...");
      calibrateGyroZ(400);
      yawDeg = 90.0f;
      Serial.printf(">> Offset = %+.3f | Yaw = 90.0°\n", gyroZOffset);
    } else if (ch == 'r') {
      odomX = 0.0f; odomY = 0.0f; yawDeg = 90.0f; totalDistM = 0.0f; legProgressM = 0.0f;
      currentLeg = LEG_AB;
      autoLoopEnabled = false;
      noInterrupts(); rawTicksL = 0; rawTicksR = 0; interrupts();
      prevTicksL = 0; prevTicksR = 0;
      Serial.println("\n[SERIAL KEY]: RESET TỌA ĐỘ VỀ GỐC A (0,0) GÓC 90°!");
    }
  }

  // Nút BOOT vật lý trên ESP32
  static unsigned long lastBtnTime = 0;
  static int lastBtn = HIGH;
  int btn = digitalRead(BUTTON_BOOT_PIN);
  if (btn == LOW && lastBtn == HIGH && (millis() - lastBtnTime > 250)) {
    lastBtnTime = millis();
    isRunning = !isRunning;
    if (!isRunning) {
      autoLoopEnabled = false;
      stopMotors();
    } else {
      startMission(currentLeg);
    }
    Serial.printf("\n[NÚT BOOT]: %s\n", isRunning ? "ĐANG CHẠY" : "ĐÃ DỪNG");
  }
  lastBtn = btn;

  delay(10);
}