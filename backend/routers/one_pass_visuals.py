"""API nút "Tạo hình cho cả dự án" ở trang Cảnh (backend/static/one_pass.js). Xử lý ở services/one_pass_visuals.py.

- GET  /api/projects/{project_id}/one-pass/plan     không tốn gì: số ảnh, số video cao trào, số lượt Muse, điều kiện thiếu
- POST /api/projects/{project_id}/one-pass/run      chạy nền (tốn lượt Muse); đang chạy, hoặc luồng cao trào cũ đang chọn
                                                    cảnh / tạo video, thì 409
- GET  /api/projects/{project_id}/one-pass/status   tiến độ: giai đoạn, cảnh đang làm, đã xong/tổng, lỗi, bỏ qua
- POST /api/projects/{project_id}/one-pass/stop     dừng sau bước đang làm

Ảnh một cảnh: `one_pass_visuals.draw_scene_image()`, đúng việc "Muse 2K" của nút trên thẻ và của khối xem trước prompt
(khoá hình services/scene_locks.py), chỉ Muse, không rơi sang nguồn ảnh trả phí. Video một cảnh cao trào:
`climax_video.run_scene_climax_video(auto_approve_grid=True)`. Cả hai gọi Muse bằng đúng hàm của luồng cao trào
(`routers/climax_video.muse_call_starting_runner`: bật Fleet Runner nếu chưa chạy rồi đưa vào hàng việc và chờ).
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from models.schemas import Project
from routers import climax_video as climax_router
from routers import muse_bridge
from security import validate_path_ids
from services import climax_video, one_pass_visuals, project_service

logger = logging.getLogger("story_studio.one_pass_router")

router = APIRouter(prefix="/api", tags=["One-pass visuals"], dependencies=[Depends(validate_path_ids)])

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


def usable_video_accounts() -> int:
    """Số tài khoản Muse video dùng được: rõ loại, đã đăng nhập, không bị khoá hạn mức (không đòi đang online, vì
    muse_call_starting_runner tự bật Fleet Runner)."""
    return sum(1 for a in muse_bridge.muse_accounts
               if muse_bridge.account_kind(a) == "video" and muse_bridge.is_account_available(a))


async def run_climax_scene(project_id: str, scene_id: str) -> dict:
    return await climax_video.run_scene_climax_video(project_id, scene_id,
                                                     muse_call=climax_router.muse_call_starting_runner,
                                                     auto_approve_grid=True)


@router.get("/projects/{project_id}/one-pass/plan")
async def one_pass_plan(project_id: str):
    project = await _load(project_id)
    data = await asyncio.to_thread(one_pass_visuals.plan, project, usable_video_accounts())
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
        data = await asyncio.to_thread(one_pass_visuals.plan, project, usable_video_accounts())
        if not data["images"] and not data["climax_videos"]:
            raise HTTPException(status_code=400, detail="Không còn ảnh hay video cao trào nào làm được"
                                                        + (" (các cảnh cao trào còn thiếu điều kiện)"
                                                           if data["missing"] else ""))

        async def draw(scene_id: str) -> dict:
            return await one_pass_visuals.draw_scene_image(project_id, scene_id,
                                                           climax_router.muse_call_starting_runner)

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
