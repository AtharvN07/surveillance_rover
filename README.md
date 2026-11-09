# Surveillance Rover — Complete System

Autonomous indoor surveillance rover using Jetson Nano + Arduino Mega + L298N.

## Quick Start

### 1. Flash Arduino
Open `arduino/rover_controller.ino` in Arduino IDE.
Install library: **Adafruit PWM Servo Driver** via Library Manager.
Select **Arduino Mega 2560**, upload.

### 2. Jetson Nano — install dependencies
```bash
cd surveillance_rover
pip3 install -r requirements.txt --break-system-packages
```

### 3. Configure
```bash
cp config/rover.env.example config/rover.env
# Edit ARDUINO_PORT, camera settings, etc.
```

### 4. Run
```bash
export $(cat config/rover.env | xargs)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. Open Dashboard
Navigate to `http://<jetson-ip>:8000` from any browser on the same network.

---

## Operating Modes

| Mode | Description |
|------|-------------|
| Manual | Joystick control, progressive PWM, full camera feed |
| Explore | Autonomous room scanning, SLAM map building |
| Patrol | Navigate between defined waypoints indefinitely |

---

## Hardware Wiring

See `config/wiring.md` for full pin diagram.

**L298N → Arduino Mega**

| L298N | Arduino Mega Pin |
|-------|-----------------|
| ENA   | D5 (PWM)        |
| IN1   | D7              |
| IN2   | D8              |
| IN3   | D9              |
| IN4   | D10             |
| ENB   | D6 (PWM)        |
| GND   | GND             |

**CSI Camera → Jetson Nano**
- Connect ribbon cable to CAM0 CSI port (30-pin connector, contacts facing heatsink)

---

## Serial Protocol (Arduino)

| Command       | Response     | Description                      |
|---------------|--------------|----------------------------------|
| `PING\n`      | `PONG`       | Heartbeat                        |
| `M:L,R\n`     | `OK:M`       | Set motors (-255..255 each)      |
| `E\n`         | `OK:ESTOP`   | Emergency stop                   |
| `STATUS\n`    | `OK:STATUS:L,R` | Current motor PWM              |
| `MAXSPD:N\n`  | `OK:MAXSPD:N` | Set speed ceiling (0-255)       |
| `ACCEL:N\n`   | `OK:ACCEL:N`  | Set acceleration step (1-50)    |
| `RESUME\n`    | `OK:RESUME`   | Clear emergency stop             |

---

## WebSocket API

Connect to `ws://<host>:8000/ws/control`

**Send:**
```json
{ "type": "joystick", "x": 0.5, "y": 0.8 }
{ "type": "estop" }
{ "type": "estop_clear" }
{ "type": "mode", "value": "manual|explore|patrol" }
{ "type": "ping" }
```

**Receive:**
```json
{ "type": "pong", "t": 1234567890.123 }
{ "type": "estop_ack" }
{ "type": "mode_ack", "mode": "manual" }
```

Telemetry stream: `ws://<host>:8000/ws/telemetry`
Map stream: `ws://<host>:8000/ws/map`

---

## REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/status` | GET | System status |
| `/api/mode` | POST | Set mode |
| `/api/estop` | POST | Emergency stop |
| `/api/estop/clear` | POST | Clear ESTOP |
| `/api/camera/stream` | GET | MJPEG stream |
| `/api/camera/snapshot` | GET | JPEG snapshot |
| `/api/map/current` | GET | Occupancy grid JSON |
| `/api/map/save?name=X` | POST | Save map |
| `/api/map/list` | GET | List saved maps |
| `/api/odometry` | GET | Current pose |

---

## Hardware Assessment Notes

**Current single CSI camera limitations:**
- Cannot provide reliable metric depth without stereo or LiDAR
- Monocular visual odometry has scale ambiguity — fused with wheel PWM odometry
- Obstacle detection relies on optical flow + edge density heuristics
- For production-grade SLAM, add: Intel RealSense D435 or RPLidar A1

**Recommended sensor additions (priority order):**
1. Wheel encoders on both drive motors (fixes odometry scale drift)
2. MPU-6050 IMU via I2C (improves rotation estimate)
3. 2D LiDAR e.g. RPLidar A1 (~$100) for reliable room mapping

**With only CSI camera, expect:**
- Obstacle avoidance: functional in good lighting (>300 lux)
- Map accuracy: ±0.5m drift over 10m travel
- Loop closure: not supported without additional sensors
