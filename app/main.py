"""
main.py — FastAPI application entry point for the Surveillance Rover.
Compatible with FastAPI 0.83 / Pydantic v1 / Python 3.6+

Run with:
  python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import config
from app.hardware.arduino import ArduinoInterface
from app.hardware.camera import CameraStream
from app.api.routes import router as http_router
from app.api.websocket import router as ws_router
from app.api.telemetry import TelemetryCollector
from app.control.safety_controller import SafetyController
from app.control.velocity_controller import VelocityController

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rover.main")


# ── Application factory ───────────────────────────────────────────────────────
app = FastAPI(title="Surveillance Rover API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(http_router, prefix="/api")
app.include_router(ws_router)

# Serve dashboard
try:
    app.mount("/", StaticFiles(directory="dashboard/frontend/dist", html=True), name="static")
except RuntimeError:
    logger.warning("Dashboard build not found — serving API only.")


# ── Shared state (attached to app.state so routers can access it) ─────────────
class RoverState:
    arduino: ArduinoInterface = None
    camera: CameraStream = None
    telemetry: TelemetryCollector = None
    safety: SafetyController = None
    velocity: VelocityController = None
    mode: str = "manual"
    running: bool = False


rover = RoverState()
app.state.rover = rover


@app.on_event("startup")
async def startup():
    logger.info("Rover startup — initialising hardware ...")

    rover.arduino = ArduinoInterface(config)
    await rover.arduino.connect()

    rover.camera = CameraStream(config)
    await rover.camera.start()

    rover.safety = SafetyController(rover.arduino, config)
    rover.safety.start()

    rover.velocity = VelocityController(rover.arduino, config)

    rover.telemetry = TelemetryCollector(rover.arduino, rover.camera, config)
    rover.running = True

    logger.info("Rover ready.")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Rover shutdown — stopping hardware ...")
    rover.running = False
    rover.safety.stop()
    await rover.arduino.emergency_stop()
    await rover.camera.stop()
    logger.info("Shutdown complete.")
