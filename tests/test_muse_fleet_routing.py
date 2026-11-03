"""
Kiểm thử định tuyến Muse Fleet (không mở trình duyệt, không đụng tài khoản thật):
- Task ảnh chỉ đến tài khoản image, task video chỉ đến tài khoản video (gán, poll, retry, failover).
- Task gán cho tài khoản bận/offline được tài khoản rảnh CÙNG LOẠI nhận thay.
- Backend từ chối media sai loại; kết quả về muộn sau timeout không ghi đè dự án.
"""
import asyncio
import io
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402
import routers.muse_bridge as mb  # noqa: E402

IMG_CAPS = ["text-to-image", "image-upscale-2k"]
VID_CAPS = ["image-to-video", "text-to-video"]
FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048


def jpeg_bytes(w=1920, h=1080) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (40, 60, 90)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def fleet(monkeypatch, tmp_path):
    accounts = [
        {"account_id": "muse_acc_img_01", "label": "Img 1", "type": "image", "capabilities": IMG_CAPS,
         "profile_dir": "chrome_profiles/muse_acc_img_01", "is_active_for_image": True, "is_active_for_video": False},
        {"account_id": "muse_acc_img_02", "label": "Img 2", "type": "image", "capabilities": IMG_CAPS,
         "profile_dir": "chrome_profiles/muse_acc_img_02", "is_active_for_image": False, "is_active_for_video": False},
        {"account_id": "muse_acc_vid_01", "label": "Vid 1", "type": "video", "capabilities": VID_CAPS,
         "profile_dir": "chrome_profiles/muse_acc_vid_01", "is_active_for_image": False, "is_active_for_video": True},
        {"account_id": "muse_acc_vid_02", "label": "Vid 2", "type": "video", "capabilities": VID_CAPS,
         "profile_dir": "chrome_profiles/muse_acc_vid_02", "is_active_for_image": False, "is_active_for_video": False},
    ]
    installed = {"muse_acc_img_01", "muse_acc_img_02", "muse_acc_vid_01", "muse_acc_vid_02"}
    outputs = tmp_path / "muse_outputs"
    outputs.mkdir()

    monkeypatch.setattr(mb, "muse_accounts", accounts)
    monkeypatch.setattr(mb, "MUSE_FLEET_ACCOUNTS_FILE", tmp_path / "muse_fleet_accounts.json")
    monkeypatch.setattr(mb, "MUSE_OUTPUTS_DIR", outputs)
    monkeypatch.setattr(mb, "is_account_profile_installed", lambda acc: acc.get("account_id") in installed)
    monkeypatch.setattr(mb, "ensure_local_fleet_runner", lambda: None)

    saved = (list(mb.pending_tasks), dict(mb.active_tasks), list(mb.task_history), dict(mb.account_workers))
    mb.pending_tasks.clear()
    mb.active_tasks.clear()
    mb.task_history.clear()
    mb.account_workers.clear()

    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    yield {"client": client, "accounts": accounts, "installed": installed, "outputs": outputs}

    mb.pending_tasks[:] = saved[0]
    mb.active_tasks.clear()
    mb.active_tasks.update(saved[1])
    mb.task_history[:] = saved[2]
    mb.account_workers.clear()
    mb.account_workers.update(saved[3])


def online(*account_ids):
    for aid in account_ids:
        mb._touch_worker(f"w_{aid}", aid)


def poll(client, account_id):
    r = client.get(f"/api/muse-bridge/tasks/poll?account_id={account_id}&timeout=1")
    assert r.status_code == 200
    return r.json()


# ---------------- Gán tài khoản ----------------
def test_assign_routes_by_kind_only(fleet):
    assert mb.assign_task_account({"mode": "text-to-image"})["assigned_account"] == "muse_acc_img_01"
    assert mb.assign_task_account({"mode": "image-to-video"})["assigned_account"] == "muse_acc_vid_01"
    assert mb.assign_task_account({"mode": "text-to-video"})["assigned_account"] == "muse_acc_vid_01"
    # Yêu cầu sai loại -> bị đưa về tài khoản đúng loại
    assert mb.assign_task_account({"mode": "text-to-image", "assigned_account": "muse_acc_vid_02"})["assigned_account"] == "muse_acc_img_01"
    assert mb.assign_task_account({"mode": "image-to-video", "assigned_account": "muse_acc_img_02"})["assigned_account"] == "muse_acc_vid_01"
    # ID trạm VM cũ -> tài khoản active đúng loại của task
    assert mb.assign_task_account({"mode": "image-to-video", "assigned_account": "muse_acc_image"})["assigned_account"] == "muse_acc_vid_01"
    assert mb.assign_task_account({"mode": "text-to-image", "assigned_account": "muse_acc_video"})["assigned_account"] == "muse_acc_img_01"
    # Yêu cầu đúng loại và dùng được -> giữ nguyên
    assert mb.assign_task_account({"mode": "text-to-image", "assigned_account": "muse_acc_img_02"})["assigned_account"] == "muse_acc_img_02"


def test_assign_skips_accounts_without_login(fleet):
    fleet["installed"].discard("muse_acc_img_01")
    fleet["installed"].discard("muse_acc_img_02")
    task = mb.assign_task_account({"mode": "text-to-image", "assigned_account": "muse_acc_img_02"})
    # Không còn tài khoản ảnh đăng nhập -> vẫn gán tài khoản ẢNH (chờ), tuyệt đối không gán tài khoản video
    assert task["assigned_account"] in ("muse_acc_img_01", "muse_acc_img_02")
    assert mb.account_kind(mb.find_account(task["assigned_account"])) == "image"


def test_accounts_have_no_vm_aliases(fleet):
    ids = {a["account_id"] for a in mb.get_enriched_accounts()}
    assert not ids & mb.LEGACY_ALIAS_ACCOUNTS
    assert all(a["kind"] in ("image", "video") for a in mb.get_enriched_accounts())


# ---------------- Poll ----------------
def test_poll_never_crosses_kind(fleet):
    c = fleet["client"]
    online("muse_acc_img_02", "muse_acc_vid_02")
    v1 = mb.enqueue_task({"mode": "image-to-video", "prompt": "v1"})
    v2 = mb.enqueue_task({"mode": "image-to-video", "prompt": "v2"})
    i1 = mb.enqueue_task({"mode": "text-to-image", "prompt": "i1"})

    # Tài khoản ảnh chỉ được nhận task ảnh (dù task video xếp trước)
    got = poll(c, "muse_acc_img_02")["task"]
    assert got["task_id"] == i1["task_id"] and got["assigned_account"] == "muse_acc_img_02"

    # Tài khoản video nhận task video (vid_01 được gán nhưng offline -> vid_02 nhận thay)
    got = poll(c, "muse_acc_vid_02")["task"]
    assert got["task_id"] == v1["task_id"] and got["assigned_account"] == "muse_acc_vid_02"

    # Chỉ còn task video -> tài khoản ảnh không nhận gì
    assert poll(c, "muse_acc_img_02")["task"] is None
    got = poll(c, "muse_acc_vid_01")["task"]
    assert got["task_id"] == v2["task_id"]


def test_poll_waits_for_online_owner_then_reassigns(fleet):
    c = fleet["client"]
    online("muse_acc_img_01", "muse_acc_img_02")
    t = mb.enqueue_task({"mode": "text-to-image", "prompt": "owner online"})
    assert t["assigned_account"] == "muse_acc_img_01"
    # Chủ task đang online và task mới xếp hàng -> tài khoản khác không giành
    assert poll(c, "muse_acc_img_02")["task"] is None
    # Chờ quá REASSIGN_AFTER_SEC (chủ bận) -> tài khoản ảnh khác nhận thay
    mb.pending_tasks[0]["queued_at"] = time.time() - mb.REASSIGN_AFTER_SEC - 1
    got = poll(c, "muse_acc_img_02")["task"]
    assert got["task_id"] == t["task_id"] and got["assigned_account"] == "muse_acc_img_02"


def test_poll_requires_account_and_rejects_unknown(fleet):
    c = fleet["client"]
    assert c.get("/api/muse-bridge/tasks/poll?timeout=1").status_code == 400
    mb.enqueue_task({"mode": "text-to-image", "prompt": "x"})
    assert poll(c, "muse_acc_img_99")["task"] is None
    assert poll(c, "muse_acc_image")["task"] is None  # ID VM cũ không còn là tài khoản


# ---------------- Hoàn thành ----------------
def _activate(task):
    mb.pending_tasks.remove(task)
    task["status"] = "processing"
    mb.active_tasks[task["task_id"]] = task


def test_complete_rejects_wrong_media_kind(fleet):
    c = fleet["client"]
    vt = mb.enqueue_task({"mode": "image-to-video", "prompt": "v"})
    it = mb.enqueue_task({"mode": "text-to-image", "prompt": "i"})
    _activate(vt)
    _activate(it)

    r = c.post(f"/api/muse-bridge/tasks/{vt['task_id']}/complete", files={"file": ("x.mp4", jpeg_bytes(), "video/mp4")})
    assert r.status_code == 422 and vt["task_id"] in mb.active_tasks
    r = c.post(f"/api/muse-bridge/tasks/{it['task_id']}/complete", files={"file": ("x.jpg", FAKE_MP4, "image/jpeg")})
    assert r.status_code == 422 and it["task_id"] in mb.active_tasks

    r = c.post(f"/api/muse-bridge/tasks/{vt['task_id']}/complete", files={"file": ("x.mp4", FAKE_MP4, "video/mp4")})
    assert r.status_code == 200
    assert Path(r.json()["output_path"]).suffix == ".mp4"
    r = c.post(f"/api/muse-bridge/tasks/{it['task_id']}/complete", files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 200
    assert Path(r.json()["output_path"]).suffix == ".jpg"
    assert not mb.active_tasks


def test_late_result_after_timeout_goes_to_gallery_only(fleet):
    c = fleet["client"]
    t = mb.enqueue_task({"mode": "text-to-image", "prompt": "late", "project_id": "proj_does_not_matter", "scene_id": "scene_001"})
    _activate(t)
    mb.abandon_task(t["task_id"], "Caller timed out after 240s")
    r = c.post(f"/api/muse-bridge/tasks/{t['task_id']}/complete", files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 200 and r.json()["abandoned"] is True
    out = Path(r.json()["output_path"])
    assert out.parent == fleet["outputs"].resolve() and out.name == f"{t['task_id']}.jpg"


# ---------------- Lỗi / retry / failover ----------------
def test_quota_error_blocks_account_and_retries_same_kind(fleet):
    c = fleet["client"]
    online("muse_acc_vid_01", "muse_acc_vid_02", "muse_acc_img_01")
    t = mb.enqueue_task({"mode": "image-to-video", "prompt": "q"})
    got = poll(c, "muse_acc_vid_01")["task"]
    assert got["task_id"] == t["task_id"]

    r = c.post(f"/api/muse-bridge/tasks/{t['task_id']}/fail", json={"task_id": t["task_id"], "error": "Rate limit exceeded (429)"})
    body = r.json()
    assert body["switched_to"] == "muse_acc_vid_02"
    assert mb.is_account_blocked(mb.find_account("muse_acc_vid_01"))
    assert mb.get_active_account_id("video") == "muse_acc_vid_02"
    # Task được xếp lại cho tài khoản VIDEO khác, tài khoản ảnh không nhận
    assert poll(c, "muse_acc_img_01")["task"] is None
    blocked = poll(c, "muse_acc_vid_01")
    assert blocked["task"] is None and blocked["blocked_until"]
    assert poll(c, "muse_acc_vid_02")["task"]["task_id"] == t["task_id"]


def test_session_expired_blocks_account(fleet):
    c = fleet["client"]
    online("muse_acc_img_01", "muse_acc_img_02")
    t = mb.enqueue_task({"mode": "text-to-image", "prompt": "s"})
    poll(c, "muse_acc_img_01")
    c.post(f"/api/muse-bridge/tasks/{t['task_id']}/fail", json={"task_id": t["task_id"], "error": "SESSION_EXPIRED: cần đăng nhập lại"})
    assert mb.is_account_blocked(mb.find_account("muse_acc_img_01"))
    assert mb.pending_tasks[0]["assigned_account"] == "muse_acc_img_02"


def test_non_quota_error_retries_then_fails(fleet):
    c = fleet["client"]
    online("muse_acc_img_01")
    fleet["installed"].discard("muse_acc_img_02")
    t = mb.enqueue_task({"mode": "text-to-image", "prompt": "n"})
    for attempt in range(mb.MAX_TASK_RETRIES + 1):
        got = poll(c, "muse_acc_img_01")["task"]
        assert got["task_id"] == t["task_id"]
        c.post(f"/api/muse-bridge/tasks/{t['task_id']}/fail", json={"task_id": t["task_id"], "error": "NO_MEDIA: không có ảnh"})
    assert not mb.pending_tasks
    assert mb.task_history[0]["status"] == "failed"
    # Lỗi thường không khóa tài khoản
    assert not mb.is_account_blocked(mb.find_account("muse_acc_img_01"))


# ---------------- Người gọi chờ kết quả ----------------
def test_enqueue_and_wait_requires_same_kind_online(fleet):
    online("muse_acc_img_01")
    with pytest.raises(RuntimeError):
        asyncio.run(mb.enqueue_and_wait_muse_task({"mode": "image-to-video", "prompt": "x", "input_image_url": "/static/a.jpg"}))
    assert not mb.pending_tasks


def test_enqueue_and_wait_timeout_removes_task(fleet):
    online("muse_acc_img_01")
    with pytest.raises(TimeoutError):
        asyncio.run(mb.enqueue_and_wait_muse_task({"mode": "text-to-image", "prompt": "x"}, timeout=0.3))
    assert not mb.pending_tasks
    assert mb.task_history[0]["abandoned"] is True


# ---------------- Endpoint ----------------
def test_switch_enforces_kind(fleet):
    c = fleet["client"]
    assert c.post("/api/muse-bridge/accounts/switch", json={"mode": "image", "account_id": "muse_acc_vid_01"}).status_code == 400
    r = c.post("/api/muse-bridge/accounts/switch", json={"mode": "video", "account_id": "muse_acc_vid_02"})
    assert r.status_code == 200 and r.json()["active_video_account"] == "muse_acc_vid_02"
    assert r.json()["active_image_account"] == "muse_acc_img_01"


def test_add_account_rejects_mixed_capabilities(fleet):
    c = fleet["client"]
    r = c.post("/api/muse-bridge/accounts/add", json={"account_id": "muse_acc_mix_01", "label": "mix", "capabilities": IMG_CAPS + VID_CAPS})
    assert r.status_code == 400


def test_status_has_no_vm_fields(fleet):
    c = fleet["client"]
    r = c.get("/api/muse-bridge/status")
    assert r.status_code == 200
    assert "bootstrap_command" not in r.json() and "tailscale" not in r.text
    assert c.get("/api/muse-bridge/bootstrap-command").status_code == 404


def test_output_in_similar_project_name_is_not_linked_to_other_project(fleet):
    """proj_a và proj_ab: ảnh nằm trong proj_ab không được gắn link /api/projects/proj_a/... (lỗi so chuỗi startswith)."""
    c = fleet["client"]
    projects = mb.PROJECTS_DIR
    (projects / "proj_a").mkdir(parents=True, exist_ok=True)
    target = projects / "proj_ab" / "images" / "lan.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    t = mb.enqueue_task({"mode": "text-to-image", "prompt": "p", "project_id": "proj_a", "output_path": str(target)})
    _activate(t)
    r = c.post(f"/api/muse-bridge/tasks/{t['task_id']}/complete", files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 200
    done = next(x for x in mb.task_history if x["task_id"] == t["task_id"])
    assert not done["media_url"].startswith("/api/projects/proj_a/")
    assert done["media_url"] == f"/static/muse_outputs/{t['task_id']}.jpg"


def test_image_result_clears_generating_status_of_scene(fleet, isolated_projects_dir):
    """Giao diện tự lưu status_image "generating" khi bấm Muse 2K; ảnh về thì máy chủ báo xong (gặp 03/11/2026: thẻ cảnh
    treo vòng quay "Đang sinh ảnh AI" dù đã có ảnh)."""
    from models.schemas import Project, Scene
    from services import project_service
    pid = "proj_status_anh01"
    project_service.ensure_project_dirs(pid)
    project_service.save_project(Project(id=pid, name="x", scenes=[
        Scene(id="scene_001", order=1, text="a", image_prompt="b", status_image="generating")]))
    t = mb.enqueue_task({"mode": "text-to-image", "prompt": "p", "project_id": pid, "scene_id": "scene_001"})
    _activate(t)
    r = fleet["client"].post(f"/api/muse-bridge/tasks/{t['task_id']}/complete",
                             files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 200
    scene = project_service.get_project(pid).scenes[0]
    assert scene.status_image == "ready" and scene.image_path
