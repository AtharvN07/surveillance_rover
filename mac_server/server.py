"""
MAC ROVER SERVER — the brain of the rover.

Pipeline:
  Jetson MJPEG  -->  YOLO detection (local)  -->  MJPEG annotated stream to browser
                                  |
                                  v
                         obstacle heuristics + VLM scene text (optional)
                                  |
                                  v
              browser dashboard <= WebSocket telemetry ; browser --cmd--> Jetson

No frames are stored to disk. The Mac pulls frames straight from the Jetson,
annotates them with YOLO boxes, and re-serves them to the browser.

Run:
  export JETSON_URL=http://192.168.31.122:8000
  python3 server.py
  # or: uvicorn server:app --host 0.0.0.0 --port 9000
"""
import asyncio
import json
import logging
import time
from typing import List, Dict, Optional

import cv2
import httpx
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from starlette.websockets import WebSocketState

from config import cfg
from detector import Detector
from jetson_client import JetsonClient
from vlm import VLM

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("mac.server")

app = FastAPI(title="Surveillance Rover — Mac Brain", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── Shared state ─────────────────────────────────────────────────────────────
class State:
    def __init__(self):
        self.frame_jpeg: Optional[bytes] = None   # annotated frame for browser
        self.raw_jpeg: Optional[bytes] = None     # raw frame (for VLM)
        self.detections: List[Dict] = []
        self.obstacles = {"front": 0.0, "left": 0.0, "right": 0.0}
        self.fps = 0.0
        self.yolo_ms = 0.0
        self.vlm_text: Optional[str] = None
        self.scan_counts: Dict[str, int] = {}
        self.mode = "manual"
        self.estop = False
        self.lock = asyncio.Lock()

state = State()
detector: Optional[Detector] = None
vlm: Optional[VLM] = None
jetson: Optional[JetsonClient] = None
fs = None                       # httpx streaming client
clients: List[WebSocket] = []   # browsers subscribed to telemetry

# ── Frame puller: consume MJPEG from Jetson, run YOLO, publish ────────────────
async def frame_puller():
    global detector, fs
    buf = b""
    async with httpx.AsyncClient(timeout=None) as fs_local:
        while True:
            try:
                async with fs_local.stream("GET", jetson.stream_url) as r:
                    log.info("Connected to Jetson stream: %s", jetson.stream_url)
                    async for chunk in r.aiter_bytes(8192):
                        buf += chunk
                        while True:
                            s = buf.find(b"\xff\xd8")
                            e = buf.find(b"\xff\xd9", s + 2) if s != -1 else -1
                            if s == -1 or e == -1:
                                buf = buf[-2:] if len(buf) > 2 else buf
                                break
                            jpg = buf[s:e + 2]
                            buf = buf[e + 2:]
                            frame = cv2.imdecode(
                                np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR
                            )
                            if frame is None:
                                continue
                            # YOLO on Mac
                            annotated, dets = await asyncio.to_thread(
                                detector.detect, frame)
                            obs = detector.obstacles(dets, frame.shape[1])
                            ok, out = cv2.imencode(".jpg", annotated,
                                                   [cv2.IMWRITE_JPEG_QUALITY, cfg.jpeg_quality])
                            async with state.lock:
                                state.raw_jpeg = jpg
                                state.frame_jpeg = out.tobytes() if ok else jpg
                                state.detections = dets
                                state.obstacles = obs
                                state.yolo_ms = detector.last_ms
                                for d in dets:
                                    state.scan_counts[d["label"]] = \
                                        state.scan_counts.get(d["label"], 0) + 1
            except Exception as e:
                log.warning("Stream pull failed (%s) — retrying in 1s", e)
                await asyncio.sleep(1)

# ── FPS counter + telemetry broadcast ─────────────────────────────────────────
async def telemetry_loop():
    last_frame = None
    fc, t0 = 0, time.time()
    while True:
        await asyncio.sleep(0.25)
        async with state.lock:
            fp = state.frame_jpeg
        if fp is not None and fp is not last_frame:
            fc += 1
            last_frame = fp
        if time.time() - t0 >= 2.0:
            state.fps = round(fc / (time.time() - t0), 1)
            fc, t0 = 0, time.time()
        jstatus = await jetson.status() if jetson else {}
        msg = {
            "type": "telemetry",
            "fps": state.fps,
            "yolo_ms": round(state.yolo_ms, 1),
            "detections": state.detections,
            "obstacles": state.obstacles,
            "scan_counts": state.scan_counts,
            "mode": state.mode,
            "estop": state.estop,
            "jetson": jstatus,
            "vlm": state.vlm_text,
        }
        dead = []
        for ws in clients:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in clients:
                clients.remove(ws)

# ── VLM scene descriptions (optional, every 8s) ───────────────────────────────
async def vlm_loop():
    while True:
        await asyncio.sleep(8.0)
        if not vlm.enabled:
            continue
        raw = state.raw_jpeg
        if raw:
            try:
                state.vlm_text = await vlm.describe(raw)
            except Exception as e:
                log.warning("VLM failed: %s", e)

# ── Startup / shutdown ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    global detector, vlm, jetson
    log.info("Loading YOLO model (%s)…", cfg.yolo_model)
    detector = Detector(cfg.yolo_model, cfg.yolo_conf)
    vlm = VLM()
    jetson = JetsonClient(cfg.jetson_url)
    ok = await jetson.health()
    log.info("Jetson %s — %s", cfg.jetson_url,
             "REACHABLE" if ok else "NOT REACHABLE (will retry)")
    asyncio.create_task(frame_puller())
    asyncio.create_task(telemetry_loop())
    asyncio.create_task(vlm_loop())

@app.on_event("shutdown")
async def shutdown():
    if jetson:
        await jetson.stop()   # always leave motors stopped
        await jetson.close()

# ── Annotated MJPEG stream for the browser ────────────────────────────────────
async def annotated_stream():
    while True:
        async with state.lock:
            jpg = state.frame_jpeg
        if jpg:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
        await asyncio.sleep(1 / 30)

@app.get("/stream")
async def stream():
    return StreamingResponse(annotated_stream(),
                             media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/snapshot")
async def snapshot():
    async with state.lock:
        jpg = state.frame_jpeg
    if not jpg:
        return JSONResponse({"error": "no frame yet"}, status_code=503)
    from starlette.responses import Response
    return Response(jpg, media_type="image/jpeg")

# ── REST API ──────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    ok = await jetson.health() if jetson else False
    return {"status": "ok", "jetson_ok": ok}

@app.get("/api/status")
async def status():
    return {
        "fps": state.fps,
        "yolo_ms": round(state.yolo_ms, 1),
        "detections": state.detections,
        "obstacles": state.obstacles,
        "scan_counts": state.scan_counts,
        "mode": state.mode,
        "vlm": state.vlm_text,
        "jetson": await jetson.status() if jetson else {},
    }

@app.post("/api/cmd")
async def api_cmd(payload: dict):
    if state.estop:
        return {"ok": False, "reason": "estop"}
    ok = await jetson.send_motors(payload.get("l", 0), payload.get("r", 0))
    return {"ok": ok}

@app.post("/api/estop")
async def api_estop():
    state.estop = True
    await jetson.estop()
    return {"estop": True}

@app.post("/api/estop/clear")
async def api_estop_clear():
    state.estop = False
    await jetson.estop_clear()
    return {"estop": False}

@app.post("/api/mode/{mode}")
async def api_mode(mode: str):
    state.mode = mode
    await jetson.stop()   # always stop motors on mode switch
    return {"mode": mode}

@app.post("/api/scan/clear")
async def api_scan_clear():
    state.scan_counts = {}
    return {"ok": True}

# ── WebSocket for the dashboard ────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    log.info("Browser connected (%d clients)", len(clients))
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "cmd":
                if not state.estop and state.mode == "manual":
                    await jetson.send_motors(msg.get("l", 0), msg.get("r", 0))
            elif kind == "estop":
                state.estop = True
                await jetson.estop()
            elif kind == "estop_clear":
                state.estop = False
                await jetson.estop_clear()
            elif kind == "mode":
                state.mode = msg.get("value", "manual")
                await jetson.stop()
            elif kind == "ping":
                await ws.send_json({"type": "pong", "t": time.time()})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("WS error: %s", e)
    finally:
        if ws in clients:
            clients.remove(ws)
        await jetson.stop()   # never leave motors running
        log.info("Browser disconnected (%d clients)", len(clients))

@app.get("/")
async def index():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=cfg.host, port=cfg.port)
