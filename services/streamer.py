import subprocess
import asyncio
import io
import threading
import base64


class ADBInputMixin:
    """Mixin class for ADB input commands (tap, swipe)."""

    adb_path: str

    async def tap(self, x: int, y: int):
        """Send tap event via ADB."""
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, lambda: self._sync_tap(x, y))
            return True
        except Exception as e:
            print(f"[STREAM] Error sending tap: {e}")
            return False

    def _sync_tap(self, x: int, y: int):
        try:
            cmd = [self.adb_path, "shell", "input", "tap", str(x), str(y)]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
        except Exception as e:
            print(f"[STREAM] Sync tap error: {e}")

    async def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300):
        """Send swipe event via ADB."""
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, lambda: self._sync_swipe(x1, y1, x2, y2, duration))
            return True
        except Exception as e:
            print(f"[STREAM] Error sending swipe: {e}")
            return False

    def _sync_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int):
        try:
            cmd = [self.adb_path, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)]
            dynamic_timeout = (duration / 1000) + 2
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=dynamic_timeout)
        except Exception as e:
            print(f"[STREAM] Sync swipe error: {e}")


class ScreenStreamer(ADBInputMixin):
    def __init__(self):
        self.adb_path = "adb"  # Assumes 'adb' is in the system PATH

    async def get_frame(self):
        """
        Captures a single frame from the connected Android device using ADB.
        Running in an executor to avoid blocking the async event loop.
        """
        return await self._capture_single()

    def _capture(self):
        """
        Sync function to run the blocking subprocess command.
        Uses 'adb exec-out screencap -p' to get the raw PNG image.
        """
        try:
            # -p ensures PNG format
            cmd = [self.adb_path, "exec-out", "screencap", "-p"]
            # timeout prevents hanging if device is disconnected
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
            
            if process.returncode == 0:
                return process.stdout
            else:
                return None
        except Exception:
            return None
    
    async def generate_stream(self):
        """
        Async generator that yields data in MJPEG format.
        Uses subprocess.Popen with a reader thread to bypass asyncio.create_subprocess_exec 
        limitations/bugs on Windows (NotImplementedError).
        """
        delimiter = b"|||EOF|||"
        cmd = [self.adb_path, "shell", "while true; do screencap -p | base64 -w 0; echo '|||EOF|||'; done"]
        
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        
        # Start standard blocking process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1024*1024*5 # 5MB buffer
        )
        
        def reader_thread():
            """Reads stdout in a separate thread and pushes to async queue."""
            try:
                while True:
                    # Blocking read - Increase chunk size for throughput
                    chunk = process.stdout.read(65536)
                    if not chunk:
                        break
                    # Thread-safe put
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as e:
                print(f"[STREAM] Reader thread error: {e}")
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None) # Signal EOF

        # Start the reader thread
        t = threading.Thread(target=reader_thread, daemon=True)
        t.start()
            
        buffer = b""
        try:
            while True:
                # Await data from the thread
                chunk = await queue.get()
                if chunk is None: # EOF signal
                    break
                
                buffer += chunk
                
                if delimiter in buffer:
                    parts = buffer.split(delimiter)
                    buffer = parts.pop()
                    
                    for b64_data in parts:
                        b64_data = b64_data.strip()
                        if not b64_data:
                            continue
                            
                        try:
                            # Offload CPU-heavy Base64 decode to thread pool
                            img_data = await loop.run_in_executor(None, base64.b64decode, b64_data)
                            
                            if img_data.startswith(b'\x89PNG'):
                                yield (b'--frame\r\n'
                                       b'Content-Type: image/png\r\n\r\n' + img_data + b'\r\n')
                        except Exception:
                            pass
                            
        except Exception as e:
            print(f"[STREAM] Error in stream loop: {e}")
        finally:
            if process:
                process.terminate()
            await asyncio.sleep(1)

    async def _capture_single(self):
        loop = asyncio.get_running_loop()
        try:
             # Just use the legacy way for single shots
             return await loop.run_in_executor(None, self._capture)
        except Exception:
            return None


class ScrcpyStreamer(ADBInputMixin):
    """
    High-performance screen streamer using ADB screenrecord + FFmpeg.
    Uses 'adb exec-out screenrecord --output-format=h264 -' piped to FFmpeg.
    Achieves 15-30 FPS with better latency than screencap.
    """
    
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self.adb_path = "adb"
        self.process = None
        self.is_running = False
        self._frame_queue = None
        self._reader_thread = None
        self._lock = threading.Lock()
        
    async def start(self):
        """Start the screenrecord + ffmpeg pipeline."""
        with self._lock:
            if self.is_running:
                return
            self.is_running = True
            
        loop = asyncio.get_running_loop()
        self._frame_queue = asyncio.Queue(maxsize=3)  # Small buffer for low latency
        
        def run_pipeline():
            """Run adb screenrecord | ffmpeg pipeline in background thread."""
            try:
                # ADB screenrecord outputs raw H.264 to stdout
                adb_cmd = [
                    self.adb_path, "exec-out",
                    "screenrecord", 
                    "--output-format=h264",
                    "--size", "720x1280",  # Lower resolution for performance
                    "--bit-rate", "4000000",  # 4 Mbps
                    "-"  # Output to stdout
                ]
                
                # FFmpeg decodes H.264 and outputs MJPEG frames
                ffmpeg_cmd = [
                    self.ffmpeg_path,
                    "-hide_banner",
                    "-loglevel", "error",
                    "-f", "h264",              # Input format is raw H.264
                    "-i", "pipe:0",            # Read from stdin
                    "-f", "image2pipe",        # Output as image stream
                    "-vcodec", "mjpeg",        # Encode to MJPEG
                    "-q:v", "8",               # Quality (2-31, lower=better)
                    "-r", "20",                # Limit to 20 fps
                    "pipe:1"                   # Output to stdout
                ]
                
                print(f"[SCRCPY] Starting ADB screenrecord pipeline...")
                
                # Start ADB process
                adb_proc = subprocess.Popen(
                    adb_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=1024*1024
                )
                
                # Start FFmpeg process, reading from ADB's stdout
                ffmpeg_proc = subprocess.Popen(
                    ffmpeg_cmd,
                    stdin=adb_proc.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=1024*1024
                )
                
                self.process = (adb_proc, ffmpeg_proc)
                
                # Read JPEG frames from ffmpeg output
                buffer = b""
                jpeg_start = b"\xff\xd8"
                jpeg_end = b"\xff\xd9"
                
                while self.is_running:
                    # Check if processes are still alive
                    if adb_proc.poll() is not None or ffmpeg_proc.poll() is not None:
                        if ffmpeg_proc.poll() is not None:
                            stderr = ffmpeg_proc.stderr.read()
                            if stderr:
                                print(f"[SCRCPY] FFmpeg error: {stderr.decode('utf-8', errors='replace')}")
                        break
                    
                    chunk = ffmpeg_proc.stdout.read(32768)
                    if not chunk:
                        break
                        
                    buffer += chunk
                    
                    # Extract complete JPEG frames
                    while True:
                        start_idx = buffer.find(jpeg_start)
                        if start_idx == -1:
                            buffer = b""
                            break
                            
                        end_idx = buffer.find(jpeg_end, start_idx + 2)
                        if end_idx == -1:
                            buffer = buffer[start_idx:]
                            break
                            
                        # Complete frame found
                        frame = buffer[start_idx:end_idx + 2]
                        buffer = buffer[end_idx + 2:]
                        
                        # Push to queue (drop old frames if full)
                        try:
                            if self._frame_queue.full():
                                try:
                                    self._frame_queue.get_nowait()
                                except Exception:
                                    pass
                            loop.call_soon_threadsafe(self._frame_queue.put_nowait, frame)
                        except Exception:
                            pass
                            
            except Exception as e:
                print(f"[SCRCPY] Pipeline error: {e}")
            finally:
                self.is_running = False
                try:
                    loop.call_soon_threadsafe(self._frame_queue.put_nowait, None)
                except Exception:
                    pass
                print("[SCRCPY] Pipeline thread ended")
        
        self._reader_thread = threading.Thread(target=run_pipeline, daemon=True)
        self._reader_thread.start()
        
        # Give pipeline time to start
        await asyncio.sleep(1.0)
        print("[SCRCPY] Stream started")
        
    async def stop(self):
        """Stop the streaming pipeline."""
        self.is_running = False
        if self.process:
            try:
                adb_proc, ffmpeg_proc = self.process
                adb_proc.terminate()
                ffmpeg_proc.terminate()
                await asyncio.sleep(0.5)
                adb_proc.kill()
                ffmpeg_proc.kill()
            except Exception:
                pass
        self.process = None
        self._frame_queue = None
        print("[SCRCPY] Stream stopped")
        
    async def get_frame(self):
        """Get the next frame from the queue."""
        if not self.is_running or self._frame_queue is None:
            return None
        try:
            frame = await asyncio.wait_for(self._frame_queue.get(), timeout=2.0)
            return frame
        except asyncio.TimeoutError:
            return None
            
    async def generate_frames(self):
        """Async generator that yields JPEG frames."""
        await self.start()
        try:
            while self.is_running:
                frame = await self.get_frame()
                if frame is None:
                    break
                yield frame
        finally:
            await self.stop()
            
    async def generate_mjpeg_stream(self):
        """Async generator for MJPEG HTTP streaming (fallback)."""
        async for frame in self.generate_frames():
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

