"""
Jetson Rover — THIN CLIENT.

The Jetson does NO AI processing. It only:
  1. Opens the IMX219 CSI camera with GStreamer (hardware pipeline)
  2. Streams it as MJPEG over HTTP so the Mac can pull frames
  3. Accepts motor commands from the Mac over plain HTTP POST
  4. Forwards them to the Arduino over serial
  5. Runs a 500 ms watchdog — motors stop if the Mac goes quiet

The Mac is the brain: YOLO, VLM, mapping, decisions all run there.
This file is the ONLY thing running on the Jetson besides nvargus-daemon.

Run:  python3 run_server.py
"""
import os, time, json, logging, threading, serial, cv2
from flask import Flask, Response, jsonify, request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("jetson")

ARDUINO_PORT = os.getenv("ARDUINO_PORT", "/dev/ttyACM0")
ARDUINO_BAUD = int(os.getenv("ARDUINO_BAUD", "115200"))
WIDTH  = int(os.getenv("CAM_WIDTH", "640"))
HEIGHT = int(os.getenv("CAM_HEIGHT", "480"))
FPS    = int(os.getenv("CAM_FPS", "30"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "70"))
WATCHDOG_S = float(os.getenv("WATCHDOG_S", "0.5"))

app = Flask(__name__)

# ── Shared state ─────────────────────────────────────────────────────────────
arduino = None
latest_jpg = None
jpg_lock = threading.Lock()
cam_fps = 0.0
last_cmd = time.time()
motor_left = 0
motor_right = 0
estop = False

# ── Arduino ──────────────────────────────────────────────────────────────────
def arduino_connect():
    global arduino
    try:
        s = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=0.05)
        time.sleep(2)
        s.reset_input_buffer()
        s.write(b"PING\n")
        time.sleep(0.1)
        resp = s.readline().decode(errors="replace").strip()
        log.info("Arduino: %s", resp)
        s.write(b"MAXSPD:220\n")
        time.sleep(0.05)
        s.write(b"ACCEL:15\n")
        arduino = s
    except Exception as e:
        log.error("Arduino failed: %s", e)
        arduino = None

def arduino_send(cmd: str):
    global arduino
    if arduino is None:
        return
    try:
        arduino.write(cmd.encode())
    except Exception as e:
        log.error("serial write failed: %s", e)
        arduino = None

def set_motors(l: int, r: int):
    global motor_left, motor_right
    l = max(-220, min(220, int(l)))
    r = max(-220, min(220, int(r)))
    motor_left, motor_right = l, r
    if not estop:
        arduino_send(f"M:{l},{r}\n")

# ── Camera: GStreamer CSI → MJPEG frames ──────────────────────────────────────
def camera_loop():
    global latest_jpg, cam_fps
    pipeline = (
        "nvarguscamerasrc sensor-id=0 ! "
        f"video/x-raw(memory:NVMM),width={WIDTH},height={HEIGHT},"
        f"format=NV12,framerate={FPS}/1 ! "
        "nvvidconv flip-method=0 ! "
        f"video/x-raw,width={WIDTH},height={HEIGHT},format=BGRx ! "
        "videoconvert ! video/x-raw,format=BGR ! "
        "appsink max-buffers=1 drop=true sync=false"
    )
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        log.warning("GStreamer failed, falling back to /dev/video0")
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    if not cap.isOpened():
        log.error("No camera. Check nvargus-daemon: sudo systemctl start nvargus-daemon")
        return
    log.info("Camera running (%dx%d @ %d fps)", WIDTH, HEIGHT, FPS)
    enc = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
    t0, fc = time.time(), 0
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.01)
            continue
        ok, jpg = cv2.imencode(".jpg", frame, enc)
        if ok:
            with jpg_lock:
                latest_jpg = jpg.tobytes()
        fc += 1
        if time.time() - t0 >= 2.0:
            cam_fps = round(fc / (time.time() - t0), 1)
            fc, t0 = 0, time.time()

# ── Watchdog: stop motors if the Mac goes quiet ───────────────────────────────
def watchdog_loop():
    while True:
        time.sleep(0.1)
        if not estop and time.time() - last_cmd > WATCHDOG_S:
            if motor_left != 0 or motor_right != 0:
                set_motors(0, 0)

# ── HTTP API ──────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok", "arduino": arduino is not None})

@app.route("/status")
def status():
    return jsonify({
        "arduino_connected": arduino is not None,
        "camera_fps": cam_fps,
        "motor_left": motor_left,
        "motor_right": motor_right,
        "estop": estop,
    })

def mjpeg_gen():
    while True:
        with jpg_lock:
            jpg = latest_jpg
        if jpg:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
        time.sleep(1.0 / FPS)

@app.route("/camera/stream")
def stream():
    return Response(mjpeg_gen(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/camera/snapshot")
def snapshot():
    with jpg_lock:
        jpg = latest_jpg
    if not jpg:
        return "no frame", 503
    return Response(jpg, mimetype="image/jpeg")

@app.route("/cmd", methods=["POST"])
def cmd():
    global last_cmd
    data = request.get_json(force=True, silent=True) or {}
    last_cmd = time.time()
    if estop:
        return jsonify({"ok": False, "reason": "estop"})
    set_motors(data.get("l", 0), data.get("r", 0))
    return jsonify({"ok": True, "l": motor_left, "r": motor_right})

@app.route("/estop", methods=["POST"])
def do_estop():
    global estop
    estop = True
    set_motors(0, 0)
    arduino_send("E\n")
    return jsonify({"ok": True, "estop": True})

@app.route("/estop/clear", methods=["POST"])
def clear_estop():
    global estop, last_cmd
    estop = False
    last_cmd = time.time()
    arduino_send("RESUME\n")
    return jsonify({"ok": True, "estop": False})

@app.route("/ping", methods=["POST"])
def ping():
    return jsonify({"pong": True, "t": time.time()})

if __name__ == "__main__":
    arduino_connect()
    threading.Thread(target=camera_loop, daemon=True).start()
    threading.Thread(target=watchdog_loop, daemon=True).start()
    log.info("Jetson thin client ready on 0.0.0.0:8000")
    # threaded=True → each HTTP client gets its own thread, MJPEG doesn't block /cmd
    app.run(host="0.0.0.0", port=8000, threaded=True)
