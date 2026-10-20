"""
Khi LLM lỗi và cảnh do bộ chia offline tạo, phản hồi phải mang fallback_reason nói rõ vì sao
(lỗi 9router, thiếu key, hay "cảnh a–b (phần i/N)" khi chỉ một phần bài dài chia offline) thay vì lặng lẽ
trả prompt ảnh mẫu chung.
Áp dụng cho 3 route: /api/vox/analyze-script, /api/projects/{id}/vox-script, /api/novel/ingest-chapter.

LLM là hàm giả (monkeypatch SemanticStoryAnalyzer.call_9router_semantic_analyzer); không gọi 9router thật.
Dữ liệu dự án nằm trong thư mục tạm.
"""
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.schemas import ProjectCreateRequest  # noqa: E402
from routers import api as api_module  # noqa: E402
from services import project_service, script_splitter  # noqa: E402

SHORT_TEXT = (
    "Đêm mưa tháng mười, một chiếc taxi dừng trước con hẻm nhỏ. "
    "Người tài xế nhìn qua gương chiếu hậu và thấy bóng người lạ đứng dưới mái hiên. "
    "Sáng hôm sau, cảnh sát tìm thấy chiếc taxi bỏ trống."
)


def _long_story(paragraphs: int = 120) -> str:
    """Khoảng 23.000 ký tự: dài hơn giới hạn một lần gọi 9router nên phải gọi nhiều phần."""
    return "\n\n".join(
        f"Đoạn {i}: Đêm mưa tháng mười, một chiếc taxi dừng trước con hẻm nhỏ. "
        f"Người tài xế nhìn qua gương chiếu hậu và thấy bóng người lạ đứng dưới mái hiên. "
        f"Không ai biết anh ta đã đợi ở đó bao lâu."
        for i in range(1, paragraphs + 1)
    )


def _fake_scenes(chunk: str):
    paras = [p.strip() for p in chunk.split("\n") if p.strip()]
    return [
        {"order": i, "text": p, "narrative_beat": "setting", "image_prompt": f"AI shot {i}",
         "camera_motion": "zoom_in", "estimated_duration": 4.0}
        for i, p in enumerate(paras, start=1)
    ]


def _set_9router_key(monkeypatch, key: str):
    monkeypatch.setattr(script_splitter, "NINEROUTER_API_KEY", key)
    if key:
        monkeypatch.setenv("NINEROUTER_API_KEY", key)
    else:
        monkeypatch.delenv("NINEROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


# Mỗi phần được gọi tối đa 2 lần (lần đầu + một lần thử lại), nên "phần 1 hỏng hẳn" là lần gọi 1 và 2
FIRST_PART_FAILS = (1, 2)
SECOND_PART_FAILS = (2, 3)


def _fake_llm(monkeypatch, fail_calls=(), error="9router HTTP 401: Invalid API key"):
    """9router giả: các lần gọi thứ trong fail_calls (đếm từ 1) lỗi và ghi last_error như hàm thật."""
    calls = []

    async def fake_call(self, text_chunk, *args, **kwargs):
        calls.append(text_chunk)
        if len(calls) in fail_calls:
            self.last_error = error
            return None
        return _fake_scenes(text_chunk)

    monkeypatch.setattr(script_splitter.SemanticStoryAnalyzer, "call_9router_semantic_analyzer", fake_call)
    return calls


@pytest.fixture
def client(isolated_projects_dir, monkeypatch):
    monkeypatch.setattr(api_module, "PROJECTS_DIR", isolated_projects_dir)
    app = FastAPI()
    app.include_router(api_module.router)
    with TestClient(app) as c:
        yield c


# ----------------------------------------------------------------------------- /api/vox/analyze-script

def test_analyze_script_returns_llm_error_as_fallback_reason(client, monkeypatch):
    _set_9router_key(monkeypatch, "dummy-key-for-test")
    calls = _fake_llm(monkeypatch, fail_calls=FIRST_PART_FAILS)

    resp = client.post("/api/vox/analyze-script", json={"text": SHORT_TEXT, "provider": "9router"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(calls) == 2, "lỗi thì thử lại đúng một lần"
    assert body["provider_used"] == "offline_semantic_rules"
    assert body["fallback_reason"] == "9router HTTP 401: Invalid API key"
    assert body["scenes"], "vẫn phải có cảnh từ bộ chia offline"


def test_analyze_script_without_key_says_key_is_missing(client, monkeypatch):
    _set_9router_key(monkeypatch, "")
    calls = _fake_llm(monkeypatch)

    resp = client.post("/api/vox/analyze-script", json={"text": SHORT_TEXT, "provider": "9router"})

    assert resp.status_code == 200, resp.text
    assert calls == [], "không có key thì không gọi LLM"
    assert "NINEROUTER_API_KEY" in resp.json()["fallback_reason"]


def test_analyze_script_long_text_names_the_failed_part(client, monkeypatch):
    _set_9router_key(monkeypatch, "dummy-key-for-test")
    _fake_llm(monkeypatch, fail_calls=SECOND_PART_FAILS, error="9router HTTP 500: upstream timeout")

    resp = client.post("/api/vox/analyze-script", json={"text": _long_story(), "provider": "9router"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider_used"] == "llm_partial", "chỉ phần lỗi chia offline, các phần khác giữ cảnh AI"
    assert "(phần 2/" in body["fallback_reason"]
    assert "HTTP 500" in body["fallback_reason"]


def test_analyze_script_llm_success_has_no_fallback_reason(client, monkeypatch):
    _set_9router_key(monkeypatch, "dummy-key-for-test")
    _fake_llm(monkeypatch)

    resp = client.post("/api/vox/analyze-script", json={"text": SHORT_TEXT, "provider": "9router"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider_used"] == "llm"
    assert body["fallback_reason"] is None


# ----------------------------------------------------------------------------- /api/projects/{id}/vox-script

def _new_project_id() -> str:
    return project_service.create_project(ProjectCreateRequest(name="Fallback test")).id


def test_project_vox_script_returns_fallback_reason(client, monkeypatch):
    _set_9router_key(monkeypatch, "dummy-key-for-test")
    _fake_llm(monkeypatch, fail_calls=FIRST_PART_FAILS)
    project_id = _new_project_id()

    resp = client.post(f"/api/projects/{project_id}/vox-script", json={"text": SHORT_TEXT, "provider": "9router"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider_used"] == "offline_semantic_rules"
    assert body["fallback_reason"] == "9router HTTP 401: Invalid API key"
    assert body["added_scenes"] > 0


def test_project_vox_script_llm_success_has_no_fallback_reason(client, monkeypatch):
    _set_9router_key(monkeypatch, "dummy-key-for-test")
    _fake_llm(monkeypatch)
    project_id = _new_project_id()

    resp = client.post(f"/api/projects/{project_id}/vox-script", json={"text": SHORT_TEXT, "provider": "9router"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider_used"] == "llm"
    assert body["fallback_reason"] is None


# ----------------------------------------------------------------------------- /api/novel/ingest-chapter

def test_ingest_chapter_returns_llm_error_as_fallback_reason(client, monkeypatch):
    _set_9router_key(monkeypatch, "dummy-key-for-test")
    _fake_llm(monkeypatch, fail_calls=FIRST_PART_FAILS)

    resp = client.post("/api/novel/ingest-chapter", json={"novel_text": SHORT_TEXT})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fallback_reason"] == "9router HTTP 401: Invalid API key"
    assert body["total_scenes"] > 0, "vẫn phải có cảnh từ bộ chia offline"
    assert project_service.get_project(body["project_id"]) is not None


def test_ingest_chapter_long_text_names_the_failed_part(client, monkeypatch):
    _set_9router_key(monkeypatch, "dummy-key-for-test")
    _fake_llm(monkeypatch, fail_calls=SECOND_PART_FAILS, error="9router HTTP 500: upstream timeout")

    resp = client.post("/api/novel/ingest-chapter", json={"novel_text": _long_story()})

    assert resp.status_code == 200, resp.text
    reason = resp.json()["fallback_reason"]
    assert "(phần 2/" in reason
    assert "HTTP 500" in reason


def test_ingest_chapter_without_key_says_key_is_missing(client, monkeypatch):
    _set_9router_key(monkeypatch, "")

    async def no_key_call(self, text_chunk, *args, **kwargs):
        # Như hàm thật: thiếu key thì trả None mà không ghi last_error
        assert not self.ninerouter_api_key
        return None

    monkeypatch.setattr(script_splitter.SemanticStoryAnalyzer, "call_9router_semantic_analyzer", no_key_call)

    resp = client.post("/api/novel/ingest-chapter", json={"novel_text": SHORT_TEXT})

    assert resp.status_code == 200, resp.text
    assert "NINEROUTER_API_KEY" in resp.json()["fallback_reason"]


def test_ingest_chapter_llm_success_has_no_fallback_reason(client, monkeypatch):
    _set_9router_key(monkeypatch, "dummy-key-for-test")
    _fake_llm(monkeypatch)

    resp = client.post("/api/novel/ingest-chapter", json={"novel_text": SHORT_TEXT})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fallback_reason"] is None
    assert body["total_scenes"] == 1
