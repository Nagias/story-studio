"""API nút "Tạo hình cho cả dự án" ở trang Cảnh (backend/static/one_pass.js). Xử lý ở services/one_pass_visuals.py.

- GET  /api/projects/{project_id}/one-pass/plan     không tốn gì: số ảnh, số video cao trào, số lượt Muse, điều kiện thiếu
- POST /api/projects/{project_id}/one-pass/run      chạy nền (tốn lượt Muse); đang chạy, hoặc luồng cao trào cũ đang chọn
                                                    cảnh / tạo video, thì 409
- GET  /api/projects/{project_id}/one-pass/status   tiến độ: giai đoạn, cảnh đang làm, đã xong/tổng, lỗi, bỏ qua
- POST /api/projects/{project_id}/one-pass/stop     dừng sau bước đang làm

Ảnh một cảnh: gọi đúng route tạo ảnh cảnh của nút trên thẻ (`routers/api.generate_scene_image`: khoá nhân vật và khoá
bối cảnh qua services/scene_locks.py), nguồn Muse; đường đó tự rơi sang 9router khi Muse lỗi thì giữ nguyên nhưng lý do
ghi vào kết quả (`fallbacks`). Video một cảnh cao trào: `climax_video.run_scene_climax_video(auto_approve_grid=True)`
với đúng hàm gọi Muse của luồng cao trào (`routers/climax_video.muse_call_starting_runner`).
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from models.schemas import ImageGenRequest, Project
from routers import api as api_router
from routers import climax_video as climax_router
from security import validate_path_ids
from services import climax_video, one_pass_visuals, project_service

logger = logging.getLogger("story_studio.one_pass_router")

router = APIRouter(prefix="/api", tags=["One-pass visuals"], dependencies=[Depends(validate_path_ids)])

IMAGE_PROVIDER = "meta_muse_cloud"   # dùng Muse (CLAUDE.md đường cấm 4: không tự chọn nguồn ảnh trả phí)


async def _load(project_id: str) -> Project:
    try:
        project = await asyncio.to_thread(project_service.get_project, project_id)
    except ValueError as e:   # id dành riêng cho hệ thống (vd _cases)
        raise HTTPException(status_code=400, detail=str(e)) from None
    if project is None:
        raise HTTPException(status_code=404, detail=f"Không có dự án {project_id}")
    return project


def _refuse_while_climax_busy(project_id: str) -> None:
    """Luồng cao trào cũ (AI chọn cảnh, tạo video) đang chạy hay đang bắt đầu cho dự án này thì không chạy chen."""
    if climax_router._is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này, chờ xong rồi bấm lại")
    if climax_router._is_picking(project_id):
        raise HTTPException(status_code=409, detail="AI đang chọn cảnh cao trào cho dự án này, chờ xong rồi bấm lại")
    if project_id in climax_router._starting:
        raise HTTPException(status_code=409, detail="Dự án đang bắt đầu một lượt chọn cảnh hoặc tạo video, chờ chút "
                                                    "rồi bấm lại")


async def draw_scene_image(project_id: str, scene_id: str) -> dict:
    """Vẽ ảnh một cảnh bằng đúng route của nút trên thẻ; trả {"error", "provider", "fallback_reason"}."""
    try:
        res = await api_router.generate_scene_image(project_id, scene_id, ImageGenRequest(provider=IMAGE_PROVIDER))
    except HTTPException as e:
        return {"error": str(e.detail)}
    if res.get("is_placeholder"):   # ảnh tạm offline không phải ảnh AI: không tính là xong
        return {"error": "Chỉ tạo được ảnh tạm offline (không phải ảnh AI)", "provider": res.get("provider")}
    return {"error": None, "provider": res.get("provider"), "fallback_reason": res.get("fallback_reason")}


async def run_climax_scene(project_id: str, scene_id: str) -> dict:
    return await climax_video.run_scene_climax_video(project_id, scene_id,
                                                     muse_call=climax_router.muse_call_starting_runner,
                                                     auto_approve_grid=True)


@router.get("/projects/{project_id}/one-pass/plan")
async def one_pass_plan(project_id: str):
    project = await _load(project_id)
    data = await asyncio.to_thread(one_pass_visuals.plan, project)
    return {**data, "running": one_pass_visuals.is_running(project_id)}


@router.post("/projects/{project_id}/one-pass/run")
async def one_pass_run(project_id: str):
    """Chạy nền: ảnh còn thiếu của mọi cảnh, rồi từng cảnh cao trào đủ điều kiện (lưới, tự duyệt, clip). Cảnh thiếu
    điều kiện bỏ qua kèm lý do. Trả kế hoạch đã chạy."""
    # Kiểm và giữ chỗ liền nhau, không có await ở giữa: yêu cầu thứ hai tới trong lúc đọc đĩa thì bị 409
    _refuse_while_climax_busy(project_id)
    try:
        one_pass_visuals.reserve(project_id)
    except one_pass_visuals.OnePassBusy as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    try:
        project = await _load(project_id)
        if getattr(project, "is_demo", False):
            raise HTTPException(status_code=400, detail="Dự án mẫu chỉ để xem, không tạo hình được")
        data = await asyncio.to_thread(one_pass_visuals.plan, project)
        if not data["images"] and not data["climax_videos"]:
            raise HTTPException(status_code=400, detail="Không còn ảnh hay video cao trào nào làm được"
                                                        + (" (các cảnh cao trào còn thiếu điều kiện)"
                                                           if data["missing"] else ""))

        async def draw(scene_id: str) -> dict:
            return await draw_scene_image(project_id, scene_id)

        async def climax(scene_id: str) -> dict:
            return await run_climax_scene(project_id, scene_id)

        job = one_pass_visuals.start(project_id, data, project, draw, climax, stop_words=climax_router.STOP_RUN_WORDS)
        return {**data, "status": job.as_json()}
    finally:
        one_pass_visuals.release(project_id)


@router.get("/projects/{project_id}/one-pass/status")
async def one_pass_status(project_id: str):
    await _load(project_id)
    return one_pass_visuals.status(project_id)


@router.post("/projects/{project_id}/one-pass/stop")
async def one_pass_stop(project_id: str):
    await _load(project_id)
    return one_pass_visuals.request_stop(project_id)
