"""
Frida Router
Handles Frida CLI spawning, injection, and WebSocket communication.
"""
import asyncio
import subprocess
import tempfile
import threading
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from routers.state import frida_core, agent

router = APIRouter(tags=["frida"])

# Global state for Frida CLI process
# Using module-level variables for shared state
frida_process = None
frida_message_queues: dict = {}
current_script_path: str = ""  # Fixed script file path for reload


# ============ Request Models ============

class SpawnRequest(BaseModel):
    package: str
    script: str


class FridaInputRequest(BaseModel):
    command: str


# ============ Helper Functions ============

def get_frida_process():
    global frida_process
    return frida_process


def set_frida_process(process):
    global frida_process
    frida_process = process


# ============ Endpoints ============

@router.get("/api/processes")
async def list_processes():
    """Lists running processes on device."""
    return frida_core.list_processes()


@router.get("/api/device/apps")
async def list_apps():
    """Lists installed applications (frida-ps -Uai)."""
    return frida_core.list_applications()


@router.post("/api/frida/spawn")
async def frida_spawn(data: SpawnRequest):
    """
    Spawns an app and injects a Frida script using CLI.
    Uses: frida -U -f <package> -l script.js
    """
    global frida_process, current_script_path
    
    package = data.package
    script_code = data.script
    
    if not package or not script_code:
        return {"status": "error", "message": "Package and script required"}
    
    # Kill any existing frida process
    if frida_process:
        try:
            frida_process.terminate()
            frida_process.wait(timeout=2)
        except:
            pass
    
    # Use fixed script file path (persistent across reload)
    import os
    script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp")
    os.makedirs(script_dir, exist_ok=True)
    current_script_path = os.path.join(script_dir, "current.js")
    
    # Write script to fixed file
    with open(current_script_path, 'w', encoding='utf-8') as f:
        f.write(script_code)
    
    # Convert to forward slashes for Frida
    script_path_unix = current_script_path.replace('\\', '/')
    
    # DEBUG: Log script content before saving
    print(f"\n[DEBUG] ===== SCRIPT TO RUN =====")
    print(f"[DEBUG] Script file: {script_path_unix}")
    print(f"[DEBUG] First 300 chars: {repr(script_code[:300])}")
    print(f"[DEBUG] =============================\n")
    
    # Create message queue for this session
    session_id = "frida_cli"
    frida_message_queues[session_id] = asyncio.Queue()
    
    # Start frida CLI process
    # -U = USB device, -f = spawn package, -l = load script
    cmd = ["frida", "-U", "-f", package, "-l", current_script_path]

    
    try:
        frida_process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,  # Allow interactive input
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        # Capture the main event loop BEFORE starting the thread
        main_loop = asyncio.get_event_loop()
        
        # Thread to read output and push to queue
        def read_output():
            print("[DEBUG] read_output thread started")
            try:
                for line in iter(frida_process.stdout.readline, ''):
                    if line:
                        line = line.strip()
                        if line:
                            # DEBUG: Print every line to server console
                            print(f"[FRIDA-OUT] {line}")
                            try:
                                # Use the captured main_loop instead of get_event_loop()
                                asyncio.run_coroutine_threadsafe(
                                    push_to_queue(session_id, line),
                                    main_loop
                                )
                            except Exception as e:
                                print(f"[DEBUG] Queue push error: {e}")
                                # Fallback: store directly
                                try:
                                    frida_message_queues[session_id].put_nowait({"type": "log", "data": line})
                                except Exception as e2:
                                    print(f"[DEBUG] Fallback queue error: {e2}")
                print("[DEBUG] read_output loop ended (EOF)")
            except Exception as e:
                print(f"[DEBUG] read_output exception: {e}")
        
        async def push_to_queue(sid, line):
            if sid in frida_message_queues:
                await frida_message_queues[sid].put({"type": "log", "data": line})
        
        output_thread = threading.Thread(target=read_output, daemon=True)
        output_thread.start()
        
        return {
            "status": "running",
            "pid": frida_process.pid,
            "package": package,
            "session_id": session_id,
            "script_path": current_script_path
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/frida/detach")
async def frida_detach():
    """Stops the Frida CLI process."""
    global frida_process
    
    if frida_process:
        try:
            frida_process.terminate()
            frida_process.wait(timeout=2)
            frida_process = None
            return {"status": "detached"}
        except Exception as e:
            frida_process = None
            return {"status": "error", "message": str(e)}
    
    return {"status": "no_process"}


class ReloadRequest(BaseModel):
    script: str


@router.post("/api/frida/reload")
async def frida_reload(data: ReloadRequest):
    """
    Re-injects a script into the running app without restarting.
    Overwrites the same script file and uses %reload or sends y to confirm.
    """
    global frida_process, current_script_path
    
    if not frida_process or frida_process.poll() is not None:
        return {"status": "error", "message": "No active Frida process. Start the app first."}
    
    if not current_script_path:
        return {"status": "error", "message": "No script file found. Start the app first."}
    
    script_code = data.script
    if not script_code:
        return {"status": "error", "message": "Script is required"}
    
    try:
        # Overwrite the SAME script file (not creating new temp file)
        with open(current_script_path, 'w', encoding='utf-8') as f:
            f.write(script_code)
        
        script_path_unix = current_script_path.replace('\\', '/')
        print(f"[RELOAD] Overwrote script: {script_path_unix}")
        
        # Send %reload command to reload the same file
        # Note: %reload doesn't need confirmation, unlike %load
        frida_process.stdin.write("%reload\n")
        frida_process.stdin.flush()
        
        print(f"[RELOAD] Sent: %reload")
        
        return {
            "status": "reloaded",
            "script_path": script_path_unix,
            "message": "Script reloaded into running app"
        }
    except Exception as e:
        print(f"[RELOAD] Error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/api/frida/input")
async def frida_input(data: FridaInputRequest):
    """Sends a command to the Frida CLI REPL."""
    global frida_process
    
    if not frida_process or frida_process.poll() is not None:
        return {"status": "error", "message": "No active Frida process"}
    
    try:
        # Send command to stdin
        frida_process.stdin.write(data.command + "\n")
        frida_process.stdin.flush()
        return {"status": "sent", "command": data.command}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.websocket("/ws/frida")
async def websocket_frida(websocket: WebSocket):
    """
    WebSocket for streaming Frida CLI output in real-time.
    Client should connect after calling /api/frida/spawn.
    """
    await websocket.accept()
    
    # Use fixed session_id for CLI approach
    session_id = "frida_cli"
    
    # Create queue if not exists
    if session_id not in frida_message_queues:
        frida_message_queues[session_id] = asyncio.Queue()
    
    queue = frida_message_queues[session_id]
    
    try:
        while True:
            try:
                # Wait for messages from Frida with timeout
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(message)
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                await websocket.send_json({"type": "heartbeat"})
            except Exception as e:
                print(f"[WS/FRIDA] Queue error: {e}")
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS/FRIDA] Error: {e}")
    finally:
        # Cleanup
        if session_id in frida_message_queues:
            del frida_message_queues[session_id]


@router.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for streaming agent logs."""
    await websocket.accept()
    # Send logs to frontend in real-time
    async for log in agent.stream_logs():
        await websocket.send_text(log)
