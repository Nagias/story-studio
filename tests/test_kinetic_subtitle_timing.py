"""Phụ đề chữ nhảy (ASS in lên hình) phải theo độ dài thật của từng đoạn hình, như file .srt.

Gặp 11/11/2026 (video vụ xưởng sắt bản tiếng Anh): clip Muse dài hơn lời kể nên mỗi đoạn hình dài hơn giọng đọc
0,5–1 giây; phụ đề cộng dồn theo độ dài giọng nên chữ chạy trước hình, lệch tới ~38 giây ở cuối video."""
import re

import pytest

from services.subtitle_engine import generate_karaoke_ass
from services.video_service import subtitle_scene_timing


def _lines(ass_text: str) -> list[tuple[float, str]]:
    """(giây bắt đầu, chữ) của từng dòng phụ đề, bỏ mã định dạng {...}."""
    out = []
    for h, m, s, text in re.findall(r"^Dialogue: 0,(\d+):(\d\d):(\d\d\.\d\d),[^,]*,(?:[^,]*,){5}(.*)$", ass_text, re.M):
        out.append((int(h) * 3600 + int(m) * 60 + float(s), re.sub(r"\{[^}]*\}", "", text).lower()))
    return out


def test_second_scene_subtitles_start_when_its_picture_starts(tmp_path):
    # giọng cảnh 1 dài 2 giây nhưng đoạn hình cảnh 1 dài 5 giây (clip Muse dài hơn lời)
    scenes = [{"text": "one two three", "duration": 2.0}, {"text": "four five six", "duration": 2.0}]
    segments = [{"srt_path": "a.srt", "duration": 5.0}, {"srt_path": "b.srt", "duration": 2.0}]
    out = tmp_path / "sub.ass"
    generate_karaoke_ass(scenes_data=subtitle_scene_timing(scenes, segments), output_ass_path=str(out),
                         style_mode="kinetic_pop")
    lines = _lines(out.read_text(encoding="utf-8"))
    lead = lines[0][0]                                        # khoảng chờ đầu cảnh của app (cảnh 1 cũng vậy)
    scene2 = [t for t, text in lines if any(w in text for w in ("four", "five", "six"))]
    assert scene2, lines
    assert abs(min(scene2) - (5.0 + lead)) < 0.01             # cảnh 2 bắt đầu đúng lúc hình cảnh 2 bắt đầu
    assert min(scene2) >= 5.0                                 # không có chữ cảnh 2 hiện sớm, lúc hình còn là cảnh 1


def test_timing_keeps_scene_fields_and_rejects_mismatched_lists():
    scenes = [{"text": "a", "duration": 2.0, "voice_audio_path": "x.mp3"}]
    assert subtitle_scene_timing(scenes, [{"duration": 3.5}]) == [
        {"text": "a", "duration": 2.0, "voice_audio_path": "x.mp3", "total_duration": 3.5}]
    assert scenes[0].get("total_duration") is None          # không sửa danh sách gốc
    assert subtitle_scene_timing(scenes, [{"duration": 0}]) == scenes   # không biết độ dài đoạn: giữ như cũ
    with pytest.raises(ValueError):
        subtitle_scene_timing(scenes, [])
