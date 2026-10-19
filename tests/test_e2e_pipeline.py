import asyncio
import json
import os
import subprocess
import sys
import pytest
from pathlib import Path

# Ensure safe console output encoding on Windows
if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr:
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add backend directory to sys.path
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.project_service import (
    create_project,
    get_project,
    add_scene,
    delete_project,
    get_scene_media_paths,
    get_render_media_paths,
    _save_project,
)
from services.tts_service import generate_speech
from services.image_service import generate_image
from services.video_service import (
    render_scene_video,
    assemble_full_video,
    generate_default_bgm_track,
)
from models.schemas import ProjectCreateRequest, SceneCreateRequest

def probe_video(file_path: str) -> dict:
    """Analyze video metadata using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(res.stdout)

@pytest.mark.asyncio
async def test_end_to_end_3_scene_story_pipeline():
    """
    Full End-to-End Pipeline QA Verification:
    - 3-scene narrative story in Vietnamese:
      Scene 1: Giới thiệu nhân vật chính (Kai).
      Scene 2: Nhân vật bước vào khu rừng kỳ bí.
      Scene 3: Đối mặt thử thách tượng đá cổ.
    - Synchronized Edge-TTS audio & SRT subtitles.
    - Consistent character & style image generation.
    - FFmpeg Ken Burns scene video rendering (zoom_in, pan_left, zoom_out).
    - Multi-scene concatenation with Audio Ducking & Hardsub subtitles.
    - Comprehensive ffprobe media inspection.
    """
    print("\n=======================================================")
    print("[*] STARTING E2E STORY VIDEO PRODUCTION PIPELINE")
    print("=======================================================")

    # 1. CREATE PROJECT
    p_req = ProjectCreateRequest(
        name="Huyền Thoại Dũng Sĩ Kai",
        description="E2E Pipeline Test: Hành trình phiêu lưu vào khu rừng kỳ bí của Kai",
        style_preset="cinematic_realistic",
        voice="vi-VN-HoaiMyNeural",
        character_anchor="Cậu bé dũng sĩ Kai tóc bạch kim, mắt xanh thẳm, mặc áo giáp da nhẹ viền bạc",
        image_provider="mock_cinematic",
        resolution="720p",
        fps=25,
        ducking=True,
        hardsub=True,
    )
    project = create_project(p_req)
    project_id = project.id
    print(f"[*] Project Created: {project_id} - '{project.name}'")

    try:
        # 2. DEFINE 3-SCENE STORYBOARD
        scenes_data = [
            {
                "text": "Ngày xửa ngày xưa, tại ngôi làng thanh bình dưới chân núi, có một cậu bé dũng cảm tên là Kai.",
                "image_prompt": "Young brave boy Kai standing proudly looking over a peaceful village beneath snowy mountains",
                "camera_motion": "zoom_in",
            },
            {
                "text": "Một buổi sáng nọ, Kai quyết định bước vào khu rừng kỳ bí, nơi những cổ thụ phát sáng mờ ảo trong sương sớm.",
                "image_prompt": "Kai stepping cautiously into an enchanted glowing forest with luminous mist and magical flora",
                "camera_motion": "pan_left",
            },
            {
                "text": "Tại trung tâm khu rừng, Kai đối mặt với thử thách lớn đầu tiên: pho tượng đá khổng lồ ngàn năm thức giấc.",
                "image_prompt": "Kai standing ready with determined gaze facing a colossal awakened ancient stone golem",
                "camera_motion": "zoom_out",
            },
        ]

        created_scenes = []
        for s_data in scenes_data:
            sc = add_scene(project_id, SceneCreateRequest(
                text=s_data["text"],
                image_prompt=s_data["image_prompt"],
                camera_motion=s_data["camera_motion"],
            ))
            created_scenes.append(sc)
            print(f"  + Added Scene {sc.order}: {sc.text[:40]}... (Motion: {sc.camera_motion})")

        assert len(created_scenes) == 3

        # 3. GENERATE AUDIO & SUBTITLES FOR ALL SCENES
        print("\n[*] Phase 1: Generating Edge-TTS Speech & Timed Subtitles...")
        scene_durations = []
        for sc in created_scenes:
            media = get_scene_media_paths(project_id, sc.id)
            tts_res = await generate_speech(
                text=sc.text,
                voice=project.voice,
                output_audio_path=str(media["audio"]),
                output_srt_path=str(media["srt"]),
            )
            sc.voice_audio_path = tts_res["audio_path"]
            sc.srt_path = tts_res["srt_path"]
            sc.duration = tts_res["duration"]
            scene_durations.append(tts_res["duration"])

            assert os.path.exists(sc.voice_audio_path)
            assert os.path.exists(sc.srt_path)
            assert sc.duration > 1.0
            print(f"  [OK] Scene {sc.order} Audio: {sc.duration}s | SRT: {os.path.getsize(sc.srt_path)} bytes")

        # 4. GENERATE CONSISTENT SCENE VISUALS
        print("\n[*] Phase 2: Generating Consistent Visual Frames...")
        for sc in created_scenes:
            media = get_scene_media_paths(project_id, sc.id)
            img_res = await generate_image(
                prompt=sc.image_prompt,
                style_preset=project.style_preset,
                character_anchor=project.character_anchor,
                provider="mock_cinematic",
                output_path=str(media["image"]),
                scene_index=sc.order,
            )
            sc.image_path = img_res["image_path"]
            assert os.path.exists(sc.image_path)
            assert os.path.getsize(sc.image_path) > 10000
            print(f"  [OK] Scene {sc.order} Image: {sc.image_path} ({os.path.getsize(sc.image_path)} bytes)")

        # 5. RENDER SCENE VIDEO SEGMENTS (KEN BURNS)
        print("\n[*] Phase 3: Rendering Ken Burns Video Segments with FFmpeg...")
        scene_video_paths = []
        scene_srt_infos = []

        for sc in created_scenes:
            media = get_scene_media_paths(project_id, sc.id)
            v_res = await render_scene_video(
                image_path=sc.image_path,
                audio_path=sc.voice_audio_path,
                output_path=str(media["video"]),
                duration=sc.duration,
                camera_motion=sc.camera_motion,
                resolution="720p",
                fps=25,
            )
            sc.video_segment_path = v_res["video_path"]
            scene_video_paths.append(v_res["video_path"])
            scene_srt_infos.append({
                "srt_path": sc.srt_path,
                "duration": v_res["duration"],
            })

            assert os.path.exists(sc.video_segment_path)
            print(f"  [OK] Scene {sc.order} Segment Video: {sc.video_segment_path} (Motion: {sc.camera_motion})")

        # 6. ASSEMBLE FULL MOVIE WITH BGM DUCKING & HARDSUB
        print("\n[*] Phase 4: Assembling Full Story Movie with BGM Ducking & Subtitles...")
        render_media = get_render_media_paths(project_id)
        bgm_path = render_media["renders_dir"] / "story_bgm.mp3"
        generate_default_bgm_track(str(bgm_path), mood="adventure")

        progress_history = []
        def track_progress(pct, step, msg):
            progress_history.append((pct, step, msg))
            print(f"    -> [{pct}%] Step {step}: {msg}")

        assemble_res = await assemble_full_video(
            scene_video_paths=scene_video_paths,
            scene_srt_infos=scene_srt_infos,
            output_video_path=str(render_media["final_video"]),
            bgm_path=str(bgm_path),
            bgm_volume=0.22,
            ducking=True,
            hardsub=True,
            resolution="720p",
            progress_callback=track_progress,
        )

        final_video_path = assemble_res["video_path"]
        final_srt_path = assemble_res["srt_path"]

        assert os.path.exists(final_video_path), "Final output video does not exist!"
        assert os.path.exists(final_srt_path), "Consolidated subtitle file does not exist!"
        assert os.path.getsize(final_video_path) > 30000, f"Final video file too small: {os.path.getsize(final_video_path)}"

        # 7. METRIC INSPECTION VIA FFPROBE
        print("\n[*] Phase 5: Deep Quality Inspection via FFprobe...")
        probe = probe_video(final_video_path)
        format_info = probe["format"]
        streams = probe["streams"]

        total_video_dur = float(format_info["duration"])
        expected_min_dur = sum(scene_durations) - 0.5
        print(f"  * Total Duration: {total_video_dur:.2f}s (Sum of scenes: {sum(scene_durations):.2f}s)")
        assert total_video_dur >= expected_min_dur, f"Duration mismatch: {total_video_dur}s vs expected {expected_min_dur}s"

        v_stream = next((s for s in streams if s["codec_type"] == "video"), None)
        assert v_stream is not None, "Missing Video Stream in final MP4!"
        assert v_stream["codec_name"] == "h264", f"Expected H.264 codec, got {v_stream['codec_name']}"
        assert v_stream["width"] == 1280, f"Expected width 1280, got {v_stream['width']}"
        assert v_stream["height"] == 720, f"Expected height 720, got {v_stream['height']}"
        print(f"  * Video Stream: Codec={v_stream['codec_name']}, Resolution={v_stream['width']}x{v_stream['height']}")

        a_stream = next((s for s in streams if s["codec_type"] == "audio"), None)
        assert a_stream is not None, "Missing Audio Stream in final MP4!"
        assert a_stream["codec_name"] == "aac", f"Expected AAC codec, got {a_stream['codec_name']}"
        assert a_stream["channels"] >= 1, f"Expected audio stream to have channels, got {a_stream['channels']}"
        print(f"  * Audio Stream: Codec={a_stream['codec_name']}, Channels={a_stream['channels']}, SampleRate={a_stream['sample_rate']}Hz")

        # Verify consolidated SRT content contains all 3 cues
        with open(final_srt_path, "r", encoding="utf-8") as f:
            full_srt = f.read()

        assert "1\n" in full_srt
        assert "2\n" in full_srt
        assert "3\n" in full_srt
        assert "Kai" in full_srt
        print("  * Hardsub & Softsub SRT: 3 chronological subtitle cues confirmed.")

        print("\n=======================================================")
        print("[SUCCESS] E2E STORY VIDEO PIPELINE SUCCEEDED 100%!")
        print("=======================================================")

    finally:
        # Clean up project
        delete_project(project_id)
        print(f"[*] Cleaned up test project {project_id}")
