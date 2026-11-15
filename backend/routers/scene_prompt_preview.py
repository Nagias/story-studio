"""Xem trước prompt thật gửi Muse cho một cảnh (thẻ cảnh). Xử lý ở services/scene_prompt_preview.py; không tốn gì.

- GET /api/projects/{project_id}/scenes/{scene_id}/muse-prompt?kind=image   chuỗi ảnh 2K Muse nhận, ảnh đính kèm
- GET /api/projects/{project_id}/scenes/{scene_id}/muse-prompt?kind=video   prompt từng video theo lời thoại, hoặc
                                                                            bản giao việc video cao trào
"""
import asyncio

from fastapi import APIRouter, HTTPException, Query

from security import require_safe_id
from services import climax_video, project_service
from services import dialogue_video as dv
from services import scene_prompt_preview as spp
from services.project_service import ProjectUnreadableError

router = APIRouter(prefix="/api", tags=["Scene Muse prompt preview"])

KINDS = {"image": spp.image_preview, "video": spp.video_preview}


def _preview(project_id: str, scene_id: str, kind: str) -> dict:
    project = project_service.get_project(project_id)
    if project is None:
        raise LookupError(f"Không có dự án {project_id}")
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if scene is None:
        raise LookupError(f"Dự án không có cảnh {scene_id}")
    return {"scene_id": scene_id, **KINDS[kind](project, scene)}


@router.get("/projects/{project_id}/scenes/{scene_id}/muse-prompt")
async def muse_prompt(project_id: str, scene_id: str, kind: str = Query("image")):
    require_safe_id(project_id, "project_id")
    require_safe_id(scene_id, "scene_id")
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="kind phải là image hoặc video")
    try:
        return await asyncio.to_thread(_preview, project_id, scene_id, kind)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ProjectUnreadableError as e:   # project.json hỏng: giữ file, báo rõ như API dự án
        raise HTTPException(status_code=409, detail=str(e)) from None
    except (ValueError, climax_video.ClimaxVideoError, dv.DialogueVideoError) as e:
        # chưa xem trước được (PromptPreviewError, danh sách nhân vật/bối cảnh hỏng), id dành riêng (vd _cases)
        raise HTTPException(status_code=400, detail=str(e)) from None
