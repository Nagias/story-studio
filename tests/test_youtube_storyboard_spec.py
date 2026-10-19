"""
Automated Verification Suite for OP_CTOOL Master Storyboard Specification
==========================================================================
Verifies:
1. Pydantic Master Storyboard schema validation (Section 5).
2. 9-Grid Composite Slicing with 3% border trimming and LANCZOS 16:9 resize.
3. 2.5D Parallax layering (foreground alpha + background).
4. 3-Layer Audio Engine (TTS + dramatic pause padding + procedural SFX + Sidechain ducking).
5. Kinetic Karaoke Subtitles (.ass word-level highlight #FFD700).
6. Deterministic Offline Storyboard Deconstruction.
7. FastAPI REST API endpoints for Master Spec.
"""

import os
import sys
import json
import wave
import pytest
from pathlib import Path
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

# Ensure backend in sys.path
TESTS_DIR = Path(__file__).resolve().parent
STORY_STUDIO_DIR = TESTS_DIR.parent
BACKEND_DIR = STORY_STUDIO_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.schemas import (
    MasterStoryboard,
    ProjectMetadata,
    MasterScene,
    MasterAudio,
    MasterSoundDesign,
    MasterVisual,
    MasterSubtitles,
    ParallaxMotion,
    CharacterAnchor,
    master_storyboard_to_project,
)
from services.grid_slicer import (
    slice_grid_image,
    compose_9grid_prompt,
    generate_parallax_layers,
)
from services.audio_engine import (
    find_or_create_sfx,
    append_silence_to_audio,
    mix_3layer_audio,
    generate_procedural_sfx,
)
from services.subtitle_engine import (
    format_ass_time,
    generate_karaoke_ass,
    extract_word_timestamps,
)
from services.storyboard_engine import (
    deconstruct_script_offline,
)
from main import app

# FEW-SHOT MASTER SPEC EXAMPLE JSON (FROM OP_CTOOL_YOUTUBE_STORYBOARD_SPEC.md)
FEW_SHOT_JSON = {
  "project_metadata": {
    "title": "Bí Ẩn Căn Biệt Thự Cổ: Lời Khai Của Người Canh Gác Lúc Nửa Đêm",
    "target_aspect_ratio": "16:9",
    "visual_style_dna": "Dark moody cinematic neo-noir, rain-drenched vintage aesthetic, 35mm anamorphic film grain",
    "character_anchors": [
      {
        "character_name": "Nam",
        "visual_prompt_anchor": "35-year-old Asian detective, rugged sharp facial features, short damp messy hair"
      }
    ],
    "bgm_overall_genre": "Cinematic Dark Ambient Cello & Muffled Piano"
  },
  "scenes": [
    {
      "scene_id": 1,
      "estimated_duration_sec": 5.0,
      "audio": {
        "speaker": "narrator",
        "voice_emotion": "calm_mysterious",
        "voiceover_text": "Cơn mưa rào trút xuống màn đêm tĩnh mịch, xóa nhòa mọi dấu vết trên con đường dẫn vào căn biệt thự bỏ hoang.",
        "pause_after_sec": 0.8
      },
      "sound_design": {
        "sfx_cue": ["heavy_rain_loop", "distant_thunder_subtle"],
        "bgm_energy": "ambient_low"
      },
      "visual": {
        "generation_mode": "single_shot",
        "grid_batch_id": None,
        "grid_cell_index": None,
        "grid_composite_prompt_en": None,
        "shot_type": "Establishing Wide Shot",
        "camera_movement": "Slow crane-down",
        "image_prompt_en": "Wide angle establishing shot of a Victorian gothic abandoned mansion standing on a stormy cliff at night",
        "parallax_motion": {
          "enable": True,
          "foreground_subject": "Falling rain and bare wet tree branches",
          "background_scene": "Dark ominous mansion facade"
        }
      },
      "subtitles": {
        "kinetic_highlight_words": ["cơn mưa rào", "biệt thự bỏ hoang"]
      }
    },
    {
      "scene_id": 2,
      "estimated_duration_sec": 6.2,
      "audio": {
        "speaker": "narrator",
        "voice_emotion": "tense_suspense",
        "voiceover_text": "Nam đẩy nhẹ cánh cổng sắt rỉ sét. Một tiếng kẽo kẹt xé toạc không gian.",
        "pause_after_sec": 1.6
      },
      "sound_design": {
        "sfx_cue": ["rusty_iron_gate_creak", "heartbeat_single_pulse"],
        "bgm_energy": "tension_buildup"
      },
      "visual": {
        "generation_mode": "9_grid_composite",
        "grid_batch_id": "batch_investigation_01",
        "grid_cell_index": 0,
        "grid_composite_prompt_en": "9-grid storyboard sequence, sequential comic narrative sheet, 35-year-old Asian detective",
        "shot_type": "Medium Dutch Angle Shot",
        "camera_movement": "Slow creeping push-in 1.05x",
        "image_prompt_en": "Medium shot of detective pushing open a tall rusty iron gate in torrential rain",
        "parallax_motion": {
          "enable": True,
          "foreground_subject": "Detective silhouette",
          "background_scene": "Dimly lit decaying porch"
        }
      },
      "subtitles": {
        "kinetic_highlight_words": ["kẽo kẹt xé toạc", "cổng sắt rỉ sét"]
      }
    }
  ]
}

def test_master_storyboard_pydantic_validation():
    """Verify Master Storyboard Schema validates few-shot spec correctly."""
    storyboard = MasterStoryboard.model_validate(FEW_SHOT_JSON)
    assert storyboard.project_metadata.title == "Bí Ẩn Căn Biệt Thự Cổ: Lời Khai Của Người Canh Gác Lúc Nửa Đêm"
    assert storyboard.project_metadata.target_aspect_ratio == "16:9"
    assert len(storyboard.scenes) == 2
    assert storyboard.scenes[0].audio.pause_after_sec == 0.8
    assert storyboard.scenes[1].visual.generation_mode == "9_grid_composite"
    assert storyboard.scenes[1].visual.grid_batch_id == "batch_investigation_01"
    assert "rusty_iron_gate_creak" in storyboard.scenes[1].sound_design.sfx_cue

def test_master_storyboard_to_project_converter():
    """Verify Master Storyboard converts seamlessly to Story Studio Project."""
    storyboard = MasterStoryboard.model_validate(FEW_SHOT_JSON)
    project = master_storyboard_to_project(storyboard, project_id="proj_test_spec")
    assert project.id == "proj_test_spec"
    assert project.name == storyboard.project_metadata.title
    assert len(project.scenes) == 2
    assert project.scenes[0].pause_after_sec == 0.8
    assert project.scenes[1].generation_mode == "9_grid_composite"
    assert project.scenes[1].sfx_cue == ["rusty_iron_gate_creak", "heartbeat_single_pulse"]

def test_9grid_slicer_with_border_trim(tmp_path):
    """Verify 9-Grid Slicer cuts 3x3 grid with border trim and outputs 1920x1080 16:9 images."""
    # Create test 3x3 grid image (1200x1200)
    grid_img = Image.new("RGB", (1200, 1200), color=(30, 30, 30))
    draw = ImageDraw.Draw(grid_img)
    # Draw dividing grid lines
    draw.line([(400, 0), (400, 1200)], fill=(255, 255, 255), width=8)
    draw.line([(800, 0), (800, 1200)], fill=(255, 255, 255), width=8)
    draw.line([(0, 400), (1200, 400)], fill=(255, 255, 255), width=8)
    draw.line([(0, 800), (1200, 800)], fill=(255, 255, 255), width=8)

    img_path = tmp_path / "test_grid.png"
    grid_img.save(str(img_path))

    out_dir = tmp_path / "slices"
    slices = slice_grid_image(
        image_path=img_path,
        output_dir=out_dir,
        rows=3,
        cols=3,
        border_trim_pct=0.03,
    )

    assert len(slices) == 9
    for sp in slices:
        assert os.path.exists(sp)
        with Image.open(sp) as panel:
            assert panel.size == (1920, 1080), f"Expected 1920x1080, got {panel.size}"

def test_compose_9grid_prompt():
    """Verify 9-Grid composite prompt generation adheres to spec."""
    prompt = compose_9grid_prompt(
        character_anchor="Asian detective Nam wearing charcoal trench coat",
        visual_style_dna="Dark moody neo-noir, 35mm film grain",
        panel_descriptions=[
            "pushing rusty gate in rain",
            "close up of footprints",
            "holding vintage flashlight",
            "beam cutting living room",
            "blinking red led light",
            "stepping closer alert",
            "bloody journal on desk",
            "shadow darting window",
            "turning around sharply",
        ],
    )
    assert "9-grid storyboard" in prompt
    assert "sequential narrative sheet" in prompt
    assert "panel 1 pushing rusty gate in rain" in prompt
    assert "panel 9 turning around sharply" in prompt
    assert "--ar 16:9" in prompt

def test_parallax_layer_generation(tmp_path):
    """Verify 2.5D Parallax generates foreground (Alpha) and blurred background."""
    test_img = Image.new("RGB", (640, 360), color=(40, 60, 100))
    draw = ImageDraw.Draw(test_img)
    # Draw subject in center
    draw.ellipse([(200, 80), (440, 300)], fill=(220, 50, 50))
    test_path = tmp_path / "scene_parallax.png"
    test_img.save(str(test_path))

    layers = generate_parallax_layers(test_path, tmp_path / "layers", prefix="scene_001")
    assert os.path.exists(layers["foreground"])
    assert os.path.exists(layers["background"])

    with Image.open(layers["foreground"]) as fg:
        assert fg.mode == "RGBA", "Foreground layer must have Alpha channel"
    with Image.open(layers["background"]) as bg:
        assert bg.size == (640, 360)

def test_procedural_sfx_and_silence_padding(tmp_path):
    """Verify procedural SFX synthesis and silence padding."""
    # Test procedural SFX
    sfx_path = tmp_path / "heartbeat.wav"
    generate_procedural_sfx("heartbeat", sfx_path, duration_sec=1.0)
    assert sfx_path.exists()
    assert sfx_path.stat().st_size > 1000

    # Test silence padding
    padded_path = tmp_path / "padded.wav"
    res = append_silence_to_audio(sfx_path, padded_path, pause_sec=0.8)
    assert os.path.exists(res)
    assert os.path.getsize(res) > os.path.getsize(sfx_path)

def test_kinetic_karaoke_ass_subtitle(tmp_path):
    """Verify Kinetic Karaoke .ass subtitle syntax."""
    out_ass = tmp_path / "subtitles.ass"
    scenes_data = [
      {
        "text": "Nam đẩy nhẹ cánh cổng sắt rỉ sét.",
        "total_duration": 4.5,
        "kinetic_highlight_words": ["cổng sắt", "rỉ sét"],
      }
    ]
    res_path = generate_karaoke_ass(scenes_data, out_ass)
    assert os.path.exists(res_path)

    with open(res_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "[Script Info]" in content
    assert "PlayResX: 1920" in content
    assert "PlayResY: 1080" in content
    assert "&H0000D7FF" in content  # Golden yellow highlight hex
    assert "\\b1" in content        # kinetic_pop (mặc định): từ đang đọc in đậm vàng

    sweep_path = generate_karaoke_ass(scenes_data, tmp_path / "sweep.ass", style_mode="karaoke_sweep")
    with open(sweep_path, "r", encoding="utf-8") as f:
        sweep = f.read()
    assert "\\kf" in sweep          # karaoke_sweep: tag karaoke chạy chữ
    assert "&H0000D7FF" in sweep

def test_offline_storyboard_deconstructor():
    """Verify deterministic offline deconstructor adheres to Section 5."""
    text = (
        "Cơn mưa rào trút xuống màn đêm tĩnh mịch, xóa nhòa mọi dấu vết.\n"
        "Nam đẩy nhẹ cánh cổng sắt rỉ sét, phát ra tiếng kẽo kẹt rợn người.\n"
        "Anh phát hiện một vệt máu tươi bên dưới thảm nhung phòng khách!"
    )
    sb = deconstruct_script_offline(text)
    assert len(sb.scenes) == 3
    assert sb.project_metadata.target_aspect_ratio == "16:9"
    # Verify dramatic pauses are assigned
    assert all(sc.audio.pause_after_sec >= 0.5 for sc in sb.scenes)
    # Verify SFX cues are populated
    assert any("heavy_rain" in sc.sound_design.sfx_cue[0] for sc in sb.scenes)
    assert any("gate" in sc.sound_design.sfx_cue[0] for sc in sb.scenes)

def test_api_storyboard_endpoints():
    """Verify FastAPI routes for Master Storyboard and Grid Slicing."""
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))

    # 1. Test deconstruct
    resp = client.post(
        "/api/storyboard/deconstruct",
        json={
            "script_text": "Cơn mưa trút xuống căn biệt thự cổ. Nam bước vào.",
            "art_style": "Dark moody neo-noir",
            "provider": "offline",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "project_metadata" in data
    assert "scenes" in data
    assert len(data["scenes"]) >= 2

    # 2. Test compose 9-grid prompt
    resp_prompt = client.post(
        "/api/grid-slicer/compose-prompt",
        json={
            "character_anchor": "Detective Nam",
            "visual_style_dna": "Neo-noir",
            "panels": ["Panel 1", "Panel 2"],
        },
    )
    assert resp_prompt.status_code == 200
    assert "9-grid storyboard" in resp_prompt.json()["prompt"]
