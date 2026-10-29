"""Giọng "nhịp review" (chủ dự án 29/10/2026): VieNeu đọc ở tốc độ gốc 1,0 và ngừng ngắn; giọng cũ giữ nguyên nhịp chậm.

Không gọi VieNeu thật: server, httpx và ffmpeg ghép câu đều là đồ giả.
"""
import re
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402
from services import tts_service  # noqa: E402

REVIEW_IDS = {"vieneu-review-TrucLy": "Trúc Ly", "vieneu-review-MaiAnh": "Mai Anh",
              "vieneu-review-ThienMinh": "Thiện Minh"}
TEXT = "Căn hộ khóa trái từ bên trong. Không ai đáp lời… Họ phá cửa sổ."


def test_split_for_pauses_takes_custom_pauses():
    assert tts_service.split_for_pauses(TEXT, 0.2, 0.6) == [
        ("Căn hộ khóa trái từ bên trong.", 0.2), ("Không ai đáp lời…", 0.6), ("Họ phá cửa sổ.", 0.0)]
    assert [p for _, p in tts_service.split_for_pauses(TEXT)] == [
        tts_service.SENTENCE_PAUSE_S, tts_service.ELLIPSIS_PAUSE_S, 0.0]


def test_review_voices_are_listed_everywhere():
    """Danh mục /api/voices (ô chọn giọng Hồ Sơ Kỳ Án) và ô chọn giọng màn chính (index.html) cùng có đủ 3 giọng."""
    catalog = {v["id"]: v for v in tts_service.get_available_voices()}
    html = (BACKEND_DIR / "static/index.html").read_text(encoding="utf-8")
    options = set(re.findall(r'<option value="(vieneu-review-[^"]+)"', html))
    assert options == set(REVIEW_IDS)
    for vid in REVIEW_IDS:
        assert catalog[vid]["locale"] == "vi-VN"
    assert catalog["vieneu-review-ThienMinh"]["gender"] == "Male"
    assert catalog["vieneu-review-TrucLy"]["gender"] == catalog["vieneu-review-MaiAnh"]["gender"] == "Female"


def _fake_vieneu(monkeypatch):
    sent, joined = [], []

    async def ready():
        return True

    class FakeResp:
        status_code = 200
        content = b"\x00" * 1000
        text = ""

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json):
            sent.append(json)
            return FakeResp()

    async def fake_join(chunks, output_path):
        joined.extend(p for _, p in chunks)
        Path(output_path).write_bytes(b"\x00" * 1000)

    monkeypatch.setattr(tts_service, "ensure_vieneu_server", ready)
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(tts_service, "join_with_pauses", fake_join)
    monkeypatch.setattr(tts_service, "get_audio_duration", lambda path: 4.0)
    return sent, joined


@pytest.mark.asyncio
@pytest.mark.parametrize("voice_id,preset", REVIEW_IDS.items())
async def test_review_voice_reads_at_native_speed_with_short_pauses(tmp_path, monkeypatch, voice_id, preset):
    sent, joined = _fake_vieneu(monkeypatch)
    res = await tts_service.generate_speech(TEXT, voice=voice_id, output_audio_path=str(tmp_path / "a.mp3"))
    assert res["fallback_used"] is False and res["voice"] == voice_id
    assert [j["voice"] for j in sent] == [preset] * 3
    assert {j["speed"] for j in sent} == {tts_service.REVIEW_SPEED} == {1.0}
    assert joined == [0.2, 0.6, 0.0]


@pytest.mark.asyncio
async def test_old_vieneu_voice_keeps_slow_pace(tmp_path, monkeypatch):
    sent, joined = _fake_vieneu(monkeypatch)
    await tts_service.generate_speech(TEXT, voice="vieneu-MaiAnh", output_audio_path=str(tmp_path / "a.mp3"))
    assert {j["speed"] for j in sent} == {config.VIENEU_SPEED}
    assert joined == [tts_service.SENTENCE_PAUSE_S, tts_service.ELLIPSIS_PAUSE_S, 0.0]
