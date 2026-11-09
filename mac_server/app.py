"""
app.py — Mac server (Flask + SocketIO) that pulls MJPEG from Jetson,
runs YOLO detection, serves dashboard, relays commands back.
"""
import os, threading, time, logging, serial, cv2, numpy as np
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mac.server")

app = Flask(__name__, static_folder="dashboard/frontend/dist", static_url_path="")
app.config["SECRET_KEY"] = "rover"
sio = SocketIO(app, cors_allowed_origins="*", async_mode="threading",
               ping_timeout=10, ping_interval=5,
               transports=["websocket"], allow_upgrades=True)

arduino=None; cap=None; latest_jpg=None; cam_fps=0.0
mode="manual"; estop=False; last_cmd=time.time()
motor_left=0; motor_right=0
jpg_lock=threading.Lock()
obstacles={"front":0.0,"left":0.0,"right":0.0}
OBSTACLE_THRESHOLD=0.65
explore_heading=0; explore_t=time.time()

def arduino_connect():
    global arduino
    try:
        s=serial.Serial("/dev/ttyACM0",115200,timeout=0.05)
        time.sleep(2); s.reset_input_buffer()
        s.write(b"PING\n"); time.sleep(0.1)
        log.info("Arduino: %s",s.readline().decode(errors="replace").strip())
        s.write(b"MAXSPD:220\n"); time.sleep(0.05)
        s.write(b"ACCEL:15\n");   time.sleep(0.05)
        arduino=s
    except Exception as e:
        log.error("Arduino failed: %s",e)

def motors(l,r):
    global motor_left,motor_right,arduino
    motor_left=l; motor_right=r
    if arduino and not estop:
        try: arduino.write(f"M:{int(l)},{int(r)}\n".encode())
        except: arduino=None

def camera_loop():
    global cap,latest_jpg,cam_fps,prev_gray
    pipeline=(
        "nvarguscamerasrc sensor-id=0 ! "
        "video/x-raw(memory:NVMM),width=640,height=480,format=NV12,framerate=30/1 ! "
        "nvvidconv flip-method=0 ! "
        "video/x-raw,width=640,height=480,format=BGRx ! "
        "videoconvert ! video/x-raw,format=BGR ! "
        "appsink max-buffers=1 drop=true sync=false"
    )
    c=cv2.VideoCapture(pipeline,cv2.CAP_GSTREAMER)
    if not c.isOpened(): log.warning("GST failed, trying /dev/video0")
    c=cv2.VideoCapture(0)
    c.set(cv2.CAP_PROP_FRAME_WIDTH,640)
    c.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
    if not c.isOpened(): log.error("Camera failed"); return
    cap=c; log.info("Camera running")
    enc=[cv2.IMWRITE_JPEG_QUALITY,70]
    t0=time.time(); fc=0
    while True:
        ret,frame=c.read()
        if not ret: time.sleep(0.01); continue
        ok,jpg=cv2.imencode(".jpg",frame,enc)
        if ok:
            with jpg_lock: latest_jpg=jpg.tobytes()
        fc+=1
        if time.time()-t0>=2.0:
            cam_fps=round(fc/(time.time()-t0),1); fc=0; t0=time.time()

def watchdog_loop():
    while True:
        time.sleep(0.25)
        if not estop and mode=="manual" and time.time()-last_cmd>0.5:
            if motor_left!=0 or motor_right!=0: motors(0,0)

def telemetry_loop():
    try: import psutil; has_ps=True
    except: has_ps=False
    while True:
        time.sleep(0.2)
        d={"fps":cam_fps,"mode":mode,"estop":estop,
           "ard":arduino is not None,"cam":cap is not None,
           "ml":motor_left,"mr":motor_right,
           "obs":obstacles}
        if has_ps:
            import psutil as ps
            d["cpu"]=ps.cpu_percent(interval=None)
            d["ram"]=ps.virtual_memory().percent
        sio.emit("tel",d)

async def mjpeg_gen():
    while True:
        with jpg_lock: jpg=latest_jpg
        if jpg:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"+jpg+b"\r\n"
        await asyncio.sleep(0.033)

@app.route("/")
def index():
    return send_from_directory("dashboard/frontend/dist","index.html")

@app.route("/api/health")
async def health():
    return jsonify({"status":"ok"})

@app.route("/api/status")
async def status():
    jetson_status={}
    if jetson and jetson.connected:
        try:
            jetson_status = await jetson.get_status()
        except Exception:
            pass
    return {
        "fps": cam_fps,
        "jetson_connected": jetson.connected if jetson else False,
        "jetson": jetson_status,
        "detections": len(detections),
        "objects_seen": len(scan_map),
    }

@app.route("/api/camera/stream")
async def stream():
    return StreamingResponse(mjpeg_gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/camera/snapshot")
async def snapshot():
    with frame_lock:
        jpg = latest_jpg
    if not jpg: return JSONResponse({"error":"no frame"}, status_code=503)
    return StreamingResponse(iter([jpg]), media_type="image/jpeg")

@app.route("/api/estop", methods=["POST"])
async def do_estop():
    global estop
    estop=True; motors(0,0)
    if arduino:
        try: arduino.write(b"E\n")
        except: pass
    return jsonify({"stopped":True})

@app.route("/api/estop/clear", methods=["POST"])
async def clear_estop():
    global estop, last_cmd
    estop=False; last_cmd=time.time()
    return jsonify({"stopped":False})

@app.route("/api/mode", methods=["POST"])
async def set_mode():
    global mode
    mode=request.json.get("mode","manual")
    if mode!="manual": motors(0,0)
    return jsonify({"mode":mode})

@sio.on("connect")
async def on_connect():
    log.info("Client: %s", request.sid)

@sio.on("disconnect")
async def on_disconnect():
    motors(0,0)

@sio.on("cmd")
async def on_cmd(data):
    global last_cmd
    last_cmd=time.time()
    if estop or mode!="manual": return
    l=max(-220,min(220,int(data.get("l",0))))
    r=max(-220,min(220,int(data.get("r",0))))
    motors(l,r)

@sio.on("estop")
async def on_estop(data=None):
    global estop; estop=True; motors(0,0)
    if arduino:
        try: arduino.write(b"E\n")
        except: pass

@sio.on("estop_clear")
async def on_estop_clear(data=None):
    global estop,last_cmd; estop=False; last_cmd=time.time()

@sio.on("mode")
async def on_mode(data):
    global mode; mode=data.get("value","manual")
    if mode!="manual": motors(0,0)

@sio.on("ping_r")
async def on_ping_r(data=None): await sio.send("pong_r", {"t":time.time()})

if __name__=="__main__":
    arduino_connect()
    threading.Thread(target=camera_loop, daemon=True).start()
    threading.Thread(target=watchdog_loop,daemon=True).start()
    threading.Thread(target=telemetry_loop,daemon=True).start()
    log.info("Starting on http://0.0.0.0:8000")
    app.run(host="0.0.0.0", port=8000, debug=False)
