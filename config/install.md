# Installation & Deployment Guide

## Jetson Nano Setup

### 1. Flash JetPack 4.6.x
Download from developer.nvidia.com/embedded/jetpack.
Flash to SD card with Balena Etcher. Boot, complete initial setup.

### 2. Enable CSI camera
```bash
# Verify camera detected
ls /dev/video*
# Test capture
gst-launch-1.0 nvarguscamerasrc ! nvvidconv ! xvimagesink
```

### 3. Clone project onto Jetson
```bash
scp -r surveillance_rover/ user@<jetson-ip>:~/
# or git clone
```

### 4. Install Python dependencies
```bash
cd ~/surveillance_rover
pip3 install -r requirements.txt --break-system-packages
# OpenCV on Jetson — use the pre-built version:
pip3 install opencv-python==4.10.0.84 --break-system-packages
```

### 5. Configure serial port permissions
```bash
sudo usermod -aG dialout $USER
# Log out and back in, then verify:
ls -la /dev/ttyACM0
```

### 6. Set up environment
```bash
cp config/rover.env.example config/rover.env
nano config/rover.env   # set ARDUINO_PORT, USE_CSI, etc.
```

### 7. Run the server
```bash
cd ~/surveillance_rover
export $(grep -v '^#' config/rover.env | xargs)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 8. Auto-start on boot (systemd)
```bash
sudo tee /etc/systemd/system/rover.service << SERVICE
[Unit]
Description=Surveillance Rover
After=network.target

[Service]
User=$USER
WorkingDirectory=/home/$USER/surveillance_rover
EnvironmentFile=/home/$USER/surveillance_rover/config/rover.env
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable rover
sudo systemctl start rover
```

---

## Arduino Setup

### 1. Install Arduino IDE 2.x
Download from arduino.cc/en/software.

### 2. Install required library
Open Library Manager → search **Adafruit PWM Servo Driver** → Install.

### 3. Flash firmware
- Open `arduino/rover_controller.ino`
- Select board: **Arduino Mega or Mega 2560**
- Select port: `/dev/ttyACM0` (Linux/Mac) or `COM3` (Windows)
- Click Upload

### 4. Verify
Open Serial Monitor at 115200 baud.
Type `PING` → should receive `PONG`.
Type `M:100,100` → both motors spin forward at ~40% speed.
Type `E` → motors stop.

---

## Testing Sequence (Phase by Phase)

### Phase 1 — Motor control
```
Serial: PING             → expect: PONG
Serial: M:150,150        → both motors forward
Serial: M:-150,-150      → both motors reverse
Serial: M:150,-150       → spin in place (right)
Serial: E                → stop
```

### Phase 2 — Dashboard
```bash
# On Jetson:
uvicorn app.main:app --host 0.0.0.0 --port 8000
# On Mac browser:
open http://<jetson-ip>:8000
# Verify joystick moves motors, camera feed appears
```

### Phase 3 — Obstacle detection
```
# Move rover toward a wall in Manual mode
# Dashboard should show obstacle warning when < 0.3m
```

### Phase 4 — SLAM
```
# Switch to Explore mode in dashboard
# Drive manually — map panel should fill in as you move
# Save map via dashboard
```

### Phase 5 — Patrol
```
# Load a saved map
# Add 2-4 waypoints on the map panel
# Switch to Patrol mode — rover navigates between waypoints
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `serial.SerialException: [Errno 13]` | `sudo chmod 666 /dev/ttyACM0` |
| Camera not opening | Check ribbon cable; try `USE_CSI=false` for USB camera |
| Arduino not responding | Check USB cable; re-flash firmware |
| High CPU on Jetson | Reduce `STREAM_FPS_MAX` to 15 in rover.env |
| Map drift badly | Slow down rover; add wheel encoders |
| Dashboard blank | Check browser console; verify Jetson IP; try `http://` not `https://` |
