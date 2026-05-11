"""
Shared state module for routers.
Contains global variables and service instances that need to be accessed across multiple routers.
"""
import asyncio
from typing import Optional
from services.agent import FridaAgent
from services.frida_core import FridaCore
from services.streamer import ScreenStreamer, ScrcpyStreamer
from services.ai_engine import AIEngine
from services.analyzer import APKAnalyzer
from services.native_analyzer import NativeAnalyzer

# Service Instances (Singleton)
agent = FridaAgent()
frida_core = FridaCore()
streamer = ScreenStreamer()
scrcpy_streamer = ScrcpyStreamer()
ai_engine = AIEngine()
analyzer = APKAnalyzer()
native_analyzer = NativeAnalyzer()

# Frida Process State
frida_process: Optional[object] = None
frida_message_queues: dict = {}

# WebSocket connections
active_websockets: dict = {}

# Analysis Context — stored after AI analysis, used by refine_script
last_analysis_context: dict = {
    "native_prompt": "",    # R2 report or ADB recon data
    "java_code": "",        # Main class source code
    "manifest_xml": "",     # AndroidManifest.xml
    "package_name": "",     # Package name
}
