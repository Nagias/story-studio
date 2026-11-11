"""Khoá cứng "khoảng 50% video là video Muse" (services/video_share.py, chủ dự án 11/11/2026).

Phải nhắc ít nhất 4 lần (29/10, 06/11, hai lần 10/11/2026): vụ Khang Cúc Hoa ra 32,9% không ai báo; vụ xưởng sắt báo
65,5% nhưng clip chỉ lia/zoom. Nay: dưới 45% thì cả hai đường dựng (nút "Sản xuất video dài" và nút Render cũ) không dựng
thành phẩm; chỉ tính clip có cử động hoặc đã duyệt tay; bản nháp ra file riêng; cảnh phong cảnh không người làm video
bằng bản giao việc riêng. Muse, dựng ffmpeg và thumbnail đều giả; dự án ghi vào thư mục tạm."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.schemas import Project, RenderRequest, Scene  # noqa: E402
from routers import api  # noqa: E402
from routers import video_share as share_router  # noqa: E402
from services import clip_motion, project_service, video_share  # noqa: E402
from services import climax_video as cv  # noqa: E402
from tests.test_climax_video import FakeMuse, _climax_project  # noqa: E402

PID = "proj_gate01"
MOVING, STILL = 6.0, 0.0


@pytest.fixture(autouse=True)
def _fake_motion(monkeypatch):
    """Clip tên chứa "dung_hinh" là clip gần như đứng hình, còn lại có cử động."""
    monkeypatch.setattr(clip_motion, "motion_score", lambda p: STILL if "dung_hinh" in Path(p).name else MOVING)
    monkeypatch.setattr(cv, "MUSE_PACE_SEC", 0)


def _project(seconds: list[float], clips: dict[int, str]) -> Project:
    """Cảnh i dài seconds[i] giây, có ảnh và giọng; cảnh trong `clips` dùng clip (tên file trong clips[i])."""
    project_service.ensure_project_dirs(PID)
    scenes = []
    for i, sec in enumerate(seconds, start=1):
        sid = f"scene_{i:03d}"
        media = project_service.get_scene_media_paths(PID, sid)
        Image.new("RGB", (640, 360), (30 * i % 255, 60, 90)).save(media["image"])
        media["audio"].write_bytes(b"giong")
        scene = Scene(id=sid, order=i, text=f"Lời kể {i}", duration=sec, image_path=str(media["image"]),
                      voice_audio_path=str(media["audio"]))
        if i in clips:
            clip = media["motion_video"].with_name(clips[i])
            clip.write_bytes(b"clip" * (10 + i))
            scene.motion_video_path = str(clip)
            scene.media_view_mode = "video"
        scenes.append(scene)
    project = Project(id=PID, name="Thử chốt", scenes=scenes)
    project_service.save_project(project)
    return project


def _share():
    return video_share.project_share(project_service.get_project(PID))


# ------------------------------------------------------------------------------------------------- cách tính, ngưỡng
@pytest.mark.parametrize("clip_sec, gate_ok", [(12.0, False), (17.6, False), (18.4, True), (20.0, True)])
def test_gate_blocks_below_45_percent(isolated_projects_dir, clip_sec, gate_ok):
    _project([clip_sec, 40.0 - clip_sec], {1: "scene_001_muse.mp4"})
    rep = _share()
    assert rep["gate_ok"] is gate_ok and rep["gate_percent"] == 45 and rep["target_percent"] == 50
    assert (video_share.gate_problem(rep) is None) is gate_ok
    if not gate_ok:
        with pytest.raises(video_share.VideoShareTooLow):
            video_share.require_gate(rep, draft=False)
        video_share.require_gate(rep, draft=True)   # bản nháp thì được dựng


def test_still_clip_counts_only_after_owner_review_of_that_exact_clip(isolated_projects_dir):
    _project([25.0, 15.0], {1: "scene_001_dung_hinh.mp4"})
    rep = _share()
    assert rep["video_seconds"] == 0 and rep["clip_seconds"] == 25.0 and rep["still_scenes"] == [1]
    assert "cảnh 1" in video_share.gate_problem(rep) and "Đã xem, có cử động" in video_share.gate_problem(rep)

    video_share.set_motion_review(PID, "scene_001", True)
    rep = _share()
    assert rep["video_seconds"] == 25.0 and rep["gate_ok"] is True and rep["reviewed_scenes"] == [1]

    clip = Path(project_service.get_project(PID).scenes[0].motion_video_path)
    clip.write_bytes(b"clip moi khac han" * 40)      # Muse làm lại clip: lần duyệt cũ hết hiệu lực
    rep = _share()
    assert rep["video_seconds"] == 0 and rep["still_scenes"] == [1]

    with pytest.raises(video_share.ReviewError):
        video_share.set_motion_review(PID, "scene_002", True)   # cảnh dựng từ ảnh: không có clip để duyệt


def test_unmeasurable_clip_is_not_counted(isolated_projects_dir, monkeypatch):
    def broken(_p):
        raise clip_motion.ClipMotionError("hỏng")
    monkeypatch.setattr(clip_motion, "motion_score", broken)
    _project([30.0, 10.0], {1: "scene_001_muse.mp4"})
    rep = _share()
    assert rep["video_seconds"] == 0 and rep["unmeasured_scenes"] == [1] and rep["gate_ok"] is False


# ---------------------------------------------------------------------------------------------- chặn ngay khi bấm
@pytest.fixture
def client(isolated_projects_dir):
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(share_router.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c


@pytest.mark.parametrize("path", ["render", "produce-long-video"])
def test_both_render_buttons_refuse_before_queueing(client, path):
    _project([12.0, 28.0], {1: "scene_001_muse.mp4"})          # 30%
    before = set(api.active_renders)
    r = client.post(f"/api/projects/{PID}/{path}", json={})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "VIDEO_SHARE_LOW" and "30,0%" in detail["message"] and detail["report"]["gate_ok"] is False
    assert set(api.active_renders) == before                    # chưa xếp việc dựng nào
    assert not any(project_service.get_render_media_paths(PID)["renders_dir"].glob("*.mp4"))


def test_video_share_endpoint_and_motion_review_endpoint(client):
    _project([25.0, 15.0], {1: "scene_001_dung_hinh.mp4"})
    r = client.get(f"/api/projects/{PID}/video-share")
    assert r.status_code == 200 and r.json()["gate_ok"] is False and r.json()["durations_known"] is True
    r = client.put(f"/api/projects/{PID}/scenes/scene_001/motion-review", json={"ok": True})
    assert r.status_code == 200 and r.json()["motion_review"]["ok"] is True
    assert client.get(f"/api/projects/{PID}/video-share").json()["gate_ok"] is True
    assert client.put(f"/api/projects/{PID}/scenes/scene_002/motion-review", json={"ok": True}).status_code == 400
    assert client.put(f"/api/projects/{PID}/scenes/scene_999/motion-review", json={"ok": True}).status_code == 404


def test_ui_autosave_keeps_owner_review():
    assert "motion_review" in api.SERVER_OWNED_METADATA_KEYS


# ------------------------------------------------------------------------------------ chốt cuối trong lúc dựng, bản nháp
@pytest.fixture
def fake_render(monkeypatch):
    calls = {"assemble": [], "thumbnail": 0}

    async def render_scene_video(image_path, audio_path, output_path, duration=None, **kw):
        Path(output_path).write_bytes(b"seg")
        return {"video_path": output_path, "duration": duration}

    async def assemble_full_video(scene_video_paths, scene_srt_infos, output_video_path, **kw):
        Path(output_video_path).write_bytes(b"video")
        calls["assemble"].append(output_video_path)
        return {"video_path": output_video_path, "duration": sum(i["duration"] for i in scene_srt_infos)}

    def thumbnail(project):
        calls["thumbnail"] += 1
        raise RuntimeError("không vẽ thumbnail trong test")

    monkeypatch.setattr(api, "render_scene_video", render_scene_video)
    monkeypatch.setattr(api, "assemble_full_video", assemble_full_video)
    monkeypatch.setattr(api, "generate_youtube_thumbnail", thumbnail)
    return calls


def _run_render(draft: bool) -> dict:
    rid = f"render_gate_{int(draft)}"
    api.active_renders[rid] = {"render_id": rid, "project_id": PID, "logs": [], "status": "queued"}
    asyncio.run(api.execute_full_render(PID, rid, RenderRequest(draft=draft)))
    return api.active_renders.pop(rid)


def test_render_in_progress_stops_below_45_percent(isolated_projects_dir, fake_render):
    _project([12.0, 28.0], {1: "scene_001_muse.mp4"})
    state = _run_render(draft=False)
    assert state["status"] == "failed" and state["error_code"] == "VIDEO_SHARE_LOW" and "45%" in state["error"]
    assert fake_render["assemble"] == [] and project_service.get_project(PID).final_video_path is None


def test_draft_goes_to_its_own_file_and_never_becomes_the_final_video(isolated_projects_dir, fake_render):
    _project([12.0, 28.0], {1: "scene_001_muse.mp4"})
    state = _run_render(draft=True)
    assert state["status"] == "completed"
    assert Path(fake_render["assemble"][0]).name == video_share.DRAFT_VIDEO_NAME
    assert any("BẢN NHÁP" in line for line in state["logs"]) and "BẢN NHÁP" in state["step_label"]
    assert not any("Thành Phẩm" in line for line in state["logs"])
    p = project_service.get_project(PID)
    assert p.final_video_path is None and p.final_video_url is None and fake_render["thumbnail"] == 0
    assert p.metadata["video_share_draft"]["percent"] == 30.0 and "video_share" not in p.metadata
    assert not project_service.get_render_media_paths(PID)["final_video"].exists()


def test_enough_video_renders_the_final_video(isolated_projects_dir, fake_render):
    _project([20.0, 20.0], {1: "scene_001_muse.mp4"})
    state = _run_render(draft=False)
    assert state["status"] == "completed" and Path(fake_render["assemble"][0]).name == "story_final.mp4"
    p = project_service.get_project(PID)
    assert p.final_video_path.endswith("story_final.mp4") and p.metadata["video_share"]["percent"] == 50.0


# ------------------------------------------------------------------------------------------- cảnh phong cảnh không người
def test_scene_without_people_gets_a_landscape_video_without_grid(isolated_projects_dir):
    project = _climax_project(duration=10.0, cast="none")
    pid, sid = project.id, "scene_003"
    assert cv.is_landscape(project_service.get_project(pid), next(
        s for s in project_service.get_project(pid).scenes if s.id == sid))
    muse = FakeMuse(pid, sid)
    state = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
    assert state["status"] == "ready" and state["landscape"] is True and state.get("grids", 0) == 0
    assert [t["mode"] for t in muse.tasks] == ["agent-video"]                 # không vẽ lưới 9 ô
    task = muse.tasks[0]
    assert "không có nhân vật" in task["prompt"] and "không lia, không zoom" in task["prompt"]
    assert "Không thêm người" in task["prompt"] and len(task["attachments"]) == 1
    assert "CẤM tự dựng clip" in task["prompt"]
    scene_img = project_service.get_scene_media_paths(pid, sid)["image"]
    assert Path(task["attachments"][0]).resolve() == scene_img.resolve()

    assert cv.redo_scene(pid, sid)["status"] == "selected"                    # làm lại: chat mới, vẫn là phong cảnh
    again = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
    assert again["status"] == "ready" and len(muse.tasks) == 2 and "thread_url" not in muse.tasks[1]


def test_project_without_any_character_list_is_not_treated_as_landscape(isolated_projects_dir):
    scene = Scene(id="scene_001", order=1, text="x", duration=5, metadata={"visual_kind": "image"})
    project = Project(id="proj_nocast01", name="Truyện chưa tìm nhân vật", scenes=[scene])
    project_service.ensure_project_dirs(project.id)
    project_service.save_project(project)
    assert cv.is_landscape(project, scene) is False


def test_real_photo_scenes_are_never_made_into_muse_video(isolated_projects_dir):
    """Vụ xưởng sắt có 8 ảnh thật không có người vẽ: không có dấu real_photo thì bị chọn làm video phong cảnh."""
    project = _climax_project(duration=10.0, cast="none")
    pid = project.id
    p = project_service.get_project(pid)
    for s in p.scenes:
        if s.id == "scene_002":
            s.metadata[cv.REAL_PHOTO_KEY] = True
    project_service.save_project(p)
    p = project_service.get_project(pid)
    photo = next(s for s in p.scenes if s.id == "scene_002")
    assert not cv.is_eligible(photo) and not cv.is_landscape(p, photo)
    assert "scene_002" not in cv.pick_climax_scenes(p)
    assert "real_photo" in api.SERVER_OWNED_METADATA_KEYS
