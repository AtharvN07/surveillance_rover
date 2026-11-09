"""
routes.py — HTTP REST endpoints for the Surveillance Rover.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class ModeRequest(BaseModel):
    mode: str  # manual | explore | patrol


class MaxSpeedRequest(BaseModel):
    value: int  # 0-255


class WaypointRequest(BaseModel):
    name: str
    x: float
    y: float


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/status")
async def status(request: Request):
    rover = request.app.state.rover
    arduino_status = await rover.arduino.get_status()
    return {
        "mode": rover.mode,
        "arduino": arduino_status,
        "camera_fps": rover.camera.fps,
        "camera_connected": rover.camera.connected,
    }


@router.post("/mode")
async def set_mode(req: ModeRequest, request: Request):
    rover = request.app.state.rover
    allowed = {"manual", "explore", "patrol"}
    if req.mode not in allowed:
        raise HTTPException(400, f"mode must be one of {allowed}")
    rover.mode = req.mode
    return {"mode": rover.mode}


@router.post("/estop")
async def emergency_stop(request: Request):
    rover = request.app.state.rover
    rover.safety.trigger_estop()
    await rover.arduino.emergency_stop()
    return {"stopped": True}


@router.post("/estop/clear")
async def clear_estop(request: Request):
    rover = request.app.state.rover
    rover.safety.clear_estop()
    return {"stopped": False}


@router.post("/maxspeed")
async def set_max_speed(req: MaxSpeedRequest, request: Request):
    rover = request.app.state.rover
    v = max(0, min(255, req.value))
    rover.config.max_speed = v
    await rover.arduino._send_raw(f"MAXSPD:{v}\n")
    return {"max_speed": v}


@router.get("/camera/snapshot")
async def snapshot(request: Request):
    rover = request.app.state.rover
    jpg = await rover.camera.get_jpeg(quality=90)
    if jpg is None:
        raise HTTPException(503, "Camera not available")
    return StreamingResponse(iter([jpg]), media_type="image/jpeg")


@router.get("/camera/stream")
async def mjpeg_stream(request: Request):
    rover = request.app.state.rover
    return StreamingResponse(
        rover.camera.stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/map/current")
async def get_map(request: Request):
    """Return the current occupancy grid as JSON."""
    rover = request.app.state.rover
    if hasattr(rover, "slam") and rover.slam:
        return rover.slam.get_map_json()
    return {"cells": [], "width": 0, "height": 0, "resolution": 0.05}


@router.post("/map/save")
async def save_map(request: Request, name: str = "default"):
    rover = request.app.state.rover
    if hasattr(rover, "slam") and rover.slam:
        path = rover.slam.save_map(name)
        return {"saved": path}
    raise HTTPException(503, "SLAM not running")


@router.get("/map/list")
async def list_maps():
    import os, glob
    maps = [os.path.basename(p) for p in glob.glob("maps/*.json")]
    return {"maps": maps}


@router.get("/odometry")
async def odometry(request: Request):
    rover = request.app.state.rover
    if hasattr(rover, "velocity") and rover.velocity:
        return rover.velocity.pose
    return {"x": 0, "y": 0, "theta": 0, "theta_deg": 0}
