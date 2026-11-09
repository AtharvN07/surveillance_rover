/*
 * rover_controller.ino  –  v10  –  Progressive Differential-Drive Firmware
 * Arduino Mega 2560 + L298N
 *
 * Serial protocol (115200 baud, LF-terminated):
 *
 *   PING\n              -> PONG
 *   M:left,right\n      -> OK:M  (left,right: -255..255 PWM, progressive)
 *   E\n                 -> OK:ESTOP  (emergency stop)
 *   STATUS\n            -> OK:STATUS:left,right
 *   MAXSPD:value\n      -> OK:MAXSPD:value  (set max speed 0-255)
 *   ACCEL:value\n       -> OK:ACCEL:value   (set accel step 1-50)
 *
 * Safety:
 *   - Motor stops if no M: command received within WATCHDOG_MS (500 ms).
 *   - E command stops immediately (no ramp).
 *   - Speed clamped to MAX_SPEED at all times.
 *   - Dead-zone applied to joystick inputs.
 *
 * Pin assignments (matching existing v9 L298N wiring):
 *   ENA = 5  ENB = 6  IN1 = 7  IN2 = 8  IN3 = 9  IN4 = 10
 */

#include <Arduino.h>

// ── Pin definitions ──────────────────────────────────────────────────────────
#define ENA  5
#define ENB  6
#define IN1  7
#define IN2  8
#define IN3  9
#define IN4  10

// ── Tuning constants (runtime-configurable via serial) ───────────────────────
int MAX_SPEED     = 220;   // absolute ceiling  (0-255)
int ACCEL_STEP    = 12;    // max PWM increase per loop tick (20 ms → ~200 ms 0→full)
int DECEL_STEP    = 20;    // max PWM decrease per loop tick (faster stop)
const int DEADZONE      = 8;    // joystick values within ±DEADZONE treated as 0
const unsigned long WATCHDOG_MS = 500;  // ms before auto-stop

// ── State ────────────────────────────────────────────────────────────────────
volatile int targetLeft  = 0;
volatile int targetRight = 0;
int currentLeft  = 0;
int currentRight = 0;
bool emergencyStop = false;
unsigned long lastCmdMs = 0;

// ── Motor helpers ─────────────────────────────────────────────────────────────
// Apply dead-zone to a raw joystick value
int applyDeadzone(int val) {
  if (abs(val) <= DEADZONE) return 0;
  return val;
}

// Drive one side: positive = forward, negative = reverse
void driveMotor(int pinA, int pinB, int enPin, int speed) {
  speed = constrain(speed, -MAX_SPEED, MAX_SPEED);
  if (speed > 0) {
    digitalWrite(pinA, HIGH); digitalWrite(pinB, LOW);
    analogWrite(enPin, speed);
  } else if (speed < 0) {
    digitalWrite(pinA, LOW);  digitalWrite(pinB, HIGH);
    analogWrite(enPin, -speed);
  } else {
    digitalWrite(pinA, LOW);  digitalWrite(pinB, LOW);
    analogWrite(enPin, 0);
  }
}

void hardStop() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  analogWrite(ENA, 0);    analogWrite(ENB, 0);
  currentLeft = currentRight = 0;
  targetLeft  = targetRight  = 0;
}

// ── Smooth ramping ────────────────────────────────────────────────────────────
int rampValue(int current, int target) {
  if (current == target) return current;
  int diff = target - current;
  int step;
  // Choose accel or decel step
  bool sameSign = (current >= 0 && target >= 0) || (current < 0 && target < 0);
  bool moving   = abs(current) > 0;
  if (moving && !sameSign) {
    // Crossing zero: decelerate
    step = DECEL_STEP;
  } else if (abs(target) > abs(current)) {
    step = ACCEL_STEP;
  } else {
    step = DECEL_STEP;
  }
  if (abs(diff) <= step) return target;
  return current + (diff > 0 ? step : -step);
}

// ── Serial command parser ──────────────────────────────────────────────────────
char serialBuf[80];
uint8_t serialPos = 0;

void handleCommand(char* cmd) {
  // trim trailing CR/LF
  int len = strlen(cmd);
  while (len > 0 && (cmd[len-1] == '\r' || cmd[len-1] == '\n')) cmd[--len] = 0;
  if (len == 0) return;

  if (strcmp(cmd, "PING") == 0) {
    Serial.println("PONG");
    return;
  }

  if (cmd[0] == 'E') {
    emergencyStop = true;
    hardStop();
    Serial.println("OK:ESTOP");
    return;
  }

  if (strcmp(cmd, "STATUS") == 0) {
    Serial.print("OK:STATUS:");
    Serial.print(currentLeft); Serial.print(','); Serial.println(currentRight);
    return;
  }

  if (strncmp(cmd, "M:", 2) == 0 && !emergencyStop) {
    int l = 0, r = 0;
    sscanf(cmd + 2, "%d,%d", &l, &r);
    targetLeft  = constrain(applyDeadzone(l), -MAX_SPEED, MAX_SPEED);
    targetRight = constrain(applyDeadzone(r), -MAX_SPEED, MAX_SPEED);
    lastCmdMs   = millis();
    Serial.println("OK:M");
    return;
  }

  if (strncmp(cmd, "MAXSPD:", 7) == 0) {
    int v = atoi(cmd + 7);
    MAX_SPEED = constrain(v, 0, 255);
    Serial.print("OK:MAXSPD:"); Serial.println(MAX_SPEED);
    return;
  }

  if (strncmp(cmd, "ACCEL:", 6) == 0) {
    int v = atoi(cmd + 6);
    ACCEL_STEP = constrain(v, 1, 50);
    Serial.print("OK:ACCEL:"); Serial.println(ACCEL_STEP);
    return;
  }

  // Resume after emergency stop
  if (strcmp(cmd, "RESUME") == 0) {
    emergencyStop = false;
    lastCmdMs = millis();
    Serial.println("OK:RESUME");
    return;
  }

  Serial.print("ERR:UNKNOWN:"); Serial.println(cmd);
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20);

  pinMode(ENA, OUTPUT); pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);

  hardStop();
  lastCmdMs = millis();
  Serial.println("READY");
}

// ── Main loop ─────────────────────────────────────────────────────────────────
void loop() {
  // Read serial bytes into line buffer
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      serialBuf[serialPos] = 0;
      handleCommand(serialBuf);
      serialPos = 0;
    } else if (c != '\r' && serialPos < sizeof(serialBuf) - 1) {
      serialBuf[serialPos++] = c;
    }
  }

  // Watchdog: stop motors if no command for WATCHDOG_MS
  if (!emergencyStop && millis() - lastCmdMs > WATCHDOG_MS) {
    targetLeft  = 0;
    targetRight = 0;
  }

  if (!emergencyStop) {
    // Ramp toward targets
    currentLeft  = rampValue(currentLeft,  targetLeft);
    currentRight = rampValue(currentRight, targetRight);
    driveMotor(IN1, IN2, ENA, currentLeft);
    driveMotor(IN3, IN4, ENB, currentRight);
  }

  delay(20);  // 50 Hz control loop
}
