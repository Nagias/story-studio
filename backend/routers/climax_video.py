"""API video cho cảnh cao trào (dự án vụ án). Xử lý ở services/climax_video.py.

- POST /api/projects/{project_id}/climax-video/pick                 tự chọn cảnh cao trào (tối đa CLIMAX_RATIO số cảnh)
- PUT  /api/projects/{project_id}/climax-video/scenes/{scene_id}   bật/tắt một cảnh
- POST /api/projects/{project_id}/climax-video/run                  chạy nền các cảnh đã chọn (tốn lượt Muse)
- GET  /api/projects/{project_id}/climax-video/status               tiến độ từng cảnh
- GET  /api/projects/{project_id}/climax-video/scenes/{scene_id}/grid?i=1   ảnh grid đang chờ duyệt / đã duyệt
- POST /api/projects/{project_id}/climax-video/scenes/{scene_id}/grid/approve
- POST /api/projects/{project_id}/climax-video/scenes/{scene_id}/grid/reject  body {"feedback": "..."} (vẽ lại lượt sau)

Mỗi cảnh hai pha (28/10/2026): "Tạo video" vẽ grid rồi dừng ở "grid_review"; duyệt grid xong, "Tạo video" lần nữa làm clip.

Làm từng bước theo ý chủ dự án: không tự chạy trong "Sản xuất video dài".
"""
import asyncio
import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from models.schemas import Project
from routers import muse_bridge
from routers.muse_bridge import enqueue_and_wait_muse_task, ensure_local_fleet_runner, is_kind_online, routing_kind
from runners import single_instance
from security import is_within, validate_path_ids
from services import climax_video, project_service

logger = logging.getLogger("story_studio.climax_video_router")

router = APIRouter(prefix="/api", tags=["Climax video"], dependencies=[Depends(validate_path_ids)])

RUNNER_START_WAIT_S = 60   # như image_service: runner vừa bật cần chừng này để đăng ký tài khoản
RUNNABLE = ("selected", "failed", "grid_approved")
KEEP_ON_PICK = ("ready", "grid_review", "grid_approved")   # "Chọn cảnh cao trào" không xoá công đã làm
# Trạng thái đang làm; lúc không có lượt chạy nào mà cảnh còn ở đây là lượt trước bị ngắt (tắt server): chạy lại được
WORKING = ("grid", "clips", "checking")
# Một lượt chạy nền cho mỗi dự án (giữ tham chiếu để task không bị dọn giữa chừng)
_running: dict[str, asyncio.Task] = {}


class SceneToggle(BaseModel):
    enabled: bool


class GridFeedback(BaseModel):
    feedback: str = Field(..., max_length=climax_video.FEEDBACK_MAX)


def _is_running(project_id: str) -> bool:
    task = _running.get(project_id)
    return task is not None and not task.done()


def _state(scene) -> dict:
    value = (scene.metadata or {}).get("climax_video")
    return value if isinstance(value, dict) else {}


async def _load(project_id: str) -> Project:
    try:
        project = await asyncio.to_thread(project_service.get_project, project_id)
    except ValueError as e:   # id dành riêng cho hệ thống (vd _cases)
        raise HTTPException(status_code=400, detail=str(e)) from None
    if project is None:
        raise HTTPException(status_code=404, detail=f"Không có dự án {project_id}")
    return project


def _set_state(scene, state) -> None:
    scene.metadata = dict(scene.metadata or {})
    if state is None:
        scene.metadata.pop("climax_video", None)
    else:
        scene.metadata["climax_video"] = state


@router.post("/projects/{project_id}/climax-video/pick")
async def pick_scenes(project_id: str):
    """Đánh dấu "selected" cho cảnh chọn được; bỏ dấu "selected" cũ của cảnh khác; không đụng cảnh đã "ready"."""
    if _is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này, chờ xong rồi chọn lại")
    project = await _load(project_id)
    chosen = climax_video.pick_climax_scenes(project)
    for scene in project.scenes:
        status = _state(scene).get("status")
        if status in KEEP_ON_PICK or _state(scene).get("grid_approved"):
            continue   # đã có công (grid đã duyệt, kể cả khi làm clip lỗi): không xoá
        if scene.id in chosen:
            _set_state(scene, {"status": "selected"})
        elif status == "selected":
            _set_state(scene, None)
    await asyncio.to_thread(project_service.save_project, project)
    return {"scene_ids": chosen, "limit": climax_video.climax_limit(project)}


@router.put("/projects/{project_id}/climax-video/scenes/{scene_id}")
async def toggle_scene(project_id: str, scene_id: str, req: SceneToggle):
    """Bật (đánh dấu "selected") hoặc tắt một cảnh. Tắt cảnh đã có video: về lại ảnh, clip vẫn giữ trên đĩa."""
    if _is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này, chờ xong rồi sửa")
    project = await _load(project_id)
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"Dự án không có cảnh {scene_id}")
    if not climax_video.is_eligible(scene):
        raise HTTPException(status_code=400, detail="Chỉ cảnh vụ án có hình vẽ (không phải bảng ghim, thẻ miễn trừ) "
                                                    "mới làm video cao trào được")
    status = _state(scene).get("status")
    if req.enabled:
        if status not in ("selected", *KEEP_ON_PICK) and not _state(scene).get("grid_approved"):
            limit = climax_video.climax_limit(project)
            marked = sum(1 for s in project.scenes if _state(s).get("status") and s.id != scene_id)
            if marked >= limit:
                raise HTTPException(status_code=400, detail=f"Đã đủ {limit} cảnh video (tối đa "
                                                            f"{climax_video.CLIMAX_RATIO:.0%} số cảnh): tắt bớt "
                                                            "một cảnh khác trước")
            _set_state(scene, {"status": "selected"})
    else:
        if status == "ready" and scene.media_view_mode == "video":
            scene.media_view_mode = "image"
        _set_state(scene, None)
    await asyncio.to_thread(project_service.save_project, project)
    return {"scene_id": scene_id, "status": _state(scene).get("status")}


async def muse_call_starting_runner(task: dict) -> dict:
    """enqueue_and_wait_muse_task, nhưng Fleet Runner chưa chạy thì bật và chờ nó đăng ký trước (không thì cảnh thất
    bại ngay vì "không có tài khoản online"). Test tắt tự bật runner bằng STORY_STUDIO_DISABLE_FLEET_AUTOSTART."""
    kind = routing_kind(task)   # việc ảnh grid chạy trên tài khoản video (route_kind)
    if not is_kind_online(kind) and not single_instance.autostart_disabled():
        ensure_local_fleet_runner()
        deadline = time.monotonic() + RUNNER_START_WAIT_S
        while not is_kind_online(kind) and time.monotonic() < deadline:
            await asyncio.sleep(2.0)
    call = enqueue_and_wait_muse_task
    if call is _ENQUEUE_ORIGINAL:   # chưa bị thay ở module này: dùng bản hiện hành của muse_bridge (test có thể thay ở đó)
        call = muse_bridge.enqueue_and_wait_muse_task
    return await call(task)


_ENQUEUE_ORIGINAL = enqueue_and_wait_muse_task
_muse_call = muse_call_starting_runner   # tên cũ (test)


async def _run_all(project_id: str, scene_ids: list[str]) -> None:
    for scene_id in scene_ids:
        try:
            await climax_video.run_scene_climax_video(project_id, scene_id, muse_call=muse_call_starting_runner)
        except Exception:   # cảnh này đã được ghi "failed" kèm lý do; làm tiếp cảnh sau
            logger.exception(f"Video cao trào {project_id}/{scene_id}: lỗi ngoài dự kiến")


@router.post("/projects/{project_id}/climax-video/run")
async def run_scenes(project_id: str):
    """Chạy nền lần lượt các cảnh "selected" hoặc "failed" (và cảnh bị ngắt giữa chừng ở lượt trước); trả ngay danh
    sách đưa vào hàng. Tốn lượt Muse."""
    if _is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này")
    project = await _load(project_id)
    queued = [s.id for s in project.scenes
              if climax_video.is_eligible(s) and _state(s).get("status") in RUNNABLE + WORKING]
    if not queued:
        raise HTTPException(status_code=400, detail="Chưa có cảnh nào được chọn: bấm \"Chọn cảnh cao trào\" hoặc bật "
                                                    "từng cảnh trước")
    _running[project_id] = asyncio.create_task(_run_all(project_id, queued))
    return {"queued": queued}


def _scene_of(project: Project, scene_id: str):
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"Dự án không có cảnh {scene_id}")
    return scene


@router.get("/projects/{project_id}/climax-video/scenes/{scene_id}/grid")
async def grid_image(project_id: str, scene_id: str, i: int = 1):
    project = await _load(project_id)
    paths = _state(_scene_of(project, scene_id)).get("grid_paths") or []
    if not 1 <= i <= len(paths):
        raise HTTPException(status_code=404, detail="Cảnh chưa có ảnh grid này")
    path = Path(paths[i - 1])
    if not path.is_file() or not is_within(path, project_service.get_scene_media_paths(project_id, scene_id)["video"].parent):
        raise HTTPException(status_code=404, detail="Không còn file ảnh grid")
    return FileResponse(path, media_type="image/jpeg")


async def _grid_action(fn, *args) -> dict:
    try:
        return await asyncio.to_thread(fn, *args)
    except climax_video.ClimaxVideoError as e:
        raise HTTPException(status_code=400, detail=e.message) from None
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/projects/{project_id}/climax-video/scenes/{scene_id}/grid/approve")
async def approve_grid(project_id: str, scene_id: str):
    if _is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này, chờ xong rồi duyệt")
    state = await _grid_action(climax_video.approve_grid, project_id, scene_id)
    return {"scene_id": scene_id, "status": state.get("status")}


@router.post("/projects/{project_id}/climax-video/scenes/{scene_id}/grid/reject")
async def reject_grid(project_id: str, scene_id: str, body: GridFeedback):
    if _is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này, chờ xong rồi sửa")
    state = await _grid_action(climax_video.reject_grid, project_id, scene_id, body.feedback)
    return {"scene_id": scene_id, "status": state.get("status")}


@router.get("/projects/{project_id}/climax-video/status")
async def climax_status(project_id: str):
    project = await _load(project_id)
    scenes = []
    for scene in project.scenes:
        state = _state(scene)
        if state.get("status"):
            scenes.append({"scene_id": scene.id, "status": state["status"], "error": state.get("error"),
                           **{k: state[k] for k in ("clips", "grids", "grid", "done", "attempts", "grid_version")
                              if k in state},
                           "grid_count": len(state.get("grid_paths") or [])})
    return {
        "running": _is_running(project_id),
        "limit": climax_video.climax_limit(project),
        "eligible": sum(1 for s in project.scenes if climax_video.is_eligible(s)),
        "scenes": scenes,
    }
