"""
Bài dài không được cắt mất đoạn cuối: bài được chia phần nhỏ (LLM_PART_MAX_CHARS) theo đoạn văn/câu,
gọi LLM lần lượt, nối cảnh và đánh lại order. Mỗi phần được kiểm (đủ cảnh, có lời kể, không tóm tắt quá
ngắn) và thử lại một lần kèm góp ý. Phần vẫn hỏng thì chỉ phần đó chia offline và fallback_reason nói rõ
cảnh nào; nhiều phần liền nhau lỗi thì ngừng gọi LLM.

LLM là hàm giả; không gọi 9router, Gemini hay OpenRouter thật.
"""
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers import api as api_module  # noqa: E402
from services import script_splitter  # noqa: E402
from services.script_splitter import (  # noqa: E402
    LLM_MAX_FAILED_PARTS_IN_ROW,
    LLM_PART_ATTEMPTS,
    LLM_PART_MAX_CHARS,
    LLM_PART_TIMEOUT_S,
    split_text_for_llm,
)

END_MARKER = "ĐOẠN KẾT CUỐI CÙNG"


def _long_story(paragraphs: int = 120) -> str:
    """Khoảng 23.000 ký tự (8 phần), đoạn cuối mang END_MARKER."""
    body = [
        f"Đoạn {i}: Đêm mưa tháng mười, một chiếc taxi dừng trước con hẻm nhỏ. "
        f"Người tài xế nhìn qua gương chiếu hậu và thấy bóng người lạ đứng dưới mái hiên. "
        f"Không ai biết anh ta đã đợi ở đó bao lâu."
        for i in range(1, paragraphs)
    ]
    body.append(f"{END_MARKER}: cảnh sát tìm thấy chiếc taxi bỏ trống vào sáng hôm sau.")
    return "\n\n".join(body)


def _no_space(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _fake_scenes(chunk: str):
    """Mỗi đoạn văn của phần thành một cảnh, order bắt đầu lại từ 1 như LLM thật."""
    paras = [p.strip() for p in chunk.split("\n") if p.strip()]
    return [
        {"order": i, "text": p, "narrative_beat": "setting", "image_prompt": f"AI shot {i}", "estimated_duration": 4.0}
        for i, p in enumerate(paras, start=1)
    ]


def _summary_scene(chunk: str):
    """LLM lười: cả phần chỉ còn một câu tóm tắt."""
    return [{"order": 1, "text": "Tóm lại, chiếc taxi biến mất.", "image_prompt": "AI shot"}]


def _install_9router(monkeypatch, answer):
    """9router giả. answer(call_no, text_chunk, self) trả danh sách cảnh hoặc None (khi đó tự ghi last_error)."""
    calls = []

    async def fake_call(self, text_chunk, *args, **kwargs):
        calls.append({"text": text_chunk, **kwargs})
        return answer(len(calls), text_chunk, self)

    monkeypatch.setattr(script_splitter.SemanticStoryAnalyzer, "call_9router_semantic_analyzer", fake_call)
    monkeypatch.setattr(script_splitter, "NINEROUTER_API_KEY", "dummy-key-for-test")
    return calls


def _fail(self, error="9router HTTP 500: upstream timeout"):
    self.last_error = error
    return None


@pytest.fixture
def fake_9router(monkeypatch):
    """9router giả luôn làm tốt: ghi lại từng phần nhận được, trả cảnh theo đoạn văn."""
    return _install_9router(monkeypatch, lambda n, chunk, self: _fake_scenes(chunk))


def _parts_of(text: str) -> list:
    return split_text_for_llm(text, LLM_PART_MAX_CHARS)


# ----------------------------------------------------------------------------- chia bài

def test_split_short_text_is_unchanged():
    text = "  Đêm mưa. Một chiếc taxi dừng lại.\r\nKhông ai xuống xe.  "
    assert split_text_for_llm(text, 15000) == [text.strip()]
    assert split_text_for_llm("   ", 15000) == []


def test_split_long_text_keeps_every_character_and_respects_paragraphs():
    text = _long_story()
    assert len(text) > LLM_PART_MAX_CHARS

    parts = _parts_of(text)

    assert len(parts) >= 2
    assert all(len(p) <= LLM_PART_MAX_CHARS for p in parts)
    assert _no_space("".join(parts)) == _no_space(text)
    paragraphs = {p.strip() for p in text.split("\n") if p.strip()}
    for part in parts:
        # Chỉ cắt ở ranh giới đoạn văn khi đoạn nào cũng ngắn hơn giới hạn
        assert all(line in paragraphs for line in part.split("\n"))
    assert parts[-1].endswith("vào sáng hôm sau.")


def test_split_one_huge_paragraph_by_sentence_then_by_word():
    sentence = "Người tài xế nhìn qua gương chiếu hậu và thấy bóng người lạ. "
    paragraph = sentence * 40 + "x" * 250 + " " + "3.5 tỷ đồng biến mất. Hết"
    parts = split_text_for_llm(paragraph, 200)

    assert all(len(p) <= 200 for p in parts)
    assert _no_space("".join(parts)) == _no_space(paragraph)
    # Cắt theo câu, không cắt giữa câu khi câu vừa giới hạn
    assert parts[0].endswith("người lạ.")
    # Không chèn khoảng trắng vào giữa số thập phân
    assert "3.5 tỷ" in " ".join(parts)


# ----------------------------------------------------------------------------- analyze_vox_script_async

@pytest.mark.asyncio
async def test_long_script_calls_9router_part_by_part_and_keeps_the_ending(fake_9router):
    text = _long_story()

    res = await script_splitter.analyze_vox_script_async(full_text=text, provider="9router")

    assert len(fake_9router) == len(_parts_of(text)) >= 2
    assert all(len(c["text"]) <= LLM_PART_MAX_CHARS for c in fake_9router)
    assert _no_space("".join(c["text"] for c in fake_9router)) == _no_space(text)
    assert fake_9router[0]["part_note"].startswith(f"PART 1/{len(fake_9router)}")
    assert "do NOT open with a new hook" in fake_9router[1]["part_note"]

    assert res["provider_used"] == "llm"
    assert "fallback_reason" not in res
    assert [s["order"] for s in res["scenes"]] == list(range(1, len(res["scenes"]) + 1))
    assert res["total_scenes"] == len(res["scenes"])
    assert END_MARKER in res["scenes"][-1]["text"]


@pytest.mark.asyncio
async def test_short_script_still_one_call_without_part_note(fake_9router):
    res = await script_splitter.analyze_vox_script_async(
        full_text="Đêm mưa. Một chiếc taxi dừng lại.", provider="9router")

    assert len(fake_9router) == 1
    assert fake_9router[0]["part_note"] is None
    assert res["provider_used"] == "llm"


@pytest.mark.asyncio
async def test_transient_error_is_retried_once(monkeypatch):
    calls = _install_9router(monkeypatch, lambda n, chunk, self: _fail(self) if n == 2 else _fake_scenes(chunk))
    text = _long_story()

    res = await script_splitter.analyze_vox_script_async(full_text=text, provider="9router")

    assert len(calls) == len(_parts_of(text)) + 1
    assert calls[1]["text"] == calls[2]["text"], "gọi lại đúng phần vừa lỗi"
    assert res["provider_used"] == "llm"
    assert "fallback_reason" not in res


@pytest.mark.asyncio
async def test_summarized_part_is_retried_with_feedback(monkeypatch):
    calls = _install_9router(
        monkeypatch, lambda n, chunk, self: _summary_scene(chunk) if n == 1 else _fake_scenes(chunk))

    res = await script_splitter.analyze_vox_script_async(full_text=_long_story(), provider="9router")

    assert calls[0]["text"] == calls[1]["text"]
    assert "PREVIOUS ATTEMPT REJECTED" in calls[1]["part_note"]
    assert "do not summarize" in calls[1]["part_note"]
    assert calls[1]["part_note"].startswith("PART 1/"), "góp ý đi kèm lời dặn phần, không thay nó"
    assert res["provider_used"] == "llm"
    assert "Tóm lại" not in " ".join(s["text"] for s in res["scenes"])


@pytest.mark.asyncio
async def test_failed_part_goes_offline_alone_and_other_parts_keep_ai_scenes(monkeypatch):
    # Phần 2 hỏng cả hai lần gọi (lần gọi 2 và 3); các phần khác AI làm tốt
    calls = _install_9router(
        monkeypatch, lambda n, chunk, self: _fail(self) if n in (2, 3) else _fake_scenes(chunk))
    text = _long_story()
    parts = _parts_of(text)

    res = await script_splitter.analyze_vox_script_async(full_text=text, provider="9router")

    assert len(calls) == len(parts) + 1
    assert res["provider_used"] == "llm_partial"
    reason = res["fallback_reason"]
    first_offline = len(_fake_scenes(parts[0])) + 1
    assert f"cảnh {first_offline}–" in reason
    assert f"(phần 2/{len(parts)})" in reason
    assert "HTTP 500" in reason
    scenes = res["scenes"]
    assert [s["order"] for s in scenes] == list(range(1, len(scenes) + 1))
    assert scenes[0]["image_prompt"].startswith("AI shot"), "phần 1 giữ cảnh AI"
    assert not scenes[first_offline - 1]["image_prompt"].startswith("AI shot"), "phần 2 là cảnh offline"
    assert scenes[-1]["image_prompt"].startswith("AI shot"), "phần cuối giữ cảnh AI"
    assert END_MARKER in scenes[-1]["text"]
    assert _no_space(parts[1]) in _no_space(" ".join(s["text"] for s in scenes)), "không mất chữ của phần lỗi"


@pytest.mark.asyncio
async def test_summarized_twice_goes_offline_with_reason(monkeypatch):
    _install_9router(
        monkeypatch, lambda n, chunk, self: _summary_scene(chunk) if n in (1, 2) else _fake_scenes(chunk))

    res = await script_splitter.analyze_vox_script_async(full_text=_long_story(), provider="9router")

    assert res["provider_used"] == "llm_partial"
    assert "tóm tắt quá ngắn" in res["fallback_reason"]
    assert "(phần 1/" in res["fallback_reason"]


@pytest.mark.asyncio
async def test_thin_answers_do_not_stop_calling_the_llm(monkeypatch):
    """LLM trả lời nhưng kể ngắn nghĩa là nó vẫn chạy: phần nào cũng được gọi (kèm thử lại), không bỏ qua."""
    calls = _install_9router(monkeypatch, lambda n, chunk, self: _summary_scene(chunk))
    text = _long_story()

    res = await script_splitter.analyze_vox_script_async(full_text=text, provider="9router")

    assert len(calls) == len(_parts_of(text)) * LLM_PART_ATTEMPTS
    assert res["provider_used"] == "offline_semantic_rules"
    assert "tóm tắt quá ngắn" in res["fallback_reason"]


@pytest.mark.asyncio
async def test_llm_down_stops_calling_and_whole_text_goes_offline(monkeypatch):
    calls = _install_9router(monkeypatch, lambda n, chunk, self: _fail(self, "9router HTTP 404: No active credentials"))
    text = _long_story()

    res = await script_splitter.analyze_vox_script_async(full_text=text, provider="9router")

    assert len(calls) == LLM_MAX_FAILED_PARTS_IN_ROW * LLM_PART_ATTEMPTS, "ngừng gọi khi LLM đang hỏng"
    assert res["provider_used"] == "offline_semantic_rules"
    assert res["fallback_reason"] == "9router HTTP 404: No active credentials"
    assert END_MARKER in " ".join(s["text"] for s in res["scenes"]), "offline vẫn chia đủ cả bài"


@pytest.mark.asyncio
async def test_bad_duration_from_llm_does_not_break_totals(monkeypatch):
    def answer(n, chunk, self):
        scenes = _fake_scenes(chunk)
        scenes[0]["estimated_duration"] = "khoảng 4 giây"
        return scenes

    _install_9router(monkeypatch, answer)

    res = await script_splitter.analyze_vox_script_async(full_text="Đêm mưa. Một chiếc taxi dừng lại.", provider="9router")

    assert res["scenes"][0]["estimated_duration"] == 4.0
    assert res["estimated_total_duration"] == 4.0


@pytest.mark.asyncio
async def test_gemini_path_is_split_the_same_way(monkeypatch):
    calls = []

    async def fake_gemini(self, text_chunk, *args, **kwargs):
        calls.append({"text": text_chunk, **kwargs})
        return _fake_scenes(text_chunk)

    monkeypatch.setattr(script_splitter.SemanticStoryAnalyzer, "call_gemini_semantic_analyzer", fake_gemini)
    monkeypatch.setattr(script_splitter, "NINEROUTER_API_KEY", "")
    monkeypatch.delenv("NINEROUTER_API_KEY", raising=False)
    text = _long_story()

    res = await script_splitter.analyze_vox_script_async(
        full_text=text, provider="gemini", gemini_api_key="fake-gemini-key")

    assert len(calls) == len(_parts_of(text))
    assert all(len(c["text"]) <= LLM_PART_MAX_CHARS for c in calls)
    assert _no_space("".join(c["text"] for c in calls)) == _no_space(text)
    assert END_MARKER in res["scenes"][-1]["text"]


@pytest.mark.asyncio
async def test_9router_request_uses_requested_pacing_and_part_timeout(monkeypatch):
    sent = {}

    class FakeResp:
        status_code = 500
        text = "stop here"

    class FakeClient:
        def __init__(self, *args, timeout=None, **kwargs):
            sent["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            sent["payload"] = json
            return FakeResp()

    monkeypatch.setattr(script_splitter.httpx, "AsyncClient", FakeClient)
    analyzer = script_splitter.SemanticStoryAnalyzer(ninerouter_api_key="dummy-key-for-test")

    await analyzer.call_9router_semantic_analyzer("Đêm mưa.", pacing="deep_story", part_note="PART 2/3 test")

    user_content = sent["payload"]["messages"][1]["content"]
    assert "TARGET PACING: deep_story" in user_content
    assert "PART 2/3 test" in user_content
    assert sent["timeout"] == LLM_PART_TIMEOUT_S
    # Chia cảnh dùng model riêng (bản -low nhanh), không dùng model chung của luồng true-crime
    assert sent["payload"]["model"] == script_splitter.NINEROUTER_SCENE_MODEL


@pytest.mark.asyncio
async def test_9router_timeout_has_a_readable_reason(monkeypatch):
    class TimeoutClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise script_splitter.httpx.ReadTimeout("")

    monkeypatch.setattr(script_splitter.httpx, "AsyncClient", TimeoutClient)
    analyzer = script_splitter.SemanticStoryAnalyzer(ninerouter_api_key="dummy-key-for-test")

    assert await analyzer.call_9router_semantic_analyzer("Đêm mưa.") is None
    assert analyzer.last_error == f"9router không trả lời trong {LLM_PART_TIMEOUT_S:g} giây"


# ----------------------------------------------------------------------------- truyện dài (novel)

@pytest.mark.asyncio
async def test_long_novel_chapter_is_adapted_part_by_part(fake_9router):
    text = _long_story()

    res = await script_splitter.adapt_novel_chapter_to_us_podcast(text)

    assert len(fake_9router) == len(_parts_of(text))
    assert all(c["is_novel"] is True for c in fake_9router)
    assert _no_space("".join(c["text"] for c in fake_9router)) == _no_space(text)
    assert [s["order"] for s in res["scenes"]] == list(range(1, len(res["scenes"]) + 1))
    assert END_MARKER in res["scenes"][-1]["text"]
    assert res["provider_used"] == "9router_gemini"


@pytest.mark.asyncio
async def test_novel_failed_part_goes_offline_alone(monkeypatch):
    _install_9router(monkeypatch, lambda n, chunk, self: _fail(self) if n in (2, 3) else _fake_scenes(chunk))

    res = await script_splitter.adapt_novel_chapter_to_us_podcast(_long_story())

    assert res["provider_used"] == "9router_gemini_partial"
    assert "(phần 2/" in res["fallback_reason"]
    assert END_MARKER in res["scenes"][-1]["text"]


# ----------------------------------------------------------------------------- route create-from-script

@pytest.fixture
def client(isolated_projects_dir, monkeypatch):
    monkeypatch.setattr(api_module, "PROJECTS_DIR", isolated_projects_dir)
    app = FastAPI()
    app.include_router(api_module.router)
    with TestClient(app) as c:
        yield c


def test_create_from_script_keeps_the_end_of_a_long_script(fake_9router, client):
    resp = client.post("/api/projects/create-from-script", json={
        "text": _long_story(),
        "generate_initial_images": False,
    })

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(fake_9router) >= 2
    assert END_MARKER in body["scenes"][-1]["text"]
    assert body["metadata"]["scene_analysis"] == {"provider": "9router", "fallback_reason": None}


def test_create_from_script_marks_partial_offline_parts(monkeypatch, client):
    _install_9router(monkeypatch, lambda n, chunk, self: _fail(self) if n in (2, 3) else _fake_scenes(chunk))

    resp = client.post("/api/projects/create-from-script", json={
        "text": _long_story(),
        "generate_initial_images": False,
    })

    assert resp.status_code == 200, resp.text
    analysis = resp.json()["metadata"]["scene_analysis"]
    assert analysis["provider"] == "partial"
    assert "(phần 2/" in analysis["fallback_reason"]
