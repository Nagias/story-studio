"""Clip Muse ngắn hơn lời đọc: kéo chậm clip (tối đa video_rules.MAX_CLIP_STRETCH lần) thay vì đứng hình ở cuối.

Gặp 10/11/2026 (bản Anh vụ Khang Cúc Hoa): clip chép từ bản Việt nên 14/23 cảnh có lời Anh dài hơn clip, khung cuối
đứng im tới 3,2 giây (cần kéo nhiều nhất 1,18 lần)."""
import asyncio
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import video_rules, video_service  # noqa: E402


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def _frame(video: Path, t: float, out: Path) -> np.ndarray:
    _ffmpeg("-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(out))
    return np.asarray(Image.open(out).convert("L"), dtype=np.int16)


def _moving_clip(path: Path, seconds: float) -> Path:
    # testsrc: hình đổi mỗi khung (bộ đếm, sọc chạy), dễ thấy đứng hình
    _ffmpeg("-f", "lavfi", "-i", f"testsrc=size=640x360:rate=24:duration={seconds}", "-pix_fmt", "yuv420p", str(path))
    return path


def _voice(path: Path, seconds: float) -> Path:
    _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}", str(path))
    return path


def _render(tmp_path: Path, clip_sec: float, voice_sec: float) -> Path:
    clip = _moving_clip(tmp_path / "clip.mp4", clip_sec)
    voice = _voice(tmp_path / "voice.mp3", voice_sec)
    out = tmp_path / "seg.mp4"
    asyncio.run(video_service.render_scene_video(str(clip), str(voice), str(out), duration=voice_sec,
                                                 resolution="720p", fps=24))
    return out


def test_clip_a_bit_shorter_than_voice_is_slowed_not_frozen(tmp_path):
    out = _render(tmp_path, clip_sec=4.0, voice_sec=4.7)        # cần kéo 1,18 lần như cảnh 13 bản Anh
    a = _frame(out, 4.35, tmp_path / "a.png")
    b = _frame(out, 4.6, tmp_path / "b.png")
    assert np.abs(a - b).mean() > 1.0, "phần cuối cảnh đang đứng hình"
    assert abs(video_service.get_audio_duration(str(out)) - 4.7) < 0.15


def test_clip_far_too_short_is_slowed_to_the_cap_then_holds_last_frame(tmp_path):
    out = _render(tmp_path, clip_sec=4.0, voice_sec=7.0)
    moving_until = 4.0 * video_rules.MAX_CLIP_STRETCH
    a = _frame(out, moving_until - 0.45, tmp_path / "a.png")
    b = _frame(out, moving_until - 0.2, tmp_path / "b.png")
    c = _frame(out, 6.5, tmp_path / "c.png")
    d = _frame(out, 6.8, tmp_path / "d.png")
    assert np.abs(a - b).mean() > 1.0, "trong phần kéo chậm hình vẫn phải chạy"
    assert np.abs(c - d).mean() < 0.5, "hết phần kéo được thì giữ khung cuối"
    assert abs(video_service.get_audio_duration(str(out)) - 7.0) < 0.15


def test_clip_longer_than_voice_is_not_slowed(tmp_path):
    assert video_rules.clip_stretch(clip_seconds=10.0, scene_seconds=8.0) == 1.0
    assert video_rules.clip_stretch(clip_seconds=8.0, scene_seconds=8.02) == 1.0
    assert abs(video_rules.clip_stretch(clip_seconds=17.0, scene_seconds=20.0) - 20 / 17) < 1e-6
    assert video_rules.clip_stretch(clip_seconds=4.0, scene_seconds=40.0) == video_rules.MAX_CLIP_STRETCH
    assert video_rules.clip_stretch(clip_seconds=None, scene_seconds=5.0) == 1.0
