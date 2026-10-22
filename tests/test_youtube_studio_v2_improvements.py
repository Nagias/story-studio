"""
Test Suite for 4 Key Production YouTube AI Storyboard Studio Improvements:
1. Scene Transitions (Dip to Black, Crossfade, Flash White).
2. Kinetic / Word-by-Word Highlight ASS Subtitles.
3. Action SFX Library (16+ effects) & Semantic Auto-detection.
4. 16:9 Full HD YouTube Thumbnail & YouTube SEO Packaging (Titles, Chapters, Tags).
"""

import sys
import tempfile
from pathlib import Path
import pytest
from PIL import Image
from httpx import AsyncClient, ASGITransport

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from main import app
from services.video_service import render_scene_video, build_xfade_video
from services.subtitle_engine import generate_karaoke_ass
from services.audio_engine import auto_detect_scene_sfx, find_or_create_sfx
from services.thumbnail_service import generate_youtube_thumbnail
from services.youtube_seo_rules import check_thumbnail, all_ok
from services.project_service import create_project, delete_project, ProjectCreateRequest


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.asyncio
async def test_feature_01_scene_transitions_dip_to_black_and_xfade():
    """Verify Scene Transitions: dip_to_black filter generation and xfade multi-clip assembly."""
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        img_p = t / "test_img.png"
        Image.new("RGB", (640, 360), color=(100, 40, 40)).save(img_p)

        out_v = t / "dip_scene.mp4"
        res = await render_scene_video(
            image_path=str(img_p),
            audio_path=None,
            output_path=str(out_v),
            duration=3.0,
            camera_motion="zoom_in",
            resolution="720p",
            transition="dip_to_black",
        )
        assert Path(res["video_path"]).exists()
        assert Path(res["video_path"]).stat().st_size > 1000

        # Test xfade assembly between 2 clips
        out_v2 = t / "dip_scene2.mp4"
        await render_scene_video(
            image_path=str(img_p),
            audio_path=None,
            output_path=str(out_v2),
            duration=3.0,
            camera_motion="zoom_out",
            resolution="720p",
        )

        xfade_out = t / "xfade_result.mp4"
        success = await build_xfade_video(
            scene_video_paths=[str(out_v), str(out_v2)],
            durations=[3.0, 3.0],
            output_video_path=xfade_out,
            transition_name="fade",
            trans_dur=0.4,
        )
        assert success is True
        assert xfade_out.exists()
        assert xfade_out.stat().st_size > 1000


def test_feature_02_kinetic_word_by_word_ass_subtitles():
    """Verify Kinetic Word-by-Word Highlight ASS Subtitles."""
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        out_ass = t / "kinetic.ass"

        scenes_data = [
            {
                "scene_id": "sc_01",
                "duration": 4.0,
                "text": "Three hundred Spartan warriors stood unyielding.",
                "kinetic_highlight_words": ["spartan", "unyielding"],
            }
        ]

        res_path = generate_karaoke_ass(
            scenes_data=scenes_data,
            output_ass_path=out_ass,
            style_mode="kinetic_pop",
            font_size=48,
        )

        assert Path(res_path).exists()
        content = Path(res_path).read_text(encoding="utf-8")
        assert "[Script Info]" in content
        assert "[V4+ Styles]" in content
        assert "Style: Default" in content
        # Check that active word pop tags are generated
        assert r"\c&H0000D7FF" in content  # Golden yellow active word highlight
        assert r"\c&H00FFFFFF" in content  # White standard word


def test_feature_03_action_sfx_library_and_auto_detect():
    """Verify 16+ Action SFX Library synthesis and semantic auto-detection."""
    # 1. Semantic cue detection
    spartan_text = "King Leonidas raised his notched ash-wood spear against the immense Persian horde."
    cues = auto_detect_scene_sfx(spartan_text, "A massive battle clash on the stormy cliff")
    assert "sword_clash" in cues or "crowd_battle_shout" in cues

    storm_text = "Sấm sét rền vang giữa cơn mưa bão tuyết mịt mù."
    cues_storm = auto_detect_scene_sfx(storm_text)
    assert "distant_thunder_subtle" in cues_storm or "heavy_rain_loop" in cues_storm

    # 2. SFX file exists or can be synthesized on demand
    sfx_path = find_or_create_sfx("sword_clash")
    assert sfx_path is not None
    assert Path(sfx_path).exists()
    assert Path(sfx_path).stat().st_size > 1000

    sfx_boom = find_or_create_sfx("explosion_boom")
    assert sfx_boom is not None
    assert Path(sfx_boom).exists()


def test_feature_04_youtube_thumbnail_and_seo_packaging():
    """Thumbnail 16:9 Full HD đạt luật YouTube. Gói SEO (tiêu đề, mô tả, tags) kiểm ở tests/test_youtube_seo_pack.py."""
    proj = create_project(ProjectCreateRequest(
        name="US Novel: 300 Spartan Stand",
        style_preset="spartan_epic_mythology",
    ))

    try:
        # Generate thumbnail
        thumb_res = generate_youtube_thumbnail(
            project=proj,
            custom_headline="300 DŨNG SĨ SPARTA",
            custom_subtext="TRẬN CHIẾN TẠI CỬA TỬ",
            badge_text="1080P",
        )

        assert thumb_res["success"] is True
        thumb_p = Path(thumb_res["thumbnail_path"])
        assert thumb_p.exists()
        assert thumb_p.stat().st_size > 5000

        # Verify resolution 1920x1080
        with Image.open(thumb_p) as im:
            assert im.size == (1920, 1080)

        assert all_ok(check_thumbnail(thumb_p))

    finally:
        delete_project(proj.id)


@pytest.mark.asyncio
async def test_feature_05_api_thumbnail_and_seo_endpoints():
    """Verify API endpoints for Thumbnail generation and SEO Pack retrieval."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # 1. Create test project
        p_res = await client.post("/api/projects", json={"name": "API SEO Test Story"})
        assert p_res.status_code == 200
        proj_id = p_res.json()["id"]

        try:
            # 2. Call Thumbnail Generate Endpoint
            t_res = await client.post(f"/api/projects/{proj_id}/thumbnail/generate", json={
                "custom_headline": "TEST HEADLINE",
                "custom_subtext": "TEST SUBTEXT",
            })
            assert t_res.status_code == 200
            t_data = t_res.json()
            assert t_data["success"] is True
            assert t_data["headline_line1"] == "TEST HEADLINE"

            # 3. Call Thumbnail GET Endpoint
            thumb_get = await client.get(f"/api/projects/{proj_id}/thumbnail")
            assert thumb_get.status_code == 200
            assert thumb_get.headers["content-type"] == "image/jpeg"

            # 4. Gói SEO mới: chưa tạo thì trạng thái rỗng (tạo gói cần video đã dựng, xem test_youtube_seo_pack.py)
            seo_get = await client.get(f"/api/projects/{proj_id}/youtube-seo")
            assert seo_get.status_code == 200
            assert seo_get.json()["pack"] is None

        finally:
            await client.delete(f"/api/projects/{proj_id}")
