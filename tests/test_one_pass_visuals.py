"""Nút "Tạo hình cho cả dự án" (services/one_pass_visuals.py, routers/one_pass_visuals.py): cảnh thường ra ảnh, cảnh
cao trào ra video trong một lượt; lưới vẽ xong tự duyệt (grid_approved_by "auto") rồi làm clip ngay.

Offline: ảnh cảnh là việc "Muse 2K" thật của thẻ (scene_prompt_preview.image_task) nhưng Muse giả; video cao trào dùng
Muse giả của tests/test_climax_video.py. Cả hai đi qua `climax_router.enqueue_and_wait_muse_task` (hàng việc Muse).
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

from routers import climax_video as climax_router  # noqa: E402
from routers import one_pass_visuals as op_router  # noqa: E402
from services import climax_video as cv  # noqa: E402
from services import one_pass_visuals as op  # noqa: E402
from services import project_service  # noqa: E402
from services import scene_prompt_preview as spp  # noqa: E402
from services.muse_prompt_format import format_image_prompt, task_attachments  # noqa: E402
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


class FakeFleet:
    """Hàng việc Muse giả: việc ảnh cảnh (tài khoản ảnh, có project_id/scene_id) vẽ file ở output_path như
    muse_bridge.complete_task (không gắn vào cảnh: one_pass tự gắn); việc của tài khoản video chuyển cho FakeMuse.
    `fail`: {scene_id: lỗi ném ra}."""

    def __init__(self, video: FakeMuse, fail=None, gate=None):
        self.video, self.fail, self.gate = video, dict(fail or {}), gate
        self.images: list[dict] = []

    async def __call__(self, task: dict) -> dict:
        if task.get("route_kind") == "video" or task.get("mode") == "agent-video":
            return await self.video(task)
        self.images.append(dict(task))
        if self.gate is not None:
            while not self.gate["go"]:
                await asyncio.sleep(0.05)
        if task["scene_id"] in self.fail:
            raise RuntimeError(self.fail[task["scene_id"]])
        out = Path(task["output_path"])
        Image.new("RGB", (320, 180), (90, 90, 90)).save(out, "JPEG")
        return {"output_path": str(out), "status": "completed", "provider": "meta_muse_cloud"}


@pytest.fixture
def client(isolated_projects_dir):
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
    [group] = plan["missing_groups"]
    assert group["scene_ids"] == ["scene_004"] and group["numbers"] == [4] and group["page"] == "script"
    assert plan["grids_pending_review"] == [] and plan["running"] is False
    assert not (Path(project_service.get_scene_media_paths(PID, "scene_002")["image"])).exists()   # không tốn gì


def test_plan_reports_unapproved_cast_with_look_page(client):
    _project(cast="draft")
    plan = client.get(f"/api/projects/{PID}/one-pass/plan").json()
    by_id = {m["scene_id"]: m for m in plan["missing"]}
    assert by_id["scene_003"]["page"] == "look" and "Thẩm Nhã Uyên" in by_id["scene_003"]["reason"]
    assert plan["climax_videos"] == 0 and plan["muse_turns"] == 2
    look = [g for g in plan["missing_groups"] if g["page"] == "look"]
    assert len(look) == 1 and look[0]["numbers"] == [3]                         # một dòng mỗi lý do, kèm số cảnh


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
    plan = client.get(f"/api/projects/{PID}/one-pass/plan").json()
    assert plan["grid_turns"] == 0
    assert plan["grids_pending_review"] == [{"scene_id": "scene_003", "label": "Cảnh 3"}]   # nêu tên: sẽ tự duyệt


# ------------------------------------------------------------------------------------------------------------ chạy
def test_run_draws_images_then_grid_auto_approve_clip(client, monkeypatch):
    _project()
    muse = FakeMuse(PID, "scene_003")
    fleet = FakeFleet(muse)
    monkeypatch.setattr(climax_router, "enqueue_and_wait_muse_task", fleet)
    project = project_service.get_project(PID)
    expected = {sid: spp.image_preview(project, next(x for x in project.scenes if x.id == sid))["prompt"]
                for sid in ("scene_002", "scene_006")}

    r = client.post(f"/api/projects/{PID}/one-pass/run")
    assert r.status_code == 200, r.text
    s = _wait(client)

    assert s["images_done"] == ["scene_002", "scene_006"] and s["videos_done"] == ["scene_003"]
    assert s["failed"] == [] and (s["done"], s["total"]) == (3, 3) and s["phase"] is None
    # ảnh cảnh: đúng việc "Muse 2K" của thẻ, đúng chuỗi khối "Prompt đầy đủ gửi Muse" hiện (qua khoá hình, đường cấm 16)
    assert [t["scene_id"] for t in fleet.images] == ["scene_002", "scene_006"]
    for t in fleet.images:
        assert t["project_id"] == PID and t["mode"] == "text-to-image" and "route_kind" not in t
        assert format_image_prompt(t, has_reference=bool(task_attachments(t))) == expected[t["scene_id"]]
        assert t["parameters"]["character_ids"] == ["person_1"]                  # khoá nhân vật đã áp
        assert t["parameters"]["style_preset"] == "horror_cartoon_2d"
    assert "fallbacks" not in s                                                   # đường này chỉ có Muse
    scene2 = _scene_now(PID, "scene_002")
    assert Path(scene2.image_path).is_file() and scene2.image_url.endswith("/images/scene_002.jpg")
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
    fleet = FakeFleet(FakeMuse(PID, "scene_003", clip_plan=lambda n: "error"),
                      fail={"scene_002": "Muse task failed: MUSE_REPLIED_ERROR quá tải (503)"})
    monkeypatch.setattr(climax_router, "enqueue_and_wait_muse_task", fleet)
    assert client.post(f"/api/projects/{PID}/one-pass/run").status_code == 200
    s = _wait(client)
    failed = {(f["scene_id"], f["step"]): f["error"] for f in s["failed"]}
    assert "503" in failed[("scene_002", "image")] and "timed out" in failed[("scene_003", "climax")]
    assert s["images_done"] == ["scene_006"] and s["videos_done"] == [] and s["done"] == 3
    assert cv.scene_state(_scene_now(PID, "scene_003"))["status"] == "failed"


def test_no_image_account_stops_image_phase_with_reason(client, monkeypatch):
    _project()
    fleet = FakeFleet(FakeMuse(PID, "scene_003"),
                      fail={"scene_002": "Không có tài khoản Muse ảnh nào đang online (Fleet Runner chưa chạy)"})
    monkeypatch.setattr(climax_router, "enqueue_and_wait_muse_task", fleet)
    assert client.post(f"/api/projects/{PID}/one-pass/run").status_code == 200
    s = _wait(client)
    assert [t["scene_id"] for t in fleet.images] == ["scene_002"]                # không thử ảnh sau
    [skip] = [x for x in s["skipped"] if x["scene_id"] == "scene_006"]
    assert skip["step"] == "image" and "tài khoản Muse ảnh" in skip["reason"]
    assert s["videos_done"] == ["scene_003"]                                     # video dùng tài khoản video: vẫn làm


def test_muse_reply_without_file_is_an_error(isolated_projects_dir):
    _project()

    async def no_file(task):
        return {"output_path": str(Path(task["output_path"]).with_name("khong_co.jpg"))}

    assert "không có file ảnh" in asyncio.run(op.draw_scene_image(PID, "scene_002", no_file))["error"]
    assert _scene_now(PID, "scene_002").image_path is None


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
    monkeypatch.setattr(climax_router, "enqueue_and_wait_muse_task", FakeFleet(FakeMuse(PID, "scene_003"), gate=opened))
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
