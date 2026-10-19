"""
Integration and End-to-End tests for True Crime API Router and Pipelines
(Endpoints: /fictionalize, /render-board-scene/{scene_id}, /create-project,
 Neo-Noir Style Preset, Procedural Noir Motion FX)
"""

import sys
import os
from pathlib import Path

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from main import app
from services.image_service import STYLE_PRESETS, build_character_anchored_prompt
from services.video_service import build_zoompan_filter, CAMERA_MOTIONS
from services.project_service import get_project


SAMPLE_DOSSIER = """
Vào đêm 14 tháng 10 năm 2021 tại Cảng Tân Hải, ông Nguyễn Văn Hải bị sát hại cạnh công-ten-nơ.
Lời khai ban đầu của Trần Đình Long cho biết phát hiện thi thể lúc 23h.
Nghi phạm Vũ Mạnh Hùng có động cơ tranh chấp hợp đồng.
Khám nghiệm pháp y kết luận nạn nhân tử vong lúc 22h15 do vật sắc nhọn tác động.
"""


def test_neo_noir_style_and_camera_motion():
    # 1. Verify STYLE_PRESETS contains neo_noir_silhouette
    assert "neo_noir_silhouette" in STYLE_PRESETS
    preset = STYLE_PRESETS["neo_noir_silhouette"]
    assert "chiaroscuro" in preset["prompt_suffix"]
    assert "#030712" in preset["colors"]

    # 2. Verify prompt composition with neo_noir_silhouette
    composed = build_character_anchored_prompt(
        scene_prompt="Detective walking in heavy rain shining flashlight into dark alley",
        style_preset="neo_noir_silhouette",
    )
    assert "neo-noir" in composed.lower()
    assert "rain" in composed.lower()

    # 3. Verify camera motions in video_service
    assert "neo_noir_dutch_tilt" in CAMERA_MOTIONS
    assert "neo_noir_rain_motion" in CAMERA_MOTIONS

    filter_dutch = build_zoompan_filter("neo_noir_dutch_tilt", duration=5.0, width=1920, height=1080)
    assert "vignette" in filter_dutch
    assert "zoompan" in filter_dutch

    filter_rain = build_zoompan_filter("neo_noir_rain_motion", duration=5.0, width=1920, height=1080)
    assert "noise" in filter_rain
    assert "contrast" in filter_rain

    print("✓ test_neo_noir_style_and_camera_motion passed")


def test_true_crime_api_endpoints():
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))

    # 1. Test POST /api/true-crime/fictionalize
    resp_fict = client.post(
        "/api/true-crime/fictionalize",
        json={"raw_report": SAMPLE_DOSSIER, "duration_minutes": 1},
    )
    assert resp_fict.status_code == 200, f"Fictionalize failed: {resp_fict.text}"
    plan_data = resp_fict.json()

    assert "case_id" in plan_data
    assert "alias_vault" in plan_data
    assert len(plan_data["nodes"]) >= 5
    assert len(plan_data["edges"]) >= 4
    assert len(plan_data["scenes_script"]) >= 4
    case_id = plan_data["case_id"]

    # Ensure no real PII leaked in response
    assert "Nguyễn Văn Hải" not in str(plan_data["alias_vault"].values())
    print(f"✓ POST /api/true-crime/fictionalize passed: Created case {case_id}")

    # 2. Test POST /api/true-crime/render-board-scene/1 (Image only)
    resp_render_img = client.post(
        f"/api/true-crime/render-board-scene/1",
        json={"case_id": case_id, "plan": plan_data, "render_video": False},
    )
    assert resp_render_img.status_code == 200, f"Render board scene failed: {resp_render_img.text}"
    render_data = resp_render_img.json()
    assert render_data["success"] is True
    assert render_data["image_url"].startswith("/static/evidence_boards/")
    img_disk_path = Path(render_data["image_path"])
    assert img_disk_path.exists()
    assert img_disk_path.stat().st_size > 50000
    print(f"✓ POST /api/true-crime/render-board-scene/1 (Image) passed: {img_disk_path} ({img_disk_path.stat().st_size} bytes)")

    # 3. Test POST /api/true-crime/render-board-scene/1 with render_video=True (2s fast test)
    resp_render_vid = client.post(
        f"/api/true-crime/render-board-scene/1",
        json={"case_id": case_id, "plan": plan_data, "render_video": True, "duration_sec": 2.0, "fps": 15},
    )
    assert resp_render_vid.status_code == 200, f"Render board video failed: {resp_render_vid.text}"
    vid_data = resp_render_vid.json()
    assert vid_data["video_url"] is not None
    vid_disk_path = Path(vid_data["video_path"])
    assert vid_disk_path.exists()
    assert vid_disk_path.stat().st_size > 10000
    print(f"✓ POST /api/true-crime/render-board-scene/1 (Video Clip) passed: {vid_disk_path} ({vid_disk_path.stat().st_size} bytes)")

    # 4. Test POST /api/true-crime/create-project
    resp_create_proj = client.post(
        "/api/true-crime/create-project",
        json={"plan": plan_data, "voice": "vi-VN-NamMinhNeural", "pre_render_boards": True},
    )
    assert resp_create_proj.status_code == 200, f"Create project failed: {resp_create_proj.text}"
    proj_resp = resp_create_proj.json()
    assert proj_resp["success"] is True
    proj_id = proj_resp["project_id"]
    assert proj_id.startswith("proj_crime_")

    # Verify project saved on disk and loadable by project_service
    saved_project = get_project(proj_id)
    assert saved_project is not None
    assert saved_project.style_preset == "neo_noir_silhouette"
    assert saved_project.voice == "vi-VN-NamMinhNeural"
    assert len(saved_project.scenes) >= 4

    # Verify scene properties
    b_roll_scenes = [s for s in saved_project.scenes if s.shot_type == "B_ROLL_BOARD"]
    assert len(b_roll_scenes) > 0
    for bs in b_roll_scenes:
        assert bs.image_url is not None
        assert bs.image_url.startswith(f"/api/projects/{proj_id}/media/images/") or bs.image_url.startswith(f"/projects/{proj_id}/images/")
        assert bs.image_path is not None
        assert os.path.exists(bs.image_path), f"Scene B-Roll image not found at {bs.image_path}"
        assert os.path.getsize(bs.image_path) > 10000

    print(f"✓ POST /api/true-crime/create-project passed: Successfully created project {proj_id} with {len(saved_project.scenes)} scenes.")


if __name__ == "__main__":
    test_neo_noir_style_and_camera_motion()
    test_true_crime_api_endpoints()
    print("\n🎉 ALL TRUE CRIME ROUTER & PIPELINE TESTS PASSED 100%!")
