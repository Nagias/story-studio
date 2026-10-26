"""Âm thanh theo cảnh của video vụ án (services/scene_sound.py). Chủ dự án 26/10/2026: video không có sound effect hợp
bối cảnh; sfx_cue và bgm_energy của kế hoạch trước đây không được dùng."""
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402
from services import scene_sound  # noqa: E402

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out.strip())


def test_every_cue_has_a_real_cc0_file_with_its_source_recorded():
    sources = (config.SFX_LIBRARY_DIR / "NGUON.md").read_text(encoding="utf-8")
    for cue in scene_sound.SFX_CUES:
        assert (config.SFX_LIBRARY_DIR / f"{cue}.mp3").is_file(), cue
        assert f"| {cue} |" in sources, f"{cue}: chưa ghi nguồn và giấy phép trong NGUON.md"
    for track in set(scene_sound.ENERGY_TRACKS.values()):
        assert (config.BGM_DIR / f"{track}.mp3").is_file() and track in sources


def test_old_cue_names_map_to_the_library_and_unknown_cues_are_dropped():
    assert scene_sound.normalize_cue("heavy_rain_loop") == "rain_heavy"
    assert scene_sound.normalize_cue("Heartbeat Single Pulse") == "heartbeat"
    assert scene_sound.normalize_cue("clock_ticking") == "clock_ticking"
    assert scene_sound.normalize_cue("magic_spell_shimmer") is None
    files = scene_sound.scene_sfx_files(["paper_rustling", "paper_shuffle", "heartbeat", "fire_crackle", "laser"])
    assert [f.stem for f in files] == ["paper_rustle", "heartbeat"]       # bỏ trùng, tối đa 2 tiếng mỗi cảnh


def test_energy_segments_group_neighbouring_scenes():
    segments = scene_sound.energy_segments(["ambient_low", None, "tension_buildup", "dramatic_climax", "ambient_low"],
                                           [10, 5, 7, 3, 4])
    assert segments == [("bgm_dark_ambient", 15.0), ("bgm_suspense", 10.0), ("bgm_dark_ambient", 4.0)]


@pytest.mark.skipif(not HAS_FFMPEG, reason="cần ffmpeg")
def test_mixing_keeps_scene_length_and_energy_bgm_covers_the_video(tmp_path):
    voice = tmp_path / "voice.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=4", str(voice)],
                   check=True)
    mixed = tmp_path / "scene_sfx.mp3"
    files = scene_sound.scene_sfx_files(["rain_heavy", "clock_ticking"])
    asyncio.run(scene_sound.mix_scene_sfx(str(voice), files, str(mixed), 4.0))
    assert abs(_duration(mixed) - 4.0) < 0.15 and mixed.read_bytes() != voice.read_bytes()

    bgm = tmp_path / "bgm.mp3"
    asyncio.run(scene_sound.build_energy_bgm([("bgm_dark_ambient", 6.0), ("bgm_suspense", 5.0)], str(bgm)))
    assert abs(_duration(bgm) - 11.0) < 0.3
