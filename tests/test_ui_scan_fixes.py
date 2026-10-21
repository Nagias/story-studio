"""Các lỗi tìm ra khi bấm thử toàn bộ giao diện (2026-10-21), phần phía máy chủ:

- Edge-TTS đôi khi trả "No audio was received" vài giây liền: phải thử lại đủ lâu thay vì bỏ cuộc sau ~1,5 giây.
- Nút tải nhạc nền MP3 riêng trước đây không làm gì: API /api/bgm-tracks/upload nhận MP3 thật, từ chối file khác.
- Bộ sưu tập Muse hiện mỗi kết quả hai lần (một lần theo lịch sử task, một lần theo file trong muse_outputs).
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402
import routers.api as api_module  # noqa: E402
import routers.muse_bridge as mb  # noqa: E402
import services.tts_service as tts  # noqa: E402

LOCAL = dict(base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
MP3_BYTES = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 64


# ---------------- Edge-TTS: thử lại khi dịch vụ chập chờn ----------------

def _fake_edge(fail_times: int, calls: list):
    class FakeCommunicate:
        def __init__(self, text, voice, **kwargs):
            self.text = text

        async def stream(self):
            calls.append(1)
            if len(calls) <= fail_times:
                raise RuntimeError("No audio was received. Please verify that your parameters are correct.")
            yield {"type": "WordBoundary", "offset": 0, "duration": 5_000_000, "text": "Xin"}
            yield {"type": "audio", "data": b"\xff\xfb" * 100}

    return FakeCommunicate


@pytest.fixture
def no_wait(monkeypatch):
    waits = []

    async def fake_sleep(sec):
        waits.append(sec)

    monkeypatch.setattr(tts.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(tts, "get_audio_duration", lambda p: 1.0)
    return waits


def test_edge_tts_retries_until_service_recovers(monkeypatch, tmp_path, no_wait):
    calls = []
    monkeypatch.setattr(tts.edge_tts, "Communicate", _fake_edge(3, calls))
    res = asyncio.run(tts.generate_speech("Xin chào các bạn.", voice="vi-VN-NamMinhNeural",
                                          output_audio_path=str(tmp_path / "a.mp3")))
    assert len(calls) == 4
    assert no_wait == [1, 2, 4]
    assert Path(res["audio_path"]).stat().st_size > 0


def test_edge_tts_gives_up_after_six_attempts(monkeypatch, tmp_path, no_wait):
    calls = []
    monkeypatch.setattr(tts.edge_tts, "Communicate", _fake_edge(99, calls))
    with pytest.raises(RuntimeError, match="after 6 attempts"):
        asyncio.run(tts.generate_speech("Xin chào các bạn.", voice="vi-VN-NamMinhNeural",
                                        output_audio_path=str(tmp_path / "a.mp3")))
    assert len(calls) == 6
    assert no_wait == [1, 2, 4, 8, 15]


def test_edge_tts_nudges_rate_when_one_request_always_fails(monkeypatch, tmp_path, no_wait):
    # Dịch vụ lỗi cố định với đúng yêu cầu gốc (tốc độ +0%), đổi tốc độ 1% là đọc được
    rates = []

    class StickyFailCommunicate:
        def __init__(self, text, voice, rate="+0%", **kwargs):
            self.rate = rate

        async def stream(self):
            rates.append(self.rate)
            if self.rate == "+0%":
                raise RuntimeError("No audio was received. Please verify that your parameters are correct.")
            yield {"type": "audio", "data": b"\xff\xfb" * 100}

    monkeypatch.setattr(tts.edge_tts, "Communicate", StickyFailCommunicate)
    res = asyncio.run(tts.generate_speech("Ánh mắt kiên định của chàng không hề nao núng.", voice="vi-VN-HoaiMyNeural",
                                          output_audio_path=str(tmp_path / "a.mp3")))
    assert rates == ["+0%", "+1%"]
    assert Path(res["audio_path"]).stat().st_size > 0


def test_nudge_rate_keeps_user_rate():
    assert tts._nudge_rate("+0%", 1) == "+1%"
    assert tts._nudge_rate("-10%", 2) == "-8%"
    assert tts._nudge_rate("+5%", -1) == "+4%"
    assert tts._nudge_rate("lạ", 1) == "+1%"


# ---------------- Tải nhạc nền riêng ----------------

@pytest.fixture
def bgm_dir(monkeypatch, tmp_path):
    d = tmp_path / "bgm"
    d.mkdir()
    monkeypatch.setattr(api_module, "BGM_DIR", d)
    return d


def test_bgm_upload_saves_mp3_with_safe_readable_id(bgm_dir):
    c = TestClient(app, **LOCAL)
    r = c.post("/api/bgm-tracks/upload", files={"file": ("Nhạc của tôi.mp3", MP3_BYTES, "audio/mpeg")})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"].startswith("custom_nhac_cua_toi_")
    assert (bgm_dir / f"{data['id']}.mp3").read_bytes() == MP3_BYTES
    ids = [t["id"] for t in c.get("/api/bgm-tracks").json()]
    assert data["id"] in ids


def test_bgm_upload_rejects_non_mp3(bgm_dir):
    c = TestClient(app, **LOCAL)
    assert c.post("/api/bgm-tracks/upload", files={"file": ("x.wav", MP3_BYTES, "audio/wav")}).status_code == 400
    assert c.post("/api/bgm-tracks/upload", files={"file": ("gia.mp3", b"not audio at all", "audio/mpeg")}).status_code == 400
    assert c.post("/api/bgm-tracks/upload", files={"file": ("rong.mp3", b"", "audio/mpeg")}).status_code == 400
    r = c.post("/api/bgm-tracks/upload", files={"file": ("../../evil.mp3", MP3_BYTES, "audio/mpeg")})
    assert r.status_code == 200
    assert list(p.name for p in bgm_dir.iterdir()) == [f"{r.json()['id']}.mp3"]


def test_bgm_upload_blocked_from_foreign_origin(bgm_dir):
    c = TestClient(app, **LOCAL)
    r = c.post("/api/bgm-tracks/upload", headers={"Origin": "http://evil.example"},
               files={"file": ("a.mp3", MP3_BYTES, "audio/mpeg")})
    assert r.status_code == 403
    assert not any(bgm_dir.iterdir())


# ---------------- Bộ sưu tập Muse không hiện trùng ----------------

def test_muse_gallery_lists_each_result_once(monkeypatch, tmp_path):
    outputs = tmp_path / "muse_outputs"
    outputs.mkdir()
    (outputs / "task_m_abc12345.jpg").write_bytes(b"\xff\xd8 jpg")
    (outputs / "scene_9.jpg").write_bytes(b"\xff\xd8 jpg")  # file lẻ không có trong lịch sử: vẫn hiện
    monkeypatch.setattr(mb, "MUSE_OUTPUTS_DIR", outputs)
    monkeypatch.setattr(mb, "get_enriched_accounts", lambda: [])
    saved = list(mb.task_history)
    mb.task_history[:] = [{
        "task_id": "task_m_abc12345", "status": "completed", "mode": "text-to-image",
        "media_url": "/static/muse_outputs/task_m_abc12345.jpg",
        "output_path": str(tmp_path / "projects" / "proj_x" / "images" / "scene_1.jpg"),
    }]
    try:
        items = TestClient(app, **LOCAL).get("/api/muse-bridge/status").json()["recent_completed"]
    finally:
        mb.task_history[:] = saved
    urls = [i["media_url"] for i in items]
    assert urls.count("/static/muse_outputs/task_m_abc12345.jpg") == 1
    assert "/static/muse_outputs/scene_9.jpg" in urls
