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
    for track in set(scene_sound.ENERGY_TRACKS.values()) - {scene_sound.SILENCE}:
        assert (config.BGM_DIR / f"{track}.mp3").is_file() and track in sources


def test_old_cue_names_map_to_the_library_and_unknown_cues_are_dropped():
    assert scene_sound.normalize_cue("heavy_rain_loop") == "rain_heavy"
    assert scene_sound.normalize_cue("Heartbeat Single Pulse") == "heartbeat"
    assert scene_sound.normalize_cue("clock_ticking") == "clock_ticking"
    assert scene_sound.normalize_cue("magic_spell_shimmer") is None
    files = scene_sound.scene_sfx_files(["paper_rustling", "paper_shuffle", "heartbeat", "fire_crackle", "laser"])
    assert [f.stem for f in files] == ["paper_rustle"]       # bỏ trùng, tối đa 1 tiếng mỗi cảnh (tiết chế 02/11/2026)


def test_energy_segments_group_neighbouring_scenes():
    segments = scene_sound.energy_segments(["ambient_low", None, "tension_buildup", "dramatic_climax", "ambient_low"],
                                           [10, 5, 7, 3, 4])
    # đoạn trầm im (chỉ giọng), đoạn căng nhạc trầm, cao trào nhạc dồn (tiết chế 02/11/2026)
    assert segments == [("silence", 15.0), ("bgm_dark_ambient", 7.0), ("bgm_suspense", 3.0), ("silence", 4.0)]


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


def _lufs(path) -> float:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-ac", "1", "-af",
                          "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True,
                         encoding="utf-8", errors="ignore").stderr
    return float(err.split('"input_i" : "')[1].split('"')[0])


@pytest.mark.skipif(not HAS_FFMPEG, reason="cần ffmpeg")
def test_every_library_sound_reaches_the_same_level_under_the_voice(tmp_path):
    """Lỗi 27/10/2026: fluorescent_hum (−6 LUFS) đè giọng ở 29 cảnh, footsteps_wet (−43 LUFS) không nghe thấy."""
    for cue in scene_sound.SFX_CUES:
        gain = scene_sound.sfx_gain_db(config.SFX_LIBRARY_DIR / f"{cue}.mp3")
        assert gain < scene_sound.SFX_MAX_BOOST_DB, f"{cue}: quá nhỏ, kéo lên tối đa vẫn không tới mức chung"
    silence = tmp_path / "silence.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "10",
                    str(silence)], check=True)
    for cue in ("fluorescent_hum", "footsteps_wet"):
        mixed = tmp_path / f"{cue}.mp3"
        asyncio.run(scene_sound.mix_scene_sfx(str(silence), scene_sound.scene_sfx_files([cue]), str(mixed), 10.0))
        assert abs(_lufs(mixed) - scene_sound.SFX_TARGET_LUFS) < 3.0, cue


@pytest.mark.skipif(not HAS_FFMPEG, reason="cần ffmpeg")
def test_mixing_does_not_lower_the_voice(tmp_path):
    """Lỗi 27/10/2026: giọng mono bị đổi sang stereo khi trộn nên cảnh có tiếng động nhỏ hơn cảnh không có ~3 dB."""
    voice = tmp_path / "voice.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=330:duration=8:sample_rate=48000",
                    "-ac", "1", str(voice)], check=True)   # khoảng −21 LUFS, gần giọng thật (−20)
    mixed = tmp_path / "mixed.mp3"
    asyncio.run(scene_sound.mix_scene_sfx(str(voice), scene_sound.scene_sfx_files(["dark_drone", "fluorescent_hum"]),
                                          str(mixed), 8.0))
    assert abs(_lufs(mixed) - _lufs(voice)) < 1.0


# ---------------------------------------------------------------- tiết chế âm thanh (02/11/2026)
# Chủ dự án 29/10/2026: "rùng rợn không có nghĩa là cả 1 video dài 22 phút đều phải có cái âm thanh kiểu ý". Đo 2 video
# mẫu: 8–11% thời lượng gần như im (khung 0,25 s dưới −40 dB); video Trạm Dung 0,2%.

def test_sfx_only_at_key_moments_spaced_and_capped():
    scenes = [("ambient_low", "image", ["rain_heavy"])] * 4 + [("tension_buildup", "image", ["heartbeat"]),
              ("dramatic_climax", "image", ["impact_hit"]), ("tension_buildup", "image", ["door_creak"])] +              [("ambient_low", "video", ["footsteps_wet"])] + [("ambient_low", "image", ["wind_soft"])] * 4 +              [("dramatic_climax", "image", ["glass_break"]), ("dramatic_climax", "image", ["thunder_distant"])]
    plan = scene_sound.plan_scene_sfx(scenes)
    picked = [i for i, cues in enumerate(plan) if cues]
    assert len(picked) <= len(scenes) * scene_sound.SFX_MAX_SHARE                 # tối đa 1/4 số cảnh
    assert all(b - a >= scene_sound.SFX_MIN_GAP_SCENES for a, b in zip(picked, picked[1:]))
    assert all(scenes[i][0] in ("tension_buildup", "dramatic_climax") or scenes[i][1] == "video" for i in picked)
    assert 5 in picked                                                            # cao trào được ưu tiên
    assert all(not plan[i] for i in range(4))                                     # cảnh trầm không có tiếng động
    assert all(len(c) <= 1 for c in plan)


def _quiet_share(path, threshold_db: float = -40.0) -> float:
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    w = 2000
    n = len(a) // w
    db = 20 * np.log10(np.sqrt((a[: n * w].reshape(n, w) ** 2).mean(1)) + 1e-9)
    return float(np.mean(db < threshold_db))


@pytest.mark.skipif(not HAS_FFMPEG, reason="cần ffmpeg")
def test_sfx_plays_once_not_looped_over_the_scene(tmp_path):
    voice = tmp_path / "voice.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "12",
                    str(voice)], check=True)                                      # giọng im 12 s: chỉ nghe tiếng động
    mixed = tmp_path / "scene_sfx.mp3"
    asyncio.run(scene_sound.mix_scene_sfx(str(voice), scene_sound.scene_sfx_files(["rain_heavy"]), str(mixed), 12.0))
    assert abs(_duration(mixed) - 12.0) < 0.15
    tail = tmp_path / "tail.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "5", "-i", str(mixed), str(tail)], check=True)
    assert _quiet_share(tail) > 0.95                                              # sau 4 s không còn tiếng mưa


@pytest.mark.skipif(not HAS_FFMPEG, reason="cần ffmpeg")
def test_quiet_sections_have_no_music(tmp_path):
    bgm = tmp_path / "bgm.mp3"
    segments = scene_sound.energy_segments(["ambient_low", "dramatic_climax"], [6, 6])
    asyncio.run(scene_sound.build_energy_bgm(segments, str(bgm)))
    first, second = tmp_path / "a.wav", tmp_path / "b.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-t", "5.5", "-i", str(bgm), str(first)], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "8", "-t", "3", "-i", str(bgm), str(second)], check=True)
    assert _quiet_share(first) > 0.95 and _quiet_share(second) < 0.5
