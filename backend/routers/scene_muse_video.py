"""API video Muse của một cảnh theo độ dài lời thoại (nút "Muse Video" trên thẻ cảnh). Xử lý ở services/dialogue_video.py.

- GET  /api/projects/{project_id}/scenes/{scene_id}/muse-video/plan     số video Muse cần (mỗi video một lượt Muse),
                                                                       lời kể từng đoạn; không tốn gì
- POST /api/projects/{project_id}/scenes/{scene_id}/muse-video/run      chạy nền (tốn đúng số lượt trong kế hoạch)
- GET  /api/projects/{project_id}/scenes/{scene_id}/muse-video/status   tiến độ (đang làm video thứ mấy, lỗi)
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from routers.climax_video import muse_call_starting_runner
from security import validate_path_ids
from services import dialogue_video as dv
from services import project_service

logger = logging.getLogger("story_studio.scene_muse_video_router")

router = APIRouter(prefix="/api", tags=["Scene Muse video"], dependencies=[Depends(validate_path_ids)])

_running: dict[tuple[str, str], asyncio.Task] = {}


def _is_running(project_id: str, scene_id: str) -> bool:
    task = _running.get((project_id, scene_id))
    return task is not None and not task.done()


async def _call(fn, *args):
    try:
        return await asyncio.to_thread(fn, *args)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except dv.DialogueVideoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except ValueError as e:   # id dành riêng cho hệ thống (vd _cases)
        raise HTTPException(status_code=400, detail=str(e)) from None


def _plan(project_id: str, scene_id: str) -> dict:
    project = project_service.get_project(project_id)
    if project is None:
        raise LookupError(f"Không có dự án {project_id}")
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if scene is None:
        raise LookupError(f"Dự án không có cảnh {scene_id}")
    plan = dv.scene_plan(project, scene)
    state = dv.scene_state(scene)
    plan["done_videos"] = len(state.get("clips") or []) if [s.get("text") for s in state.get("segments") or []] == \
        [s["text"] for s in plan["segments"]] else 0
    return plan


@router.get("/projects/{project_id}/scenes/{scene_id}/muse-video/plan")
async def plan(project_id: str, scene_id: str):
    return await _call(_plan, project_id, scene_id)


async def _run(project_id: str, scene_id: str) -> None:
    try:
        await dv.run_scene(project_id, scene_id, muse_call_starting_runner)
    except Exception:   # run_scene đã ghi "failed" cho lỗi đã biết; lỗi khác ghi log để còn biết
        logger.exception(f"Video theo lời thoại {project_id}/{scene_id}: lỗi ngoài dự kiến")


@router.post("/projects/{project_id}/scenes/{scene_id}/muse-video/run")
async def run(project_id: str, scene_id: str):
    if _is_running(project_id, scene_id):
        raise HTTPException(status_code=409, detail="Đang làm video Muse cho cảnh này")
    state = await _call(dv.prepare_run, project_id, scene_id)
    _running[(project_id, scene_id)] = asyncio.create_task(_run(project_id, scene_id))
    return {"scene_id": scene_id, "video_count": state["video_count"], "done_videos": len(state["clips"]),
            "muse_calls_needed": state["video_count"] - len(state["clips"])}


def _status(project_id: str, scene_id: str) -> dict:
    _, scene = dv.load_scene(project_id, scene_id)
    state = dv.scene_state(scene)
    return {"scene_id": scene_id, "running": _is_running(project_id, scene_id),
            **{k: state.get(k) for k in ("status", "error", "current", "video_count", "muse_calls", "video_seconds",
                                         "narration_seconds")},
            "done_videos": len(state.get("clips") or [])}


@router.get("/projects/{project_id}/scenes/{scene_id}/muse-video/status")
async def status(project_id: str, scene_id: str):
    return await _call(_status, project_id, scene_id)
