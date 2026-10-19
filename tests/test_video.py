import asyncio
import json
import os
import shutil
import subprocess
import sys
import pytest
from pathlib import Path

# Add backend directory to sys.path
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.video_service import (
    render_scene_video,
    assemble_full_video,
    build_zoompan_filter,
    generate_ai_video_segment,
    ensure_speedlines_asset,
    merge_srt_files,
    generate_default_bgm_track,
    get_available_bgm_tracks,
    parse_srt_time,
    format_srt_time,
    CAMERA_MOTIONS,
)
from services.image_service import generate_mock_cinematic
from services.tts_service import generate_speech

def probe_media_file(file_path: str) -> dict:
    """Run ffprobe on media file and return JSON analysis of streams and format."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)

def test_srt_time_helpers():
    """Verify parse_srt_time and format_srt_time conversions."""
    assert abs(parse_srt_time("00:00:01,500") - 1.5) < 0.001
    assert abs(parse_srt_time("00:01:05,250") - 65.25) < 0.001
    assert format_srt_time(1.5) == "00:00:01,500"
    assert format_srt_time(65.25) == "00:01:05,250"

def test_build_zoompan_filter():
    """Verify FFmpeg zoompan filter string construction for camera motions."""
    f_in = build_zoompan_filter("zoom_in", 3.0, 1280, 720, 25)
    assert "zoompan=" in f_in
    assert "min(zoom+" in f_in
    assert "1.25" in f_in
    assert "s=1280x720" in f_in

    f_out = build_zoompan_filter("zoom_out", 3.0, 1280, 720, 25)
    assert "zoompan=" in f_out
    assert "max(1.001,zoom-" in f_out

    f_pan_l = build_zoompan_filter("pan_left", 3.0, 1280, 720, 25)
    assert "zoompan=" in f_pan_l
    assert "pan_left" not in f_pan_l  # ensures it generated the math expression
    assert "(1-on/" in f_pan_l

    f_diag = build_zoompan_filter("diagonal", 3.0, 1280, 720, 25)
    assert "zoompan=" in f_diag
    assert "(on/" in f_diag

    # Action Motion FX verification
    f_shake = build_zoompan_filter("action_camera_shake", 3.0, 1280, 720, 25)
    assert "zoompan=" in f_shake
    assert "sin(on*" in f_shake
    assert "cos(on*" in f_shake

    f_manga = build_zoompan_filter("manga_speedlines", 3.0, 1280, 720, 25)
    assert "zoompan=" in f_manga
    assert "1.32" in f_manga

    f_pano = build_zoompan_filter("panoramic_sweep", 4.0, 1280, 720, 25)
    assert "zoompan=" in f_pano
    assert "0.35" in f_pano

    f_punch = build_zoompan_filter("punch_zoom", 3.0, 1280, 720, 25)
    assert "zoompan=" in f_punch
    assert "if(lt(on," in f_punch
    assert "1.38" in f_punch

    f_static = build_zoompan_filter("static", 3.0, 1280, 720, 25)
    assert "scale=1280:720" in f_static

    # Verify all supported camera motions
    for m in CAMERA_MOTIONS:
        vf = build_zoompan_filter(m, 3.0, 1280, 720, 25)
        assert len(vf) > 10

def test_merge_srt_files(tmp_path):
    """Verify merging multiple SRT files applies cumulative duration offsets correctly."""
    srt1 = tmp_path / "scene1.srt"
    srt2 = tmp_path / "scene2.srt"
    merged = tmp_path / "merged.srt"

    with open(srt1, "w", encoding="utf-8") as f:
        f.write("1\n00:00:00,500 --> 00:00:02,000\nLời thoại cảnh 1\n\n")

    with open(srt2, "w", encoding="utf-8") as f:
        f.write("1\n00:00:00,400 --> 00:00:01,800\nLời thoại cảnh 2\n\n")

    scenes_info = [
        {"srt_path": str(srt1), "duration": 3.0},
        {"srt_path": str(srt2), "duration": 3.0},
    ]

    out_path = merge_srt_files(scenes_info, str(merged))
    assert os.path.exists(out_path)

    with open(out_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = [l.strip() for l in content.split("\n") if l.strip()]
    # Cue 1 starts at 0.5s
    assert "00:00:00,500 --> 00:00:02,000" in lines
    # Cue 2 starts at 0.4s + 3.0s = 3.4s -> 00:00:03,400
    assert "00:00:03,400 --> 00:00:04,800" in lines
    assert "Lời thoại cảnh 1" in content
    assert "Lời thoại cảnh 2" in content

@pytest.mark.asyncio
async def test_render_scene_video_zoom_in(tmp_path):
    """Test rendering a scene video with zoom_in Ken Burns effect and verify ffprobe streams."""
    img_path = str(tmp_path / "scene1_img.jpg")
    audio_path = str(tmp_path / "scene1_voice.mp3")
    video_out = str(tmp_path / "scene1_video.mp4")

    # Generate test image
    generate_mock_cinematic("Hero standing at forest entrance", "cinematic_realistic", img_path, 1)

    # Generate test audio
    await generate_speech("Nhân vật chính bước vào khu rừng thần bí.", "vi-VN-HoaiMyNeural", audio_path)

    # Render scene video
    res = await render_scene_video(
        image_path=img_path,
        audio_path=audio_path,
        output_path=video_out,
        camera_motion="zoom_in",
        resolution="720p",
        fps=25,
    )

    assert os.path.exists(res["video_path"])
    assert res["motion"] == "zoom_in"
    assert res["resolution"] == "1280x720"

    # Deep verification via ffprobe
    probe = probe_media_file(video_out)
    streams = probe.get("streams", [])
    v_stream = next((s for s in streams if s["codec_type"] == "video"), None)
    a_stream = next((s for s in streams if s["codec_type"] == "audio"), None)

    assert v_stream is not None, "Missing video stream"
    assert a_stream is not None, "Missing audio stream"
    assert v_stream["codec_name"] == "h264", f"Unexpected video codec: {v_stream['codec_name']}"
    assert a_stream["codec_name"] == "aac", f"Unexpected audio codec: {a_stream['codec_name']}"
    assert v_stream["width"] == 1280
    assert v_stream["height"] == 720

    duration = float(probe["format"]["duration"])
    assert duration > 1.0, f"Video duration too short: {duration}s"

@pytest.mark.asyncio
async def test_render_scene_video_pan_left(tmp_path):
    """Test rendering a scene video with pan_left camera motion."""
    img_path = str(tmp_path / "scene2_img.jpg")
    audio_path = str(tmp_path / "scene2_voice.mp3")
    video_out = str(tmp_path / "scene2_video.mp4")

    generate_mock_cinematic("A vast cyberpunk city skyline", "cyberpunk", img_path, 2)
    await generate_speech("Thành phố tương lai chìm trong ánh đèn rực rỡ.", "vi-VN-NamMinhNeural", audio_path)

    res = await render_scene_video(
        image_path=img_path,
        audio_path=audio_path,
        output_path=video_out,
        camera_motion="pan_left",
        resolution="720p",
        fps=25,
    )

    assert os.path.exists(res["video_path"])
    probe = probe_media_file(video_out)
    streams = probe.get("streams", [])
    v_stream = next((s for s in streams if s["codec_type"] == "video"), None)
    assert v_stream is not None
    assert v_stream["codec_name"] == "h264"
    assert v_stream["width"] == 1280
    assert v_stream["height"] == 720

def test_bgm_procedural_generation(tmp_path):
    """Verify procedural BGM loop generation for multiple moods."""
    for mood in ["peaceful", "dark", "adventure"]:
        bgm_file = tmp_path / f"bgm_{mood}.mp3"
        track_path = generate_default_bgm_track(str(bgm_file), mood)
        assert os.path.exists(track_path)
        assert os.path.getsize(track_path) > 10000, f"BGM file too small for {mood}"

        probe = probe_media_file(track_path)
        a_stream = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
        assert a_stream is not None
        assert a_stream["codec_name"] == "mp3"
        dur = float(probe["format"]["duration"])
        assert dur >= 29.0, f"Expected 30s BGM, got {dur}s"

@pytest.mark.asyncio
async def test_assemble_full_video_with_ducking_and_hardsub(tmp_path):
    """Test assembling multi-scene movie with BGM ducking (sidechaincompress) and hardsub subtitles."""
    # 1. Create 2 scenes
    scenes_videos = []
    scenes_srt = []

    for idx, (text, motion) in enumerate([
        ("Đây là cảnh mở đầu của chuyến phiêu lưu vĩ đại.", "zoom_in"),
        ("Họ vượt qua ngọn núi băng giá hiểm trở nhất thế giới.", "pan_right"),
    ], start=1):
        img_p = str(tmp_path / f"seg_{idx}_img.jpg")
        aud_p = str(tmp_path / f"seg_{idx}_aud.mp3")
        srt_p = str(tmp_path / f"seg_{idx}_aud.srt")
        vid_p = str(tmp_path / f"seg_{idx}_vid.mp4")

        generate_mock_cinematic(f"Scene {idx} visual", "cinematic_realistic", img_p, idx)
        tts_res = await generate_speech(text, "vi-VN-HoaiMyNeural", aud_p, srt_p)
        v_res = await render_scene_video(img_p, aud_p, vid_p, tts_res["duration"], motion, "720p", 25)

        scenes_videos.append(v_res["video_path"])
        scenes_srt.append({"srt_path": srt_p, "duration": v_res["duration"]})

    # 2. Generate BGM
    bgm_file = str(tmp_path / "test_bgm.mp3")
    generate_default_bgm_track(bgm_file, "peaceful")

    # 3. Assemble
    final_output = str(tmp_path / "final_movie.mp4")
    progress_updates = []

    def on_progress(p, step, msg):
        progress_updates.append((p, step, msg))

    assemble_res = await assemble_full_video(
        scene_video_paths=scenes_videos,
        scene_srt_infos=scenes_srt,
        output_video_path=final_output,
        bgm_path=bgm_file,
        bgm_volume=0.2,
        ducking=True,
        hardsub=True,
        resolution="720p",
        progress_callback=on_progress,
    )

    # 4. Check results
    assert os.path.exists(assemble_res["video_path"])
    assert os.path.exists(assemble_res["srt_path"])
    assert len(progress_updates) > 0

    # 5. FFprobe verification
    probe = probe_media_file(assemble_res["video_path"])
    v_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    a_stream = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)

    assert v_stream is not None, "Missing final video stream"
    assert a_stream is not None, "Missing final audio stream"
    assert v_stream["codec_name"] == "h264"
    assert a_stream["codec_name"] == "aac"
    assert v_stream["width"] == 1280
    assert v_stream["height"] == 720

    duration = float(probe["format"]["duration"])
    assert duration >= 4.0, f"Assembled duration too short: {duration}s"

def test_ensure_speedlines_asset():
    """Verify procedural generation of manga speedlines asset."""
    asset_path = ensure_speedlines_asset()
    assert os.path.exists(asset_path)
    assert os.path.getsize(asset_path) > 1000

@pytest.mark.asyncio
async def test_generate_ai_video_segment_fallback(tmp_path):
    """Test Cloud Video Gen Provider Interface offline fallback to FFmpeg Motion FX."""
    img_path = str(tmp_path / "ai_seg_input.jpg")
    vid_path = str(tmp_path / "ai_seg_output.mp4")
    generate_mock_cinematic("Hero battle punch", "cinematic_realistic", img_path, 1)

    res = await generate_ai_video_segment(
        image_path=img_path,
        prompt="Anime epic punch impact",
        motion_type="action_camera_shake",
        duration=2.5,
        output_path=vid_path,
        provider="auto",
        resolution="720p",
    )

    assert os.path.exists(res["video_path"])
    assert res["fallback_used"] is True
    assert res["motion"] == "action_camera_shake"
    assert res["provider"] == "ffmpeg_motion_fx"
    assert res["duration"] == 2.5

@pytest.mark.asyncio
async def test_render_scene_video_action_fx(tmp_path):
    """Test rendering scene video with manga speedlines and dip-to-black transition."""
    img_path = str(tmp_path / "speedline_input.jpg")
    vid_path = str(tmp_path / "speedline_output.mp4")
    generate_mock_cinematic("Fast samurai dash", "cinematic_realistic", img_path, 2)

    res = await render_scene_video(
        image_path=img_path,
        audio_path=None,
        output_path=vid_path,
        duration=2.0,
        camera_motion="manga_speedlines",
        resolution="720p",
        transition="dip_to_black",
    )

    assert os.path.exists(res["video_path"])
    probe = probe_media_file(vid_path)
    v_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    assert v_stream is not None
    assert v_stream["width"] == 1280
    assert v_stream["height"] == 720
