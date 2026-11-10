"""
JetsonClient — plain HTTP client for the Jetson thin client.
No WebSocket, no Socket.IO — just POST/GET over HTTP. This cannot break
because the Jetson runs Flask with threaded=True.
"""
import logging
import httpx

log = logging.getLogger("mac.jetson")

class JetsonClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=5.0,
                                         limits=httpx.Limits(max_connections=10))

    @property
    def stream_url(self) -> str:
        return f"{self.base}/camera/stream"

    async def health(self) -> bool:
        try:
            r = await self._client.get(f"{self.base}/health")
            return r.status_code == 200
        except Exception:
            return False

    async def status(self) -> dict:
        try:
            r = await self._client.get(f"{self.base}/status")
            return r.json()
        except Exception:
            return {"arduino_connected": False, "camera_fps": 0, "error": "unreachable"}

    async def send_motors(self, left: int, right: int) -> bool:
        try:
            r = await self._client.post(f"{self.base}/cmd",
                                        json={"l": int(left), "r": int(right)})
            return r.json().get("ok", False)
        except Exception as e:
            log.warning("send_motors failed: %s", e)
            return False

    async def stop(self) -> bool:
        return await self.send_motors(0, 0)

    async def estop(self) -> bool:
        try:
            await self._client.post(f"{self.base}/estop")
            return True
        except Exception:
            return False

    async def estop_clear(self) -> bool:
        try:
            await self._client.post(f"{self.base}/estop/clear")
            return True
        except Exception:
            return False

    async def close(self):
        await self._client.aclose()
