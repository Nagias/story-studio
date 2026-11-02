"""DEFAULT_VOICE trong .env là giọng của dự án mới khi yêu cầu không ghi giọng.

Lỗi cũ (rà soát 21/10/2026): config.DEFAULT_VOICE không được dùng ở đâu, mọi chỗ chép cứng "vi-VN-NamMinhNeural",
nên đặt DEFAULT_VOICE trong .env không có tác dụng.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from models.schemas import ProjectCreateRequest
from routers import api as api_module
from services import project_service


def test_new_project_uses_default_voice(isolated_projects_dir, monkeypatch):
    monkeypatch.setattr(project_service, "DEFAULT_VOICE", "vieneu-MaiAnh")
    assert project_service.create_project(ProjectCreateRequest(name="Không ghi giọng")).voice == "vieneu-MaiAnh"
    chosen = project_service.create_project(ProjectCreateRequest(name="Có ghi giọng", voice="en-US-AvaMultilingualNeural"))
    assert chosen.voice == "en-US-AvaMultilingualNeural"


@pytest.mark.asyncio
@pytest.mark.parametrize("default_voice, expected", [
    ("vieneu-MaiAnh", "vieneu-MaiAnh"),                  # giọng Việt: dùng luôn
    ("en-US-AvaMultilingualNeural", "vi-VN-NamMinhNeural"),  # giọng Anh không đọc được truyện Việt: giữ giọng Việt
])
async def test_vietnamese_script_uses_default_voice_when_vietnamese(isolated_projects_dir, monkeypatch,
                                                                   default_voice, expected):
    from main import app

    monkeypatch.setattr(api_module, "DEFAULT_VOICE", default_voice)
    monkeypatch.setattr(project_service, "DEFAULT_VOICE", default_voice)

    from services import story_review
    from tests.story_review_fakes import FakeStoryLLM
    monkeypatch.setattr(story_review, "_story_llm", FakeStoryLLM())   # không gọi 9router
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        resp = await client.post("/api/projects/create-from-script", json={
            "text": "Đêm mưa, Nam bước vào căn nhà cũ.\n\nCánh cửa kẽo kẹt mở ra.",
            "generate_initial_images": False,
        })
    assert resp.status_code == 200, resp.text
    assert resp.json()["voice"] == expected
