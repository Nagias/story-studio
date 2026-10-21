import asyncio
import io
import os
import sys
import uuid
import pytest
from pathlib import Path
import numpy as np
import cv2
from httpx import AsyncClient, ASGITransport

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from services.comic_slicer import slice_comic, assign_camera_motion, sort_reading_order
from services.project_service import delete_project

@pytest.fixture
def anyio_backend():
    return 'asyncio'

def create_synthetic_manga_image() -> bytes:
    """Generate a 1000x1400 white page with 3 panels: 1 wide top, 2 tall bottom."""
    W, H = 1000, 1400
    canvas = np.ones((H, W, 3), dtype=np.uint8) * 255

    # Top wide panel (w: 900, h: 400) -> AR > 1.5 -> pan
    cv2.rectangle(canvas, (50, 50), (950, 450), (10, 10, 10), 4)
    cv2.putText(canvas, "PANEL 1 WIDE", (100, 250), cv2.FONT_HERSHEY_SIMPLEX, 1, (30, 30, 30), 2)

    # Bottom left panel (w: 420, h: 800) -> AR <= 1.5 -> zoom_in
    cv2.rectangle(canvas, (50, 500), (470, 1300), (10, 10, 10), 4)
    cv2.putText(canvas, "PANEL 2 LEFT", (80, 900), cv2.FONT_HERSHEY_SIMPLEX, 1, (30, 30, 30), 2)

    # Bottom right panel (w: 420, h: 800) -> AR <= 1.5 -> zoom_in
    cv2.rectangle(canvas, (530, 500), (950, 1300), (10, 10, 10), 4)
    cv2.putText(canvas, "PANEL 3 RIGHT", (560, 900), cv2.FONT_HERSHEY_SIMPLEX, 1, (30, 30, 30), 2)

    _, buf = cv2.imencode(".jpg", canvas)
    return buf.tobytes()

def create_synthetic_webtoon_strip() -> bytes:
    """Generate a tall 800x2400 webtoon strip with 3 panels separated by white gutters."""
    W, H = 800, 2400
    strip = np.ones((H, W, 3), dtype=np.uint8) * 255

    # Panel 1: y 50..700
    cv2.rectangle(strip, (20, 50), (780, 700), (40, 40, 180), -1)
    # Gutter: 700..800
    # Panel 2: y 800..1500
    cv2.rectangle(strip, (20, 800), (780, 1500), (180, 40, 40), -1)
    # Gutter: 1500..1600
    # Panel 3: y 1600..2300
    cv2.rectangle(strip, (20, 1600), (780, 2300), (40, 180, 40), -1)

    _, buf = cv2.imencode(".jpg", strip)
    return buf.tobytes()

def test_camera_motion_assignment():
    """Verify camera_motion rule: > 1.5 -> pan, <= 1.5 -> zoom_in."""
    assert assign_camera_motion(1920, 1080, 0) == "pan_right"
    assert assign_camera_motion(1920, 1080, 1) == "pan_left"
    assert assign_camera_motion(1080, 1920, 0) == "zoom_in"
    assert assign_camera_motion(1000, 1000, 0) == "zoom_in"
    assert assign_camera_motion(1500, 1000, 0) == "zoom_in"  # 1.5 is <= 1.5
    assert assign_camera_motion(1501, 1000, 0) == "pan_right"  # 1.501 is > 1.5

def test_reading_order_sorting():
    """Verify LTR vs RTL sorting."""
    # Row 1: panel A
    # Row 2: panel B (left), panel C (right)
    boxes = [
        (530, 500, 420, 800),  # Right
        (50, 50, 900, 400),    # Top
        (50, 500, 420, 800),   # Left
    ]

    sorted_ltr = sort_reading_order(boxes, "ltr")
    assert sorted_ltr[0][1] == 50  # Top panel first
    assert sorted_ltr[1][0] == 50  # Left panel second
    assert sorted_ltr[2][0] == 530 # Right panel third

    sorted_rtl = sort_reading_order(boxes, "rtl")
    assert sorted_rtl[0][1] == 50  # Top panel first
    assert sorted_rtl[1][0] == 530 # Right panel second (Manga RTL)
    assert sorted_rtl[2][0] == 50  # Left panel third

def test_slice_service_grid():
    """Test slice_comic on grid image."""
    img_bytes = create_synthetic_manga_image()
    res = slice_comic(img_bytes, mode="grid", reading_order="ltr")
    assert res["success"] is True
    assert res["total_panels"] == 3
    assert len(res["panels"]) == 3

    p1 = res["panels"][0]
    assert p1["is_wide"] is True
    assert p1["camera_motion"] in ("pan_right", "pan_left")

    p2 = res["panels"][1]
    assert p2["is_wide"] is False
    assert p2["camera_motion"] == "zoom_in"

def test_slice_service_strip():
    """Test slice_comic on strip webtoon image."""
    img_bytes = create_synthetic_webtoon_strip()
    res = slice_comic(img_bytes, mode="strip")
    assert res["success"] is True
    assert res["total_panels"] == 3
    assert len(res["panels"]) == 3
    # Top to bottom order
    assert res["panels"][0]["bbox"]["y"] < res["panels"][1]["bbox"]["y"] < res["panels"][2]["bbox"]["y"]

@pytest.mark.asyncio
async def test_api_comic_slice_and_import():
    """Test full API pipeline: upload -> slice -> import to storyboard."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # 1. Upload & slice image
        img_bytes = create_synthetic_manga_image()
        files = {"file": ("test_manga.jpg", img_bytes, "image/jpeg")}
        data = {"mode": "grid", "reading_order": "ltr", "min_area_ratio": "0.03"}

        resp = await client.post("/api/comic/slice", files=files, data=data)
        assert resp.status_code == 200
        slice_data = resp.json()
        assert slice_data["success"] is True
        assert slice_data["total_panels"] == 3
        assert len(slice_data["panels"]) == 3

        # 2. Import into a test project
        test_proj_id = f"test_proj_comic_{uuid.uuid4().hex[:6]}"
        import_req = {
            "panels": slice_data["panels"],
            "clear_existing": True,
            "text_prefix": "Truyện tranh Manga"
        }
        resp_import = await client.post(f"/api/projects/{test_proj_id}/comic/import-scenes", json=import_req)
        assert resp_import.status_code == 200
        import_res = resp_import.json()
        assert import_res["success"] is True
        assert import_res["imported_scenes_count"] == 3

        # 3. Retrieve project and verify scenes
        resp_proj = await client.get(f"/api/projects/{test_proj_id}")
        assert resp_proj.status_code == 200
        proj_data = resp_proj.json()
        scenes = proj_data["scenes"]
        assert len(scenes) == 3
        assert scenes[0]["camera_motion"] in ("pan_left", "pan_right")
        assert scenes[1]["camera_motion"] == "zoom_in"
        assert scenes[0]["status"] == "imaged"
        assert scenes[0]["image_url"].startswith(f"/api/projects/{test_proj_id}/media/images/")

        # Cleanup
        delete_project(test_proj_id)

@pytest.mark.live  # produce-long-video thật: 9router, ảnh, Edge-TTS
@pytest.mark.asyncio
async def test_api_produce_long_video_endpoint():
    """Verify POST /api/projects/{id}/produce-long-video initiates MoneyPrinterTurbo stepper pipeline."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        test_proj_id = f"test_proj_produce_{uuid.uuid4().hex[:6]}"
        produce_req = {
            "text": "Trận chiến nổ ra tại cổng thành. Tướng quân giơ cao thanh kiếm lệnh.",
            "pacing": "fast",
            "style_preset": "manga_battle_action",
            "character_anchor": "Vị tướng áo giáp đen",
            "voice": "vi-VN-HoaiMyNeural",
            "bgm": "none",
            "ducking": False,
            "hardsub": False,
            "resolution": "720p",
            "fps": 25
        }
        resp = await client.post(f"/api/projects/{test_proj_id}/produce-long-video", json=produce_req)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "render_id" in data
        assert data["status"] == "queued"

        # Check render status
        render_id = data["render_id"]
        resp_status = await client.get(f"/api/render-status/{render_id}")
        assert resp_status.status_code == 200
        status_data = resp_status.json()
        assert status_data["render_id"] == render_id
        assert status_data["project_id"] == test_proj_id

        delete_project(test_proj_id)

