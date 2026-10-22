"""API gói SEO YouTube (Bước 4). Xử lý ở services/youtube_seo_pack.py và services/youtube_keywords.py.

- GET  /api/projects/{project_id}/youtube-seo            trạng thái (từ khoá còn hạn, gói đã lưu, kết quả kiểm luật)
- POST /api/projects/{project_id}/youtube-seo/research   tìm từ khoá từ nguồn thật (người dùng bấm mới gọi)
- POST /api/projects/{project_id}/youtube-seo/generate   AI viết gói trong khuôn từ khoá đã chọn (tốn 1+ lần gọi LLM)
- PUT  /api/projects/{project_id}/youtube-seo/pack       lưu bản sửa tay (không đạt luật thì 422 kèm từng luật)
- GET  /api/projects/{project_id}/youtube-seo/download   file .txt để dán vào YouTube Studio
"""
import asyncio
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

import config
from security import validate_path_ids
from services import youtube_keywords, youtube_seo_pack
from services.case_adaptation_steps import StepFailed
from services.youtube_seo_pack import SeoPackError, SeoPackRejected

router = APIRouter(prefix="/api", tags=["YouTube SEO"], dependencies=[Depends(validate_path_ids)])

MAX_MANUAL_KEYWORDS = 50


class ResearchRequest(BaseModel):
    seed: str = Field("", max_length=200)
    sources: list[Literal["youtube_suggest", "youtube_data_api"]] = Field(default_factory=lambda: ["youtube_suggest"])
    manual_keywords: list[str] = Field(default_factory=list, max_length=MAX_MANUAL_KEYWORDS)


class GenerateRequest(BaseModel):
    keywords: list[str] = Field(..., min_length=1, max_length=30)


class PackUpdateRequest(BaseModel):
    title: str = Field(..., max_length=500)
    description: str = Field(..., max_length=20000)
    tags: list[str] = Field(default_factory=list, max_length=200)
    hashtags: list[str] = Field(default_factory=list, max_length=100)


def _checks_json(checks) -> list[dict]:
    return [asdict(c) for c in checks]


def _state_json(project) -> dict:
    state = youtube_seo_pack.current_state(project)
    pack = state.pack
    return {
        "language": youtube_seo_pack.project_language(project),
        "true_crime": youtube_seo_pack.is_true_crime(project),
        "has_youtube_api_key": bool((config.YOUTUBE_API_KEY or "").strip()),
        "research": state.research.model_dump(mode="json") if state.research else None,
        "pack": pack.model_dump(mode="json") if pack else None,
        "checks": _checks_json(youtube_seo_pack.pack_checks(pack)) if pack else [],
    }


async def _load(project_id: str):
    try:
        return await asyncio.to_thread(youtube_seo_pack.load_project, project_id)
    except SeoPackError as e:
        raise HTTPException(status_code=404, detail=e.user_message) from None


@router.get("/projects/{project_id}/youtube-seo")
async def get_youtube_seo(project_id: str):
    return _state_json(await _load(project_id))


@router.post("/projects/{project_id}/youtube-seo/research")
async def research_keywords(project_id: str, req: ResearchRequest):
    project = await _load(project_id)
    try:
        research = await youtube_keywords.research(req.seed, youtube_seo_pack.project_language(project), req.sources,
                                                   req.manual_keywords)
    except youtube_keywords.KeywordSourceError as e:
        raise HTTPException(status_code=400, detail=e.user_message) from None
    await asyncio.to_thread(youtube_seo_pack.save_research, project_id, research)
    return _state_json(await _load(project_id))


@router.post("/projects/{project_id}/youtube-seo/generate")
async def generate_youtube_seo(project_id: str, req: GenerateRequest):
    await _load(project_id)
    try:
        await youtube_seo_pack.generate_pack(project_id, req.keywords)
    except SeoPackRejected as e:
        raise HTTPException(status_code=422, detail={"message": e.user_message, "checks": _checks_json(e.checks)}) from None
    except SeoPackError as e:
        raise HTTPException(status_code=409, detail=e.user_message) from None
    except StepFailed as e:
        raise HTTPException(status_code=502, detail=e.user_message) from None
    return _state_json(await _load(project_id))


@router.put("/projects/{project_id}/youtube-seo/pack")
async def update_youtube_seo_pack(project_id: str, req: PackUpdateRequest):
    await _load(project_id)
    try:
        await asyncio.to_thread(youtube_seo_pack.update_pack, project_id, title=req.title, description=req.description,
                                tags=req.tags, hashtags=req.hashtags)
    except SeoPackRejected as e:
        raise HTTPException(status_code=422, detail={"message": e.user_message, "checks": _checks_json(e.checks)}) from None
    except SeoPackError as e:
        raise HTTPException(status_code=409, detail=e.user_message) from None
    return _state_json(await _load(project_id))


@router.get("/projects/{project_id}/youtube-seo/download")
async def download_youtube_seo(project_id: str):
    project = await _load(project_id)
    try:
        text = youtube_seo_pack.download_text(project)
    except SeoPackRejected as e:
        raise HTTPException(status_code=422, detail={"message": e.user_message, "checks": _checks_json(e.checks)}) from None
    except SeoPackError as e:
        raise HTTPException(status_code=409, detail=e.user_message) from None
    return Response(text.encode("utf-8-sig"), media_type="text/plain; charset=utf-8",   # có BOM để Notepad đọc đúng dấu
                    headers={"Content-Disposition": f'attachment; filename="{project_id}_youtube_seo.txt"'})
