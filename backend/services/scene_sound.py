"""Âm thanh theo cảnh cho video vụ án: tiếng động thật (CC0) trộn vào giọng từng cảnh, nhạc nền đổi theo độ căng.

Chủ dự án 26/10/2026: video không có sound effect hợp bối cảnh, không tạo được không khí rùng rợn. Trước đó `sfx_cue` và
`bgm_energy` của kế hoạch có vào project.json nhưng không chỗ nào dùng, và 15 tiếng trong assets/sfx là tiếng tổng hợp.

- Thư viện tiếng: `config.SFX_LIBRARY_DIR` (backend/assets/sfx_cc0), mỗi tên trong SFX_CUES một file .mp3, giấy phép
  CC0/Public Domain ghi trong NGUON.md cùng thư mục. Tên cũ model hay viết quy về tên trong thư viện (CUE_ALIASES).
- Nhạc nền: bgm_dark_ambient (đoạn trầm) và bgm_suspense (đoạn căng, cao trào) trong assets/bgm, CC0 (NGUON.md).
"""
import asyncio
import logging
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import config

logger = logging.getLogger("story_studio.scene_sound")

SFX_CUES = (
    "rain_heavy", "rain_on_window", "thunder_distant", "wind_howl", "wind_soft", "fire_crackle", "footsteps_indoor",
    "footsteps_wet", "door_creak", "door_knock", "door_slam_metal", "clock_ticking", "heartbeat", "paper_rustle",
    "camera_shutter", "police_radio_static", "siren_distant", "fluorescent_hum", "water_drip", "glass_break",
    "dark_drone", "city_night_ambience", "dog_bark_distant", "impact_hit",
)
# Tên model viết trước khi có thư viện (đo ở kế hoạch vụ Trạm Dung, 61 kiểu tên) -> tên trong thư viện
CUE_ALIASES = {
    "heavy_rain_loop": "rain_heavy", "distant_rain_loop": "rain_heavy", "rain_on_asphalt": "rain_heavy",
    "rain_on_pavement": "rain_heavy", "rain_against_window": "rain_on_window",
    "distant_thunder_subtle": "thunder_distant", "subtle_rumble": "thunder_distant",
    "wind_whistling": "wind_howl", "ambient_wind_hum": "wind_soft",
    "smoke_hissing": "fire_crackle", "thick_smoke_hiss": "fire_crackle",
    "footsteps": "footsteps_indoor", "heavy_footsteps": "footsteps_indoor", "footsteps_in_water": "footsteps_wet",
    "metal_creak": "door_creak", "rusty_iron_gate_creak": "door_creak", "heavy_door_knocking": "door_knock",
    "heavy_iron_door_slam": "door_slam_metal",
    "heartbeat_single_pulse": "heartbeat",
    "paper_rustling": "paper_rustle", "paper_shuffle": "paper_rustle", "debris_rustle": "paper_rustle",
    "camera_flash": "camera_shutter", "camera_flash_burst": "camera_shutter", "camera_shutter_click": "camera_shutter",
    "vintage_camera_shutter": "camera_shutter",
    "ambient_police_radio": "police_radio_static", "radio_static_crackle": "police_radio_static",
    "distant_siren": "siren_distant", "distant_siren_wail": "siren_distant", "distant_siren_echo": "siren_distant",
    "fluorescent_buzz": "fluorescent_hum", "fluorescent_light_hum": "fluorescent_hum",
    "harsh_fluorescent_buzz": "fluorescent_hum", "ambient_office_hum": "fluorescent_hum",
    "water_dripping": "water_drip", "water_drip_echo": "water_drip", "water_drips_echo": "water_drip",
    "glass_shattering": "glass_break", "glass_crunch_underfoot": "glass_break",
    "heavy_bass_drone": "dark_drone", "ambient_hum": "dark_drone", "film_projector_hum": "dark_drone",
    "city_traffic_hum": "city_night_ambience", "distant_city_hum": "city_night_ambience",
    "car_engine_hum": "city_night_ambience",
    "distant_dog_bark": "dog_bark_distant",
    "dramatic_sub_drop": "impact_hit", "dramatic_hit": "impact_hit",
}
SFX_VOLUME = 0.28          # so với giọng đọc (1.0): nghe rõ không khí nhưng không lấn lời kể
SFX_FADE_OUT_S = 1.2
MAX_CUES_PER_SCENE = 2

ENERGY_TRACKS = {"ambient_low": "bgm_dark_ambient", "tension_buildup": "bgm_suspense", "dramatic_climax": "bgm_suspense"}
DEFAULT_ENERGY = "ambient_low"
BGM_FADE_S = 2.0


def normalize_cue(cue: str) -> Optional[str]:
    """Tên trong thư viện của một gợi ý tiếng động (`sfx_cue`), hoặc None nếu thư viện không có tiếng đó."""
    key = "_".join(str(cue or "").strip().lower().replace("-", " ").split())
    key = CUE_ALIASES.get(key, key)
    return key if key in SFX_CUES else None


def library_sfx(cue: str) -> Optional[Path]:
    name = normalize_cue(cue)
    if name is None:
        return None
    path = config.SFX_LIBRARY_DIR / f"{name}.mp3"
    return path if path.is_file() else None


def scene_sfx_files(cues: Iterable[str]) -> List[Path]:
    """File tiếng động có thật cho các gợi ý của một cảnh (bỏ trùng, tối đa MAX_CUES_PER_SCENE)."""
    files: List[Path] = []
    for cue in cues or ():
        path = library_sfx(cue)
        if path is not None and path not in files:
            files.append(path)
    return files[:MAX_CUES_PER_SCENE]


async def _run_ffmpeg(cmd: List[str], what: str) -> None:
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"{what} lỗi (ffmpeg mã {proc.returncode}): {err.decode(errors='ignore')[-300:]}")


async def mix_scene_sfx(voice_path: str, sfx_files: Sequence[Path], output_path: str, duration: float) -> str:
    """Trộn tiếng động vào giọng một cảnh: tiếng động lặp cho đủ độ dài cảnh, nhỏ (SFX_VOLUME), nhỏ dần ở cuối.
    Độ dài bằng giọng (duration=first). Ghi ra `output_path` (không đè file giọng gốc)."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(voice_path)]
    for path in sfx_files:
        cmd += ["-stream_loop", "-1", "-i", str(path)]
    fade_start = max(0.0, float(duration) - SFX_FADE_OUT_S)
    parts = ["[0:a]aformat=sample_rates=48000:channel_layouts=stereo[v]"]
    for i in range(1, len(sfx_files) + 1):
        parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={SFX_VOLUME},"
                     f"afade=t=out:st={fade_start:.2f}:d={SFX_FADE_OUT_S}[s{i}]")
    inputs = "[v]" + "".join(f"[s{i}]" for i in range(1, len(sfx_files) + 1))
    parts.append(f"{inputs}amix=inputs={len(sfx_files) + 1}:duration=first:dropout_transition=0:normalize=0[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2", str(output_path)]
    await _run_ffmpeg(cmd, "trộn tiếng động vào giọng")
    return str(output_path)


def energy_segments(energies: Sequence[Optional[str]], durations: Sequence[float]) -> List[Tuple[str, float]]:
    """Gộp các cảnh liền nhau cùng độ căng thành đoạn [(tên bản nhạc, số giây)]."""
    segments: List[Tuple[str, float]] = []
    for energy, seconds in zip(energies, durations):
        track = ENERGY_TRACKS.get(energy or DEFAULT_ENERGY, ENERGY_TRACKS[DEFAULT_ENERGY])
        if segments and segments[-1][0] == track:
            segments[-1] = (track, segments[-1][1] + float(seconds))
        else:
            segments.append((track, float(seconds)))
    return segments


async def build_energy_bgm(segments: Sequence[Tuple[str, float]], output_path: str) -> str:
    """Nhạc nền cả video ghép từ các đoạn theo độ căng: mỗi đoạn lặp bản nhạc của nó cho đủ số giây, mờ vào/ra BGM_FADE_S
    để chuyển bản không giật. Bản nhạc thiếu file thì báo lỗi (người gọi quyết định dùng nhạc nền chung)."""
    cmd = ["ffmpeg", "-y", "-v", "error"]
    parts = []
    for i, (track, seconds) in enumerate(segments):
        path = config.BGM_DIR / f"{track}.mp3"
        if not path.is_file():
            raise FileNotFoundError(f"thiếu nhạc nền {path.name}")
        cmd += ["-stream_loop", "-1", "-t", f"{seconds:.3f}", "-i", str(path)]
        fade = min(BGM_FADE_S, seconds / 3)
        parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,afade=t=in:d={fade:.2f},"
                     f"afade=t=out:st={max(0.0, seconds - fade):.2f}:d={fade:.2f}[b{i}]")
    parts.append("".join(f"[b{i}]" for i in range(len(segments))) + f"concat=n={len(segments)}:v=0:a=1[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "3", str(output_path)]
    await _run_ffmpeg(cmd, "ghép nhạc nền theo độ căng")
    return str(output_path)
