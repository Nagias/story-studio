import asyncio
import os
import sys
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from services.script_splitter import (
    split_text_into_scenes,
    split_text_into_vox_scenes_offline,
    PACING_CONFIGS,
    SemanticStoryAnalyzer,
)
from services.project_service import delete_project

STORY_VOX_TEXT = """
Tại sao một đế chế hùng mạnh từng cai trị toàn cõi lại sụp đổ chỉ sau một đêm? Sự thật kinh hoàng ít ai ngờ tới bắt đầu từ một quyết định sai lầm.

Năm 1850, giữa kinh thành hoa lệ với những tòa lâu đài nguy nga và hàng ngàn người dân tấp nập buôn bán. Vị hoàng đế trẻ tuổi đắm chìm trong sự ngạo nghễ của quyền lực tối thượng.

Thế nhưng, từ những ngọn núi tuyết hiểm trở phía bắc, một toán chiến binh bí ẩn với giáp sắt xám xịt bắt đầu tiến quân. Họ mang theo ngọn lửa thù hận và những chiến xa hạng nặng. Căng thẳng leo thang từng ngày khi các thành trì tiền tiêu lần lượt thất thủ trong khói lửa ngút trời.

Khoảnh khắc cao trào định mệnh diễn ra khi hai đội quân giáp lá cà ngay trước cổng thành chính. Tiếng gươm đao va chạm chát chúa, bầu trời đêm rực sáng bởi những quả cầu lửa bay vút qua không gian. Vị hoàng đế đối mặt trực tiếp với thủ lĩnh phe nổi dậy trong một trận đấu kiếm sinh tử.

Cuối cùng, khi ánh bình minh ló dạng chiếu rọi qua làn khói bụi tàn cuộc, một kỷ nguyên mới đã mở ra trong sự yên bình trở lại. Bài học lịch sử đau đớn này vẫn còn vang vọng cho muôn đời sau.
"""

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.asyncio
async def test_vox_pacing_presets_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        res = await client.get("/api/vox/pacing-presets")
        assert res.status_code == 200
        data = res.json()
        assert "fast" in data
        assert "vox" in data
        assert "balanced" in data
        assert "deep_story" in data
        assert data["fast"]["target_duration"] == 3.5

@pytest.mark.asyncio
async def test_vox_analyze_script_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        res = await client.post("/api/vox/analyze-script", json={
            "text": STORY_VOX_TEXT,
            "pacing": "fast",
            "style_preset": "cinematic_realistic"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["total_scenes"] >= 6
        assert data["estimated_total_duration"] > 20.0
        assert "hook" in data["narrative_summary"]

        # Check scene 1 structure
        s1 = data["scenes"][0]
        assert s1["narrative_beat"] == "hook"
        assert s1["camera_framing"] in [
            "dramatic close-up shot focusing on intense eyes",
            "breathtaking sweeping high-angle drone shot"
        ]
        assert s1["camera_motion"] in ["zoom_in", "zoom_out", "pan_left", "pan_right"]
        assert len(s1["image_prompt"].split()) > 15

@pytest.mark.asyncio
async def test_vox_project_script_injection():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # Create project
        c_res = await client.post("/api/projects", json={
            "name": "Vox Test Pytest",
            "style_preset": "cinematic_realistic"
        })
        assert c_res.status_code == 200
        p_id = c_res.json()["id"]

        try:
            # Inject Vox Script
            v_res = await client.post(f"/api/projects/{p_id}/vox-script", json={
                "text": STORY_VOX_TEXT,
                "pacing": "fast",
                "replace_existing": True
            })
            assert v_res.status_code == 200
            v_data = v_res.json()
            assert v_data["success"] is True
            assert v_data["added_scenes"] >= 6

            # Fetch project
            detail = await client.get(f"/api/projects/{p_id}")
            assert detail.status_code == 200
            p_obj = detail.json()
            assert len(p_obj["scenes"]) == v_data["added_scenes"]
            first_scene = p_obj["scenes"][0]
            assert "narrative_beat" in first_scene["metadata"]
            assert first_scene["metadata"]["narrative_beat"] == "hook"
        finally:
            await client.delete(f"/api/projects/{p_id}")

def test_semantic_story_analyzer_unit():
    res = split_text_into_vox_scenes_offline(
        full_text=STORY_VOX_TEXT,
        pacing="fast",
        style_preset="cyberpunk"
    )
    assert res["total_scenes"] >= 6
    assert len(res["scenes"]) == res["total_scenes"]
    for sc in res["scenes"]:
        assert sc["narrative_beat"] in ["hook", "setting", "escalation", "climax", "resolution"]
        assert "cyberpunk" in sc["image_prompt"] or "neon" in sc["image_prompt"] or "photorealistic" in sc["image_prompt"]
