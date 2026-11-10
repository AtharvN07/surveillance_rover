# Surveillance Rover — Mac/Jetson Split Architecture

**Jetson = hands** (camera + motors, zero AI). **Mac = brain** (YOLO, decisions, dashboard).

## Layout

    surveillance_rover/
    ├── arduino/rover_controller.ino   # Arduino Mega firmware (L298N + watchdog)
    ├── jetson/run_server.py           # Jetson: thin MJPEG streamer + motor relay (Flask)
    ├── jetson/requirements.txt        # Jetson deps (system python3)
    ├── mac_server/                    # Mac: the brain
    │   ├── server.py                  #   FastAPI app — pulls Jetson stream, runs YOLO, serves dashboard
    │   ├── detector.py                #   YOLO wrapper (auto-downloads yolo11n.pt)
    │   ├── jetson_client.py           #   Plain HTTP client → Jetson (/cmd /estop ...)
    │   ├── vlm.py                     #   Optional GPT-4o-mini scene descriptions
    │   ├── config.py                  #   JETSON_URL etc.
    │   ├── static/index.html          #   Dashboard (open http://<mac-ip>:9000)
    │   └── requirements.txt
    └── config/                        # wiring.md, rover.env.example

## 1. Arduino (one-time)

Flash `arduino/rover_controller.ino` with Arduino IDE. Serial Monitor @115200 → type `PING`, expect `PONG`.

## 2. Jetson (every session)

    sudo systemctl start nvargus-daemon
    cd ~/surveillance_rover/jetson
    python3 run_server.py

Test:  `curl http://192.168.31.122:8000/health` → `{"status":"ok","arduino":true}`

## 3. Mac (every session)

    cd mac_server
    pip3 install -r requirements.txt
    export JETSON_URL=http://192.168.31.122:8000
    python3 server.py
    # open http://localhost:9000

The Mac pulls the Jetson's MJPEG stream, runs YOLO per frame, draws boxes,
and serves the annotated feed to any browser on the LAN.

## Controls

Arrow keys / WASD drive · Space = ESTOP · 1-5 = speed presets · or use the D-pad.
Max speed is the default preset; nothing finer-grained is needed for direct control.

## Optional: VLM scene understanding

    export OPENAI_API_KEY=sk-...
    python3 server.py

The rover then captions its camera view every 8 s on the dashboard.
Without the key, YOLO-only mode runs unchanged.

## Optional: Explore / patrol modes

Currently EXPLORE/PATROL buttons set the mode flag; autonomous navigation
runs on the Jetson's own ROS2 workspace instead (see ~/ros2_ws on the Jetson).
To route exploration decisions through the Mac, extend `server.py`'s `/api/mode`
handler — the Mac already owns the detection stream needed for it.

## Safety chain

Browser disconnect → Mac stops motors → Jetson watchdog (0.5 s) also stops motors
→ Arduino itself zeroes PWM on `E`. Any single failure stops the rover.
