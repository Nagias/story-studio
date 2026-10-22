"""Dữ liệu gói SEO YouTube của một dự án: `Project.youtube_seo`.

Chỉ `services/youtube_seo_pack.py` ghi trường này (qua `project_service.save_project()`); lưu dự án từ giao diện
(PUT /api/projects/{id}) không chạm tới nó.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

KeywordSource = Literal["youtube_suggest", "youtube_data_api", "manual"]


class TopVideo(BaseModel):
    """Một video đứng đầu kết quả tìm kiếm YouTube (YouTube Data API), giữ nguyên dữ liệu thô làm bằng chứng."""
    video_id: str
    title: str
    channel: str = ""
    tags: list[str] = Field(default_factory=list)


class KeywordCandidate(BaseModel):
    keyword: str
    source: KeywordSource
    evidence: str = ""   # vd "gợi ý số 2 của ô tìm kiếm YouTube" hoặc "có trong tags của 4/10 video đầu"


class KeywordResearch(BaseModel):
    seed: str
    language: Literal["vi", "en"]
    fetched_at: datetime
    candidates: list[KeywordCandidate] = Field(default_factory=list)
    top_videos: list[TopVideo] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)   # nguồn nào lỗi thì ghi lý do bằng lời thường


class Chapter(BaseModel):
    start_s: int
    label: str


class SeoPack(BaseModel):
    language: Literal["vi", "en"]
    keywords: list[str]                      # từ khoá đã chọn, từ khoá chính đứng đầu
    title: str
    title_options: list[str] = Field(default_factory=list)
    description: str
    tags: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)
    thumbnail_lines: list[str] = Field(default_factory=list)
    video_seconds: float
    generated_at: datetime
    edited_at: Optional[datetime] = None


class YoutubeSeoState(BaseModel):
    research: Optional[KeywordResearch] = None
    pack: Optional[SeoPack] = None
