"""API bảng nhân vật đủ góc (truyện chữ và vụ án). Xử lý ở services/character_sheets.py, services/story_cast.py.

- GET  /api/projects/{project_id}/characters                          danh sách, nhân vật từng cảnh, người cần cho video
- POST /api/projects/{project_id}/characters/analyze                  truyện chữ: LLM tìm nhân vật (chạy nền; 1 lượt LLM)
- POST /api/projects/{project_id}/characters/draw-all                 vẽ lần lượt mọi bảng còn thiếu (nền; mỗi bảng 1 lượt Muse)
- GET  /api/projects/{project_id}/characters/draw-all/status          tiến độ lượt vẽ tất cả
- POST /api/projects/{project_id}/characters/draw-all/stop            dừng sau nhân vật đang vẽ
- POST /api/projects/{project_id}/characters/approve-all              duyệt mọi bảng đang chờ duyệt
- PUT  /api/projects/{project_id}/characters/{entity_id}              sửa thiết kế (design_en)
- POST /api/projects/{project_id}/characters/{entity_id}/draw         Muse vẽ bảng (chạy nền; tốn 1 lượt Muse)
- POST /api/projects/{project_id}/characters/{entity_id}/approve      duyệt
- POST /api/projects/{project_id}/characters/{entity_id}/reject       ghi chỗ sai (vẽ lại sẽ sửa đúng chỗ đó)
- GET  /api/projects/{project_id}/characters/{entity_id}/sheet        ảnh bảng hiện tại
- PUT  /api/projects/{project_id}/scenes/{scene_id}/cast              chọn tay nhân vật của cảnh
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
from services import character_sheets as cs
from services import look_batch, project_service, story_cast
from services.case_adaptation_steps import StepFailed

logger = logging.getLogger("story_studio.character_sheets_router")

router = APIRouter(prefix="/api", tags=["Character sheets"], dependencies=[Depends(validate_path_ids)])

NEEDED_STATUSES = ("selected", "failed", "grid", "grid_review", "grid_approved", "clips", "checking")
_drawing: dict[tuple[str, str], asyncio.Task] = {}
_analyzing: dict[str, asyncio.Task] = {}
BATCH_KIND = "characters"


class DesignBody(BaseModel):
    design_en: str = Field(..., max_length=4000)


class FeedbackBody(BaseModel):
    feedback: str = Field(..., max_length=cs.FEEDBACK_MAX)


class CastBody(BaseModel):
    entity_ids: list[str] = Field(default_factory=list, max_length=12)


def _sheet_json(project_id: str, s: cs.CharacterSheet) -> dict:
    data = s.model_dump(mode="json", exclude={"sheet_path", "versions", "thread_url"})
    has_sheet = bool(s.sheet_path and Path(s.sheet_path).is_file())
    data["sheet_url"] = (f"/api/projects/{project_id}/characters/{s.entity_id}/sheet?v={len(s.versions)}"
                         if has_sheet else None)
    data["versions"] = len(s.versions)
    data["drawing"] = _is_drawing(project_id, s.entity_id)
    return data


def _is_drawing(project_id: str, entity_id: str) -> bool:
    t = _drawing.get((project_id, entity_id))
    return t is not None and not t.done()


async def _call(fn, *args):
    try:
        return await asyncio.to_thread(fn, *args)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except cs.CastError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except ValueError as e:   # id dành riêng cho hệ thống (vd _cases)
        raise HTTPException(status_code=400, detail=str(e)) from None


def _busy_analyzing(project_id: str) -> bool:
    task = _analyzing.get(project_id)
    return task is not None and not task.done()


def _overview(project_id: str) -> dict:
    project = project_service.get_project(project_id)
    if project is None:
        raise LookupError(f"Không có dự án {project_id}")
    cast = cs.load_cast(project_id)
    by_scene = cs.scene_cast(project, cast)
    climax = {s.id for s in project.scenes if ((s.metadata or {}).get("climax_video") or {}).get("status") in NEEDED_STATUSES}
    needed = list(dict.fromkeys(e for sid in by_scene if sid in climax for e in by_scene[sid]))
    analyzing = _analyzing.get(project_id)
    return {
        "characters": [_sheet_json(project_id, s) for s in cast.characters.values()],
        "scene_cast": by_scene,
        "needed": needed,
        # vụ án: người lấy từ bảng tên; truyện chữ: tìm bằng LLM (story_cast)
        "source": "case" if cs.case_people(project) else "story",
        "analyzed_at": cast.analyzed_at,
        "analysis_error": cast.analysis_error,
        "analyzing": analyzing is not None and not analyzing.done(),
    }


async def _analyze(project_id: str) -> None:
    try:
        await story_cast.analyze_people(project_id)
    except (StepFailed, cs.CastError) as e:
        await asyncio.to_thread(story_cast.record_analysis_error, project_id, str(e))
    except Exception as e:   # lỗi ngoài dự kiến: ghi log và báo lên giao diện, không im lặng
        logger.exception(f"Tìm nhân vật {project_id}: lỗi ngoài dự kiến")
        await asyncio.to_thread(story_cast.record_analysis_error, project_id, f"Lỗi ngoài dự kiến: {e}")


@router.post("/projects/{project_id}/characters/analyze")
async def analyze(project_id: str):
    task = _analyzing.get(project_id)
    if task is not None and not task.done():
        raise HTTPException(status_code=409, detail="Đang tìm nhân vật cho dự án này")
    if look_batch.is_running(BATCH_KIND, project_id):
        raise HTTPException(status_code=409, detail="Muse đang vẽ tất cả bảng nhân vật, chờ xong hoặc bấm Dừng rồi tìm lại")

    def prepare():
        project = project_service.get_project(project_id)
        if project is None:
            raise LookupError(f"Không có dự án {project_id}")
        if cs.case_people(project):
            raise cs.CastError("Dự án vụ án lấy nhân vật từ bảng tên đã duyệt của vụ án, không cần tìm lại")
        if not story_cast.eligible_scenes(project):
            raise cs.CastError("Dự án chưa có cảnh nào có lời kể hoặc prompt ảnh để tìm nhân vật")
    await _call(prepare)
    _analyzing[project_id] = asyncio.create_task(_analyze(project_id))
    return {"analyzing": True}


@router.get("/projects/{project_id}/characters")
async def list_characters(project_id: str):
    return await _call(_overview, project_id)


@router.put("/projects/{project_id}/characters/{entity_id}")
async def update_design(project_id: str, entity_id: str, body: DesignBody):
    require_safe_id(entity_id, "entity_id")
    if _is_drawing(project_id, entity_id):
        raise HTTPException(status_code=409, detail="Muse đang vẽ bảng của nhân vật này")
    return _sheet_json(project_id, await _call(cs.set_design, project_id, entity_id, body.design_en))


def _reference(project_id: str, entity_id: str) -> Optional[Path]:
    project = project_service.get_project(project_id)
    if project is None:
        raise LookupError(f"Không có dự án {project_id}")
    cast = cs.load_cast(project_id)
    if entity_id not in cast.characters:
        raise LookupError(f"Dự án không có nhân vật {entity_id}")
    # Có ảnh cảnh có người này thì Muse theo đúng nét vẽ của ảnh đó; chưa có (luồng chung: khoá nhân vật trước
    # khi tạo ảnh cảnh) thì vẽ theo phong cách ghi trong thiết kế
    return cs.reference_image(project, cast, entity_id)


async def _draw(project_id: str, entity_id: str, reference: Optional[Path]) -> None:
    try:
        await cs.draw_sheet(project_id, entity_id, muse_call_starting_runner, reference)
    except Exception:   # draw_sheet đã ghi "failed" cho lỗi Muse; lỗi khác ghi log để còn biết
        logger.exception(f"Vẽ bảng nhân vật {project_id}/{entity_id}: lỗi ngoài dự kiến")


@router.post("/projects/{project_id}/characters/{entity_id}/draw")
async def draw(project_id: str, entity_id: str):
    require_safe_id(entity_id, "entity_id")
    if _is_drawing(project_id, entity_id):
        raise HTTPException(status_code=409, detail="Muse đang vẽ bảng của nhân vật này")

    reference = await _call(_reference, project_id, entity_id)
    _drawing[(project_id, entity_id)] = asyncio.create_task(_draw(project_id, entity_id, reference))
    return {"entity_id": entity_id, "drawing": True}


@router.post("/projects/{project_id}/characters/{entity_id}/approve")
async def approve(project_id: str, entity_id: str):
    require_safe_id(entity_id, "entity_id")
    return _sheet_json(project_id, await _call(cs.approve_sheet, project_id, entity_id))


@router.post("/projects/{project_id}/characters/{entity_id}/reject")
async def reject(project_id: str, entity_id: str, body: FeedbackBody):
    require_safe_id(entity_id, "entity_id")
    return _sheet_json(project_id, await _call(cs.reject_sheet, project_id, entity_id, body.feedback))


@router.get("/projects/{project_id}/characters/{entity_id}/sheet")
async def sheet_image(project_id: str, entity_id: str):
    require_safe_id(entity_id, "entity_id")
    cast = await _call(cs.load_cast, project_id)
    s = cast.characters.get(entity_id)
    path = Path(s.sheet_path) if s and s.sheet_path else None
    if path is None or not path.is_file() or not is_within(path, cs.characters_dir(project_id)):
        raise HTTPException(status_code=404, detail="Nhân vật chưa có bảng")
    return FileResponse(path, media_type="image/jpeg")


@router.put("/projects/{project_id}/scenes/{scene_id}/cast")
async def set_cast(project_id: str, scene_id: str, body: CastBody):
    for e in body.entity_ids:
        require_safe_id(e, "entity_id")
    return {"scene_id": scene_id, "entity_ids": await _call(cs.set_scene_cast, project_id, scene_id, body.entity_ids)}


# ------------------------------------------------------------------------------- vẽ tất cả / duyệt tất cả (A6)
async def _batch_draw_one(project_id: str, entity_id: str) -> Optional[str]:
    """Vẽ một bảng bằng đúng hàm của nút "Vẽ bảng" (draw_sheet); ghi vào _drawing để thẻ hiện "đang vẽ" và nút vẽ
    từng người trả 409. Trả lời báo lỗi, None khi vẽ xong."""
    reference = await asyncio.to_thread(_reference, project_id, entity_id)
    task = asyncio.create_task(cs.draw_sheet(project_id, entity_id, muse_call_starting_runner, reference))
    _drawing[(project_id, entity_id)] = task
    try:
        sheet = await task
    except Exception as e:   # draw_sheet chỉ tự ghi "failed" cho lỗi Muse: lỗi khác ghi trạng thái rồi báo lên lượt
        await asyncio.to_thread(cs.mark_draw_crashed, project_id, entity_id, f"Lỗi ngoài dự kiến: {e}")
        raise
    return (sheet.error or "Muse không vẽ được bảng nhân vật") if sheet.status == "failed" else None


async def _batch_still_needed(project_id: str, entity_id: str) -> bool:
    if _is_drawing(project_id, entity_id):
        return False   # người dùng đã bấm vẽ riêng người này
    cast = await asyncio.to_thread(cs.load_cast, project_id)
    s = cast.characters.get(entity_id)
    return s is not None and s.status in cs.BATCH_DRAW_STATUSES


@router.post("/projects/{project_id}/characters/draw-all")
async def draw_all(project_id: str):
    """Vẽ lần lượt (không song song) mọi người chưa có bảng, bị ghi chỗ sai hoặc vẽ lỗi; mỗi người 1 lượt Muse."""
    if _busy_analyzing(project_id):
        raise HTTPException(status_code=409, detail="AI đang tìm nhân vật, chờ xong rồi vẽ")
    try:
        look_batch.reserve(BATCH_KIND, project_id)
    except look_batch.BatchBusy as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    try:
        cast = await _call(cs.load_cast, project_id)
        items = [(s.entity_id, s.name_vi) for s in cs.batch_targets(cast, project_id)
                 if not _is_drawing(project_id, s.entity_id)]
        if not items:
            raise HTTPException(status_code=400, detail="Không còn nhân vật nào cần vẽ bảng")
        look_batch.start(BATCH_KIND, project_id, items,
                         lambda e: _batch_still_needed(project_id, e), lambda e: _batch_draw_one(project_id, e))
    finally:
        look_batch.release(BATCH_KIND, project_id)
    return look_batch.status(BATCH_KIND, project_id)


@router.get("/projects/{project_id}/characters/draw-all/status")
async def draw_all_status(project_id: str):
    return look_batch.status(BATCH_KIND, project_id)


@router.post("/projects/{project_id}/characters/draw-all/stop")
async def draw_all_stop(project_id: str):
    return look_batch.request_stop(BATCH_KIND, project_id)


@router.post("/projects/{project_id}/characters/approve-all")
async def approve_all(project_id: str):
    ids, failed = await _call(cs.approve_all, project_id)
    return {"approved": len(ids), "entity_ids": ids, "failed": failed}
