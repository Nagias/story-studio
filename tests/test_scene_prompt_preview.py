"""Xem trước prompt thật gửi Muse trên thẻ cảnh (services/scene_prompt_preview.py, routers/scene_prompt_preview.py).

Chủ dự án 15/11/2026: "Prompt thực tế như nào cũng phải có trên tool luôn". Test đối chiếu chuỗi xem trước với chuỗi
mà đường thật tạo ra (route tạo việc Muse + Fleet Runner), không với một bản chép tay của khuôn chữ.
Offline: LLM giả, ảnh vẽ bằng PIL, dự án ghi vào thư mục tạm.
"""
import asyncio
import json
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

from models.schemas import Project, Scene  # noqa: E402
from routers import muse_bridge as mb  # noqa: E402
from routers import scene_prompt_preview as spp_router  # noqa: E402
from runners import muse_fleet_runner as runner  # noqa: E402
from services import character_sheets as cs  # noqa: E402
from services import climax_video  # noqa: E402
from services import dialogue_video as dv  # noqa: E402
from services import image_service, muse_prompt_format, project_service, story_cast  # noqa: E402
from services import scene_prompt_preview as spp  # noqa: E402
from services.climax_brief import landscape_brief, scene_brief, target_seconds  # noqa: E402
from tests.story_review_fakes import FakePeopleLLM  # noqa: E402

PID = "proj_prompt_prev01"
LONG_TEXT = ("Đêm đó trời mưa rất to. Lan đứng trước cửa căn hộ và gõ ba lần. Không ai trả lời. Cô đẩy cửa bước vào "
             "phòng khách tối om, nghe tiếng nước nhỏ giọt ở đâu đó. Trên bàn có một lá thư chưa mở. Cô cầm lên đọc và "
             "bàn tay bắt đầu run. Ngoài cửa sổ, ánh đèn xe cảnh sát loé lên rồi tắt.")


def _project(scene_meta=None, duration=None) -> Project:
    scenes = [Scene(id=f"scene_{n:03d}", order=n, text=LONG_TEXT if n == 2 else f"Lý Minh Hạ mở cánh cửa thứ {n}.",
                    image_prompt=f"Medium shot, Ly Minh Ha opens door number {n} in a dim basement corridor.",
                    duration=duration, metadata=dict(scene_meta or {}) if n == 2 else {})
              for n in range(1, 4)]
    project = Project(id=PID, name="Thử xem prompt", style_preset="horror_cartoon_2d", scenes=scenes,
                      character_anchor="featuring character: an old samurai with a red cape")
    project_service.ensure_project_dirs(PID)
    for s in scenes:
        img = project_service.get_scene_media_paths(PID, s.id)["image"]
        Image.new("RGB", (1280, 720), (30, 40, 50 + s.order)).save(img)
        s.image_path = str(img)
    project_service.save_project(project)
    return project


def _with_cast(approve=False) -> None:
    asyncio.run(story_cast.analyze_people(PID, llm=FakePeopleLLM()))
    if approve:
        sheet = cs.characters_dir(PID) / "duyet_ngoai_nv_1.jpg"
        Image.new("RGB", (1600, 900), (200, 200, 200)).save(sheet)
        cs.import_approved_sheet(PID, "nv_1", sheet)


def _scene(sid="scene_002"):
    project = project_service.get_project(PID)
    return project, next(s for s in project.scenes if s.id == sid)


def _real_image_prompt(monkeypatch, project, scene) -> str:
    """Chuỗi Muse nhận theo đường thật: payload như app.js generateSceneWithMuse → route tạo việc → Fleet Runner."""
    queued = []
    monkeypatch.setattr(mb, "enqueue_task", lambda task: queued.append(task) or task)
    monkeypatch.setattr(mb, "ensure_local_fleet_runner", lambda: None)
    prompt = spp.base_image_prompt(project, scene)
    app = FastAPI()
    app.include_router(mb.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        r = c.post("/api/muse-bridge/tasks/create", json={
            "project_id": PID, "scene_id": scene.id, "mode": "text-to-image", "prompt": prompt,
            "action_prompt": prompt, "negative_prompt": "", "input_image_url": None,
            "parameters": {"resolution": "2K", "aspect_ratio": "16:9", "style_preset": project.style_preset,
                           "duration_sec": 5, "fps": 25, "action_cues": prompt}})
        assert r.status_code == 200
    task = queued[0]
    return runner.MusePromptFormatter.build_prompt(task, has_attachment=bool(runner.task_attachments(task)))


# ------------------------------------------------------------------------------------------------------------- ảnh
def test_image_preview_equals_real_path_without_locks(isolated_projects_dir, monkeypatch):
    project = _project()
    project, scene = _scene()
    got = spp.image_preview(project, scene)
    assert got["prompt"] == _real_image_prompt(monkeypatch, project, scene)
    assert got["prompt"].startswith("tạo cho tôi 1 hình ảnh 2K tỉ lệ 16:9: ")
    assert image_service.STYLE_PRESETS["horror_cartoon_2d"]["prompt_suffix"] in got["prompt"]
    assert "an old samurai with a red cape" in got["prompt"]          # character_anchor chèn như app.js
    assert got["attachments"] == [] and got["locks"] == {"characters": [], "location": None}


def test_image_preview_equals_real_path_with_character_lock_and_board(isolated_projects_dir, monkeypatch):
    _project()
    _with_cast(approve=True)
    project, scene = _scene()
    got = spp.image_preview(project, scene)
    assert got["prompt"] == _real_image_prompt(monkeypatch, project, scene)
    assert "FIXED CHARACTERS in this scene" in got["prompt"] and "Lý Minh Hạ" in got["prompt"]
    assert "BẢNG NHÂN VẬT" in got["prompt"]                            # vai ảnh đính kèm do runner dặn
    assert got["attachments"][0]["role"] == "characters" and got["attachments"][0]["name"].startswith("board_")
    assert "Lý Minh Hạ" in got["locks"]["characters"]


def test_runner_still_builds_the_old_image_text():
    """Runner chỉ chuyển phần ghép chữ sang services/muse_prompt_format.py: chuỗi giữ nguyên từng chữ."""
    t = {"mode": "text-to-image", "prompt": " p ", "negative_prompt": "ng", "character_anchor": "anc",
         "attachments": ["b.jpg", "prev.jpg", "plate.jpg"],
         "parameters": {"aspect_ratio": "16:9", "style_preset": "st", "lighting": "li",
                        "attachment_roles": ["characters", "previous_scene", "location"]}}
    text = runner.MusePromptFormatter.build_prompt(t, has_attachment=True)
    assert text == muse_prompt_format.format_image_prompt(t, has_reference=True)
    assert text.startswith("tạo cho tôi 1 hình ảnh 2K tỉ lệ 16:9: Ảnh đính kèm đầu tiên là BẢNG NHÂN VẬT")
    assert text.endswith(", Character Anchor: anc, Style: st, Scene Details: p, Atmosphere: li, "
                         "16:9 widescreen cinematic, Avoid: ng")
    old = runner.MusePromptFormatter.build_prompt({"mode": "text-to-image", "prompt": "q",
                                                   "reference_image_path": "a.jpg",
                                                   "parameters": {"aspect_ratio": "9:16"}}, has_attachment=True)
    assert old == ("tạo cho tôi 1 hình ảnh 2K tỉ lệ 9:16: Giữ đúng gương mặt, trang phục và đặc điểm nhân vật "
                   "trong ảnh đính kèm (ảnh tham chiếu), Scene Details: q, 9:16")
    assert runner.task_attachments is muse_prompt_format.task_attachments


def test_prompt_format_module_imports_only_the_standard_library():
    """Runner chạy riêng nạp file này theo đường dẫn: không được import gói của app."""
    src = (BACKEND_DIR / "services" / "muse_prompt_format.py").read_text(encoding="utf-8")
    imports = [ln for ln in src.splitlines() if ln.startswith(("import ", "from "))]
    assert imports == ["from typing import Any, Dict, List"]


# ----------------------------------------------------------------------------------------------------------- video
def test_dialogue_preview_matches_scene_plan(isolated_projects_dir):
    _project()
    project, scene = _scene()
    got = spp.video_preview(project, scene)
    plan = dv.scene_plan(project, scene)
    assert got["climax"] is None                                       # cảnh không chọn làm video cao trào
    d = got["dialogue"]
    assert d["video_count"] == plan["video_count"] == len(d["segments"]) > 1
    assert d["estimated"] is True                                      # chưa có giọng: ước theo số chữ
    assert "chưa có giọng đọc" in d["blocked"]                         # nút Muse Video sẽ dừng như prepare_run
    for k, seg in enumerate(d["segments"], 1):
        assert seg["prompt"] == dv.segment_prompt(project, scene, plan["segments"], k, None, False)
        assert f"video {k}/{plan['video_count']}" in seg["prompt"]


def test_climax_scene_shows_both_buttons_and_the_scene_brief(isolated_projects_dir):
    """Nút "Muse Video" trên thẻ luôn gửi prompt theo lời thoại; nút cao trào gửi bản giao việc: tab hiện cả hai."""
    _project(scene_meta={"climax_video": {"status": "selected"}}, duration=12.0)
    _with_cast(approve=True)
    project, scene = _scene()
    got = spp.video_preview(project, scene)
    plan = dv.scene_plan(project, scene)
    assert [s["prompt"] for s in got["dialogue"]["segments"]] == [
        dv.segment_prompt(project, scene, plan["segments"], k, None, False) for k in range(1, plan["video_count"] + 1)]
    c = got["climax"]
    assert c["blocked"] is None and c["brief_kind"] == "cast" and c["needs_grid_first"] is True
    assert c["target_seconds"] == target_seconds(12.0) == 12
    people, _pos, _board = climax_video.cast_for(project, scene)
    assert c["prompt"] == scene_brief(project, scene, people, c["grid_count"], 12.0, spp.DONE_TOKEN_PLACEHOLDER)
    assert spp.DONE_TOKEN_PLACEHOLDER in c["prompt"]


def test_climax_brief_is_not_shown_when_the_real_path_would_refuse(isolated_projects_dir):
    _project(scene_meta={"climax_video": {"status": "selected"}}, duration=12.0)
    _with_cast(approve=False)                                          # bảng nhân vật chưa duyệt
    project, scene = _scene()
    with pytest.raises(climax_video.ClimaxVideoError) as real:
        climax_video.cast_for(project, scene)
    c = spp.video_preview(project, scene)["climax"]
    assert c["prompt"] is None and c["blocked"] == real.value.message and "chưa" in c["blocked"].lower()


def test_climax_approved_grid_that_no_longer_fits_is_blocked(isolated_projects_dir):
    _project(scene_meta={"climax_video": {"status": "grid_approved", "grid_approved": True, "grid_paths": []}},
             duration=12.0)
    _with_cast(approve=True)
    project, scene = _scene()
    c = spp.video_preview(project, scene)["climax"]
    assert c["prompt"] is None and "không khớp" in c["blocked"]


def test_climax_scene_without_people_returns_landscape_brief(isolated_projects_dir):
    _project(scene_meta={"climax_video": {"status": "selected"}}, duration=7.0)
    _with_cast()
    cs.set_scene_cast(PID, "scene_002", [])
    project, scene = _scene()
    c = spp.video_preview(project, scene)["climax"]
    assert c["brief_kind"] == "none" and c["needs_grid_first"] is False and c["blocked"] is None
    assert c["prompt"] == landscape_brief(project, scene, 7.0, spp.DONE_TOKEN_PLACEHOLDER, None, False)


def test_climax_scene_without_voice_is_blocked_with_the_real_message(isolated_projects_dir):
    _project(scene_meta={"climax_video": {"status": "selected"}})
    project, scene = _scene()
    c = spp.video_preview(project, scene)["climax"]
    assert c["prompt"] is None and "giọng đọc" in c["blocked"]


def test_old_private_names_still_point_at_the_public_helpers():
    assert climax_video._prepare is climax_video.prepare_scene
    assert climax_video._scene_state is climax_video.scene_state
    assert climax_video._cast_for is climax_video.cast_for


# ------------------------------------------------------------------------------------------------------------- API
@pytest.fixture
def client(isolated_projects_dir):
    app = FastAPI()
    app.include_router(spp_router.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c


def _files(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def test_api_returns_previews_and_writes_nothing_but_the_board_cache(client, isolated_projects_dir):
    _project()
    _with_cast(approve=True)
    project_json = (isolated_projects_dir / PID / "project.json").read_bytes()
    before = _files(isolated_projects_dir)
    base = f"/api/projects/{PID}/scenes/scene_002/muse-prompt"
    img = client.get(f"{base}?kind=image")
    vid = client.get(f"{base}?kind=video")
    assert img.status_code == 200 and img.json()["prompt"].startswith("tạo cho tôi 1 hình ảnh 2K")
    assert vid.status_code == 200 and vid.json()["dialogue"]["video_count"] >= 1
    added = _files(isolated_projects_dir) - before
    assert all(Path(p).name.startswith("board_") and Path(p).suffix == ".jpg" for p in added), added
    assert (isolated_projects_dir / PID / "project.json").read_bytes() == project_json
    json.dumps(img.json(), ensure_ascii=False)                          # trả về được dạng JSON


def test_api_errors(client):
    _project()
    base = f"/api/projects/{PID}/scenes"
    assert client.get(f"{base}/scene_999/muse-prompt?kind=image").status_code == 404
    assert client.get("/api/projects/proj_khong_co/scenes/scene_001/muse-prompt").status_code == 404
    assert client.get(f"{base}/scene_001/muse-prompt?kind=audio").status_code == 400
    assert client.get(f"{base}/bad..id/muse-prompt?kind=image").status_code in (400, 404)


def test_api_unreadable_project_is_409(client, isolated_projects_dir):
    _project()
    (isolated_projects_dir / PID / "project.json").write_text("{hỏng", encoding="utf-8")
    r = client.get(f"/api/projects/{PID}/scenes/scene_001/muse-prompt?kind=image")
    assert r.status_code == 409 and "không đọc được" in r.json()["detail"]
