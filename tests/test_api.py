import asyncio
import sys
import uuid
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

# Add backend directory to sys.path
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from services.project_service import delete_project

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.asyncio
async def test_get_health():
    """Verify GET /api/health returns online status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "online"
        assert data["service"] == "YouTube Story Maker Backend"

@pytest.mark.asyncio
async def test_get_voices():
    """Verify GET /api/voices returns catalog of available voices."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        resp = await client.get("/api/voices")
        assert resp.status_code == 200
        voices = resp.json()
        assert isinstance(voices, list)
        assert len(voices) >= 6

        ids = [v["id"] for v in voices]
        assert "vi-VN-HoaiMyNeural" in ids
        assert "vi-VN-NamMinhNeural" in ids
        assert "en-US-JennyNeural" in ids

@pytest.mark.asyncio
async def test_get_styles():
    """Verify GET /api/styles returns style presets."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        resp = await client.get("/api/styles")
        assert resp.status_code == 200
        styles = resp.json()
        assert len(styles) >= 6
        ids = [s["id"] for s in styles]
        assert "cinematic_realistic" in ids
        assert "anime" in ids
        assert "manga_battle_action" in ids

@pytest.mark.asyncio
async def test_get_bgm_tracks():
    """Verify GET /api/bgm-tracks returns music tracks catalog."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        resp = await client.get("/api/bgm-tracks")
        assert resp.status_code == 200
        tracks = resp.json()
        assert len(tracks) >= 3

@pytest.mark.asyncio
async def test_post_split_script():
    """Verify POST /api/split-script intelligently splits long story text."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        long_story = (
            "Ngày xửa ngày xưa có một chú bé dũng cảm sống ở một ngôi làng ven biển. "
            "Một ngày kia, bầu trời bỗng nổi cơn giông bão dữ dội và một con thuyền lạ dạt vào bờ. "
            "Cậu bé quyết định leo lên thuyền để tìm kiếm những người còn sống sót."
        )
        resp = await client.post("/api/split-script", json={
            "text": long_story,
            "max_words_per_scene": 18,
            "language": "vi",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "scenes" in data
        assert data["count"] >= 2
        for sc in data["scenes"]:
            assert "text" in sc
            assert "image_prompt" in sc
            assert "camera_motion" in sc

@pytest.mark.live  # thu giọng Edge-TTS thật
@pytest.mark.asyncio
async def test_project_crud_and_render_flow():
    """Verify complete CRUD flow: Create project, add scenes, and invoke render pipeline."""
    transport = ASGITransport(app=app)
    created_proj_id = None

    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        try:
            # 1. POST /api/projects
            create_payload = {
                "name": "QA Automation Story",
                "description": "Integration test project for Story Studio API",
                "style_preset": "cinematic_realistic",
                "voice": "vi-VN-HoaiMyNeural",
                "character_anchor": "Cậu bé tóc đen mặc áo choàng xanh thẫm",
                "image_provider": "mock_cinematic",
            }
            resp_create = await client.post("/api/projects", json=create_payload)
            assert resp_create.status_code == 200
            proj_data = resp_create.json()
            created_proj_id = proj_data["id"]
            assert created_proj_id.startswith("proj_")
            assert proj_data["name"] == "QA Automation Story"

            # 2. GET /api/projects/{id}
            resp_get = await client.get(f"/api/projects/{created_proj_id}")
            assert resp_get.status_code == 200
            assert resp_get.json()["id"] == created_proj_id

            # 3. POST /api/projects/{id}/scenes (Scene 1)
            resp_sc1 = await client.post(f"/api/projects/{created_proj_id}/scenes", json={
                "text": "Cậu bé đứng nhìn về phía ngọn hải đăng cổ kính ven biển.",
                "image_prompt": "Young boy standing looking at an ancient lighthouse at dusk",
                "camera_motion": "zoom_in",
            })
            assert resp_sc1.status_code == 200
            sc1 = resp_sc1.json()
            sc1_id = sc1["id"]

            # 4. POST /api/projects/{id}/scenes (Scene 2)
            resp_sc2 = await client.post(f"/api/projects/{created_proj_id}/scenes", json={
                "text": "Ngọn đèn bỗng tỏa ra ánh sáng xanh lam huyền bí.",
                "image_prompt": "Ancient lighthouse emitting ethereal glowing blue light",
                "camera_motion": "pan_left",
            })
            assert resp_sc2.status_code == 200
            sc2 = resp_sc2.json()

            # 5. PUT /api/projects/{id}/scenes/{sc_id}
            resp_put = await client.put(f"/api/projects/{created_proj_id}/scenes/{sc1_id}", json={
                "camera_motion": "zoom_out",
            })
            assert resp_put.status_code == 200
            assert resp_put.json()["camera_motion"] == "zoom_out"

            # 6. POST /api/projects/{id}/render
            render_payload = {
                "resolution": "720p",
                "ducking": True,
                "hardsub": True,
                "bgm": "ambient_peaceful",
                "bgm_volume": 0.2,
                "fps": 25,
            }
            resp_render = await client.post(f"/api/projects/{created_proj_id}/render", json=render_payload)
            assert resp_render.status_code == 200
            render_info = resp_render.json()
            assert render_info["success"] is True
            render_id = render_info["render_id"]
            assert render_id.startswith("render_")

            # 7. GET /api/render-status/{render_id} (Poll until completed)
            max_wait_seconds = 60
            poll_interval = 2.0
            elapsed = 0.0
            final_status = None

            while elapsed < max_wait_seconds:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                resp_status = await client.get(f"/api/render-status/{render_id}")
                assert resp_status.status_code == 200
                st_data = resp_status.json()
                final_status = st_data["status"]

                if final_status in ("completed", "failed"):
                    break

            assert final_status == "completed", f"Render did not complete in time, status: {final_status}"
            assert st_data["progress"] == 100
            assert st_data["video_url"] is not None

        finally:
            # 8. Clean up created project
            if created_proj_id:
                delete_project(created_proj_id)

@pytest.mark.asyncio
async def test_api_validation_errors():
    """Verify expected HTTP errors for non-existent projects or invalid render requests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # Non-existent project
        resp = await client.get("/api/projects/proj_non_existent")
        assert resp.status_code == 404

        # Non-existent scene addition
        resp = await client.post("/api/projects/proj_non_existent/scenes", json={"text": "Hello"})
        assert resp.status_code == 404

        # Render project with no scenes
        resp_empty_proj = await client.post("/api/projects", json={"name": "Empty Project"})
        empty_id = resp_empty_proj.json()["id"]
        try:
            resp_render_empty = await client.post(f"/api/projects/{empty_id}/render", json={})
            assert resp_render_empty.status_code == 400
        finally:
            delete_project(empty_id)

@pytest.mark.asyncio
async def test_api_gen_image_upsert():
    """Verify that gen-image handles standalone generation and auto-upserts missing projects."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # 1. Standalone /api/gen-image
        resp = await client.post("/api/gen-image", json={
            "prompt": "Test standalone image generation",
            "style": "cinematic_realistic",
            "provider": "mock_cinematic"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "/api/projects/" in data["image_url"]

        # Verify serving the generated media
        media_resp = await client.get(data["image_url"])
        assert media_resp.status_code == 200
        assert media_resp.headers["content-type"] == "image/jpeg"

        # 2. Auto-upsert on uncreated project / scene
        upsert_proj_id = f"proj_test_upsert_{uuid.uuid4().hex[:6]}"
        try:
            resp_upsert = await client.post(
                f"/api/projects/{upsert_proj_id}/scenes/scene_1/gen-image",
                json={
                    "prompt": "Test auto-upsert image generation",
                    "style": "anime",
                    "provider": "mock_cinematic"
                }
            )
            assert resp_upsert.status_code == 200
            up_data = resp_upsert.json()
            assert up_data["success"] is True
            assert up_data["scene_id"] == "scene_1"
            assert up_data["image_url"] == f"/api/projects/{upsert_proj_id}/media/images/scene_1.jpg"

            # Verify image file exists and serves
            up_media = await client.get(up_data["image_url"])
            assert up_media.status_code == 200
            assert len(up_media.content) > 1000
        finally:
            delete_project(upsert_proj_id)
            delete_project("default_preview")
