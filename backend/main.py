import os
import sys
from pathlib import Path

# Add backend directory to sys.path so imports work from any working directory
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, Response

from config import STATIC_DIR, PROJECTS_DIR, BGM_DIR, HOST, PORT
from security import LocalAccessMiddleware, is_safe_id
from routers.api import router as api_router, active_renders, active_connections
from routers.muse_bridge import router as muse_bridge_router
from routers.true_crime import router as true_crime_router
from services.video_service import get_available_bgm_tracks

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure directories and default BGM tracks exist
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    BGM_DIR.mkdir(parents=True, exist_ok=True)

    try:
        get_available_bgm_tracks(BGM_DIR)
    except Exception as e:
        print(f"Warning initializing BGM tracks: {e}")

    yield
    # Shutdown logic if any

app = FastAPI(
    title="YouTube Story Maker API",
    version="1.0.0",
    description="Automated Storyboard & Video Production Engine with Edge-TTS and FFmpeg Ken Burns Effects",
    lifespan=lifespan,
)

# CORS: giao diện chạy cùng origin nên chỉ cần cho phép localhost; thêm origin khác qua STORY_STUDIO_ALLOWED_ORIGINS
_extra_origins = [o.strip() for o in os.getenv("STORY_STUDIO_ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}", *_extra_origins],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Chỉ cho phép truy cập từ chính máy này; worker từ xa cần header X-Worker-Token (thêm sau CORS để chạy trước)
app.add_middleware(LocalAccessMiddleware)

# Include API Router
app.include_router(api_router)
app.include_router(muse_bridge_router)
app.include_router(true_crime_router)

# WebSocket endpoint for real-time render progress
@app.websocket("/ws/render/{render_id}")
async def websocket_render_progress(websocket: WebSocket, render_id: str):
    if not is_safe_id(render_id):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    if render_id not in active_connections:
        active_connections[render_id] = []
    active_connections[render_id].append(websocket)

    # Immediately send latest state if exists
    if render_id in active_renders:
        await websocket.send_json(active_renders[render_id])

    try:
        while True:
            # Keep socket alive and listen for client pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        if render_id in active_connections and websocket in active_connections[render_id]:
            active_connections[render_id].remove(websocket)

# Mount Static Files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.get("/")
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(
        """
        <html>
            <head><title>Story Studio Backend</title></head>
            <body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; text-align: center;">
                <h1 style="color: #38bdf8;">🎬 YouTube Story Maker API is Running!</h1>
                <p>FastAPI Backend is online with Edge-TTS, Image Generator, and FFmpeg Video Engine.</p>
                <p><a href="/docs" style="color: #f59e0b; text-decoration: underline;">Open Interactive API Documentation (Swagger)</a></p>
            </body>
        </html>
        """
    )

if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True, app_dir=str(BACKEND_DIR))
