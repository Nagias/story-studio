"""API video cho cảnh cao trào (dự án vụ án). Xử lý ở services/climax_video.py.

- POST /api/projects/{project_id}/climax-video/pick                 tự chọn cảnh cao trào (tối đa CLIMAX_RATIO số cảnh)
- PUT  /api/projects/{project_id}/climax-video/scenes/{scene_id}   bật/tắt một cảnh
- POST /api/projects/{project_id}/climax-video/run                  chạy nền các cảnh đã chọn (tốn lượt Muse)
- GET  /api/projects/{project_id}/climax-video/status               tiến độ từng cảnh

Làm từng bước theo ý chủ dự án: không tự chạy trong "Sản xuất video dài".
"""
import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from models.schemas import Project
from routers import muse_bridge
from routers.muse_bridge import enqueue_and_wait_muse_task, ensure_local_fleet_runner, is_kind_online, task_kind
from runners import single_instance
from security import validate_path_ids
from services import climax_video, project_service

logger = logging.getLogger("story_studio.climax_video_router")

router = APIRouter(prefix="/api", tags=["Climax video"], dependencies=[Depends(validate_path_ids)])

RUNNER_START_WAIT_S = 60   # như image_service: runner vừa bật cần chừng này để đăng ký tài khoản
RUNNABLE = ("selected", "failed")
# Trạng thái đang làm; lúc không có lượt chạy nào mà cảnh còn ở đây là lượt trước bị ngắt (tắt server): chạy lại được
WORKING = ("grid", "clips", "checking")
# Một lượt chạy nền cho mỗi dự án (giữ tham chiếu để task không bị dọn giữa chừng)
_running: dict[str, asyncio.Task] = {}


class SceneToggle(BaseModel):
    enabled: bool


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
        if status == "ready":
            continue
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
        if status not in ("selected", "ready"):
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


async def _muse_call(task: dict) -> dict:
    """enqueue_and_wait_muse_task, nhưng Fleet Runner chưa chạy thì bật và chờ nó đăng ký trước (không thì cảnh thất
    bại ngay vì "không có tài khoản online"). Test tắt tự bật runner bằng STORY_STUDIO_DISABLE_FLEET_AUTOSTART."""
    kind = task_kind(task.get("mode"))
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


async def _run_all(project_id: str, scene_ids: list[str]) -> None:
    for scene_id in scene_ids:
        try:
            await climax_video.run_scene_climax_video(project_id, scene_id, muse_call=_muse_call)
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


@router.get("/projects/{project_id}/climax-video/status")
async def climax_status(project_id: str):
    project = await _load(project_id)
    scenes = []
    for scene in project.scenes:
        state = _state(scene)
        if state.get("status"):
            scenes.append({"scene_id": scene.id, "status": state["status"], "error": state.get("error"),
                           **{k: state[k] for k in ("clips", "grids", "grid", "done", "attempts") if k in state}})
    return {
        "running": _is_running(project_id),
        "limit": climax_video.climax_limit(project),
        "eligible": sum(1 for s in project.scenes if climax_video.is_eligible(s)),
        "scenes": scenes,
    }
