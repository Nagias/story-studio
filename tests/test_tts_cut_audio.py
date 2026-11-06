"""Edge-TTS có lúc ngắt luồng giữa chừng: trả tiếng cụt nhưng vẫn gửi đủ mốc từng chữ.

Đã gặp 06/11/2026 (video vụ án `proj_crime_03b5d8c5`, cảnh 52): file giọng 6,96 giây trong khi mốc chữ
tới 13,3 giây; người xem mất nửa câu, phụ đề phần mất tràn sang đè lên cảnh sau.
App phải thu lại, và nếu lần nào cũng cụt thì báo lỗi, không coi là xong (CLAUDE.md mục 5, dòng 3).
"""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import tts_service  # noqa: E402

WORDS = [("Những", 0.1, 0.4), ("người", 0.4, 0.8), ("thụ", 5.0, 5.3), ("lý", 12.9, 13.3)]


def fake_edge(audio_per_attempt):
    """Communicate giả: lần gọi thứ i trả audio_per_attempt[i] cùng đủ mốc chữ tới 13,3 giây."""
    calls = []

    class FakeCommunicate:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.data = audio_per_attempt[min(len(calls) - 1, len(audio_per_attempt) - 1)]

        async def stream(self):
            yield {"type": "audio", "data": self.data}
            for word, start, end in WORDS:
                yield {"type": "WordBoundary", "offset": int(start * 1e7),
                       "duration": int((end - start) * 1e7), "text": word}

    return FakeCommunicate, calls


@pytest.fixture
def no_wait(monkeypatch):
    async def instant(_seconds):
        return None
    monkeypatch.setattr(tts_service.asyncio, "sleep", instant)
    # độ dài "đo" theo nội dung file giả: b"cut" = tiếng cụt 6,96 giây, b"full" = đủ 13,5 giây
    monkeypatch.setattr(tts_service, "get_audio_duration",
                        lambda path: 6.96 if Path(path).read_bytes() == b"cut" else 13.5)


@pytest.mark.asyncio
async def test_cut_audio_is_recorded_again(tmp_path, monkeypatch, no_wait):
    fake, calls = fake_edge([b"cut", b"full"])
    monkeypatch.setattr(tts_service.edge_tts, "Communicate", fake)

    result = await tts_service.generate_speech(
        "Những người thụ lý.", voice="vi-VN-NamMinhNeural",
        output_audio_path=str(tmp_path / "scene_052.mp3"))

    assert len(calls) == 2
    assert result["duration"] == 13.5
    assert (tmp_path / "scene_052.mp3").read_bytes() == b"full"


@pytest.mark.asyncio
async def test_always_cut_audio_fails_loudly(tmp_path, monkeypatch, no_wait):
    fake, calls = fake_edge([b"cut"])
    monkeypatch.setattr(tts_service.edge_tts, "Communicate", fake)

    with pytest.raises(RuntimeError, match="cụt"):
        await tts_service.generate_speech(
            "Những người thụ lý.", voice="vi-VN-NamMinhNeural",
            output_audio_path=str(tmp_path / "scene_052.mp3"))
    assert len(calls) == 6
