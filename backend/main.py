import os
import sys
from pathlib import Path

# Add backend directory to sys.path so imports work from any working directory
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncio

import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from config import STATIC_DIR, PROJECTS_DIR, BGM_DIR, HOST, PORT
from security import LocalAccessMiddleware, is_safe_id
from routers.api import router as api_router, active_renders, active_connections
from routers.muse_bridge import router as muse_bridge_router
from routers.true_crime import router as true_crime_router
from routers.language_versions import router as language_versions_router
from services import case_worker
from services.project_service import ProjectUnreadableError
from services.video_service import get_available_bgm_tracks


async def _start_case_worker():
    """Worker phân tích vụ án (spec 7.1a): đưa việc bị gián đoạn về hàng chờ rồi chạy hàng việc ngầm.
    Trả (stop, task), hoặc (None, None) khi bị tắt bằng STORY_STUDIO_DISABLE_CASE_WORKER=1 hay khi một server khác
    đang chạy worker (bật run.bat hai lần): server này khi đó không đụng tới hàng việc, kể cả việc đang `running`."""
    if case_worker.worker_disabled():
        return None, None
    try:
        held = await asyncio.to_thread(case_worker.acquire_worker_lock)
    except OSError as e:
        print(f"Warning: không tạo được khoá hàng việc phân tích, server này không chạy worker: {e}")
        return None, None
    if not held:
        print("[*] Case worker: một server Story Studio khác đang chạy hàng việc phân tích; server này không chạy worker")
        return None, None
    try:
        recovered = await asyncio.to_thread(case_worker.recover_interrupted)
        if recovered:
            print(f"[*] Case worker: {recovered} việc phân tích bị gián đoạn sẽ chạy lại")
    except Exception as e:  # đĩa lỗi lúc khởi động không được chặn server; worker tự đánh dấu việc lạ
        print(f"Warning recovering case analysis queue: {e}")
    stop = asyncio.Event()
    return stop, asyncio.create_task(case_worker.worker_loop(stop))


async def _stop_case_worker(stop, task) -> None:
    """Dừng ngay, kể cả khi đang chờ LLM: việc đang chạy giữ `running` và được chạy lại ở lần khởi động sau."""
    if task is None:
        return
    stop.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)   # nuốt CancelledError của task con, không nuốt của lifespan
    case_worker.release_worker_lock()


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

    worker_stop, worker_task = await _start_case_worker()
    try:
        yield
    finally:
        await _stop_case_worker(worker_stop, worker_task)

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
# Chỉ cho phép truy cập từ chính máy này (thêm sau CORS để chạy trước)
app.add_middleware(LocalAccessMiddleware)

@app.exception_handler(ProjectUnreadableError)
async def project_unreadable_handler(request, exc: ProjectUnreadableError):
    """project.json hỏng: báo rõ cho giao diện (409), không để route nào coi là "chưa có" rồi ghi đè."""
    return JSONResponse(status_code=409, content={"detail": str(exc), "project_id": exc.project_id})

# Include API Router
app.include_router(api_router)
app.include_router(muse_bridge_router)
app.include_router(true_crime_router)
app.include_router(language_versions_router)

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
