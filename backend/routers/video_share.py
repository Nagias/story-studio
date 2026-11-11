"""API của chốt tỉ lệ video Muse (services/video_share.py).

- GET /api/projects/{project_id}/video-share                         tỉ lệ video Muse có cử động nếu dựng ngay bây giờ
- PUT /api/projects/{project_id}/scenes/{scene_id}/motion-review     body {"ok": true}: chủ dự án đã xem clip, có cử
  động (máy đo bỏ sót cử động nhỏ); {"ok": false}: bỏ duyệt. Gắn với đúng file clip: đổi clip thì phải duyệt lại.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from security import validate_path_ids
from services import project_service, video_share

router = APIRouter(prefix="/api", tags=["Video share"], dependencies=[Depends(validate_path_ids)])


class MotionReview(BaseModel):
    ok: bool


@router.get("/projects/{project_id}/video-share")
async def get_video_share(project_id: str):
    try:
        project = await asyncio.to_thread(project_service.get_project, project_id)
    except ValueError as e:   # id dành riêng cho hệ thống (vd _cases)
        raise HTTPException(status_code=400, detail=str(e)) from None
    if project is None:
        raise HTTPException(status_code=404, detail=f"Không có dự án {project_id}")
    report = await asyncio.to_thread(video_share.project_share, project)
    return {**report, "durations_known": video_share.has_all_durations(project),
            "problem": video_share.gate_problem(report)}


@router.put("/projects/{project_id}/scenes/{scene_id}/motion-review")
async def put_motion_review(project_id: str, scene_id: str, req: MotionReview):
    try:
        stamp = await asyncio.to_thread(video_share.set_motion_review, project_id, scene_id, req.ok)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except video_share.ReviewError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"scene_id": scene_id, "motion_review": stamp}
