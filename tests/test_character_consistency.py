import pytest
import sys
from pathlib import Path
from httpx import AsyncClient, ASGITransport

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from models.schemas import (
    get_preset_characters,
    get_preset_character_by_id,
)
from services.image_service import (
    get_available_styles,
    build_character_anchored_prompt,
    MASTER_NEGATIVE_PROMPT,
)

@pytest.fixture
def anyio_backend():
    return 'asyncio'

def test_preset_characters_catalog():
    """Verify all 4 required master consistency characters exist with complete specifications."""
    presets = get_preset_characters()
    assert len(presets) >= 4

    preset_ids = {c.id for c in presets}
    assert "paladin_kai" in preset_ids
    assert "roman_titus" in preset_ids
    assert "spartan_leon" in preset_ids
    assert "kingdom_shin" in preset_ids

    # 1. Paladin Kai check
    kai = get_preset_character_by_id("paladin_kai")
    assert kai is not None
    assert "silver" in kai.armor_or_costume.lower()
    assert "cyan" in kai.armor_or_costume.lower() or "turquoise" in kai.armor_or_costume.lower()
    assert "scarlet" in kai.armor_or_costume.lower() or "crimson" in kai.armor_or_costume.lower()
    assert "broadsword" in kai.main_weapon.lower()
    assert "gold" in kai.main_weapon.lower()
    assert len(kai.face_features) > 10
    assert len(kai.distinguishing_marks) > 10

    # 2. Roman Titus check
    titus = get_preset_character_by_id("roman_titus")
    assert titus is not None
    assert "scutum" in titus.main_weapon.lower()
    assert "bull" in titus.main_weapon.lower()
    assert "pilum" in titus.main_weapon.lower()
    assert "galea" in titus.distinguishing_marks.lower()

    # 3. Spartan Leon check
    leon = get_preset_character_by_id("spartan_leon")
    assert leon is not None
    assert "muscle cuirass" in leon.armor_or_costume.lower()
    assert "corinthian" in leon.distinguishing_marks.lower()
    assert "hoplon" in leon.main_weapon.lower()
    assert "lambda" in leon.main_weapon.lower()

    # 4. Kingdom Shin check
    shin = get_preset_character_by_id("kingdom_shin")
    assert shin is not None
    assert "scale armor" in shin.armor_or_costume.lower() or "lamellar" in shin.armor_or_costume.lower()
    assert "broadsword" in shin.main_weapon.lower()
    assert "ponytail" in shin.hair_style_and_color.lower()

def test_five_new_style_presets():
    """Verify the 5 specialized master styles are configured accurately."""
    styles = {s["id"]: s for s in get_available_styles()}

    # 1. manga_battle_action
    assert "manga_battle_action" in styles
    s1 = styles["manga_battle_action"]
    assert "Murata" in s1["prompt_suffix"] or "Kengan" in s1["prompt_suffix"]
    assert "speed lines" in s1["prompt_suffix"]
    assert "SFX" in s1["prompt_suffix"]

    # 2. manga_historical_war
    assert "manga_historical_war" in styles
    s2 = styles["manga_historical_war"]
    assert "Kingdom" in s2["prompt_suffix"]
    assert "Yasuhisa Hara" in s2["prompt_suffix"]
    assert "army" in s2["prompt_suffix"]

    # 3. fantasy_paladin_armor
    assert "fantasy_paladin_armor" in styles
    s3 = styles["fantasy_paladin_armor"]
    assert "Fate/Grand Order" in s3["prompt_suffix"] or "Granblue" in s3["prompt_suffix"]
    assert "silver plate armor" in s3["prompt_suffix"]

    # 4. roman_legionary_epic
    assert "roman_legionary_epic" in styles
    s4 = styles["roman_legionary_epic"]
    assert "Roman" in s4["prompt_suffix"]
    assert "oil painting" in s4["prompt_suffix"]
    assert "scutum" in s4["prompt_suffix"]

    # 5. spartan_mythic_warrior
    assert "spartan_mythic_warrior" in styles
    s5 = styles["spartan_mythic_warrior"]
    assert "Spartan" in s5["prompt_suffix"]
    assert "muscle cuirass" in s5["prompt_suffix"]
    assert "hoplon" in s5["prompt_suffix"]

def test_masterpiece_negative_prompt():
    """Ensure master negative prompt eliminates all anatomical flaws and style anomalies."""
    assert len(MASTER_NEGATIVE_PROMPT.split()) > 15
    assert "deformed" in MASTER_NEGATIVE_PROMPT
    assert "bad anatomy" in MASTER_NEGATIVE_PROMPT
    assert "inconsistent clothing" in MASTER_NEGATIVE_PROMPT
    assert "modern artifacts in historical scene" in MASTER_NEGATIVE_PROMPT

def test_build_character_anchored_prompt_across_scenes():
    """Test character anchoring across multiple consecutive scenes to ensure 0% identity drift."""
    kai = get_preset_character_by_id("paladin_kai")
    scenes = [
        "Standing heroically on the edge of a cliff overlooking misty valleys",
        "Charging fiercely into the battle against a swarm of shadowy demons",
        "Kneeling down to inspect ancient glowing ruins in the dense forest",
        "Raising the legendary broadsword high as golden dawn rays pierce through clouds",
        "Walking calmly through the cheering crowds in the royal capital city",
    ]

    for scene in scenes:
        prompt = build_character_anchored_prompt(
            scene_prompt=scene,
            style_preset="fantasy_paladin_armor",
            character=kai,
        )
        assert scene in prompt
        # Verify key character traits are immutable in every scene
        assert "silver full plate armor" in prompt
        assert "cyan turquoise gemstones" in prompt
        assert "crimson scarlet velvet cape" in prompt
        assert "gold hilt" in prompt
        assert "Fate/Grand Order" in prompt or "Granblue" in prompt

def test_character_anchor_with_kingdom_shin_and_manga_war():
    """Test Kingdom Shin with the epic manga war style."""
    shin = get_preset_character_by_id("kingdom_shin")
    scene = "Leading the vanguard unit screaming with fiery resolve across the battlefield"

    prompt = build_character_anchored_prompt(
        scene_prompt=scene,
        style_preset="manga_historical_war",
        character=shin,
    )
    assert scene in prompt
    assert "scale armor" in prompt or "lamellar" in prompt
    assert "ponytail" in prompt
    assert "Yasuhisa Hara Kingdom style" in prompt
    assert "monumental double-page spread" in prompt

@pytest.mark.asyncio
async def test_api_character_presets_endpoints():
    """Verify REST API endpoints for character presets."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # GET /api/characters/presets
        r = await client.get("/api/characters/presets")
        assert r.status_code == 200
        chars = r.json()
        assert len(chars) >= 4
        ids = [c["id"] for c in chars]
        assert "paladin_kai" in ids
        assert "roman_titus" in ids

        # GET /api/characters/presets/paladin_kai
        r_kai = await client.get("/api/characters/presets/paladin_kai")
        assert r_kai.status_code == 200
        kai_data = r_kai.json()
        assert kai_data["id"] == "paladin_kai"
        assert "Kai" in kai_data["name"]

        # GET 404 for unknown character
        r_404 = await client.get("/api/characters/presets/non_existent_hero")
        assert r_404.status_code == 404

@pytest.mark.asyncio
async def test_project_creation_with_character_preset():
    """Test creating a project with a preset character automatically sets up character anchor."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        r = await client.post("/api/projects", json={
            "name": "Spartan War Chronicle",
            "style_preset": "spartan_mythic_warrior",
            "character_preset_id": "spartan_leon",
        })
        assert r.status_code == 200
        p = r.json()
        p_id = p["id"]

        try:
            assert p["style_preset"] == "spartan_mythic_warrior"
            assert "Leon" in p["character"]["name"]
            assert "muscle cuirass" in p["character_anchor"]

            # Add scene and generate image (mock_cinematic)
            sc_res = await client.post(f"/api/projects/{p_id}/scenes", json={
                "text": "Chiến binh Sparta đứng canh gác bên bờ vực hẻm núi Thermopylae.",
                "image_prompt": "Guarding the narrow mountain pass under blazing sunset",
            })
            assert sc_res.status_code == 200
            sc_id = sc_res.json()["id"]

            img_res = await client.post(f"/api/projects/{p_id}/scenes/{sc_id}/gen-image", json={
                "provider": "mock_cinematic",
            })
            assert img_res.status_code == 200
            assert img_res.json()["success"] is True
            assert "full_prompt" in img_res.json()
            assert "muscle cuirass" in img_res.json()["full_prompt"]
        finally:
            await client.delete(f"/api/projects/{p_id}")
