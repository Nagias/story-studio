"""
Đồng bộ giao diện ↔ server (2026-10-19): server là bản chính.

- PUT /projects/{id} lưu được settings và nhân vật dạng giao diện (trong settings).
- Bản client cũ (thiếu ảnh/video mà server vừa tạo) không xoá mất media trên server.
- POST /projects/{id}/scenes/{scene_id}/upload-media lưu đúng file mà bước dựng đọc.

Dữ liệu dự án nằm trong tmp_path; không gọi dịch vụ ngoài.
"""
import io
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.schemas import ProjectCreateRequest, SceneCreateRequest  # noqa: E402
from routers import api as api_module  # noqa: E402
from services import project_service  # noqa: E402

MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048


@pytest.fixture
def projects_dir(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(project_service, "PROJECTS_DIR", projects)
    monkeypatch.setattr(api_module, "PROJECTS_DIR", projects)
    monkeypatch.setattr(api_module, "STATIC_DIR", tmp_path / "static")
    return projects


@pytest.fixture
def client(projects_dir):
    app = FastAPI()
    app.include_router(api_module.router)
    with TestClient(app) as c:
        yield c


def _project_with_scene():
    project = project_service.create_project(ProjectCreateRequest(name="Sync test"))
    scene = project_service.add_scene(project.id, SceneCreateRequest(text="Cảnh 1", image_prompt="rainy street"))
    return project_service.get_project(project.id), scene


def _jpeg_bytes(size=(640, 360)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (90, 30, 30)).save(buf, "JPEG")
    return buf.getvalue()


def test_put_persists_settings_and_ui_character(client):
    project, _ = _project_with_scene()
    payload = project.model_dump()
    payload["settings"] = {"bgm": "mysterious_dark", "ui_character": {"name": "Lâm", "prompt": "young swordsman"}}
    payload["bgm_track"] = "mysterious_dark"

    resp = client.put(f"/api/projects/{project.id}", json=payload)
    assert resp.status_code == 200, resp.text

    saved = project_service.get_project(project.id)
    assert saved.settings["bgm"] == "mysterious_dark"
    assert saved.settings["ui_character"]["name"] == "Lâm"
    assert saved.bgm_track == "mysterious_dark"


def test_put_with_stale_client_scene_keeps_server_media(client, projects_dir):
    """Muse vừa ghi ảnh lên server, giao diện tự lưu bản cũ chưa có ảnh: ảnh không được mất."""
    project, scene = _project_with_scene()
    stale_payload = project.model_dump()  # bản giao diện đang giữ: chưa có ảnh

    # Server (Muse) cập nhật ảnh cho cảnh
    fresh = project_service.get_project(project.id)
    fresh.scenes[0].image_path = str(projects_dir / project.id / "images" / f"{scene.id}.jpg")
    fresh.scenes[0].image_url = f"/api/projects/{project.id}/media/images/{scene.id}.jpg"
    project_service._save_project(fresh)

    # Người dùng sửa lời thoại rồi giao diện tự lưu bản cũ
    stale_payload["scenes"][0]["text"] = "Lời thoại đã sửa"
    resp = client.put(f"/api/projects/{project.id}", json=stale_payload)
    assert resp.status_code == 200, resp.text

    saved = project_service.get_project(project.id).scenes[0]
    assert saved.text == "Lời thoại đã sửa"
    assert saved.image_url == f"/api/projects/{project.id}/media/images/{scene.id}.jpg"
    assert saved.image_path and saved.image_path.endswith(f"{scene.id}.jpg")


def test_gen_image_does_not_overwrite_edits_saved_while_generating(client, projects_dir, monkeypatch):
    """Muse mất vài phút; giao diện tự lưu chỉnh sửa trong lúc đó. Kết quả ảnh không được xoá chúng."""
    project, scene = _project_with_scene()
    project_service.add_scene(project.id, SceneCreateRequest(text="Cảnh 2 gốc"))

    async def slow_generate_image(**kwargs):
        # Trong lúc "chờ Muse", giao diện tự lưu: sửa lời thoại cảnh 2
        current = project_service.get_project(project.id)
        current.scenes[1].text = "Cảnh 2 đã sửa trong lúc chờ"
        project_service._save_project(current)
        out = Path(kwargs["output_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(_jpeg_bytes())
        return {"success": True, "image_path": str(out), "provider": "meta_muse_cloud"}

    monkeypatch.setattr(api_module, "generate_image", slow_generate_image)
    resp = client.post(f"/api/projects/{project.id}/scenes/{scene.id}/gen-image", json={"prompt": "x"})
    assert resp.status_code == 200, resp.text

    saved = project_service.get_project(project.id)
    assert saved.scenes[1].text == "Cảnh 2 đã sửa trong lúc chờ"
    assert saved.scenes[0].image_url.endswith(f"/media/images/{scene.id}.jpg")


def test_produce_request_keeps_project_image_provider():
    """Không truyền image_provider thì sản xuất video phải giữ provider của dự án (vd Muse)."""
    from models.schemas import LongVideoProduceRequest
    assert LongVideoProduceRequest().image_provider is None


def test_upload_media_image_writes_render_input(client, projects_dir):
    project, scene = _project_with_scene()
    resp = client.post(
        f"/api/projects/{project.id}/scenes/{scene.id}/upload-media",
        files={"file": ("my.png", _jpeg_bytes(), "image/jpeg")},
        data={"kind": "image"},
    )
    assert resp.status_code == 200, resp.text
    target = projects_dir / project.id / "images" / f"{scene.id}.jpg"
    assert target.exists()
    with Image.open(target) as img:
        assert img.format == "JPEG"

    saved = project_service.get_project(project.id).scenes[0]
    assert saved.image_url.endswith(f"/media/images/{scene.id}.jpg")
    assert saved.status_image == "ready"
    assert not saved.image_url.startswith("data:")


def test_upload_media_video_goes_to_motion_clip(client, projects_dir):
    project, scene = _project_with_scene()
    resp = client.post(
        f"/api/projects/{project.id}/scenes/{scene.id}/upload-media",
        files={"file": ("clip.mp4", MP4_BYTES, "video/mp4")},
        data={"kind": "video"},
    )
    assert resp.status_code == 200, resp.text
    videos = projects_dir / project.id / "videos"
    assert (videos / f"{scene.id}_muse.mp4").exists()
    assert not (videos / f"{scene.id}.mp4").exists()

    saved = project_service.get_project(project.id).scenes[0]
    assert saved.media_view_mode == "video"
    assert saved.motion_video_path.endswith(f"{scene.id}_muse.mp4")
    assert not (saved.video_url or "").startswith("blob:")


@pytest.mark.parametrize("kind,content", [("image", b"not an image"), ("video", b"not a video at all")])
def test_upload_media_rejects_invalid_files(client, kind, content):
    project, scene = _project_with_scene()
    resp = client.post(
        f"/api/projects/{project.id}/scenes/{scene.id}/upload-media",
        files={"file": ("bad.bin", content, "application/octet-stream")},
        data={"kind": kind},
    )
    assert resp.status_code == 400


def test_upload_media_unknown_scene_is_404(client):
    project, _ = _project_with_scene()
    resp = client.post(
        f"/api/projects/{project.id}/scenes/scene_khong_co/upload-media",
        files={"file": ("a.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"kind": "image"},
    )
    assert resp.status_code == 404
