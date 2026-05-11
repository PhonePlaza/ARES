"""
ARES - Automated Reconnaissance and Exploitation System for Android
Main FastAPI application entry point.

This file has been refactored to use APIRouters for better organization.
All endpoints have been moved to the routers/ directory.
"""

from fastapi import FastAPI 
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()


app = FastAPI(
    title="ARES - Android Pentesting Agent",
    description="Automated Android penetration testing with AI-powered script generation",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from routers.device import router as device_router
from routers.streaming import router as streaming_router
from routers.apk import router as apk_router
from routers.ai import router as ai_router
from routers.ai import reports_router
from routers.frida import router as frida_router
from routers.logcat import router as logcat_router


app.include_router(device_router)
app.include_router(streaming_router)
app.include_router(apk_router)
app.include_router(ai_router)
app.include_router(reports_router)
app.include_router(frida_router)
app.include_router(logcat_router)


from routers.state import frida_core

@app.get("/api/status")
async def get_status():
    """Check backend and Frida connection status."""
    device_status = frida_core.connect_device()
    return {
        "backend": "online",
        "frida_connection": device_status
    }


if __name__ == "__main__":

    import uvicorn
    
    print("\n" + "="*50)
    print("  ARES - Android Pentesting Agent")
    print("  Starting server on http://localhost:8000")
    print("="*50 + "\n")
    
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
