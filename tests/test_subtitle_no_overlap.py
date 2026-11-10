"""Phụ đề kiểu "kinetic_pop" (mỗi chữ một dòng ASS) không được để hai dòng hiện cùng lúc.

Đã gặp 10/11/2026 (bản Anh `proj_crime_f297bced`): mỗi dòng giữ tối thiểu 0,12 giây nên với giọng đọc nhanh, dòng của
chữ trước chưa tắt thì dòng chữ sau đã hiện; libass xếp dòng sau lên trên, người xem thấy hai dòng phụ đề nháy
(388 chỗ ở bản Anh, 7 chỗ ở bản Việt).
"""
import json
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.subtitle_engine import generate_karaoke_ass  # noqa: E402


def _secs(stamp: str) -> float:
    h, m, s = stamp.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _events(ass_path: Path) -> list[tuple[float, float]]:
    out = []
    for line in ass_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Dialogue:"):
            f = line.split(",", 9)
            out.append((_secs(f[1]), _secs(f[2])))
    return sorted(out)


def _scene(tmp_path: Path, name: str, words: list[tuple[str, float, float]], duration: float) -> dict:
    audio = tmp_path / f"{name}.mp3"
    audio.write_bytes(b"")   # chỉ cần file .words.json đi kèm
    audio.with_suffix(".words.json").write_text(
        json.dumps([{"word": w, "start": s, "end": e} for w, s, e in words]), encoding="utf-8")
    return {"text": " ".join(w for w, _, _ in words), "audio_path": str(audio), "total_duration": duration}


def test_short_words_do_not_overlap(tmp_path):
    # chữ ngắn 0,05 giây (giọng Anh đọc nhanh) và một chữ báo kết thúc trễ hơn chữ sau bắt đầu
    words = [("He", 0.10, 0.15), ("claimed", 0.15, 0.40), ("he", 0.40, 0.45), ("followed", 0.43, 0.80),
             ("the", 0.80, 0.85), ("victim", 0.85, 1.20), ("from", 1.20, 1.25), ("the", 1.25, 1.30), ("mill", 1.30, 1.70)]
    scenes = [_scene(tmp_path, "a", words, 1.75), _scene(tmp_path, "b", [("Then", 0.0, 0.05), ("silence", 0.05, 0.6)], 1.0)]
    out = tmp_path / "sub.ass"
    generate_karaoke_ass(scenes, out, style_mode="kinetic_pop")

    events = _events(out)
    assert len(events) == 11
    overlaps = [(a, b) for a, b in zip(events, events[1:]) if b[0] < a[1]]
    assert overlaps == []
    assert all(e[1] > e[0] for e in events)


def test_long_words_keep_their_timing(tmp_path):
    words = [("Một", 0.10, 0.50), ("buổi", 0.60, 1.00), ("chiều", 1.10, 1.60)]
    out = tmp_path / "sub.ass"
    generate_karaoke_ass([_scene(tmp_path, "a", words, 2.0)], out, style_mode="kinetic_pop")
    assert _events(out) == [(0.10, 0.50), (0.60, 1.00), (1.10, 1.60)]
    assert re.search(r"\\fscx110", out.read_text(encoding="utf-8"))
