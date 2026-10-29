"""Test ẩn bổ sung của bộ việc mẫu T7 (docs/bo-viec-mau): chỉ chép vào tests/ của bản chấm, không thuộc bộ test dự án.

Yêu cầu của đề mà test của lần sửa thật chưa kiểm: đỉnh không vượt −1 dBTP; video vẫn đủ hình, đủ tiếng, đúng độ dài.
"""
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.image_service import generate_mock_cinematic  # noqa: E402
from services.video_service import assemble_full_video, generate_default_bgm_track, render_scene_video  # noqa: E402


def _true_peak(path: str) -> float:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    return float(re.findall(r"Peak:\s+(-?\d+(?:\.\d+)?) dBFS", out)[-1])


def _streams(path: str) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", path],
                       capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    return {"types": sorted(s["codec_type"] for s in d["streams"]), "duration": float(d["format"]["duration"])}


@pytest.mark.asyncio
@pytest.mark.parametrize("with_bgm", [True, False])
async def test_video_thanh_pham_khong_vo_dinh_va_du_hinh_tieng(tmp_path, with_bgm):
    img_p, aud_p, vid_p = str(tmp_path / "img.jpg"), str(tmp_path / "voice.wav"), str(tmp_path / "seg.mp4")
    generate_mock_cinematic("scene", "cinematic_realistic", img_p, 1)
    # giọng to sát đỉnh: chuẩn hoá không được đẩy đỉnh vượt −1 dBTP
    await asyncio.to_thread(subprocess.run, ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                            "sine=frequency=330:duration=6", "-af", "volume=-1dB", aud_p], check=True)
    seg = await render_scene_video(img_p, aud_p, vid_p, 6.0, "zoom_in", "720p", 25)
    bgm = None
    if with_bgm:
        bgm = str(tmp_path / "bgm.mp3")
        generate_default_bgm_track(bgm, "peaceful")
    out = str(tmp_path / "final.mp4")
    await assemble_full_video(scene_video_paths=[seg["video_path"]], scene_srt_infos=[{"srt_path": None, "duration": 6.0}],
                              output_video_path=out, bgm_path=bgm, bgm_volume=0.2, ducking=True, hardsub=False,
                              resolution="720p")
    assert await asyncio.to_thread(_true_peak, out) <= -1.0
    info = await asyncio.to_thread(_streams, out)
    assert info["types"] == ["audio", "video"]
    assert abs(info["duration"] - 6.0) < 0.6
