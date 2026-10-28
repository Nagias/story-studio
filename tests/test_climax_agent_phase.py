"""Pha clip mới của video cao trào: một việc giao nhiều bước cho Muse mỗi cảnh (services/climax_video.run_scene_clips).

Muse giả (tests/test_climax_video.FakeMuse) trả video cuối + ảnh cảnh đã sửa tóc + ảnh góc sau. Offline, ffmpeg thật.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402
from routers import climax_video as climax_router  # noqa: E402
from services import climax_video as cv  # noqa: E402
from services import project_service  # noqa: E402
from tests.test_climax_video import (FakeMuse, _climax_project, _picture, _probe, _run_full,  # noqa: E402,F401
                                     _scene_now, client)


def _agent_tasks(muse):
    return [t for t in muse.tasks if t["mode"] == "agent-video"]


def test_agent_phase_sends_one_brief_and_marks_ready(isolated_projects_dir):
    project = _climax_project(duration=12.0)
    pid, sid = project.id, "scene_003"
    scene_img = project_service.get_scene_media_paths(pid, sid)["image"]
    original = scene_img.read_bytes()
    muse = FakeMuse(pid, sid)
    state = _run_full(pid, sid, muse)

    tasks = _agent_tasks(muse)
    assert len(tasks) == 1 and len(muse.tasks) == 2                       # 1 grid + 1 việc giao nhiều bước
    t = tasks[0]
    assert t["route_kind"] == "video" and t["raw_prompt"] is True
    assert Path(t["attachments"][0]).resolve() == scene_img.resolve()
    assert Path(t["attachments"][1]).name.startswith("board_")
    assert Path(t["attachments"][2]).name == f"{sid}_grid1_v1.jpg"
    assert t["agent"]["target_seconds"] == 12 and t["agent"]["wait_sec"] == config.MUSE_AGENT_WAIT_MIN * 60
    assert t["prompt"].rstrip().endswith(t["agent"]["done_token"]) and t["agent"]["done_token"].startswith("XONG-")
    assert t["thread_url"] and t["pin_account"] is True                   # cùng chat của cảnh (chat vẽ grid)
    assert "project_id" not in t and "scene_id" not in t

    assert state["status"] == "ready" and state["scene_image_updated"] is True
    assert "ANH_CANH_MOI" in state["muse_report"] and state["media_count"] == {"video": 3, "image": 2}
    scene = _scene_now(pid, sid)
    final = project_service.get_scene_media_paths(pid, sid)["motion_video"]
    assert Path(scene.motion_video_path) == final and final.is_file() and scene.media_view_mode == "video"
    assert abs(float(_probe(final)["format"]["duration"]) - 12.0) < 0.3
    backup = Path(state["backup_image"])
    assert backup.name == f"{sid}.truoc_sua_toc.jpg" and backup.read_bytes() == original
    assert scene_img.read_bytes() != original and Path(scene.image_path) == scene_img   # ảnh mới, giữ tên file


def test_choose_scene_image_ignores_back_view_and_wrong_ratio(tmp_path):
    old = _picture(tmp_path / "old.jpg", seed=7)
    similar = tmp_path / "fixed.jpg"
    Image.open(old).convert("RGB").point(lambda v: min(255, v + 10)).save(similar)
    back = _picture(tmp_path / "back.jpg", seed=4242)
    square = tmp_path / "square.jpg"
    Image.open(similar).resize((1080, 1080)).save(square)
    assert cv.choose_scene_image(old, [back, similar]) == similar
    assert cv.choose_scene_image(old, [back]) is None
    assert cv.choose_scene_image(old, [square]) is None
    assert cv.choose_scene_image(old, []) is None
    assert cv.SCENE_IMAGE_MIN_SIMILARITY == 0.45


def test_no_similar_extra_keeps_old_scene_image(isolated_projects_dir):
    project = _climax_project(duration=6.0)
    pid, sid = project.id, "scene_003"
    scene_img = project_service.get_scene_media_paths(pid, sid)["image"]
    original = scene_img.read_bytes()
    state = _run_full(pid, sid, FakeMuse(pid, sid, clip_plan=lambda n: "back_only"))
    assert state["status"] == "ready" and state["scene_image_updated"] is False and "backup_image" not in state
    assert scene_img.read_bytes() == original


def test_redo_twice_keeps_original_backup(isolated_projects_dir):
    project = _climax_project(duration=6.0)
    pid, sid = project.id, "scene_003"
    original = project_service.get_scene_media_paths(pid, sid)["image"].read_bytes()
    muse = FakeMuse(pid, sid)
    _run_full(pid, sid, muse)
    for _ in range(2):
        assert cv.redo_scene(pid, sid)["status"] == cv.GRID_APPROVED
        state = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
        assert state["status"] == "ready"
    assert Path(state["backup_image"]).read_bytes() == original
    agent = _agent_tasks(muse)
    assert len(agent) == 3 and "thread_url" not in agent[1] and "thread_url" not in agent[2]   # làm lại: chat mới


@pytest.mark.parametrize("plan, words", [
    (lambda n: "short", "giây"),
    (lambda n: "error", "timed out"),
    (lambda n: "no_media", "NO_FINAL"),
])
def test_failure_keeps_image_and_marks_chat_dirty(isolated_projects_dir, plan, words):
    project = _climax_project(duration=12.0)
    pid, sid = project.id, "scene_003"
    scene_img = project_service.get_scene_media_paths(pid, sid)["image"]
    original = scene_img.read_bytes()
    muse = FakeMuse(pid, sid, clip_plan=plan)
    state = _run_full(pid, sid, muse)
    assert state["status"] == "failed" and words in state["error"], state
    assert len(_agent_tasks(muse)) == 1                                    # không tự thử lại (tốn tới 6 video)
    assert "thread_url" not in state and state["grid_approved"] is True    # chat bẩn bỏ, grid giữ
    scene = _scene_now(pid, sid)
    assert scene.motion_video_path is None and scene.media_view_mode == "image"
    assert scene_img.read_bytes() == original
    asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
    assert "thread_url" not in _agent_tasks(muse)[1]                       # lần sau mở chat mới


def test_redo_rejects_scene_without_approved_grid(isolated_projects_dir):
    project = _climax_project(duration=6.0)
    with pytest.raises(cv.ClimaxVideoError):
        cv.redo_scene(project.id, "scene_003")


def test_api_redo_resets_state_and_409_while_running(client, monkeypatch):  # noqa: F811 (fixture dùng chung)
    project = _climax_project(duration=6.0)
    pid, sid = project.id, "scene_003"
    _run_full(pid, sid, FakeMuse(pid, sid))
    url = f"/api/projects/{pid}/climax-video/scenes/{sid}/redo"
    monkeypatch.setattr(climax_router, "_is_running", lambda project_id: True)
    assert client.post(url).status_code == 409
    monkeypatch.setattr(climax_router, "_is_running", lambda project_id: False)
    r = client.post(url)
    assert r.status_code == 200 and r.json()["status"] == cv.GRID_APPROVED
    state = _scene_now(pid, sid).metadata["climax_video"]
    assert state["thread_dirty"] is True and state["grid_approved"] is True
    assert client.post(f"/api/projects/{pid}/climax-video/scenes/scene_002/redo").status_code == 400
    st = client.get(f"/api/projects/{pid}/climax-video/status").json()["scenes"][0]
    assert st["scene_image_updated"] is True and "ANH_CANH_MOI" in st["muse_report"]


def _poster_of(video: Path, out: Path) -> Path:
    """Ảnh bìa như Muse: một khung của chính video cuối, cùng cỡ khung video."""
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", str(video), "-frames:v", "1", str(out)], check=True)
    return out


def test_video_poster_never_replaces_scene_image(isolated_projects_dir, tmp_path):
    """Giám khảo 28/10/2026: ảnh bìa video thật giống ảnh cảnh 0,68 (> 0,45) nên bị chọn thay ảnh cảnh."""
    from tests.test_climax_video import _clip_from_image
    project = _climax_project(duration=6.0)
    pid, sid = project.id, "scene_003"
    scene_img = project_service.get_scene_media_paths(pid, sid)["image"]
    video = _clip_from_image(scene_img, tmp_path / "final.mp4", seconds=6.0, darken=False, size="1248x704")
    poster = _poster_of(video, tmp_path / "poster.jpg")
    assert cv.choose_scene_image(scene_img, [poster], exclude_size=(1248, 704)) is None


def test_scene_image_replaced_only_when_muse_says_so(isolated_projects_dir):
    project = _climax_project(duration=6.0)
    pid, sid = project.id, "scene_003"
    scene_img = project_service.get_scene_media_paths(pid, sid)["image"]
    original = scene_img.read_bytes()
    muse = FakeMuse(pid, sid)
    real_agent = muse._agent

    def says_no(task, out, kind):
        r = real_agent(task, out, kind)
        r["muse_reply"] = "Ảnh 1 đã đúng tóc nên không vẽ lại. ANH_CANH_MOI: không. ĐẠT."
        return r
    muse._agent = says_no
    state = _run_full(pid, sid, muse)
    assert state["status"] == "ready" and state["scene_image_updated"] is False
    assert scene_img.read_bytes() == original
