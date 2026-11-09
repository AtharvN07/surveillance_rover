"""
main.py — FastAPI application entry point for the Surveillance Rover.
Run with: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
import logging
from contextlib import asynccontextmanager

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rover.main")

# ── Shared application state ─────────────────────────────────────────────────
class AppState:
    arduino: ArduinoInterface = None
    camera: CameraStream = None
    telemetry: TelemetryCollector = None
    safety: SafetyController = None
    mode: str = "manual"          # manual | explore | patrol
    running: bool = False

state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop all hardware interfaces cleanly."""
    logger.info("Rover startup — initialising hardware …")

    state.arduino = ArduinoInterface(config)
    await state.arduino.connect()

    state.camera = CameraStream(config)
    await state.camera.start()

    state.safety = SafetyController(state.arduino, config)
    state.safety.start()

    state.telemetry = TelemetryCollector(state.arduino, state.camera, config)
    state.running = True

    logger.info("Rover ready.")
    yield

    logger.info("Rover shutdown — stopping hardware …")
    state.running = False
    state.safety.stop()
    await state.arduino.emergency_stop()
    await state.camera.stop()
    logger.info("Shutdown complete.")


# ── Application factory ───────────────────────────────────────────────────────
app = FastAPI(
    title="Surveillance Rover API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(http_router, prefix="/api")
app.include_router(ws_router)

# Serve the dashboard frontend (built React app)
try:
    app.mount("/", StaticFiles(directory="dashboard/frontend/dist", html=True), name="static")
except RuntimeError:
    logger.warning("Dashboard build not found — serving API only.")


# ── Expose state to routers via request.app.state ─────────────────────────────
@app.on_event("startup")
async def expose_state():
    app.state.rover = state
