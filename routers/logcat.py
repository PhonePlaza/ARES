"""
Logcat Router
Handles ADB logcat streaming via WebSocket.
"""
import asyncio
import subprocess
import threading
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["logcat"])


@router.websocket("/ws/device/logcat")
async def websocket_logcat(websocket: WebSocket):
    """
    Streams ADB Logcat. 
    Client can send "filter:<package_name>" to filter logs.
    """
    await websocket.accept()
    process = None
    
    try:
        # Start adb logcat process
        cmd = ["adb", "logcat"]
        
        target_package = None
        # Check for initial filter message
        try:
            filter_msg = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            if filter_msg.startswith("filter:"):
                target_package = filter_msg.split(":")[1]
        except asyncio.TimeoutError:
            pass

        # Use standard Popen with a thread to avoid blocking asyncio loop on Windows
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace'
        )

        loop = asyncio.get_running_loop()
        async_queue = asyncio.Queue()

        def log_reader():
            """Reads lines in a background thread"""
            try:
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    loop.call_soon_threadsafe(async_queue.put_nowait, line)
            except Exception as e:
                print(f"Log reader error: {e}")
            finally:
                loop.call_soon_threadsafe(async_queue.put_nowait, None)  # EOF

        # Start background thread
        t = threading.Thread(target=log_reader, daemon=True)
        t.start()

        filter_str = target_package if (target_package and target_package != "all") else None
        keep_running = True
        
        while keep_running:
            try:
                # Wait for next line from queue
                line = await async_queue.get()
                
                if line is None:  # EOF
                    break

                # Truncate extremely long lines
                if len(line) > 1000:
                    line = line[:1000] + "... [TRUNCATED]\n"
                
                # Filter out system noise (Emulator/Graphics spam)
                ignored_tags = [
                    "hwservicemanager", "Gralloc4", "servicemanager", 
                    "BpBinder", "ProcessState", "EGL_emulation"
                ]
                if any(tag in line for tag in ignored_tags):
                    continue

                if filter_str:
                    if filter_str in line:
                        await websocket.send_text(line)
                else:
                    await websocket.send_text(line)

            except asyncio.CancelledError:
                keep_running = False
                raise
            except Exception as e:
                # websocket closed or other error
                keep_running = False
                break

    except WebSocketDisconnect:
        # Normal client disconnect
        pass
    except Exception as e:
        print(f"Logcat handler error: {e}")
        # Only try to send error if connection is likely still open
        try:
            await websocket.send_text(f"[ERROR] Logcat stream failed: {e}")
        except:
            pass
    finally:
        if process:
            process.terminate()
        try:
            await websocket.close()
        except:
            pass  # Already closed
