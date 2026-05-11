"""
Streaming Router
Handles screen mirroring via MJPEG and WebSocket.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from routers.state import streamer, scrcpy_streamer

router = APIRouter(tags=["streaming"])


@router.get("/video_feed")
async def video_feed():
    """MJPEG Stream endpoint for device screen mirroring (legacy)."""
    return StreamingResponse(
        streamer.generate_stream(), 
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.get("/video_feed_scrcpy")
async def video_feed_scrcpy():
    """MJPEG Stream using scrcpy (higher performance)."""
    return StreamingResponse(
        scrcpy_streamer.generate_mjpeg_stream(), 
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.websocket("/ws/screen")
async def websocket_screen(websocket: WebSocket):
    """
    WebSocket endpoint for high-performance screen streaming.
    Sends raw JPEG frames as binary messages.
    """
    await websocket.accept()
    
    try:
        await scrcpy_streamer.start()
        
        while scrcpy_streamer.is_running:
            frame = await scrcpy_streamer.get_frame()
            if frame is None:
                break
            # Send binary frame
            await websocket.send_bytes(frame)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS/SCREEN] Error: {e}")
    finally:
        await scrcpy_streamer.stop()
        try:
            await websocket.close()
        except:
            pass
