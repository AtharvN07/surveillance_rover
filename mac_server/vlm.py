"""
VLM (Vision-Language Model) — optional scene understanding via OpenAI.
Activates only when OPENAI_API_KEY is set. If unset, the rover works fully
with local YOLO only. Sends the current frame to GPT-4o and returns a
one-line situation report for the dashboard.
"""
import base64
import logging
import os
from typing import Optional

log = logging.getLogger("mac.vlm")

class VLM:
    def __init__(self):
        self.key = os.getenv("OPENAI_API_KEY", "").strip()
        self.client = None
        if self.key:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.key)
            log.info("VLM enabled (OpenAI)")
        else:
            log.info("VLM disabled — set OPENAI_API_KEY to enable scene descriptions")

    @property
    def enabled(self) -> bool:
        return self.client is not None

    async def describe(self, jpeg_bytes: bytes) -> Optional[str]:
        if not self.client:
            return None
        import asyncio
        return await asyncio.to_thread(self._describe_sync, jpeg_bytes)

    def _describe_sync(self, jpeg_bytes: bytes) -> str:
        b64 = base64.b64encode(jpeg_bytes).decode()
        resp = self.client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=40,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text":
                     "One short sentence: what do you see in this rover camera view? "
                     "Mention obstacles, people, or open paths."},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
        )
        return resp.choices[0].message.content.strip()
