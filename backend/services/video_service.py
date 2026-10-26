import asyncio
import logging
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

import config
from services.tts_service import MediaDurationError, get_audio_duration

logger = logging.getLogger("story_studio.video_service")

# Mọi đoạn cảnh dùng chung định dạng âm thanh để ghép `-c copy` không hỏng
# khi trộn VieNeu, Edge-TTS (24 kHz mono) và cảnh im lặng.
AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2
SEGMENT_AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_SAMPLE_RATE), "-ac", str(AUDIO_CHANNELS)]
SILENT_AUDIO_SRC = f"anullsrc=r={AUDIO_SAMPLE_RATE}:cl=stereo"

# Resolution presets
# Độ to chuẩn của video thành phẩm: -16 LUFS, đỉnh -1.5 dBTP (mức các kênh YouTube hay dùng); loudnorm nâng tần số
# mẫu lên 192 kHz nên lấy mẫu lại 48 kHz.
LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"

RESOLUTIONS = {
    "1080p": (1920, 1080),
    "720p": (1280, 720),
}

# Supported camera motions & Action Motion FX
CAMERA_MOTIONS = [
    "zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "diagonal",
    "action_camera_shake",
    "manga_speedlines",
    "panoramic_sweep",
    "punch_zoom",
    "neo_noir_dutch_tilt",
    "neo_noir_rain_motion",
    "static",
]

def parse_srt_time(ts_str: str) -> float:
    """Parse SRT timestamp '00:00:01,234' into seconds."""
    ts_str = ts_str.strip().replace(",", ".")
    parts = ts_str.split(":")
    hours = float(parts[0])
    minutes = float(parts[1])
    seconds = float(parts[2])
    return hours * 3600.0 + minutes * 60.0 + seconds

def format_srt_time(sec: float) -> str:
    """Format seconds into SRT timestamp '00:00:01,234'."""
    total_ms = max(0, int(round(sec * 1000)))
    hours = total_ms // 3600000
    minutes = (total_ms % 3600000) // 60000
    secs = (total_ms % 60000) // 1000
    ms = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

def merge_srt_files(scenes_srt_list: List[Dict[str, Any]], output_srt_path: str) -> str:
    """
    Merge multiple SRT files sequentially by applying cumulative duration offsets.
    scenes_srt_list: [{"srt_path": "...", "duration": 3.5}, ...]
    """
    merged_cues: List[str] = []
    cue_index = 1
    current_offset = 0.0

    for item in scenes_srt_list:
        srt_file = item.get("srt_path")
        duration = float(item.get("duration", 3.0))

        if srt_file and os.path.exists(srt_file):
            with open(srt_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()

            blocks = content.split("\n\n")
            for block in blocks:
                lines = [line.strip() for line in block.split("\n") if line.strip()]
                time_line_idx = -1
                for idx, l in enumerate(lines):
                    if "-->" in l:
                        time_line_idx = idx
                        break

                if time_line_idx != -1:
                    time_parts = lines[time_line_idx].split("-->")
                    try:
                        start_t = parse_srt_time(time_parts[0]) + current_offset
                        end_t = parse_srt_time(time_parts[1]) + current_offset
                        text_lines = "\n".join(lines[time_line_idx + 1:])
                        if text_lines.strip():
                            merged_cues.append(
                                f"{cue_index}\n{format_srt_time(start_t)} --> {format_srt_time(end_t)}\n{text_lines}\n"
                            )
                            cue_index += 1
                    except Exception:
                        pass

        current_offset += duration

    out_p = Path(output_srt_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        f.write("\n".join(merged_cues) + "\n")

    return str(out_p)

def build_zoompan_filter(
    camera_motion: str,
    duration: float,
    width: int = 1280,
    height: int = 720,
    fps: int = 25,
) -> str:
    """
    Generate the appropriate FFmpeg video filter for Ken Burns & Action Motion FX.
    Adapts zoom and pan velocities smoothly to duration (Fast/Vox pacing 3-4s, balanced 5s, narrative 7s+).
    Ensures continuous motion without premature freeze or frame jitter.
    Supports:
      - zoom_in, zoom_out, pan_left, pan_right, diagonal
      - action_camera_shake: violent rapid vibration for battle impacts (frame MAD > 15.0)
      - manga_speedlines: fast converging zoom with action intensity
      - panoramic_sweep: 2-stage multi-stop pan for wide double-page spreads
      - punch_zoom: sudden instant snap zoom into character focal point
      - static: clean scaling
    """
    total_frames = max(25, int(duration * fps))

    if camera_motion == "random":
        camera_motion = random.choice([
            "zoom_in", "zoom_out", "pan_left", "pan_right", "diagonal",
            "action_camera_shake", "manga_speedlines", "panoramic_sweep", "punch_zoom"
        ])

    # Target zoom ratio: 1.25 for dynamic cinematic feeling
    max_zoom = 1.25
    # Calculate step dynamically so motion spans the entire clip smoothly
    zoom_step = max(0.0008, round((max_zoom - 1.0) / total_frames, 5))

    if camera_motion == "zoom_in":
        # Smooth zoom in towards center from 1.0 to 1.25
        return (
            f"zoompan=z='min(zoom+{zoom_step:.5f},{max_zoom:.2f})':d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        )
    elif camera_motion == "zoom_out":
        # Smooth zoom out from 1.25 down to 1.0
        return (
            f"zoompan=z='if(lte(on,1),{max_zoom:.2f},max(1.001,zoom-{zoom_step:.5f}))':d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        )
    elif camera_motion == "pan_left":
        # Pan horizontally from right to left smoothly across total_frames
        return (
            f"zoompan=z=1.18:d={total_frames}:"
            f"x='(iw-iw/zoom)*(1-on/{total_frames})':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        )
    elif camera_motion == "pan_right":
        # Pan horizontally from left to right smoothly across total_frames
        return (
            f"zoompan=z=1.18:d={total_frames}:"
            f"x='(iw-iw/zoom)*(on/{total_frames})':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        )
    elif camera_motion in ("diagonal", "kenburns_diagonal", "kenburns-diagonal"):
        # Smooth diagonal pan and zoom
        diag_step = max(0.0008, round(0.18 / total_frames, 5))
        return (
            f"zoompan=z='min(zoom+{diag_step:.5f},1.20)':d={total_frames}:"
            f"x='(iw-iw/zoom)*(on/{total_frames})':y='(ih-ih/zoom)*(on/{total_frames})':"
            f"s={width}x{height}:fps={fps}"
        )
    elif camera_motion == "action_camera_shake":
        # Base zoom 1.18 provides safety margin against black borders during heavy shaking
        # High-frequency sinusoidal displacement creates intense battle impact (MAD > 15.0)
        return (
            f"zoompan=z=1.18:d={total_frames}:"
            f"x='(iw/2-(iw/zoom/2))+sin(on*4.0)*22+sin(on*9.5)*10':"
            f"y='(ih/2-(ih/zoom/2))+cos(on*5.2)*18+cos(on*11.3)*8':"
            f"s={width}x{height}:fps={fps}"
        )
    elif camera_motion == "manga_speedlines":
        # Rapid convergent action zoom
        sl_step = max(0.0020, round(0.25 / total_frames, 5))
        return (
            f"zoompan=z='min(zoom+{sl_step:.5f},1.32)':d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        )
    elif camera_motion == "panoramic_sweep":
        # Multi-stop 2-phase panoramic sweep for wide double-page spreads
        half_f = max(1, total_frames // 2)
        return (
            f"zoompan=z='if(lte(on,{half_f}),1.10+0.06*(on/{half_f}),1.16+0.06*((on-{half_f})/{half_f}))':"
            f"d={total_frames}:"
            f"x='if(lte(on,{half_f}),(iw-iw/zoom)*0.35*(on/{half_f}),(iw-iw/zoom)*(0.35+0.65*((on-{half_f})/{half_f})))':"
            f"y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        )
    elif camera_motion == "punch_zoom":
        # Instant punch-in magnification jump onto focal point/face
        punch_frame = max(8, int(total_frames * 0.2))
        return (
            f"zoompan=z='if(lt(on,{punch_frame}),1.05,1.38+0.04*((on-{punch_frame})/{total_frames}))':"
            f"d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        )
    elif camera_motion == "neo_noir_dutch_tilt":
        # Dutch tilt slow creep with film grain and atmospheric vignette
        zoom_step = max(0.0005, round(0.10 / total_frames, 5))
        return (
            f"zoompan=z='min(zoom+{zoom_step:.5f},1.15)':d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)+sin(on*0.04)*10':y='ih/2-(ih/zoom/2)+cos(on*0.03)*6':s={width}x{height}:fps={fps},"
            f"noise=alls=8:allf=t,vignette=PI/4"
        )
    elif camera_motion == "neo_noir_rain_motion":
        # Atmospheric rain noir motion with subtle film grain and high contrast
        return (
            f"zoompan=z='min(zoom+0.0008,1.10)':d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},"
            f"noise=alls=12:allf=t,eq=contrast=1.15:brightness=-0.03"
        )
    else:
        # static
        return f"scale={width}:{height},setsar=1"

def ensure_speedlines_asset(asset_path: Optional[str] = None, dark: bool = False) -> str:
    """
    Ensure transparent PNG asset of manga radial speedlines exists.
    If not found, procedurally generates a 1920x1080 transparent PNG with convergent speedline rays.
    """
    if asset_path is None:
        asset_dir = Path(__file__).resolve().parent.parent / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        fname = "manga_speedlines_dark.png" if dark else "manga_speedlines.png"
        asset_path = str(asset_dir / fname)

    p = Path(asset_path)
    if p.exists() and p.stat().st_size > 1000:
        return str(p)

    p.parent.mkdir(parents=True, exist_ok=True)
    import math
    from PIL import Image, ImageDraw

    w, h = 1920, 1080
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2
    num_lines = 140
    r_inner = min(w, h) * 0.22
    r_outer = max(w, h) * 0.88

    for i in range(num_lines):
        angle = (2 * math.pi / num_lines) * i + (math.sin(i * 3.7) * 0.02)
        inner = r_inner * (0.8 + 0.45 * abs(math.sin(i * 5.3)))
        outer = r_outer
        x1 = cx + inner * math.cos(angle)
        y1 = cy + inner * math.sin(angle)
        x2 = cx + outer * math.cos(angle)
        y2 = cy + outer * math.sin(angle)
        width_factor = 3.5 + 4.0 * abs(math.cos(i * 2.1))
        dx = -math.sin(angle) * width_factor
        dy = math.cos(angle) * width_factor
        points = [(x1, y1), (x2 + dx, y2 + dy), (x2 - dx, y2 - dy)]
        fill = (20, 20, 20, 185) if dark else (255, 255, 255, 175)
        draw.polygon(points, fill=fill)

    img.save(p, "PNG")
    return str(p)

async def render_scene_video(
    image_path: str,
    audio_path: Optional[str],
    output_path: str,
    duration: Optional[float] = None,
    camera_motion: str = "zoom_in",
    resolution: str = "1080p",
    fps: int = 25,
    transition: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Render a single scene into an MP4 segment with Ken Burns or Action Motion FX.
    Synchronized with the audio duration.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Check if input media is already an existing video file (AI Video or imported MP4)
    is_video_input = str(image_path).lower().endswith((".mp4", ".mov", ".webm", ".avi", ".mkv"))

    if is_video_input and Path(image_path).resolve() == out.resolve():
        raise ValueError(f"Đầu vào và đầu ra trùng file ({out}); clip gốc phải nằm ở file riêng.")

    # Determine duration
    if duration is None or duration <= 0:
        if audio_path and os.path.exists(audio_path):
            duration = get_audio_duration(audio_path)
        elif is_video_input:
            duration = get_audio_duration(str(image_path))  # ffprobe đọc được thời lượng video
        else:
            duration = 3.5

    # Target resolution
    w, h = RESOLUTIONS.get(resolution, (1280, 720))

    # Optional transition: dip to black / fade / white flash (dùng chung cho ảnh và video)
    fade_vf = ""
    if transition in ("dip_to_black", "fade_black", "fade"):
        fade_dur = min(0.35, max(0.18, duration / 6.0))
        fade_vf = f",fade=t=in:st=0:d={fade_dur:.2f},fade=t=out:st={(duration-fade_dur):.2f}:d={fade_dur:.2f}"
    elif transition in ("flash_white", "white_flash"):
        fade_dur = min(0.25, max(0.12, duration / 8.0))
        fade_vf = f",fade=t=in:st=0:d={fade_dur:.2f}:color=white,fade=t=out:st={(duration-fade_dur):.2f}:d={fade_dur:.2f}:color=white"

    if is_video_input:
        has_video_audio = False
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(image_path)],
                capture_output=True, text=True, timeout=5
            )
            has_video_audio = bool(probe.stdout.strip())
        except Exception:
            has_video_audio = False

        # -stream_loop -1: clip Muse (5-10s) ngắn hơn giọng đọc thì lặp lại, -t cắt đúng độ dài cảnh
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(image_path)]
        filter_complex_parts = [
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={fps},setpts=PTS-STARTPTS{fade_vf}[vout]"
        ]

        has_voice = audio_path and os.path.exists(audio_path)
        if has_voice:
            cmd.extend(["-i", str(audio_path)])

        if has_video_audio and has_voice:
            # Tôn trọng âm thanh video: Trộn âm thanh nền video (25% ambient) với giọng đọc Voice (100%).
            # normalize=0 để giọng không bị hạ một nửa so với cảnh ảnh.
            filter_complex_parts.append(
                "[0:a]volume=0.25[amb];[1:a]volume=1.0[voice];[voice][amb]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
            )
            audio_map = "[aout]"
        elif has_voice:
            audio_map = "1:a"
        elif has_video_audio:
            filter_complex_parts.append("[0:a]volume=0.8[aout]")
            audio_map = "[aout]"
        else:
            cmd.extend(["-f", "lavfi", "-i", SILENT_AUDIO_SRC])
            audio_map = "1:a"

        cmd.extend([
            "-filter_complex", ";".join(filter_complex_parts),
            "-map", "[vout]",
            "-map", audio_map,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            *SEGMENT_AUDIO_ARGS,
            str(out),
        ])
    else:
        # Base video filter for static image (Ken Burns)
        vf = build_zoompan_filter(
            camera_motion=camera_motion,
            duration=duration,
            width=w,
            height=h,
            fps=fps,
        ) + fade_vf

        # Prepare command
        cmd = ["ffmpeg", "-y"]
        cmd.extend(["-loop", "1", "-i", str(image_path)])

        # Check if manga_speedlines with overlay is used
        sl_asset = ensure_speedlines_asset()
        use_speedlines_overlay = (camera_motion == "manga_speedlines" and os.path.exists(sl_asset))

        if use_speedlines_overlay:
            cmd.extend(["-loop", "1", "-i", str(sl_asset)])
            if audio_path and os.path.exists(audio_path):
                cmd.extend(["-i", str(audio_path)])
            else:
                cmd.extend(["-f", "lavfi", "-i", SILENT_AUDIO_SRC])

            fc = (
                f"[0:v]{vf}[zoomed];"
                f"[1:v]scale={w}:{h},format=rgba[sl];"
                f"[zoomed][sl]overlay=x=0:y=0:format=auto[vout]"
            )
            cmd.extend([
                "-filter_complex", fc,
                "-map", "[vout]",
                "-map", "2:a",
                "-t", str(duration),
                "-c:v", "libx264",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                *SEGMENT_AUDIO_ARGS,
                "-shortest",
                str(out),
            ])
        else:
            if audio_path and os.path.exists(audio_path):
                cmd.extend(["-i", str(audio_path)])
            else:
                cmd.extend(["-f", "lavfi", "-i", SILENT_AUDIO_SRC])

            cmd.extend([
                "-vf", vf,
                "-t", str(duration),
                "-c:v", "libx264",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                *SEGMENT_AUDIO_ARGS,
                "-shortest",
                str(out),
            ])

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        err_msg = stderr.decode(errors="ignore")[-400:]
        raise RuntimeError(f"FFmpeg scene render failed (code {process.returncode}): {err_msg}")

    return {
        "video_path": str(out),
        "duration": duration,
        "motion": camera_motion,
        "resolution": f"{w}x{h}",
    }

async def build_xfade_video(
    scene_video_paths: List[str],
    durations: List[float],
    output_video_path: Path,
    transition_name: str = "fade",
    trans_dur: float = 0.45,
) -> bool:
    """
    Seamlessly crossfade multiple video clips using FFmpeg xfade and acrossfade filters.
    """
    if len(scene_video_paths) < 2:
        return False

    n = len(scene_video_paths)
    min_dur = min(durations) if durations else 3.0
    safe_trans_dur = min(trans_dur, max(0.2, min_dur * 0.25))

    offsets = []
    cur_off = durations[0] - safe_trans_dur
    offsets.append(cur_off)
    for i in range(1, n - 1):
        cur_off += durations[i] - safe_trans_dur
        offsets.append(cur_off)

    inputs = []
    for vp in scene_video_paths:
        inputs.extend(["-i", str(vp)])

    v_lines = []
    a_lines = []
    for i in range(n - 1):
        pv = f"[v{i}]" if i > 0 else "[0:v]"
        nv = f"[{i+1}:v]"
        ov = f"[v{i+1}]" if i < n - 2 else "[vout]"
        v_lines.append(f"{pv}{nv}xfade=transition={transition_name}:duration={safe_trans_dur:.2f}:offset={offsets[i]:.3f}{ov}")

        pa = f"[a{i}]" if i > 0 else "[0:a]"
        na = f"[{i+1}:a]"
        oa = f"[a{i+1}]" if i < n - 2 else "[aout]"
        a_lines.append(f"{pa}{na}acrossfade=d={safe_trans_dur:.2f}{oa}")

    fc = ";".join(v_lines + a_lines)
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", fc,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        *SEGMENT_AUDIO_ARGS,
        str(output_video_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return proc.returncode == 0 and output_video_path.exists() and output_video_path.stat().st_size > 1000

async def assemble_full_video(
    scene_video_paths: List[str],
    scene_srt_infos: List[Dict[str, Any]],
    output_video_path: str,
    bgm_path: Optional[str] = None,
    bgm_volume: float = 0.2,
    ducking: bool = True,
    hardsub: bool = True,
    subtitle_style: str = "kinetic_pop",  # kinetic_pop, karaoke_sweep, classic
    resolution: str = "1080p",
    transition: Optional[str] = "dip_to_black",
    scenes_data: Optional[List[Dict[str, Any]]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Assemble all scene video segments into a complete narrative movie:
    1. Support seamless scene transitions (cut, dip_to_black, crossfade, wipe_left).
    2. Support Kinetic Karaoke (.ass) word-by-word highlights and classic (.srt).
    3. Apply Adaptive Audio Ducking with sidechaincompress to lower BGM when speech plays.
    4. Auto-clean temporary assembly files after completion.
    """
    if not scene_video_paths:
        raise ValueError("Cannot assemble video with empty scene list.")

    out_file = Path(output_video_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = out_file.parent / "temp_assemble"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        if progress_callback:
            progress_callback(65, 3, "Đang kết nối các phân đoạn video và chuyển cảnh...")

        raw_concat_video = temp_dir / "raw_concat.mp4"
        use_xfade = (transition in ("crossfade", "wipe_left", "circle_crop") and len(scene_video_paths) >= 2)
        xfade_ok = False

        if use_xfade:
            try:
                durs = [float(item.get("duration") or 3.5) for item in scene_srt_infos]
                if len(durs) != len(scene_video_paths):
                    durs = [get_audio_duration(vp) for vp in scene_video_paths]
                trans_map = {"crossfade": "fade", "wipe_left": "wipeleft", "circle_crop": "circlecrop"}
                t_name = trans_map.get(transition, "fade")
                xfade_ok = await build_xfade_video(
                    scene_video_paths=scene_video_paths,
                    durations=durs,
                    output_video_path=raw_concat_video,
                    transition_name=t_name,
                    trans_dur=0.45,
                )
            except Exception as e:
                logger.warning(f"Xfade transition failed ({e}), falling back to concat demuxer.")
                xfade_ok = False

        if not xfade_ok:
            # Standard fast concat demuxer (supports dip_to_black baked into segments)
            concat_list_file = temp_dir / "concat_list.txt"
            with open(concat_list_file, "w", encoding="utf-8") as f:
                for vp in scene_video_paths:
                    safe_vp = os.path.abspath(vp).replace("\\", "/")
                    f.write(f"file '{safe_vp}'\n")

            cmd_concat = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_file),
                "-c", "copy",
                str(raw_concat_video),
            ]

            p1 = await asyncio.create_subprocess_exec(
                *cmd_concat,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await p1.communicate()
            if p1.returncode != 0:
                cmd_concat_reencode = [
                    "ffmpeg", "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_list_file),
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    *SEGMENT_AUDIO_ARGS,
                    str(raw_concat_video),
                ]
                p1b = await asyncio.create_subprocess_exec(
                    *cmd_concat_reencode,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await p1b.communicate()

        if progress_callback:
            progress_callback(75, 3, "Đang tạo phụ đề động Kinetic Karaoke & SRT...")

        # Step 3: Merge subtitles (both SRT and Kinetic ASS)
        merged_srt_file = temp_dir / "full_subtitles.srt"
        merged_ass_file = temp_dir / "full_subtitles.ass"
        merge_srt_files(scene_srt_infos, str(merged_srt_file))

        has_ass = False
        if scenes_data:
            try:
                from services.subtitle_engine import generate_karaoke_ass
                generate_karaoke_ass(
                    scenes_data=scenes_data,
                    output_ass_path=str(merged_ass_file),
                    style_mode=subtitle_style or "kinetic_pop"
                )
                has_ass = merged_ass_file.exists() and merged_ass_file.stat().st_size > 100
            except Exception as e:
                logger.warning(f"ASS subtitle generation failed ({e}), falling back to SRT.")
                has_ass = False

        # Step 4: Final mixing & encoding (BGM Ducking + Hardsub)
        if progress_callback:
            progress_callback(85, 4, "Đang xử lý âm thanh Ducking và in phụ đề Hardsub...")

        has_bgm = bgm_path and os.path.exists(bgm_path)
        has_sub = hardsub and os.path.exists(merged_srt_file) and os.path.getsize(merged_srt_file) > 10

        cmd_final = ["ffmpeg", "-y", "-i", str(raw_concat_video)]

        if has_bgm:
            cmd_final.extend(["-stream_loop", "-1", "-i", str(bgm_path)])

        filter_complex_parts: List[str] = []
        video_map = "0:v"
        audio_map = "0:a"

        # Video subtitle filter: prioritize ASS kinetic karaoke
        if hardsub:
            if has_ass:
                escaped_ass = os.path.abspath(merged_ass_file).replace("\\", "/").replace(":", "\\:")
                escaped_fonts = os.path.abspath(config.FONTS_DIR).replace("\\", "/").replace(":", "\\:")
                # fontsdir: font đóng gói (Be Vietnam Pro) cho phụ đề, không phụ thuộc font cài trên máy
                filter_complex_parts.append(f"[0:v]ass='{escaped_ass}':fontsdir='{escaped_fonts}'[vout]")
                video_map = "[vout]"
            elif has_sub:
                escaped_srt = os.path.abspath(merged_srt_file).replace("\\", "/").replace(":", "\\:")
                w, h = RESOLUTIONS.get(resolution, (1920, 1080))
                font_size = 24 if w >= 1920 else 18
                margin_v = 40 if w >= 1920 else 28
                sub_style = (
                    f"FontName=Arial,FontSize={font_size},PrimaryColour=&H00FFFFFF,"
                    f"OutlineColour=&H00000000,BorderStyle=3,Outline=2,Shadow=1,MarginV={margin_v},Alignment=2"
                )
                filter_complex_parts.append(f"[0:v]subtitles='{escaped_srt}':force_style='{sub_style}'[vout]")
                video_map = "[vout]"

        # Âm thanh: trộn nhạc nền (amix normalize=0: mặc định amix chia đôi âm lượng, giọng bị nhỏ ~6 dB) rồi chuẩn hoá
        # độ to về mức YouTube. Gặp 26/10/2026: video ra trung bình -29 dB, nghe nhỏ hơn hẳn các kênh khác.
        if has_bgm:
            if ducking:
                filter_complex_parts.append(
                    f"[1:a]volume={bgm_volume:.2f}[bgm_vol];"
                    f"[bgm_vol][0:a]sidechaincompress=threshold=0.08:ratio=4:attack=100:release=500[ducked_bgm];"
                    f"[0:a][ducked_bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,{LOUDNORM_FILTER}[aout]"
                )
            else:
                filter_complex_parts.append(
                    f"[1:a]volume={bgm_volume:.2f}[bgm_vol];"
                    f"[0:a][bgm_vol]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,{LOUDNORM_FILTER}[aout]"
                )
        else:
            filter_complex_parts.append(f"[0:a]{LOUDNORM_FILTER}[aout]")
        audio_map = "[aout]"

        # Hình không qua bộ lọc nào (không in phụ đề) thì giữ nguyên, không mã hoá lại
        video_codec = (["-c:v", "copy"] if video_map == "0:v"
                       else ["-c:v", "libx264", "-preset", "fast", "-threads", "0", "-pix_fmt", "yuv420p"])
        cmd_final.extend([
            "-filter_complex", ";".join(filter_complex_parts),
            "-map", video_map,
            "-map", audio_map,
            *video_codec,
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_file),
        ])

        p_final = await asyncio.create_subprocess_exec(
            *cmd_final,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        p_out, p_err = await p_final.communicate()

        if p_final.returncode != 0:
            err_msg = p_err.decode(errors="ignore")[-400:]
            raise RuntimeError(f"FFmpeg assemble failed (code {p_final.returncode}): {err_msg}")

        # Calculate final duration (file đã ghép xong: đo lỗi thì ước lượng bằng tổng các cảnh, không báo thất bại)
        try:
            total_duration = get_audio_duration(str(out_file))
        except MediaDurationError as e:
            total_duration = round(sum(float(i.get("duration") or 0) for i in scene_srt_infos), 3)
            logger.warning(f"{e}; ước lượng thời lượng video bằng tổng các cảnh: {total_duration}s")

        # Save consolidated SRT and ASS alongside final video for softsub/download
        final_srt_path = out_file.with_suffix(".srt")
        final_ass_path = out_file.with_suffix(".ass")
        if os.path.exists(merged_srt_file):
            shutil.copyfile(merged_srt_file, final_srt_path)
        if os.path.exists(merged_ass_file):
            shutil.copyfile(merged_ass_file, final_ass_path)

        if progress_callback:
            progress_callback(100, 4, "Hoàn tất dựng video truyện thành công!")

        return {
            "video_path": str(out_file),
            "srt_path": str(final_srt_path),
            "ass_path": str(final_ass_path) if final_ass_path.exists() else None,
            "duration": total_duration,
            "resolution": resolution,
            "transition": transition,
            "subtitle_style": subtitle_style,
        }
    finally:
        # Clean up temporary assemble files to prevent disk leak
        shutil.rmtree(temp_dir, ignore_errors=True)

def generate_default_bgm_track(output_path: str, mood: str = "peaceful") -> str:
    """Generate a clean procedural ambient BGM loop using FFmpeg audio synthesis."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 10000:
        return str(out)

    if mood == "peaceful":
        # Calming A major chord (220, 277, 330) with chorus
        expr = "0.06*sin(2*PI*220*t)+0.04*sin(2*PI*277.18*t)+0.04*sin(2*PI*329.63*t)+0.02*sin(2*PI*440*t)"
        filter_expr = "lowpass=f=1200,chorus=0.5:0.9:50|60:0.4|0.32:0.25|0.4:2|1.2"
    elif mood == "dark":
        # Dark mysterious low drone
        expr = "0.08*sin(2*PI*110*t)+0.05*sin(2*PI*130.81*t)+0.04*sin(2*PI*164.81*t)+0.03*sin(2*PI*220*t)"
        filter_expr = "lowpass=f=600,flanger=delay=5:depth=2:regen=50"
    else:  # adventure
        # Cinematic rhythmic progression
        expr = "0.07*sin(2*PI*146.83*t)+0.05*sin(2*PI*220*t)+0.05*sin(2*PI*293.66*t)+0.03*sin(2*PI*370*t)"
        filter_expr = "lowpass=f=1800,chorus=0.6:0.8:40|50:0.3|0.3:0.3|0.3:1.5|1.5"

    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"aevalsrc={expr}:d=30:s=44100",
        "-af", filter_expr,
        "-c:a", "libmp3lame", "-b:a", "128k",
        str(out),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return str(out)

def get_available_bgm_tracks(bgm_dir: Path) -> List[Dict[str, Any]]:
    """List available BGM tracks and ensure built-in defaults exist."""
    bgm_dir.mkdir(parents=True, exist_ok=True)

    tracks = [
        {"id": "ambient_peaceful", "name": "Thanh bình (Peaceful Ambient)", "mood": "peaceful", "filename": "ambient_peaceful.mp3"},
        {"id": "cinematic_adventure", "name": "Hùng tráng (Cinematic Adventure)", "mood": "adventure", "filename": "cinematic_adventure.mp3"},
        {"id": "mysterious_dark", "name": "Bí ẩn (Mysterious Dark)", "mood": "dark", "filename": "mysterious_dark.mp3"},
    ]

    result = []
    for t in tracks:
        track_path = bgm_dir / t["filename"]
        if not track_path.exists():
            try:
                generate_default_bgm_track(str(track_path), t["mood"])
            except Exception:
                pass
        
        result.append({
            "id": t["id"],
            "name": t["name"],
            "filename": t["filename"],
            "path": str(track_path),
            "url": f"/api/bgm/{t['filename']}",
            "exists": track_path.exists(),
        })

    # Also list any custom uploaded files in bgm_dir
    for f in bgm_dir.glob("*.mp3"):
        if f.name not in [t["filename"] for t in tracks]:
            result.append({
                "id": f.stem,
                "name": f.stem.replace("_", " ").title(),
                "filename": f.name,
                "path": str(f),
                "url": f"/api/bgm/{f.name}",
                "exists": True,
            })

    return result
