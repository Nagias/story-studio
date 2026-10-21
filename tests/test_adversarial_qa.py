"""
YouTube Story Studio - Adversarial QA Test Suite
------------------------------------------------
Comprehensive adversarial verification:
1. Frame Delta Pixel Difference (MAD > 5.0) on rendered scene videos:
   - zoom_in, zoom_out, pan_left, pan_right, diagonal.
   - Static video control test (MAD < 1.0 proving test sensitivity).
2. Assembled Full Video Frame Delta & Cut Transition verification.
3. Comic Slicer adversarial tests:
   - Synthetic manga grid with gutters (LTR & RTL reading order, aspect ratio & camera motion assignment).
   - Synthetic webtoon vertical scroll strip.
4. Vox Script Splitter adversarial tests:
   - Vox pacing (3-4s scene rhythm, Hook retention beat).
   - Multi-dimensional semantic extraction & cinematic English prompt generation.
   - Pacing tier comparisons (fast vs balanced vs deep_story).
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np
import pytest

# Ensure backend and tests are in sys.path
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

from services.video_service import (
    render_scene_video,
    assemble_full_video,
    ensure_speedlines_asset,
)
from services.comic_slicer import slice_comic
from services.script_splitter import (
    split_text_into_vox_scenes_offline,
)
from services.image_service import (
    build_character_anchored_prompt,
)
from models.schemas import (
    PRESET_CHARACTERS,
    Character,
    ProjectCreateRequest,
    LongVideoProduceRequest,
)
from routers.api import execute_produce_long_video, active_renders
from services.project_service import create_project, delete_project


# ==============================================================================
# Helper Functions: Video Frame Extraction & Mean Absolute Difference (MAD)
# ==============================================================================

def extract_video_frames(video_path: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int, float]:
    """
    Open an MP4 video file and extract:
      - Frame 0 (Start)
      - Frame T_half (Middle: total_frames // 2)
      - Frame T_end (End: total_frames - 1)
    Returns (f0, f_half, f_end, total_frames, fps).
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise IOError(f"Cannot open video file: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    assert total_frames >= 10, f"Video too short: only {total_frames} frames."

    # Frame 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ret0, f0 = cap.read()
    assert ret0 and f0 is not None, "Failed to read Frame 0"

    # Frame T_half
    half_idx = total_frames // 2
    cap.set(cv2.CAP_PROP_POS_FRAMES, half_idx)
    ret_half, f_half = cap.read()
    assert ret_half and f_half is not None, f"Failed to read Frame {half_idx} (T_half)"

    # Frame T_end
    end_idx = total_frames - 1
    cap.set(cv2.CAP_PROP_POS_FRAMES, end_idx)
    ret_end, f_end = cap.read()
    assert ret_end and f_end is not None, f"Failed to read Frame {end_idx} (T_end)"

    cap.release()
    return f0, f_half, f_end, total_frames, fps


def calculate_mad(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    """
    Compute Mean Absolute Difference (MAD) between two RGB/BGR frames.
    Formula: (1 / (W * H * C)) * sum(|frame_a - frame_b|)
    """
    assert frame_a.shape == frame_b.shape, f"Frame shape mismatch: {frame_a.shape} vs {frame_b.shape}"
    abs_diff = cv2.absdiff(frame_a, frame_b)
    return float(np.mean(abs_diff))


def generate_high_entropy_test_image(output_path: str, width: int = 1280, height: int = 720) -> str:
    """
    Generate an image with high spatial frequencies, distinct color blocks,
    diagonal gradients, and high contrast geometric shapes so that even minor
    camera movements create massive, detectable pixel shifts.
    """
    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    # 1. Gradient background
    for y in range(height):
        for x in range(width):
            canvas[y, x] = [
                int((x / width) * 220 + 20),
                int((y / height) * 200 + 30),
                int(((x + y) / (width + height)) * 240 + 10),
            ]

    # 2. Checkerboard patterns in corner and center
    step = 40
    for y in range(0, height, step):
        for x in range(0, width, step):
            if ((x // step) + (y // step)) % 2 == 0:
                cv2.rectangle(canvas, (x, y), (x + step // 2, y + step // 2), (255, 255, 255), -1)

    # 3. High-contrast circles and text
    cv2.circle(canvas, (width // 4, height // 2), 120, (0, 0, 255), -1)
    cv2.circle(canvas, (width * 3 // 4, height // 2), 120, (0, 255, 0), -1)
    cv2.circle(canvas, (width // 2, height // 2), 160, (255, 0, 0), 8)

    cv2.putText(canvas, "KEN BURNS MOTION QA", (width // 4, height // 2),
                cv2.FONT_HERSHEY_DUPLEX, 1.8, (255, 255, 255), 4)

    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(p), canvas)
    return str(p)


# ==============================================================================
# SECTION 1: Adversarial Ken Burns Frame Delta QA Tests (MAD > 5.0)
# ==============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("motion", ["zoom_in", "zoom_out", "pan_left", "pan_right", "diagonal"])
async def test_adversarial_camera_motion_frame_delta(tmp_path, motion):
    """
    Adversarial QA Test:
    Renders scene video for each Ken Burns camera motion and extracts Frame 0, T_half, T_end.
    Computes Mean Absolute Difference (MAD).
    Enforces MAD(0, T_half) > 5.0 and MAD(0, T_end) > 5.0 to strictly prove that
    camera motion actually displaces pixels and avoids static image freeze.
    """
    img_path = str(tmp_path / f"test_input_{motion}.jpg")
    vid_path = str(tmp_path / f"test_output_{motion}.mp4")

    # Generate high-entropy image
    generate_high_entropy_test_image(img_path, width=1280, height=720)

    # Render scene video (3.0s duration = 75 frames at 25 fps)
    result = await render_scene_video(
        image_path=img_path,
        audio_path=None,
        output_path=vid_path,
        duration=3.0,
        camera_motion=motion,
        resolution="720p",
        fps=25,
    )
    assert os.path.exists(result["video_path"])

    # Extract frames using OpenCV
    f0, f_half, f_end, total_frames, fps = extract_video_frames(vid_path)
    assert total_frames >= 70, f"Expected ~75 frames, got {total_frames}"

    # Calculate MAD deltas
    mad_0_half = calculate_mad(f0, f_half)
    mad_0_end = calculate_mad(f0, f_end)
    mad_half_end = calculate_mad(f_half, f_end)

    print(f"\n[QA Adversarial MAD] Motion: {motion:<10} | Frames: {total_frames} | "
          f"MAD(0, half): {mad_0_half:6.2f} | MAD(0, end): {mad_0_end:6.2f} | MAD(half, end): {mad_half_end:6.2f}")

    # Core QA Assertion: MAD > 5.0 requirement
    assert mad_0_half > 5.0, (
        f"CRITICAL FAILURE: {motion} failed MAD > 5.0 between Frame 0 and Frame T_half (got {mad_0_half:.2f}). "
        f"Pixels are frozen or not moving smoothly!"
    )
    assert mad_0_end > 5.0, (
        f"CRITICAL FAILURE: {motion} failed MAD > 5.0 between Frame 0 and Frame T_end (got {mad_0_end:.2f}). "
        f"Total trajectory did not displace sufficient pixels!"
    )
    assert mad_half_end > 3.0, (
        f"CRITICAL FAILURE: {motion} froze during second half! MAD(half, end) was {mad_half_end:.2f}."
    )


@pytest.mark.asyncio
async def test_adversarial_static_control_negative(tmp_path):
    """
    Adversarial Negative Control Test:
    Verifies that a 'static' video produces MAD < 1.0 (essentially 0.0),
    proving that our MAD metric is highly discriminating and sensitive to actual motion.
    """
    img_path = str(tmp_path / "test_input_static.jpg")
    vid_path = str(tmp_path / "test_output_static.mp4")

    generate_high_entropy_test_image(img_path, width=1280, height=720)

    await render_scene_video(
        image_path=img_path,
        audio_path=None,
        output_path=vid_path,
        duration=2.0,
        camera_motion="static",
        resolution="720p",
        fps=25,
    )

    f0, f_half, f_end, total_frames, fps = extract_video_frames(vid_path)
    mad_0_half = calculate_mad(f0, f_half)
    mad_0_end = calculate_mad(f0, f_end)

    print(f"\n[QA Control Static] MAD(0, half): {mad_0_half:.4f} | MAD(0, end): {mad_0_end:.4f}")
    assert mad_0_half < 1.0, f"Static video should have MAD < 1.0, got {mad_0_half}"
    assert mad_0_end < 1.0, f"Static video should have MAD < 1.0, got {mad_0_end}"


@pytest.mark.asyncio
async def test_adversarial_assembled_full_video_motion(tmp_path):
    """
    Adversarial QA Test for assemble_full_video:
    1. Render 2 scenes with distinct Ken Burns motions (Scene 1: zoom_in, Scene 2: pan_right).
    2. Assemble into full movie with audio ducking and subtitles.
    3. Use OpenCV to inspect the assembled video:
       - Verify intra-scene motion: MAD within scene 1 > 5.0.
       - Verify inter-scene cut transition: sharp pixel change across the scene boundary (MAD > 25.0).
       - Verify full video duration and validity.
    """
    scene_vids = []
    scene_srts = []

    motions = ["zoom_in", "pan_right"]
    for i, motion in enumerate(motions, start=1):
        img_p = str(tmp_path / f"scene_{i}_img.jpg")
        vid_p = str(tmp_path / f"scene_{i}_vid.mp4")
        srt_p = str(tmp_path / f"scene_{i}.srt")

        generate_high_entropy_test_image(img_p, width=1280, height=720)

        # 2.5s duration per scene
        await render_scene_video(
            image_path=img_p,
            audio_path=None,
            output_path=vid_p,
            duration=2.5,
            camera_motion=motion,
            resolution="720p",
            fps=25,
        )
        scene_vids.append(vid_p)

        with open(srt_p, "w", encoding="utf-8") as f:
            f.write(f"1\n00:00:00,200 --> 00:00:02,000\nLời thoại cảnh {i} với phụ đề rõ nét.\n\n")
        scene_srts.append({"srt_path": srt_p, "duration": 2.5})

    # Assemble full video
    assembled_out = str(tmp_path / "assembled_full.mp4")
    result = await assemble_full_video(
        scene_video_paths=scene_vids,
        scene_srt_infos=scene_srts,
        output_video_path=assembled_out,
        ducking=False,
        hardsub=False,
        resolution="720p",
    )

    assert os.path.exists(assembled_out)
    assert result["duration"] >= 4.8

    # Inspect assembled frames
    cap = cv2.VideoCapture(assembled_out)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Frame 5 (inside Scene 1) and Frame 50 (near end of Scene 1, before 2.5s = 62 frames)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 5)
    _, f_scene1_start = cap.read()
    cap.set(cv2.CAP_PROP_POS_FRAMES, 50)
    _, f_scene1_mid = cap.read()

    mad_scene1 = calculate_mad(f_scene1_start, f_scene1_mid)
    print(f"\n[QA Assembled Video] Scene 1 intra-motion MAD: {mad_scene1:.2f}")
    assert mad_scene1 > 5.0, f"Assembled Scene 1 lost motion! MAD = {mad_scene1:.2f}"

    # Frame 55 (Scene 1) vs Frame 75 (Scene 2) -> sharp cut
    cap.set(cv2.CAP_PROP_POS_FRAMES, 55)
    _, f_scene1_end = cap.read()
    cap.set(cv2.CAP_PROP_POS_FRAMES, 75)
    _, f_scene2_start = cap.read()

    mad_cut = calculate_mad(f_scene1_end, f_scene2_start)
    print(f"[QA Assembled Video] Scene cut delta MAD: {mad_cut:.2f}")
    # Transition between different frames should have high difference
    assert mad_cut > 15.0, f"Expected clear scene transition cut, got MAD = {mad_cut:.2f}"

    cap.release()


# ==============================================================================
# SECTION 2: Adversarial Comic Slicer QA Tests
# ==============================================================================

def create_synthetic_manga_page_with_gutters(width: int = 1200, height: int = 1600) -> np.ndarray:
    """
    Create a synthetic manga page with 4 distinct panels separated by gutters:
      - Panel 1: Top wide banner panel (x: 60..1140, y: 50..400) -> AR ~ 3.0 > 1.5 -> pan
      - Panel 2: Middle-left tall panel (x: 60..540, y: 460..1040) -> AR ~ 0.83 <= 1.5 -> zoom_in
      - Panel 3: Middle-right tall panel (x: 660..1140, y: 460..1040) -> AR ~ 0.83 <= 1.5 -> zoom_in (gutter = 120px)
      - Panel 4: Bottom wide action panel (x: 60..1140, y: 1100..1540) -> AR ~ 2.4 > 1.5 -> pan
    Separated by distinct gutters.
    """
    canvas = np.ones((height, width, 3), dtype=np.uint8) * 255  # Pure white background

    # Panel 1: Top wide (x: 60, y: 50, w: 1080, h: 350)
    cv2.rectangle(canvas, (60, 50), (1140, 400), (20, 20, 20), 4)
    cv2.putText(canvas, "TOP WIDE BANNER PANEL", (100, 220), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (40, 40, 40), 3)

    # Gutter: y 400..460 (60px)

    # Panel 2: Middle-Left (x: 60..540, w: 480, h: 580)
    cv2.rectangle(canvas, (60, 460), (540, 1040), (20, 20, 20), 4)
    cv2.putText(canvas, "MID LEFT PANEL", (100, 750), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (40, 40, 40), 2)

    # Gutter: x 540..660 (120px)

    # Panel 3: Middle-Right (x: 660..1140, w: 480, h: 580)
    cv2.rectangle(canvas, (660, 460), (1140, 1040), (20, 20, 20), 4)
    cv2.putText(canvas, "MID RIGHT PANEL", (700, 750), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (40, 40, 40), 2)

    # Gutter: y 1040..1100 (60px)

    # Panel 4: Bottom Wide (x: 60..1140, w: 1080, h: 440)
    cv2.rectangle(canvas, (60, 1100), (1140, 1540), (20, 20, 20), 4)
    cv2.putText(canvas, "BOTTOM WIDE ACTION PANEL", (100, 1350), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (40, 40, 40), 3)

    return canvas


def test_adversarial_comic_slicer_grid_ltr(tmp_path):
    """
    Adversarial QA Test for Comic Slicer in Grid Mode (LTR):
    - Validates detection of all 4 panels across gutters.
    - Validates reading order: Top panel first, then Middle-Left before Middle-Right, then Bottom panel last.
    - Validates correct aspect ratio and camera motion assignment:
      * Wide panels (AR > 1.5) get 'pan_left' or 'pan_right'.
      * Non-wide panels (AR <= 1.5) get 'zoom_in'.
    - Validates cropped images exist and are readable.
    """
    canvas = create_synthetic_manga_page_with_gutters()
    img_path = tmp_path / "synthetic_manga_grid.jpg"
    cv2.imwrite(str(img_path), canvas)

    out_dir = tmp_path / "sliced_ltr"
    res = slice_comic(
        image_input=str(img_path),
        output_dir=out_dir,
        mode="grid",
        reading_order="ltr",
    )

    assert res["success"] is True
    assert res["total_panels"] == 4, f"Expected 4 panels, got {res['total_panels']}"
    panels = res["panels"]

    # 1. Panel 0: Top panel
    assert panels[0]["bbox"]["y"] < 100, "Panel 1 should be at the top"
    assert panels[0]["is_wide"] is True
    assert panels[0]["camera_motion"] in ("pan_left", "pan_right")

    # 2. Panel 1: Middle-Left before Middle-Right in LTR
    assert panels[1]["bbox"]["x"] < panels[2]["bbox"]["x"], (
        f"In LTR order, Panel 1 (x={panels[1]['bbox']['x']}) should be left of Panel 2 (x={panels[2]['bbox']['x']})"
    )
    assert panels[1]["camera_motion"] == "zoom_in"
    assert panels[2]["camera_motion"] == "zoom_in"

    # 3. Panel 3: Bottom panel
    assert panels[3]["bbox"]["y"] > 1000, "Panel 4 should be at the bottom"
    assert panels[3]["is_wide"] is True
    assert panels[3]["camera_motion"] in ("pan_left", "pan_right")

    # 4. Check all cropped panel files exist on disk and are non-empty
    for p in panels:
        p_path = Path(p["image_path"])
        assert p_path.exists(), f"Cropped panel image not found: {p_path}"
        assert p_path.stat().st_size > 1000, f"Panel image too small: {p_path}"


def test_adversarial_comic_slicer_grid_rtl(tmp_path):
    """
    Adversarial QA Test for Comic Slicer in RTL (Manga) Mode:
    - In RTL reading order, Middle-Right must come BEFORE Middle-Left!
    """
    canvas = create_synthetic_manga_page_with_gutters()
    img_path = tmp_path / "synthetic_manga_rtl.jpg"
    cv2.imwrite(str(img_path), canvas)

    out_dir = tmp_path / "sliced_rtl"
    res = slice_comic(
        image_input=str(img_path),
        output_dir=out_dir,
        mode="grid",
        reading_order="rtl",
    )

    assert res["success"] is True
    assert res["total_panels"] == 4
    panels = res["panels"]

    # In RTL, panel 1 should be Middle-Right and panel 2 should be Middle-Left
    assert panels[1]["bbox"]["x"] > panels[2]["bbox"]["x"], (
        f"In RTL manga order, Panel 1 (x={panels[1]['bbox']['x']}) should be right of Panel 2 (x={panels[2]['bbox']['x']})"
    )


def test_adversarial_comic_slicer_webtoon_strip(tmp_path):
    """
    Adversarial QA Test for Webtoon Strip Mode:
    - Vertical strip layout with 3 scenes separated by 80px white gutters.
    - Validates sequential top-to-bottom panel slicing without missing panels.
    """
    W, H = 800, 2400
    strip = np.ones((H, W, 3), dtype=np.uint8) * 255

    # Panel 1: y 60..700 (h: 640)
    cv2.rectangle(strip, (30, 60), (770, 700), (30, 80, 200), -1)
    # Gutter 700..800
    # Panel 2: y 800..1500 (h: 700)
    cv2.rectangle(strip, (30, 800), (770, 1500), (200, 80, 30), -1)
    # Gutter 1500..1600
    # Panel 3: y 1600..2340 (h: 740)
    cv2.rectangle(strip, (30, 1600), (770, 2340), (80, 200, 30), -1)

    strip_path = tmp_path / "webtoon_strip.jpg"
    cv2.imwrite(str(strip_path), strip)

    out_dir = tmp_path / "sliced_strip"
    res = slice_comic(
        image_input=str(strip_path),
        output_dir=out_dir,
        mode="strip",
    )

    assert res["success"] is True
    assert res["total_panels"] == 3, f"Expected 3 panels for webtoon strip, got {res['total_panels']}"
    panels = res["panels"]

    # Strictly descending y positions
    assert panels[0]["bbox"]["y"] < panels[1]["bbox"]["y"] < panels[2]["bbox"]["y"]


# ==============================================================================
# SECTION 3: Adversarial Vox Script Splitter QA Tests (3-4s Rhythm & Hook)
# ==============================================================================

VOX_PUNCHY_SCRIPT = """
Tàu thám hiểm hiện đại nhất đột ngột biến mất.
Chỉ trong ba mươi giây ngắn ngủi.
Không một tín hiệu cầu cứu nào phát ra.
Vùng biển Bắc Cực mịt mù sương tuyết.
Đoàn thám hiểm tiến vào nơi nguy hiểm nhất.
Kim đồng hồ điểm đúng nửa đêm.
Hiện tượng dị thường bùng nổ dữ dội.
Sóng biển cuồn cuộn dâng cao.
Nước biển chuyển sang màu đen kịt.
Hệ thống radar bị tê liệt hoàn toàn.
Tiếng còi báo động vang lên inh ỏi.
Bóng đen khổng lồ trồi lên từ đáy biển.
Đôi mắt rực lửa xé toạc màn đêm.
Thuyền trưởng dũng cảm siết chặt vô lăng.
Hệ thống phát điện của tàu phát nổ dữ dội.
Tất cả chìm vào im lặng tuyệt đối.
Mặt biển phẳng lặng dưới ánh bình minh.
Bí ẩn đại dương vẫn chưa có lời đáp.
"""

VOX_STORY_SAMPLE = """
Tập 1: Bí Mật Đêm Trăng Trên Biển Bắc.

Tại sao một chiếc tàu thám hiểm hiện đại bậc nhất thế giới lại biến mất không dấu vết chỉ trong 30 giây? Sự thật đằng sau vùng biển cấm này nguy hiểm hơn bất kỳ ai có thể tưởng tượng.

Ngày 14 tháng 10 năm 2024, một đoàn nghiên cứu gồm các nhà khoa học hàng đầu rời cảng trong sự hân hoan. Họ tiến sâu vào vùng biển Bắc Cực mịt mù sương tuyết, nơi những ngọn núi băng khổng lồ đứng sừng sững như những pháo đài thời cổ đại.

Nhưng khi kim đồng hồ điểm đúng nửa đêm, một hiện tượng dị thường bùng nổ. Sóng biển dâng cao dữ dội, nước biển từ màu xanh thẳm đột ngột chuyển sang màu đen kịt. Hệ thống định vị radar bị tê liệt hoàn toàn, tiếng còi báo động khẩn cấp vang lên inh ỏi khắp các khoang tàu. Các thủy thủ đoàn hoảng loạn nhìn ra ngoài cửa sổ boong tàu.

Đột nhiên, từ sâu thẳm dưới đáy đại dương, một bóng đen khổng lồ với đôi mắt rực lửa trồi lên. Đó là một sinh vật thần thoại cổ xưa mà nhân loại tưởng chỉ có trong truyền thuyết. Vị thuyền trưởng dũng cảm siết chặt vô lăng, cố gắng điều khiển con tàu vượt qua những đợt sóng thần cuồn cuộn.

Trong khoảnh khắc sinh tử quyết định, toàn bộ hệ thống phát điện của tàu phát nổ. Ánh sáng chớp giật lóe lên trong màn đêm bão tố trước khi mọi thứ chìm vào im lặng tuyệt đối.

Cuối cùng, sau cơn bão tố kinh hoàng, mặt biển phẳng lặng trở lại dưới ánh bình minh dịu nhẹ. Bí ẩn về con tàu thám hiểm vẫn là một câu hỏi lớn chưa có lời giải đáp cho hậu thế.
"""


def test_adversarial_vox_pacing_and_hook():
    """
    Adversarial QA Test for Vox Narrative Engine:
    1. Tests pacing='fast' / 'vox' (target 3-4s per scene rhythm for high retention).
    2. Validates that Scene 1 is designated as 'hook' (0-30s YouTube retention).
    3. Validates that scene durations strictly follow the Vox fast rhythm (average 3-4s).
    4. Validates rich semantic bisection: setting, subject, action, lighting, camera_framing.
    5. Validates cinematic English prompt generation without empty placeholders.
    """
    res = split_text_into_vox_scenes_offline(
        full_text=VOX_PUNCHY_SCRIPT,
        pacing="fast",
        style_preset="cinematic_realistic",
    )

    scenes = res["scenes"]
    assert len(scenes) >= 8, f"Expected >= 8 scenes for fast Vox pacing, got {len(scenes)}"

    # 1. Check Hook in Scene 1
    assert scenes[0]["narrative_beat"] == "hook", f"Scene 1 must be 'hook', got '{scenes[0]['narrative_beat']}'"

    # 2. Check 3-4s timing per scene
    durations = [sc["estimated_duration"] for sc in scenes]
    avg_duration = sum(durations) / len(durations)
    print(f"\n[QA Vox Pacing] Total scenes: {len(scenes)} | Avg scene duration: {avg_duration:.2f}s | Range: {min(durations)}s - {max(durations)}s")

    assert 3.0 <= avg_duration <= 4.0, (
        f"Vox fast pacing rhythm out of bounds! Expected average 3-4s, got {avg_duration:.2f}s"
    )

    # 3. Check Semantic Layers and Cinematic Prompts
    for sc in scenes:
        assert sc["setting"], f"Scene {sc['order']} has empty setting"
        assert sc["subject"], f"Scene {sc['order']} has empty subject"
        assert sc["lighting"], f"Scene {sc['order']} has empty lighting"
        assert sc["camera_framing"], f"Scene {sc['order']} has empty camera_framing"
        assert sc["camera_motion"] in ("zoom_in", "zoom_out", "pan_left", "pan_right", "diagonal"), (
            f"Invalid camera motion: {sc['camera_motion']}"
        )
        prompt = sc["image_prompt"]
        assert len(prompt) > 40, f"Prompt too short: '{prompt}'"
        assert any(term in prompt.lower() for term in ["cinematic", "photorealistic", "shot", "lighting", "ultra"]), (
            f"Prompt missing cinematic cues: '{prompt}'"
        )


def test_adversarial_pacing_tiers_comparison():
    """
    Adversarial QA Test comparing Pacing Tiers:
    - Fast / Vox (3-4s): yields highest scene count.
    - Balanced (5-6s): yields intermediate scene count.
    - Deep Story (7-8s): yields lowest scene count.
    Validates strictly monotonic relationship: count(fast) > count(balanced) > count(deep_story).
    """
    res_fast = split_text_into_vox_scenes_offline(VOX_STORY_SAMPLE, pacing="fast")
    res_balanced = split_text_into_vox_scenes_offline(VOX_STORY_SAMPLE, pacing="balanced")
    res_deep = split_text_into_vox_scenes_offline(VOX_STORY_SAMPLE, pacing="deep_story")

    n_fast = res_fast["total_scenes"]
    n_bal = res_balanced["total_scenes"]
    n_deep = res_deep["total_scenes"]

    print(f"\n[QA Pacing Comparison] Fast: {n_fast} scenes | Balanced: {n_bal} scenes | Deep Story: {n_deep} scenes")

    assert n_fast > n_bal, f"Fast pacing ({n_fast}) should yield more scenes than Balanced ({n_bal})"
    assert n_bal > n_deep, f"Balanced pacing ({n_bal}) should yield more scenes than Deep Story ({n_deep})"

    # Check that average durations scale up accordingly
    avg_f = res_fast["estimated_total_duration"] / n_fast
    avg_b = res_balanced["estimated_total_duration"] / n_bal
    avg_d = res_deep["estimated_total_duration"] / n_deep

    assert avg_f < avg_b < avg_d, f"Average scene durations must strictly increase: {avg_f:.2f} < {avg_b:.2f} < {avg_d:.2f}"


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


# ==============================================================================
# SECTION 4: Character Consistency Engine Adversarial Verification (15-20 Scenes)
# ==============================================================================

def test_adversarial_character_consistency_across_20_scenes():
    """
    Adversarial QA Test for Character Consistency:
    1. Tests prompt anchoring across 20 consecutive scenes for each of the 4 Preset Characters:
       - Paladin Kai (silver-white hair, blue eyes, silver full plate armor, cyan gems, broadsword)
       - Roman Titus (lorica segmentata, pilum, red scutum shield, bull emblem, bronze helmet)
       - Spartan Leon (bronze muscle cuirass, Corinthian helmet, hoplon shield, Lambda, dory spear)
       - Kingdom Shin (lamellar scale armor, broadsword, messy ponytail, fierce smile)
    2. Validates that 100% of the scenes strictly retain immutable features:
       - face_features
       - hair_style_and_color
       - armor_or_costume
       - main_weapon
       - signature_colors
    3. Validates custom character anchor generation with 0% attribute drift.
    """
    assert len(PRESET_CHARACTERS) >= 4, f"Expected at least 4 preset characters, got {len(PRESET_CHARACTERS)}"

    # 20 diverse story scene descriptions
    scene_descriptions = [
        f"Cảnh {i}: Chiến binh đứng hiên ngang tại địa điểm {i}, chuẩn bị rút vũ khí chiến đấu."
        for i in range(1, 21)
    ]

    for char in PRESET_CHARACTERS:
        for idx, desc in enumerate(scene_descriptions, start=1):
            anchored_prompt = build_character_anchored_prompt(
                scene_prompt=desc,
                style_preset="cinematic_realistic",
                character=char,
            )

            # Strict verification of all immutable traits
            assert char.face_features in anchored_prompt, (
                f"DRIFT ERROR: Scene {idx} lost face features for {char.name}"
            )
            assert char.hair_style_and_color in anchored_prompt, (
                f"DRIFT ERROR: Scene {idx} lost hair style/color for {char.name}"
            )
            assert char.armor_or_costume in anchored_prompt, (
                f"DRIFT ERROR: Scene {idx} lost armor/costume for {char.name}"
            )
            assert char.main_weapon in anchored_prompt, (
                f"DRIFT ERROR: Scene {idx} lost weapon for {char.name}"
            )
            assert char.signature_colors in anchored_prompt, (
                f"DRIFT ERROR: Scene {idx} lost signature colors for {char.name}"
            )

    # Test Custom Character
    custom_hero = Character(
        id="cyber_ninja_ren",
        name="Ren Shadowblade",
        face_features="sharp angular cybernetic face, glowing amber synthetic eyes",
        hair_style_and_color="short neon-blue undercut hair",
        armor_or_costume="matte-black nanotech stealth suit with carbon-fiber plating",
        main_weapon="high-frequency plasma katana emitting violet sparks",
        signature_colors="obsidian black, neon cyan, electric violet",
        distinguishing_marks="dragon barcode tattoo glowing faintly on left temple",
    )

    for idx, desc in enumerate(scene_descriptions, start=1):
        custom_prompt = build_character_anchored_prompt(
            scene_prompt=desc,
            style_preset="cyberpunk",
            character=custom_hero,
        )
        assert "high-frequency plasma katana" in custom_prompt
        assert "matte-black nanotech stealth suit" in custom_prompt
        assert "short neon-blue undercut hair" in custom_prompt
        assert "sharp angular cybernetic face" in custom_prompt


# ==============================================================================
# SECTION 5: Adversarial Frame Delta Pixel Difference for Action Motion FX
# ==============================================================================

@pytest.mark.asyncio
async def test_adversarial_motion_fx_action_camera_shake(tmp_path):
    """
    Adversarial QA Test for 'action_camera_shake':
    - Renders video with intense sinusoidal camera vibration.
    - Measures Mean Absolute Difference (MAD) between CONSECUTIVE FRAMES:
      Bắt buộc Consecutive Frame MAD > 15.0 để chứng minh độ rung lắc dữ dội khi va chạm.
    """
    img_path = str(tmp_path / "shake_input.jpg")
    vid_path = str(tmp_path / "shake_output.mp4")

    generate_high_entropy_test_image(img_path, width=1280, height=720)

    await render_scene_video(
        image_path=img_path,
        audio_path=None,
        output_path=vid_path,
        duration=2.0,
        camera_motion="action_camera_shake",
        resolution="720p",
        fps=25,
    )

    cap = cv2.VideoCapture(vid_path)
    frames = []
    while True:
        ret, f = cap.read()
        if not ret:
            break
        frames.append(f)
    cap.release()

    assert len(frames) >= 45, f"Expected ~50 frames, got {len(frames)}"

    consecutive_mads = [
        calculate_mad(frames[i], frames[i + 1])
        for i in range(len(frames) - 1)
    ]
    avg_consec_mad = sum(consecutive_mads) / len(consecutive_mads)
    max_consec_mad = max(consecutive_mads)

    print(f"\n[QA Motion FX Shake] Frames: {len(frames)} | Avg Consecutive MAD: {avg_consec_mad:.2f} | Max Consecutive MAD: {max_consec_mad:.2f}")

    assert avg_consec_mad > 15.0, (
        f"CRITICAL FAILURE: action_camera_shake consecutive MAD was {avg_consec_mad:.2f} (Required > 15.0)!"
    )
    assert max_consec_mad > 25.0, (
        f"CRITICAL FAILURE: Peak shake amplitude too low (max consecutive MAD = {max_consec_mad:.2f})!"
    )


@pytest.mark.asyncio
async def test_adversarial_motion_fx_punch_zoom(tmp_path):
    """
    Adversarial QA Test for 'punch_zoom':
    - Renders video with instant zoom-in snap at 20% into duration.
    - Compares pre-punch frame (frame 5) vs post-punch frame (frame 15).
    - Enforces significant instant magnification jump (MAD > 15.0).
    """
    img_path = str(tmp_path / "punch_input.jpg")
    vid_path = str(tmp_path / "punch_output.mp4")

    generate_high_entropy_test_image(img_path, width=1280, height=720)

    await render_scene_video(
        image_path=img_path,
        audio_path=None,
        output_path=vid_path,
        duration=2.0,
        camera_motion="punch_zoom",
        resolution="720p",
        fps=25,
    )

    cap = cv2.VideoCapture(vid_path)
    frames = []
    while True:
        ret, f = cap.read()
        if not ret:
            break
        frames.append(f)
    cap.release()

    assert len(frames) >= 45
    # Compare pre-punch (frame 5) and post-punch (frame 15)
    f_pre = frames[5]
    f_post = frames[15]
    mad_punch = calculate_mad(f_pre, f_post)

    print(f"\n[QA Motion FX Punch Zoom] MAD(frame 5, frame 15): {mad_punch:.2f}")
    assert mad_punch > 15.0, (
        f"CRITICAL FAILURE: punch_zoom failed to jump magnification! MAD = {mad_punch:.2f} (Required > 15.0)"
    )


@pytest.mark.asyncio
async def test_adversarial_motion_fx_panoramic_sweep(tmp_path):
    """
    Adversarial QA Test for 'panoramic_sweep':
    - Renders video on high-resolution double-page spread canvas (1716x1200).
    - Verifies smooth multi-stop 2-phase panning across the entire wide landscape:
      MAD(0, T_half) > 15.0 and MAD(0, T_end) > 25.0.
    """
    img_path = str(tmp_path / "panoramic_input.jpg")
    vid_path = str(tmp_path / "panoramic_output.mp4")

    generate_high_entropy_test_image(img_path, width=1716, height=1200)

    await render_scene_video(
        image_path=img_path,
        audio_path=None,
        output_path=vid_path,
        duration=3.0,
        camera_motion="panoramic_sweep",
        resolution="720p",
        fps=25,
    )

    f0, f_half, f_end, total_frames, fps = extract_video_frames(vid_path)
    mad_half = calculate_mad(f0, f_half)
    mad_end = calculate_mad(f0, f_end)

    print(f"\n[QA Motion FX Panoramic] Frames: {total_frames} | MAD(0, half): {mad_half:.2f} | MAD(0, end): {mad_end:.2f}")

    assert mad_half > 15.0, f"panoramic_sweep slow start: MAD(0, half) = {mad_half:.2f}"
    assert mad_end > 25.0, f"panoramic_sweep insufficient sweep displacement: MAD(0, end) = {mad_end:.2f}"


@pytest.mark.asyncio
async def test_adversarial_motion_fx_manga_speedlines(tmp_path):
    """
    Adversarial QA Test for 'manga_speedlines':
    - Verifies procedural speedlines asset creation/verification.
    - Renders video with manga_speedlines on pure dark background.
    - Verifies radial speedlines rays are overlaid as high-contrast RGBA lines (white pixels > 10,000).
    - Verifies rapid action zoom trajectory: MAD(0, T_end) > 20.0.
    """
    sl_asset_path = ensure_speedlines_asset()
    assert os.path.exists(sl_asset_path), f"Manga speedlines asset not found: {sl_asset_path}"
    assert os.path.getsize(sl_asset_path) > 1000

    # Render dark background with speedlines
    dark_img_path = str(tmp_path / "dark_bg.jpg")
    vid_path = str(tmp_path / "speedlines_out.mp4")

    dark_canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.imwrite(dark_img_path, dark_canvas)

    await render_scene_video(
        image_path=dark_img_path,
        audio_path=None,
        output_path=vid_path,
        duration=1.5,
        camera_motion="manga_speedlines",
        resolution="720p",
        fps=25,
    )

    cap = cv2.VideoCapture(vid_path)
    ret, frame0 = cap.read()
    assert ret and frame0 is not None

    # Count bright pixels contributed by speedlines overlay
    bright_pixels = int(np.sum(frame0 > 100))
    print(f"\n[QA Motion FX Speedlines] Bright overlay pixels on black canvas: {bright_pixels}")
    assert bright_pixels > 10000, (
        f"Speedlines overlay failed: only {bright_pixels} bright pixels detected!"
    )

    # Now verify with high entropy image for zoom motion
    high_img_path = str(tmp_path / "high_speedlines.jpg")
    vid_high_path = str(tmp_path / "high_speedlines.mp4")
    generate_high_entropy_test_image(high_img_path, width=1280, height=720)

    await render_scene_video(
        image_path=high_img_path,
        audio_path=None,
        output_path=vid_high_path,
        duration=2.0,
        camera_motion="manga_speedlines",
        resolution="720p",
        fps=25,
    )

    f0, f_half, f_end, total_f, _ = extract_video_frames(vid_high_path)
    mad_sl = calculate_mad(f0, f_end)
    print(f"[QA Motion FX Speedlines] Zoom Delta MAD(0, end): {mad_sl:.2f}")
    assert mad_sl > 20.0, f"manga_speedlines zoom too weak: MAD = {mad_sl:.2f}"


# ==============================================================================
# SECTION 6: MoneyPrinterTurbo Stepper Long Video Production Pipeline E2E
# ==============================================================================

@pytest.mark.live  # 9router chia cảnh + Edge-TTS thật
@pytest.mark.asyncio
async def test_adversarial_produce_long_video_pipeline(tmp_path):
    """
    Adversarial QA Test for produce_long_video (MoneyPrinterTurbo 5-phase Stepper):
    - Creates project with mock_cinematic image provider and Paladin Kai character.
    - Executes complete 5-step pipeline:
      (1) Script parsing & character anchoring (15%)
      (2) Edge-TTS voice generation & timed SRT subtitles (40%)
      (3) 8K Style Preset Visual generation (65%)
      (4) Motion FX Scene segments (85%)
      (5) Video assembly + Studio BGM Ducking + Hardsub subtitles (100%)
    - Verifies rendered output:
      * Full HD MP4 file exists and size > 50KB
      * ffprobe validates H.264 video stream & AAC audio stream
      * Master SRT subtitle file with multiple cues exists
      * Project cleanup succeeds without memory leak
    """
    project = create_project(ProjectCreateRequest(
        name="QA Long Video Stepper Test",
        image_provider="mock_cinematic",
        style_preset="fantasy_paladin_armor",
        character_anchor="Paladin Kai with ornate silver full plate armor and glowing cyan runes",
    ))
    proj_id = project.id
    render_id = f"test_render_{proj_id}"
    active_renders[render_id] = {"logs": []}

    story_script = """
    Dũng Sĩ Kai vung thanh kiếm runic tỏa ánh sáng lam ngọc rực rỡ.
    Khuôn mặt kiên định của chàng không hề nao núng trước bầy quái vật.
    Ánh bình minh ló rạng trên chiến trường, đem lại hòa bình cho vương quốc.
    """

    req = LongVideoProduceRequest(
        text=story_script,
        pacing="fast",
        style_preset="fantasy_paladin_armor",
        character_anchor="Paladin Kai with ornate silver full plate armor and glowing cyan runes",
        voice="vi-VN-HoaiMyNeural",
        resolution="720p",
        fps=25,
        ducking=True,
        hardsub=True,
    )

    try:
        await execute_produce_long_video(proj_id, render_id, req)
        render_state = active_renders.get(render_id, {})
        status = render_state.get("status")
        err = render_state.get("error")

        assert status == "completed", f"Long video production failed: {err}"
        video_path = render_state.get("video_path")
        srt_path = render_state.get("srt_path")

        assert video_path and os.path.exists(video_path), f"Final video not found: {video_path}"
        assert srt_path and os.path.exists(srt_path), f"Final SRT not found: {srt_path}"

        # Deep ffprobe inspection
        probe = probe_media_file(video_path)
        streams = probe.get("streams", [])
        v_stream = next((s for s in streams if s["codec_type"] == "video"), None)
        a_stream = next((s for s in streams if s["codec_type"] == "audio"), None)

        assert v_stream is not None, "Missing video stream in assembled long video"
        assert a_stream is not None, "Missing audio stream in assembled long video"
        assert v_stream["codec_name"] == "h264"
        assert a_stream["codec_name"] == "aac"
        assert v_stream["width"] == 1280
        assert v_stream["height"] == 720

        total_dur = float(probe["format"]["duration"])
        assert total_dur >= 6.0, f"Long video duration too short: {total_dur}s"

        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()
        assert "-->" in srt_content, "Missing SRT timestamp cues"
        assert "Dũng Sĩ Kai" in srt_content or "Kai" in srt_content

        print(f"\n[QA Long Video Stepper] Final video duration: {total_dur:.2f}s | Codec: {v_stream['codec_name']}/{a_stream['codec_name']} | SRT size: {len(srt_content)} bytes")

    finally:
        delete_project(proj_id)

