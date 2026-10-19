import os
import sys
import pytest
from pathlib import Path
from PIL import Image

# Add backend directory to sys.path
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.image_service import (
    STYLE_PRESETS,
    get_available_styles,
    build_consistent_prompt,
    generate_mock_cinematic,
    generate_image,
)

def test_style_presets_catalog():
    """Verify image style presets catalog contains all required cinematic & artistic styles."""
    styles = get_available_styles()
    assert isinstance(styles, list)
    assert len(styles) >= 11, f"Expected at least 11 style presets, got {len(styles)}"

    style_ids = {s["id"] for s in styles}
    expected_ids = {
        "cinematic_realistic",
        "anime",
        "dark_fantasy",
        "cyberpunk",
        "comic_book",
        "3d_animation",
        "manga_battle_action",
        "manga_historical_war",
        "fantasy_paladin_armor",
        "roman_legionary_epic",
        "spartan_mythic_warrior",
    }
    assert expected_ids <= style_ids, f"Missing style presets: {expected_ids - style_ids}"

    for s in styles:
        assert "id" in s and len(s["id"]) > 0
        assert "name" in s and len(s["name"]) > 0
        assert "prompt_suffix" in s and len(s["prompt_suffix"]) > 0
        assert "negative_prompt" in s
        assert "description" in s and len(s["description"]) > 0

def test_build_consistent_prompt():
    """Test combining scene action, character anchor, and style suffix into a consistent prompt."""
    scene_action = "A young knight standing in front of a majestic castle"
    character_anchor = "A red-haired boy with silver armor and a glowing sword"

    # Test with character anchor and anime style
    full_prompt = build_consistent_prompt(
        scene_prompt=scene_action,
        style_preset="anime",
        character_anchor=character_anchor,
    )
    assert scene_action in full_prompt
    assert f"featuring character: {character_anchor}" in full_prompt
    assert "Makoto Shinkai studio ghibli aesthetic" in full_prompt

    # Test with empty character anchor
    prompt_no_char = build_consistent_prompt(
        scene_prompt=scene_action,
        style_preset="cyberpunk",
        character_anchor="",
    )
    assert scene_action in prompt_no_char
    assert "featuring character" not in prompt_no_char
    assert "cyberpunk aesthetic" in prompt_no_char

    # Test fallback on unknown style preset
    prompt_fallback = build_consistent_prompt(
        scene_prompt=scene_action,
        style_preset="non_existent_style",
    )
    from config import DEFAULT_STYLE
    assert STYLE_PRESETS[DEFAULT_STYLE]["prompt_suffix"] in prompt_fallback

def test_mock_cinematic_resolution_and_format(tmp_path):
    """Test offline mock generator produces exact 1280x720 16:9 JPEG canvas."""
    out_file = tmp_path / "mock_frame.jpg"
    prompt = "A mysterious glowing tree inside a foggy forest"

    generated_path = generate_mock_cinematic(
        prompt=prompt,
        style_preset="cinematic_realistic",
        output_path=str(out_file),
        scene_index=1,
    )

    assert os.path.exists(generated_path)
    assert os.path.getsize(generated_path) > 10000, "Image file too small"

    # Verify Pillow Image metadata
    with Image.open(generated_path) as img:
        assert img.size == (1280, 720), f"Invalid resolution: {img.size}, expected (1280, 720)"
        assert img.format == "JPEG", f"Invalid format: {img.format}, expected JPEG"
        # Aspect ratio 16:9
        aspect_ratio = img.size[0] / img.size[1]
        assert abs(aspect_ratio - (16 / 9)) < 0.01, f"Aspect ratio not 16:9: {aspect_ratio}"

def test_mock_cinematic_all_style_presets(tmp_path):
    """Verify mock generator successfully generates distinct frames for every style preset."""
    for style_id in STYLE_PRESETS.keys():
        out_file = tmp_path / f"mock_{style_id}.jpg"
        generated_path = generate_mock_cinematic(
            prompt=f"Scenic landscape in {style_id} aesthetic",
            style_preset=style_id,
            output_path=str(out_file),
            scene_index=2,
        )
        assert os.path.exists(generated_path)
        with Image.open(generated_path) as img:
            assert img.size == (1280, 720)

@pytest.mark.asyncio
async def test_generate_image_mock_provider(tmp_path):
    """Test generate_image service wrapper with mock_cinematic provider."""
    out_file = tmp_path / "service_mock.jpg"
    prompt = "Hero arriving at ancient temple ruins"

    res = await generate_image(
        prompt=prompt,
        style_preset="dark_fantasy",
        character_anchor="Brave traveler in leather cloak",
        provider="mock_cinematic",
        output_path=str(out_file),
        scene_index=3,
    )

    assert res["success"] is True
    assert res["provider"] == "mock_cinematic"
    assert os.path.exists(res["image_path"])
    assert "featuring character: Brave traveler in leather cloak" in res["full_prompt"]
    assert "dark fantasy concept art" in res["full_prompt"]

@pytest.mark.asyncio
async def test_generate_image_unsupported_provider_reports_error(tmp_path):
    """Provider không nhận ra phải báo lỗi, không được rơi về ảnh giả (mock_cinematic)."""
    out_file = tmp_path / "fallback_frame.jpg"
    res = await generate_image(
        prompt="A serene waterfall under starlight",
        style_preset="3d_animation",
        provider="unsupported_provider",
        output_path=str(out_file),
    )

    assert res["success"] is False
    assert res["provider"] is None
    assert res["image_path"] is None
    assert "unsupported_provider" in res["error"]
    assert not out_file.exists()

@pytest.mark.asyncio
async def test_generate_image_missing_output_path():
    """Verify ValueError is raised when output_path is not specified."""
    with pytest.raises(ValueError):
        await generate_image(prompt="Sample scene", output_path=None)
