"""API khoá bối cảnh (nơi lặp lại ở từ 2 cảnh trở lên). Xử lý ở services/location_sheets.py.

- GET    /api/projects/{project_id}/locations                          danh sách, cảnh của từng nơi, trạng thái tìm
- POST   /api/projects/{project_id}/locations/analyze                  LLM tìm bối cảnh lặp lại (chạy nền; 1 lượt LLM)
- POST   /api/projects/{project_id}/locations                          chủ dự án tự thêm một bối cảnh
- PUT    /api/projects/{project_id}/locations/{location_id}            sửa tên, mô tả cố định, danh sách cảnh
- DELETE /api/projects/{project_id}/locations/{location_id}            bỏ khỏi danh sách (ảnh chuẩn vẫn giữ trên đĩa)
- POST   /api/projects/{project_id}/locations/{location_id}/draw       Muse vẽ ảnh chuẩn (chạy nền; 1 lượt Muse ảnh)
- POST   /api/projects/{project_id}/locations/{location_id}/approve    duyệt (từ đây ảnh cảnh của nơi này dùng khoá)
- POST   /api/projects/{project_id}/locations/{location_id}/reject     ghi chỗ sai (vẽ lại sẽ sửa đúng chỗ đó)
- GET    /api/projects/{project_id}/locations/{location_id}/plate      ảnh chuẩn hiện tại
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from routers.climax_video import muse_call_starting_runner
from security import is_within, require_safe_id, validate_path_ids
from services import location_sheets as ls
from services import project_service
from services.case_adaptation_steps import StepFailed

logger = logging.getLogger("story_studio.location_sheets_router")

router = APIRouter(prefix="/api", tags=["Location sheets"], dependencies=[Depends(validate_path_ids)])

_drawing: dict[tuple[str, str], asyncio.Task] = {}
_analyzing: dict[str, asyncio.Task] = {}


class LocationBody(BaseModel):
    name_vi: str = Field(..., max_length=ls.NAME_MAX)
    design_en: str = Field(..., max_length=ls.MAX_DESIGN_CHARS)
    scene_ids: list[str] = Field(default_factory=list, max_length=500)


class LocationEdit(BaseModel):
    name_vi: Optional[str] = Field(None, max_length=ls.NAME_MAX)
    design_en: Optional[str] = Field(None, max_length=ls.MAX_DESIGN_CHARS)
    scene_ids: Optional[list[str]] = Field(None, max_length=500)


class FeedbackBody(BaseModel):
    feedback: str = Field(..., max_length=ls.FEEDBACK_MAX)


def _busy(task: Optional[asyncio.Task]) -> bool:
    return task is not None and not task.done()


def _is_drawing(project_id: str, location_id: str) -> bool:
    return _busy(_drawing.get((project_id, location_id)))


def _loc_json(project_id: str, loc: ls.LocationSheet) -> dict:
    data = loc.model_dump(mode="json", exclude={"plate_path", "versions", "thread_url"})
    has_plate = bool(loc.plate_path and Path(loc.plate_path).is_file())
    data["plate_url"] = (f"/api/projects/{project_id}/locations/{loc.location_id}/plate?v={len(loc.versions)}"
                         if has_plate else None)
    data["versions"] = len(loc.versions)
    data["drawing"] = _is_drawing(project_id, loc.location_id)
    return data


async def _call(fn, *args):
    try:
        return await asyncio.to_thread(fn, *args)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:   # LocationError, id dành riêng cho hệ thống (vd _cases)
        raise HTTPException(status_code=400, detail=str(e)) from None


def _overview(project_id: str) -> dict:
    project = project_service.get_project(project_id)
    if project is None:
        raise LookupError(f"Không có dự án {project_id}")
    data = ls.load_locations(project_id)
    return {
        "locations": [_loc_json(project_id, v) for v in data.locations.values()],
        "scene_location": ls.scene_location_map(data),
        "analyzed_at": data.analyzed_at,
        "analysis_error": data.analysis_error,
        "analyzing": _busy(_analyzing.get(project_id)),
        "eligible_scenes": len(ls.eligible_scenes(project)),
        "min_scenes": ls.MIN_SCENES,
    }


@router.get("/projects/{project_id}/locations")
async def list_locations(project_id: str):
    return await _call(_overview, project_id)


async def _analyze(project_id: str) -> None:
    try:
        await ls.analyze_locations(project_id)
    except (StepFailed, ls.LocationError) as e:
        await asyncio.to_thread(ls.record_analysis_error, project_id, str(e))
    except Exception as e:   # lỗi ngoài dự kiến: ghi log và báo lên giao diện, không im lặng
        logger.exception(f"Tìm bối cảnh {project_id}: lỗi ngoài dự kiến")
        await asyncio.to_thread(ls.record_analysis_error, project_id, f"Lỗi ngoài dự kiến: {e}")


@router.post("/projects/{project_id}/locations/analyze")
async def analyze(project_id: str):
    if _busy(_analyzing.get(project_id)):
        raise HTTPException(status_code=409, detail="Đang tìm bối cảnh cho dự án này")
    if any(_is_drawing(p, loc) for p, loc in _drawing if p == project_id):
        raise HTTPException(status_code=409, detail="Muse đang vẽ ảnh chuẩn bối cảnh, chờ xong rồi tìm lại")

    def prepare():
        project = project_service.get_project(project_id)
        if project is None:
            raise LookupError(f"Không có dự án {project_id}")
        if len(ls.eligible_scenes(project)) < ls.MIN_SCENES:
            raise ls.LocationError(f"Dự án cần ít nhất {ls.MIN_SCENES} cảnh có hình vẽ mới tìm được bối cảnh lặp lại")

    await _call(prepare)
    _analyzing[project_id] = asyncio.create_task(_analyze(project_id))
    return {"analyzing": True}


@router.post("/projects/{project_id}/locations")
async def create(project_id: str, body: LocationBody):
    for s in body.scene_ids:
        require_safe_id(s, "scene_id")
    loc = await _call(ls.create_location, project_id, body.name_vi, body.design_en, body.scene_ids)
    return _loc_json(project_id, loc)


@router.put("/projects/{project_id}/locations/{location_id}")
async def edit(project_id: str, location_id: str, body: LocationEdit):
    require_safe_id(location_id, "location_id")
    for s in body.scene_ids or []:
        require_safe_id(s, "scene_id")
    if _is_drawing(project_id, location_id):
        raise HTTPException(status_code=409, detail="Muse đang vẽ ảnh chuẩn của bối cảnh này")
    loc = await _call(ls.edit_location, project_id, location_id, body.name_vi, body.design_en, body.scene_ids)
    return _loc_json(project_id, loc)


@router.delete("/projects/{project_id}/locations/{location_id}")
async def remove(project_id: str, location_id: str):
    require_safe_id(location_id, "location_id")
    if _is_drawing(project_id, location_id):
        raise HTTPException(status_code=409, detail="Muse đang vẽ ảnh chuẩn của bối cảnh này")
    await _call(ls.remove_location, project_id, location_id)
    return {"location_id": location_id, "removed": True}


async def _draw(project_id: str, location_id: str) -> None:
    try:
        await ls.draw_plate(project_id, location_id, muse_call_starting_runner)
    except Exception as e:   # draw_plate đã ghi "failed" cho lỗi Muse; lỗi khác ghi log và trạng thái để còn biết
        logger.exception(f"Vẽ ảnh chuẩn bối cảnh {project_id}/{location_id}: lỗi ngoài dự kiến")
        await asyncio.to_thread(ls.mark_draw_crashed, project_id, location_id, f"Lỗi ngoài dự kiến: {e}")


@router.post("/projects/{project_id}/locations/{location_id}/draw")
async def draw(project_id: str, location_id: str):
    require_safe_id(location_id, "location_id")
    if _is_drawing(project_id, location_id):
        raise HTTPException(status_code=409, detail="Muse đang vẽ ảnh chuẩn của bối cảnh này")
    data = await _call(ls.load_locations, project_id)
    if location_id not in data.locations:
        raise HTTPException(status_code=404, detail=f"Dự án không có bối cảnh {location_id}")
    _drawing[(project_id, location_id)] = asyncio.create_task(_draw(project_id, location_id))
    return {"location_id": location_id, "drawing": True}


@router.post("/projects/{project_id}/locations/{location_id}/approve")
async def approve(project_id: str, location_id: str):
    require_safe_id(location_id, "location_id")
    return _loc_json(project_id, await _call(ls.approve_plate, project_id, location_id))


@router.post("/projects/{project_id}/locations/{location_id}/reject")
async def reject(project_id: str, location_id: str, body: FeedbackBody):
    require_safe_id(location_id, "location_id")
    return _loc_json(project_id, await _call(ls.reject_plate, project_id, location_id, body.feedback))


@router.get("/projects/{project_id}/locations/{location_id}/plate")
async def plate_image(project_id: str, location_id: str):
    require_safe_id(location_id, "location_id")
    data = await _call(ls.load_locations, project_id)
    loc = data.locations.get(location_id)
    path = Path(loc.plate_path) if loc and loc.plate_path else None
    if path is None or not path.is_file() or not is_within(path, ls.locations_dir(project_id)):
        raise HTTPException(status_code=404, detail="Bối cảnh chưa có ảnh chuẩn")
    return FileResponse(path, media_type="image/jpeg")
