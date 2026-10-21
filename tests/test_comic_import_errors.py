"""Nhập khung truyện tranh: khung không chép được ảnh thì đánh dấu "Lỗi ảnh", không trỏ vào ảnh không tồn tại.

Lỗi cũ (rà soát 21/10/2026): chép ảnh lỗi thì `pass` nhưng cảnh vẫn được gán image_url, status "imaged" — giao diện
hiện như có ảnh, đến lúc dựng video mới hỏng.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

import config


@pytest.mark.asyncio
async def test_panel_without_image_is_marked_error(isolated_projects_dir):
    from main import app

    good = config.COMIC_SLICES_DIR / "sess1" / "panel_1.jpg"
    good.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (320, 180), (200, 30, 30)).save(good, "JPEG")
    missing = config.COMIC_SLICES_DIR / "sess1" / "panel_khong_co.jpg"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        created = await client.post("/api/projects", json={"name": "Thử nhập truyện tranh"})
        project_id = created.json()["id"]
        resp = await client.post(f"/api/projects/{project_id}/comic/import-scenes", json={
            "panels": [{"image_path": str(good)}, {"image_path": str(missing)}],
        })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    scenes = data["project"]["scenes"]
    assert len(scenes) == 2 and data["imported_scenes_count"] == 2
    ok, bad = scenes
    assert ok["status_image"] == "ready" and ok["image_url"]
    assert (isolated_projects_dir / project_id / "images" / f"{ok['id']}.jpg").exists()
    assert bad["status_image"] == "error"
    assert bad["image_url"] is None and bad["image_path"] is None
    assert "panel_khong_co.jpg" in bad["metadata"]["image_error"]
    assert data["failed_panels"] == 1
