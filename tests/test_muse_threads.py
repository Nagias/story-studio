"""Side chat Muse dùng lại được cho video cao trào (kế hoạch docs/superpowers/plans/2026-10-28-video-cao-trao-bang-nhan-vat.md).

Phần muse_bridge (Task 1): việc ảnh chạy trên tài khoản video (`route_kind`), ghim việc vào tài khoản sở hữu chat
(`pin_account`), tránh tài khoản vừa lỗi (`avoid_accounts`), trả `thread_url`/`muse_reply` về người gọi.
Phần Fleet Runner (Task 2): chỉ test hàm thuần; luồng trình duyệt kiểm bằng chạy thật.
Không mở trình duyệt, không đụng tài khoản thật.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import routers.muse_bridge as mb  # noqa: E402
import tests.test_muse_fleet_routing as routing  # noqa: E402
from tests.test_muse_fleet_routing import jpeg_bytes, online, poll  # noqa: E402

fleet = routing.fleet   # dùng chung fixture tài khoản giả của test định tuyến

THREAD = "https://muse.ai/thread/2d353dc3-3d3d-44b3-a3e7-51f54a295757"


# ------------------------------------------------------------------------------------------------- muse_bridge
def test_image_task_routed_to_video_account_when_route_kind_video(fleet):
    task = mb.assign_task_account({"mode": "text-to-image", "route_kind": "video", "assigned_account": "muse_acc_vid_02"})
    assert task["assigned_account"] == "muse_acc_vid_02"
    assert mb.routing_kind(task) == "video" and mb.task_kind(task["mode"]) == "image"
    mb.pending_tasks.append(task)
    assert mb._pick_task_for_account("muse_acc_img_01", "image") == -1
    assert mb._pick_task_for_account("muse_acc_vid_02", "video") == 0


def test_route_kind_without_account_uses_active_video_account(fleet):
    assert mb.assign_task_account({"mode": "text-to-image", "route_kind": "video"})["assigned_account"] == "muse_acc_vid_01"


def test_avoid_accounts_picks_another_account_of_same_kind(fleet):
    task = mb.assign_task_account({"mode": "image-to-video", "avoid_accounts": ["muse_acc_vid_01"]})
    assert task["assigned_account"] == "muse_acc_vid_02"


def test_pinned_task_never_reassigned(fleet):
    online("muse_acc_vid_01")   # vid_02 (chủ chat) offline
    task = mb.assign_task_account({"mode": "image-to-video", "assigned_account": "muse_acc_vid_02", "pin_account": True})
    task["queued_at"] = time.time() - 10 * mb.REASSIGN_AFTER_SEC
    mb.pending_tasks.append(task)
    assert mb._pick_task_for_account("muse_acc_vid_01", "video") == -1
    assert task["assigned_account"] == "muse_acc_vid_02"


def test_pinned_task_with_unusable_account_fails_fast(fleet):
    online("muse_acc_vid_01")
    fleet["installed"].discard("muse_acc_vid_02")   # chủ chat mất đăng nhập
    started = time.time()
    with pytest.raises(RuntimeError) as err:
        asyncio.run(mb.enqueue_and_wait_muse_task({"mode": "image-to-video", "prompt": "x", "input_image_url": "/static/a.jpg",
                                                   "assigned_account": "muse_acc_vid_02", "pin_account": True,
                                                   "thread_url": THREAD}, timeout=5))
    assert "muse_acc_vid_02" in str(err.value) and time.time() - started < 2
    assert not mb.pending_tasks


def test_pinned_task_is_not_retried_on_another_account(fleet):
    online("muse_acc_vid_01", "muse_acc_vid_02")
    task = mb.enqueue_task({"mode": "image-to-video", "prompt": "x", "assigned_account": "muse_acc_vid_02",
                            "pin_account": True})
    assert poll(fleet["client"], "muse_acc_vid_02")["task"]["task_id"] == task["task_id"]
    r = fleet["client"].post(f"/api/muse-bridge/tasks/{task['task_id']}/fail", json={"task_id": task["task_id"], "error": "MUSE_REPLIED_ERROR: quá tải (503)"})
    assert r.status_code == 200 and r.json()["auto_failover"] is False
    assert not mb.pending_tasks and mb.task_history[0]["status"] == "failed"


@pytest.mark.parametrize("bad", [
    {"thread_url": "https://evil.example/thread/2d353dc3-3d3d-44b3-a3e7-51f54a295757"},
    {"thread_url": "https://muse.ai/thread/new"},
    {"route_kind": "audio"},
    {"attachments": ["C:/Windows/win.ini"]},
    {"attachments": "khong-phai-danh-sach"},
])
def test_invalid_thread_fields_are_rejected(fleet, bad):
    online("muse_acc_vid_01")
    with pytest.raises(ValueError):
        asyncio.run(mb.enqueue_and_wait_muse_task({"mode": "text-to-image", "prompt": "x", **bad}, timeout=1))
    assert not mb.pending_tasks


def test_complete_returns_thread_url_and_reply(fleet):
    online("muse_acc_vid_01")
    task = mb.enqueue_task({"mode": "text-to-image", "route_kind": "video", "prompt": "x"})
    assert poll(fleet["client"], "muse_acc_vid_01")["task"]["task_id"] == task["task_id"]
    meta = {"account_id": "muse_acc_vid_01", "thread_url": THREAD, "muse_reply": "Bảng đã xong." * 500}
    r = fleet["client"].post(f"/api/muse-bridge/tasks/{task['task_id']}/complete",
                             files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")}, data={"metadata": json.dumps(meta)})
    assert r.status_code == 200
    done = mb.task_history[0]
    assert done["thread_url"] == THREAD and len(done["muse_reply"]) <= 2000
    assert done["output_path"].endswith(".jpg")   # việc ảnh chạy trên tài khoản video vẫn ra ảnh


def test_complete_ignores_bad_thread_url_from_worker(fleet):
    online("muse_acc_vid_01")
    task = mb.enqueue_task({"mode": "text-to-image", "route_kind": "video", "prompt": "x"})
    poll(fleet["client"], "muse_acc_vid_01")
    meta = {"thread_url": "javascript:alert(1)"}
    fleet["client"].post(f"/api/muse-bridge/tasks/{task['task_id']}/complete",
                         files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")}, data={"metadata": json.dumps(meta)})
    assert mb.task_history[0].get("thread_url") is None
