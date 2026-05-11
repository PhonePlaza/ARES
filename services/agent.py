"""
FridaAgent - Real-time log streaming from Frida to frontend via WebSocket.
Uses asyncio.Queue as a message broker and async generators for streaming.
"""

import asyncio


class FridaAgent:
    """Manages log streaming from Frida scripts to the frontend."""
    
    def __init__(self):
        self.logs_queue = asyncio.Queue()
        self._running = True

    async def log(self, message: str):
        """Add a log message to the queue."""
        await self.logs_queue.put(message)

    def stop(self):
        """Gracefully stop the agent. stream_logs() will exit within 1 second."""
        self._running = False

    async def stream_logs(self):
        """Async generator that yields log messages one at a time."""
        yield "[SYSTEM] Agent initialized..."
        yield "[SYSTEM] Waiting for device connection..."
        
        while self._running:
            try:
                log = await asyncio.wait_for(
                    self.logs_queue.get(), 
                    timeout=1.0
                )
                yield log
                self.logs_queue.task_done()
                
            except asyncio.TimeoutError:
                continue
                
            except asyncio.CancelledError:
                break
