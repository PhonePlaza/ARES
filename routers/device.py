"""
Device Control Router
Handles touch input (tap, swipe) and device listing.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from routers.state import streamer, frida_core

router = APIRouter(prefix="/api", tags=["device"])


class TapRequest(BaseModel):
    x: int
    y: int


class SwipeRequest(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    duration: int = 300


@router.post("/input/tap")
async def input_tap(data: TapRequest):
    """Send touch input to device."""
    await streamer.tap(data.x, data.y)
    return {"status": "sent"}


@router.post("/input/swipe")
async def input_swipe(data: SwipeRequest):
    """Send swipe input to device."""
    await streamer.swipe(data.x1, data.y1, data.x2, data.y2, data.duration)
    return {"status": "sent"}


@router.get("/devices")
async def list_devices():
    """List connected ADB devices."""
    return frida_core.list_devices()
