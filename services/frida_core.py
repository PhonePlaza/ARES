"""
FridaCore - Core Frida management for device connection, process listing, and script injection.
Supports spawn, attach, inject, and detach operations via Frida Python bindings.
"""

import subprocess
import frida
from typing import List, Dict


class FridaCore:
    """Core class for managing Frida device connections and script injection."""
    
    def __init__(self):
        self.device = None
        self.session = None
        self.current_pid = None

    def connect_device(self):
        """Connect to an Android device via USB (frida-server must be running)."""
        try:
            self.device = frida.get_usb_device(timeout=5)
            return {"status": "connected", "device": self.device.name}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def list_devices(self) -> List[Dict[str, str]]:
        """List all devices visible to Frida (equivalent to frida-ls-devices)."""
        try:
            devices = frida.enumerate_devices()
            return [{"id": d.id, "name": d.name, "type": d.type} for d in devices]
        except Exception as e:
            print(f"[FRIDA] Error listing devices: {e}")
            return []

    def spawn_process(self, package_name: str):
        """Spawn an app and attach Frida (equivalent to frida -U -f <package>)."""
        if not self.device:
            result = self.connect_device()
            if result.get("status") == "error":
                return result
        
        try:
            pid = self.device.spawn([package_name])
            self.session = self.device.attach(pid)
            self.device.resume(pid)
            return {"status": "spawned", "pid": pid}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def list_processes(self):
        """List running processes on device (equivalent to frida-ps -U)."""
        if not self.device:
            result = self.connect_device()
            if result.get("status") == "error":
                return []
            
        try:
            processes = self.device.enumerate_processes()
            return [{"pid": p.pid, "name": p.name} for p in processes]
        except Exception as e:
            print(f"[FRIDA] Error listing processes: {e}")
            print("[FRIDA] Attempting to reconnect...")
            self.connect_device()
            
            if self.device:
                try:
                    processes = self.device.enumerate_processes()
                    return [{"pid": p.pid, "name": p.name} for p in processes]
                except Exception as e2:
                     print(f"[FRIDA] Reconnection failed: {e2}")
            return []

    def list_applications(self):
        """List installed applications (equivalent to frida-ps -Uai)."""
        if not self.device:
            result = self.connect_device()
            if result.get("status") == "error":
                return []
            
        try:
            apps = self.device.enumerate_applications()
            return [{
                "pid": (app.pid if app.pid != 0 else "-"),
                "name": app.name,
                "identifier": app.identifier
            } for app in apps]
        except Exception as e:
            print(f"[FRIDA] Error listing applications: {e}")
            return []

    def get_foreground_app(self):
        """Get the currently focused app via ADB dumpsys."""
        try:
            cmd = ["adb", "shell", "dumpsys", "window", "windows"]
            output = subprocess.check_output(cmd).decode("utf-8")
            
            for line in output.splitlines():
                if "mCurrentFocus" in line or "mFocusedApp" in line:
                    parts = line.split(" ")
                    for part in parts:
                        if "/" in part and "}" not in part:
                            return part.split("/")[0]
            return None
        except Exception:
            return None

    def inject_script(self, pid: int, script_code: str, on_message=None):
        """Inject a Frida script into a running process (equivalent to frida -U -p <pid> -l script.js)."""
        if not self.device:
            result = self.connect_device()
            if result.get("status") == "error":
                return result
            
        try:
            if not self.session or self.current_pid != pid:
                self.session = self.device.attach(pid)
                self.current_pid = pid
                
            def default_handler(message, data):
                if message['type'] == 'send':
                    print(f"[FRIDA] {message['payload']}")
                elif message['type'] == 'error':
                    error_detail = message.get('stack', message.get('description', str(message)))
                    print(f"[FRIDA ERROR] {error_detail}")
            
            handler = on_message if on_message else default_handler
            
            script = self.session.create_script(script_code)
            script.on('message', handler)
            script.load()
            
            return {
                "status": "injected",
                "pid": pid,
                "script": script
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def spawn_and_inject(self, package_name: str, script_code: str, on_message=None):
        """Spawn an app and inject a script (equivalent to frida -U -f <package> -l script.js)."""
        import time
        
        if not self.device:
            result = self.connect_device()
            if result.get("status") == "error":
                return result
            
        try:
            pid = self.device.spawn([package_name])
            print(f"[FRIDA] Spawned {package_name} with PID {pid}")
            
            self.session = self.device.attach(pid)
            self.current_pid = pid
            
            def default_handler(message, data):
                if message['type'] == 'send':
                    print(f"[FRIDA] {message['payload']}")
                elif message['type'] == 'error':
                    error_detail = message.get('stack', message.get('description', str(message)))
                    print(f"[FRIDA ERROR] {error_detail}")
            
            handler = on_message if on_message else default_handler
            
            self.device.resume(pid)
            print(f"[FRIDA] Process resumed, waiting for app initialization...")
            
            time.sleep(2.0)
            
            script = self.session.create_script(script_code)
            script.on('message', handler)
            script.load()
            print(f"[FRIDA] Script injected successfully")
            
            return {
                "status": "running",
                "pid": pid,
                "package": package_name,
                "script": script
            }
        except Exception as e:
            print(f"[FRIDA] Error: {e}")
            return {"status": "error", "message": str(e)}

    def detach(self):
        """Detach from current process and reset session state."""
        if self.session:
            try:
                self.session.detach()
                self.session = None
                self.current_pid = None
                return {"status": "detached"}
            except Exception as e:
                print(f"[FRIDA] Detach warning: {e}")
                self.session = None
                self.current_pid = None
                return {"status": "detached", "warning": str(e)}
        return {"status": "no_session"}
