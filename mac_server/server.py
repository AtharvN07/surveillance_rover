"""
mac_server/server.py — Mac-side processing server for Surveillance Rover.

Architecture:
  Jetson (camera + motors) <--WebSocket--> Mac (YOLO + dashboard) <--Browser-->

Mac pulls MJPEG from Jetson, runs YOLO on each frame, annotates it,
streams result to browser, and relays drive commands from browser back to Jetson.

Run:
  cd mac_server
  uvicorn server:app --host 0.0.0.0 --port 9000 --reload
"""

import asyncio
import logging
import time
import threading
from typing import Optional

import cv2
import numpy as np
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import cfg
from jetson_client import JetsonClient
from detector import Detector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("mac.server")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Rover Mac Server", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── Shared state ──────────────────────────────────────────────────────────────
latest_annotated: Optional[bytes] = None
latest_raw: Optional[np.ndarray] = None
frame_lock = threading.Lock()
detections = []          # list of {label, conf, box}
scan_map = {}            # label -> count seen
fps_out = 0.0
jetson: Optional[JetsonClient] = None
detector: Optional[Detector] = None


@app.on_event("startup")
async def startup():
    global jetson, detector
    detector = Detector(cfg.yolo_model, cfg.confidence)
    log.info("YOLO model loaded: %s", cfg.yolo_model)
    jetson = JetsonClient(cfg.jetson_url)
    asyncio.create_task(jetson.connect())
    asyncio.create_task(frame_pull_loop())
    asyncio.create_task(telemetry_push_loop())
    log.info("Mac server ready — dashboard at http://localhost:%d", cfg.port)


@app.on_event("shutdown")
async def shutdown():
    if jetson:
        await jetson.disconnect()


# ── Frame pull: fetch MJPEG from Jetson, run YOLO, store annotated JPEG ──────
async def frame_pull_loop():
    global latest_annotated, latest_raw, detections, scan_map, fps_out
    log.info("Starting frame pull from %s", cfg.jetson_stream_url)
    loop = asyncio.get_event_loop()

    fc = 0
    t0 = time.time()
    buf = b""

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                async with client.stream("GET", cfg.jetson_stream_url) as resp:
                    async for chunk in resp.aiter_bytes(chunk_size=4096):
                        buf += chunk
                        # Parse MJPEG boundary
                        while True:
                            start = buf.find(b"\xff\xd8")
                            end   = buf.find(b"\xff\xd9")
                            if start == -1 or end == -1 or end < start:
                                break
                            jpg_bytes = buf[start:end+2]
                            buf = buf[end+2:]

                            # Decode frame
                            arr = np.frombuffer(jpg_bytes, np.uint8)
                            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            if frame is None:
                                continue

                            # Run YOLO in thread pool (non-blocking)
                            annotated, dets = await loop.run_in_executor(
                                None, detector.detect, frame
                            )

                            # Update scan map
                            for d in dets:
                                scan_map[d["label"]] = scan_map.get(d["label"], 0) + 1

                            # Encode annotated frame
                            ok, jpg_out = cv2.imencode(
                                ".jpg", annotated,
                                [cv2.IMWRITE_JPEG_QUALITY, cfg.stream_quality]
                            )
                            if ok:
                                with frame_lock:
                                    latest_annotated = jpg_out.tobytes()
                                    latest_raw = frame
                                    detections = dets

                            fc += 1
                            elapsed = time.time() - t0
                            if elapsed >= 2.0:
                                fps_out = round(fc / elapsed, 1)
                                fc = 0; t0 = time.time()

            except Exception as e:
                log.warning("Frame pull error: %s — retrying in 2s", e)
                await asyncio.sleep(2)


# ── MJPEG stream to browser ───────────────────────────────────────────────────
async def annotated_stream():
    while True:
        with frame_lock:
            jpg = latest_annotated
        if jpg:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
        await asyncio.sleep(1.0 / cfg.stream_fps_max)


@app.get("/stream")
async def stream():
    return StreamingResponse(
        annotated_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/snapshot")
async def snapshot():
    with frame_lock:
        jpg = latest_annotated
    if not jpg:
        return JSONResponse({"error": "no frame"}, status_code=503)
    return StreamingResponse(iter([jpg]), media_type="image/jpeg")


# ── REST API ──────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "jetson": jetson.connected if jetson else False}


@app.get("/api/detections")
async def get_detections():
    with frame_lock:
        dets = list(detections)
    return {"detections": dets, "fps": fps_out}


@app.get("/api/scan_map")
async def get_scan_map():
    return {"objects": scan_map, "unique": len(scan_map)}


@app.post("/api/scan_map/clear")
async def clear_scan_map():
    scan_map.clear()
    return {"cleared": True}


@app.get("/api/status")
async def status():
    jetson_status = {}
    if jetson and jetson.connected:
        try:
            jetson_status = await jetson.get_status()
        except Exception:
            pass
    return {
        "fps": fps_out,
        "jetson_connected": jetson.connected if jetson else False,
        "jetson": jetson_status,
        "detections": len(detections),
        "objects_seen": len(scan_map),
    }


@app.post("/api/mode/{mode}")
async def set_mode(mode: str):
    if jetson:
        await jetson.set_mode(mode)
    return {"mode": mode}


@app.post("/api/estop")
async def estop():
    if jetson:
        await jetson.emergency_stop()
    return {"stopped": True}


@app.post("/api/estop/clear")
async def estop_clear():
    if jetson:
        await jetson.resume()
    return {"stopped": False}


# ── WebSocket: browser sends drive commands, Mac relays to Jetson ─────────────
@app.websocket("/ws/control")
async def control_ws(ws: WebSocket):
    await ws.accept()
    log.info("Browser connected")
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")

            if kind == "cmd" and jetson:
                await jetson.send_motors(msg.get("l", 0), msg.get("r", 0))
                await ws.send_json({"type": "ack", "t": time.time()})

            elif kind == "estop" and jetson:
                await jetson.emergency_stop()
                await ws.send_json({"type": "estop_ack"})

            elif kind == "estop_clear" and jetson:
                await jetson.resume()
                await ws.send_json({"type": "estop_cleared"})

            elif kind == "mode" and jetson:
                await jetson.set_mode(msg.get("value", "manual"))
                await ws.send_json({"type": "mode_ack", "mode": msg.get("value")})

            elif kind == "ping":
                await ws.send_json({"type": "pong", "t": time.time()})

    except WebSocketDisconnect:
        log.info("Browser disconnected")
        if jetson:
            await jetson.emergency_stop()


# ── Telemetry push to all browsers via SSE-style endpoint ─────────────────────
clients = set()

@app.websocket("/ws/telemetry")
async def telemetry_ws(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        clients.discard(ws)


async def telemetry_push_loop():
    import psutil
    while True:
        await asyncio.sleep(0.25)
        with frame_lock:
            dets = list(detections)
        payload = {
            "type": "telemetry",
            "fps": fps_out,
            "detections": dets,
            "objects_seen": dict(sorted(scan_map.items(),
                                        key=lambda x: -x[1])[:10]),
            "jetson_connected": jetson.connected if jetson else False,
            "cpu": psutil.cpu_percent(interval=None),
            "ram": psutil.virtual_memory().percent,
        }
        dead = set()
        for ws in list(clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.add(ws)
        clients -= dead


# Serve dashboard
try:
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
except RuntimeError:
    pass
