"""Gặp 13/11/2026: 8 clip Muse của hai vụ có dải trắng ở mép hình (Muse tự ghép đoạn), dày 3–30 điểm ảnh. App đo và cắt
viền khi nhận clip (services/clip_border.py, gọi trong climax_video.run_scene_clips)."""
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import clip_border  # noqa: E402


def _clip(path: Path, top: int = 0, right: int = 0) -> Path:
    """Clip 2 giây 640x360 nền tối có ô vuông chạy; có viền thì đè dải trắng ở mép trên/phải."""
    vf = "drawbox=x='mod(t*200,600)':y=150:w=40:h=40:color=red:t=fill"
    if top:
        vf += f",drawbox=x=0:y=0:w=iw:h={top}:color=white:t=fill"
    if right:
        vf += f",drawbox=x=iw-{right}:y=0:w={right}:h=ih:color=white:t=fill"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x202830:s=640x360:d=2:r=25",
                    "-vf", vf, "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_detects_and_trims_white_border_keeping_size(tmp_path):
    clip = _clip(tmp_path / "a.mp4", top=14, right=8)
    top, bottom, left, right = clip_border.border_widths(clip)
    assert 12 <= top <= 16 and 6 <= right <= 10 and bottom == 0 and left == 0
    got = clip_border.trim_in_place(clip, backup_dir=tmp_path / "cu")
    assert got is not None and (tmp_path / "cu" / "a.mp4").is_file()
    assert max(clip_border.border_widths(clip)) < clip_border.MIN_BORDER
    w, h, d = clip_border._probe(clip)
    assert (w, h) == (640, 360) and d == pytest.approx(2.0, abs=0.1)


def test_clean_clip_is_left_alone(tmp_path):
    clip = _clip(tmp_path / "b.mp4")
    before = clip.stat().st_mtime_ns
    assert clip_border.trim_in_place(clip) is None
    assert clip.stat().st_mtime_ns == before


def test_crop_box_keeps_aspect_ratio_inside_clean_area():
    cw, ch, x, y = clip_border.crop_box(1920, 1080, (30, 22, 5, 17))
    assert abs(cw / ch - 16 / 9) < 0.01 and cw % 2 == 0 and ch % 2 == 0
    assert y >= 32 and y + ch <= 1080 - 24 and x >= 7 and x + cw <= 1920 - 19


def test_unreadable_clip_raises(tmp_path):
    bad = tmp_path / "x.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(clip_border.ClipBorderError):
        clip_border.border_widths(bad)
