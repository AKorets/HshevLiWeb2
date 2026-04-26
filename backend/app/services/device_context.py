"""Parse device context from the request body.

The Flutter client sends a device_context JSON object in heartbeat requests.
This service validates and sanitises it before writing to sessions.
"""

from __future__ import annotations
from pydantic import BaseModel, model_validator
from typing import Literal


VALID_DEVICE_TYPES = {"desktop", "mobile", "tablet", "unknown"}
VALID_CONNECTION_TYPES = {"wifi", "ethernet", "4g", "3g", "2g", "unknown"}


class DeviceContext(BaseModel):
    device_type: Literal["desktop", "mobile", "tablet", "unknown"] | None = None
    os_family: str | None = None
    browser_family: str | None = None
    screen_width: int | None = None
    screen_height: int | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    device_pixel_ratio: float | None = None
    cpu_cores: int | None = None
    device_memory_gb: float | None = None
    connection_type: Literal["wifi", "ethernet", "4g", "3g", "2g", "unknown"] | None = None

    @model_validator(mode="after")
    def clamp_screen(self) -> "DeviceContext":
        # Clamp to SMALLINT range (0-32767)
        for attr in ("screen_width", "screen_height", "viewport_width", "viewport_height"):
            val = getattr(self, attr)
            if val is not None:
                setattr(self, attr, max(0, min(val, 32767)))
        if self.cpu_cores is not None:
            self.cpu_cores = max(0, min(self.cpu_cores, 256))
        if self.device_memory_gb is not None:
            self.device_memory_gb = max(0.0, min(self.device_memory_gb, 512.0))
        return self
