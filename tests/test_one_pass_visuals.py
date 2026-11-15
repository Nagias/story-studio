"""Nút "Tạo hình cho cả dự án" (services/one_pass_visuals.py, routers/one_pass_visuals.py): cảnh thường ra ảnh, cảnh
cao trào ra video trong một lượt; lưới vẽ xong tự duyệt (grid_approved_by "auto") rồi làm clip ngay.

Offline: ảnh cảnh qua route thật của nút trên thẻ nhưng `generate_image` giả; Muse giả của tests/test_climax_video.py.
"""
import asyncio
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers import api as api_module  # noqa: E402
from routers import climax_video as climax_router  # noqa: E402
from routers import one_pass_visuals as op_router  # noqa: E402
from services import climax_video as cv  # noqa: E402
from services import one_pass_visuals as op  # noqa: E402
from services import project_service  # noqa: E402
from tests.test_climax_video import FakeMuse, _save_project, _scene, _scene_now  # noqa: E402

PID = "proj_crime_onepass"


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch):
    monkeypatch.setattr(cv, "MUSE_PACE_SEC", 0)
    monkeypatch.setattr(op, "PACE_SEC", 0)
    yield
    op._jobs.clear()
    op._starting.clear()


def _drop_image(pid: str, sid: str) -> None:
    project_service.get_scene_media_paths(pid, sid)["image"].unlink()
    p = project_service.get_project(pid)
    for s in p.scenes:
        if s.id == sid:
            s.image_path, s.image_url = None, None
    project_service.save_project(p)


def _select(pid: str, *sids: str) -> None:
    p = project_service.get_project(pid)
    for s in p.scenes:
        if s.id in sids:
            s.metadata = {**s.metadata, "climax_video": {"status": "selected", "picked_by": "manual"}}
    project_service.save_project(p)


def _project(cast: str = "approved"):
    """002, 006 thường thiếu ảnh; 003 cao trào đủ điều kiện (4 giây: 1 lưới); 004 cao trào chưa có giọng; 005 có ảnh."""
    scenes = [_scene("scene_001", kind="disclaimer"), _scene("scene_002"), _scene("scene_003", duration=4.0),
              _scene("scene_004", duration=None), _scene("scene_005"), _scene("scene_006")]
    _save_project(scenes, pid=PID, cast=cast)
    _drop_image(PID, "scene_002")
    _drop_image(PID, "scene_006")
    _select(PID, "scene_003", "scene_004")


class FakeImages:
    """generate_image giả: vẽ file ở output_path, ghi lại tham số (để kiểm khoá hình); `fail`/`fallback` theo cảnh."""

    def __init__(self, fail=(), fallback=()):
        self.calls: list[dict] = []
        self.fail, self.fallback = set(fail), set(fallback)

    async def __call__(self, **kw):
        self.calls.append(kw)
        out = Path(kw["output_path"])
        if out.stem in self.fail:
            return {"success": False, "error": "Muse quá tải (503)"}
        Image.new("RGB", (320, 180), (90, 90, 90)).save(out, "JPEG")
        if out.stem in self.fallback:
            return {"success": True, "image_path": str(out), "provider": "9router_gemini",
                    "fallback_reason": "Muse: Không có tài khoản Muse ảnh nào online"}
        return {"success": True, "image_path": str(out), "provider": "meta_muse_cloud", "fallback_reason": None}


@pytest.fixture
def client(isolated_projects_dir, monkeypatch):
    monkeypatch.setattr(api_module, "PROJECTS_DIR", isolated_projects_dir)
    app = FastAPI()
    app.include_router(op_router.router)
    app.include_router(climax_router.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c
    climax_router._running.clear()


def _wait(client, seconds=120) -> dict:
    deadline = time.time() + seconds
    while time.time() < deadline:
        s = client.get(f"/api/projects/{PID}/one-pass/status").json()
        if not s["running"]:
            return s
        time.sleep(0.1)
    raise AssertionError("lượt Tạo hình cho cả dự án chạy quá lâu")


# ---------------------------------------------------------------------------------------------------------- kế hoạch
def test_plan_counts_images_videos_turns_and_missing(client):
    _project()
    plan = client.get(f"/api/projects/{PID}/one-pass/plan").json()
    assert plan["image_scene_ids"] == ["scene_002", "scene_006"] and plan["images_normal"] == 2
    assert plan["images_climax"] == 0 and plan["climax_total"] == 2
    assert plan["climax_scene_ids"] == ["scene_003"] and plan["climax_videos"] == 1
    assert plan["grid_turns"] == 1 and plan["muse_turns"] == 2 + 1 + 1      # 2 ảnh + 1 lưới + 1 việc agent-video
    [miss] = plan["missing"]
    assert miss["scene_id"] == "scene_004" and "giọng" in miss["reason"] and miss["page"] == "script"
    assert plan["running"] is False
    assert not (Path(project_service.get_scene_media_paths(PID, "scene_002")["image"])).exists()   # không tốn gì


def test_plan_reports_unapproved_cast_with_look_page(client):
    _project(cast="draft")
    plan = client.get(f"/api/projects/{PID}/one-pass/plan").json()
    by_id = {m["scene_id"]: m for m in plan["missing"]}
    assert by_id["scene_003"]["page"] == "look" and "Thẩm Nhã Uyên" in by_id["scene_003"]["reason"]
    assert plan["climax_videos"] == 0 and plan["muse_turns"] == 2


def test_plan_counts_image_for_climax_scene_and_skips_grid_already_drawn(client):
    _project()
    _drop_image(PID, "scene_003")
    plan = client.get(f"/api/projects/{PID}/one-pass/plan").json()
    assert plan["images_climax"] == 1 and plan["muse_turns"] == 3 + 1 + 1
    p = project_service.get_project(PID)
    for s in p.scenes:
        if s.id == "scene_003":
            s.metadata["climax_video"] = {"status": "grid_review", "grid_paths": ["x.jpg"]}
    project_service.save_project(p)
    assert client.get(f"/api/projects/{PID}/one-pass/plan").json()["grid_turns"] == 0


# ------------------------------------------------------------------------------------------------------------ chạy
def test_run_draws_images_then_grid_auto_approve_clip(client, monkeypatch):
    _project()
    images = FakeImages(fallback={"scene_006"})
    muse = FakeMuse(PID, "scene_003")
    monkeypatch.setattr(api_module, "generate_image", images)
    monkeypatch.setattr(climax_router, "enqueue_and_wait_muse_task", muse)

    r = client.post(f"/api/projects/{PID}/one-pass/run")
    assert r.status_code == 200, r.text
    s = _wait(client)

    assert s["images_done"] == ["scene_002", "scene_006"] and s["videos_done"] == ["scene_003"]
    assert s["failed"] == [] and (s["done"], s["total"]) == (3, 3) and s["phase"] is None
    # ảnh cảnh qua khoá hình (CLAUDE.md đường cấm 16), nguồn Muse
    assert all({"characters", "location"} <= set(kw) for kw in images.calls)
    assert all(kw["provider"] == "meta_muse_cloud" for kw in images.calls)
    assert images.calls[0]["characters"]["names"] == ["Thẩm Nhã Uyên"]
    # đường ảnh tự rơi sang 9router: giữ, nhưng lý do có trong kết quả
    assert s["fallbacks"] == [{"scene_id": "scene_006", "label": "Cảnh 6", "provider": "9router_gemini",
                               "reason": "Muse: Không có tài khoản Muse ảnh nào online"}]
    # cảnh cao trào: lưới rồi clip ngay, không dừng chờ duyệt
    assert [t["mode"] for t in muse.tasks] == ["text-to-image", "agent-video"]
    state = cv.scene_state(_scene_now(PID, "scene_003"))
    assert state["status"] == "ready" and state["grid_approved"] is True and state["grid_approved_by"] == "auto"
    assert muse.tasks[1]["thread_url"]                                            # cùng side chat với lưới
    # cảnh thiếu giọng: bỏ qua có lý do, không gọi Muse cho nó
    [skip] = [x for x in s["skipped"] if x["scene_id"] == "scene_004"]
    assert skip["step"] == "climax" and "giọng" in skip["reason"]
    assert cv.scene_state(_scene_now(PID, "scene_004"))["status"] == "selected"
    assert _scene_now(PID, "scene_002").status_image == "ready"


def test_one_failing_scene_does_not_stop_the_run(client, monkeypatch):
    _project()
    monkeypatch.setattr(api_module, "generate_image", FakeImages(fail={"scene_002"}))
    monkeypatch.setattr(climax_router, "enqueue_and_wait_muse_task",
                        FakeMuse(PID, "scene_003", clip_plan=lambda n: "error"))
    assert client.post(f"/api/projects/{PID}/one-pass/run").status_code == 200
    s = _wait(client)
    failed = {(f["scene_id"], f["step"]): f["error"] for f in s["failed"]}
    assert "503" in failed[("scene_002", "image")] and "timed out" in failed[("scene_003", "climax")]
    assert s["images_done"] == ["scene_006"] and s["videos_done"] == [] and s["done"] == 3
    assert cv.scene_state(_scene_now(PID, "scene_003"))["status"] == "failed"


def test_auto_approve_picks_up_grid_waiting_for_review(isolated_projects_dir):
    _project()
    muse = FakeMuse(PID, "scene_003")
    state = asyncio.run(cv.run_scene_climax_video(PID, "scene_003", muse_call=muse))      # cách cũ: dừng chờ duyệt
    assert state["status"] == cv.GRID_REVIEW
    state = asyncio.run(cv.run_scene_climax_video(PID, "scene_003", muse_call=muse, auto_approve_grid=True))
    assert state["status"] == "ready" and state["grid_approved_by"] == "auto"
    assert [t["mode"] for t in muse.tasks] == ["text-to-image", "agent-video"]          # không vẽ lại lưới


def test_manual_approve_is_recorded_as_manual(isolated_projects_dir):
    _project()
    asyncio.run(cv.run_scene_climax_video(PID, "scene_003", muse_call=FakeMuse(PID, "scene_003")))
    assert cv.approve_grid(PID, "scene_003")["grid_approved_by"] == "manual"
    assert "grid_approved_by" not in cv.reject_grid(PID, "scene_003", "tóc sai")


def test_stop_after_current_step(isolated_projects_dir):
    _project()

    async def scenario():
        opened = asyncio.Event()
        calls = []

        async def draw(sid):
            calls.append(sid)
            await opened.wait()
            return {"error": None}

        async def climax(sid):
            calls.append(sid)
            return {"status": "ready"}

        project = project_service.get_project(PID)
        job = op.start(PID, op.plan(project), project, draw, climax)
        while not calls:
            await asyncio.sleep(0.01)
        assert op.request_stop(PID)["stop_requested"] is True
        opened.set()
        await job.task
        return calls, op.status(PID)

    calls, s = asyncio.run(scenario())
    assert calls == ["scene_002"]                                                # dừng sau ảnh đang vẽ
    assert s["stopped"] is True and s["running"] is False and s["images_done"] == ["scene_002"]


def test_409_while_running_and_while_climax_flow_busy(client, monkeypatch):
    _project()
    opened = {"go": False}

    async def slow_images(**kw):
        while not opened["go"]:
            await asyncio.sleep(0.05)
        return await FakeImages()(**kw)

    monkeypatch.setattr(api_module, "generate_image", slow_images)
    monkeypatch.setattr(climax_router, "enqueue_and_wait_muse_task", FakeMuse(PID, "scene_003"))
    base = f"/api/projects/{PID}"
    assert client.post(f"{base}/one-pass/run").status_code == 200
    assert client.post(f"{base}/one-pass/run").status_code == 409
    # luồng cao trào cũ không chạy chen khi đang tạo hình cho cả dự án
    assert client.post(f"{base}/climax-video/pick?mode=score").status_code == 409
    assert client.post(f"{base}/climax-video/run").status_code == 409
    assert client.put(f"{base}/climax-video/scenes/scene_005", json={"enabled": True}).status_code == 409
    assert client.get(f"{base}/climax-video/status").json()["one_pass_running"] is True
    opened["go"] = True
    _wait(client)

    # và ngược lại: luồng cao trào đang bắt đầu / đang chọn cảnh thì 409
    climax_router._starting.add(PID)
    try:
        assert client.post(f"{base}/one-pass/run").status_code == 409
    finally:
        climax_router._starting.discard(PID)


def test_run_refuses_when_nothing_to_do_and_bad_ids(client):
    _project(cast="draft")
    p = project_service.get_project(PID)
    p.scenes = [s for s in p.scenes if s.id not in ("scene_002", "scene_006")]
    project_service.save_project(p)
    r = client.post(f"/api/projects/{PID}/one-pass/run")
    assert r.status_code == 400 and "thiếu điều kiện" in r.json()["detail"]
    assert client.get("/api/projects/proj_khong_co/one-pass/plan").status_code == 404
    assert client.get("/api/projects/bad.id/one-pass/plan").status_code in (400, 404)
    assert client.get(f"/api/projects/{PID}/one-pass/status").json()["running"] is False
