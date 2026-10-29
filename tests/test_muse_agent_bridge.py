"""muse_bridge cho việc giao nhiều bước (`agent-video`): thời gian chờ, giữ nguyên chế độ, nhận ảnh phụ và báo cáo.

Không mở trình duyệt; tài khoản giả của test định tuyến.
"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402
import routers.muse_bridge as mb  # noqa: E402
import tests.test_muse_fleet_routing as routing  # noqa: E402
from tests.test_muse_fleet_routing import jpeg_bytes, online, poll  # noqa: E402

fleet = routing.fleet


def mp4_bytes(tmp_path: Path, seconds: float = 2.0) -> bytes:
    out = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s=320x180:d={seconds}",
                    "-pix_fmt", "yuv420p", str(out)], check=True)
    return out.read_bytes()


def test_agent_task_timeout_uses_config():
    assert config.MUSE_AGENT_WAIT_MIN == 75
    assert mb._task_timeout({"mode": "agent-video"}) == config.MUSE_AGENT_WAIT_MIN * 60 + 120
    assert mb._task_timeout({"mode": "image-to-video"}) == mb.VIDEO_TASK_TIMEOUT_SEC


def test_enqueue_keeps_agent_video_mode(fleet):
    online("muse_acc_vid_01")

    async def run():
        job = asyncio.create_task(mb.enqueue_and_wait_muse_task(
            {"mode": "agent-video", "route_kind": "video", "raw_prompt": True, "prompt": "brief",
             "agent": {"done_token": "XONG-1", "wait_sec": 60, "target_seconds": 12}}, timeout=1))
        await asyncio.sleep(0.2)
        seen = [dict(t) for t in mb.pending_tasks]
        with pytest.raises(TimeoutError):
            await job
        return seen

    seen = asyncio.run(run())
    assert seen and seen[0]["mode"] == "agent-video" and seen[0]["agent"]["done_token"] == "XONG-1"


def test_complete_saves_extra_images_and_agent_fields(fleet, tmp_path):
    online("muse_acc_vid_01")
    task = mb.enqueue_task({"mode": "agent-video", "route_kind": "video", "prompt": "brief"})
    assert poll(fleet["client"], "muse_acc_vid_01")["task"]["task_id"] == task["task_id"]
    meta = {"account_id": "muse_acc_vid_01", "muse_reply": "báo cáo " * 700,
            "media_count": {"video": 4, "image": 2}, "warnings": ["Muse gửi 2 video, app lấy video cuối cùng"]}
    files = [("file", ("v.mp4", mp4_bytes(tmp_path), "video/mp4")),
             ("extras", ("a.jpg", jpeg_bytes(), "image/jpeg")),
             ("extras", ("b.jpg", jpeg_bytes(1280, 720), "image/jpeg")),
             ("extras", ("c.jpg", b"khong phai anh" * 100, "image/jpeg"))]
    r = fleet["client"].post(f"/api/muse-bridge/tasks/{task['task_id']}/complete", files=files,
                             data={"metadata": json.dumps(meta)})
    assert r.status_code == 200, r.text
    done = mb.task_history[0]
    assert done["output_path"].endswith(".mp4")
    assert len(done["extra_images"]) == 2 and all(Path(p).is_file() for p in done["extra_images"])
    assert all(Path(p).parent == mb.MUSE_OUTPUTS_DIR for p in done["extra_images"])
    assert len(done["muse_reply"]) > 2000 and len(done["muse_reply"]) <= 8000
    assert done["media_count"] == {"video": 4, "image": 2}
    assert done["warnings"] == meta["warnings"]


def test_complete_keeps_at_most_four_extras_and_rejects_bad_fields(fleet, tmp_path):
    online("muse_acc_vid_01")
    task = mb.enqueue_task({"mode": "agent-video", "route_kind": "video", "prompt": "brief"})
    poll(fleet["client"], "muse_acc_vid_01")
    meta = {"media_count": {"video": "nhiều"}, "warnings": "khong-phai-danh-sach"}
    files = [("file", ("v.mp4", mp4_bytes(tmp_path), "video/mp4"))]
    files += [("extras", (f"{i}.jpg", jpeg_bytes(), "image/jpeg")) for i in range(6)]
    r = fleet["client"].post(f"/api/muse-bridge/tasks/{task['task_id']}/complete", files=files,
                             data={"metadata": json.dumps(meta)})
    assert r.status_code == 200, r.text
    done = mb.task_history[0]
    assert len(done["extra_images"]) == 4
    assert "media_count" not in done and "warnings" not in done


def test_normal_video_task_keeps_short_reply(fleet, tmp_path):
    online("muse_acc_vid_01")
    task = mb.enqueue_task({"mode": "image-to-video", "prompt": "x"})
    poll(fleet["client"], "muse_acc_vid_01")
    r = fleet["client"].post(f"/api/muse-bridge/tasks/{task['task_id']}/complete",
                             files={"file": ("v.mp4", mp4_bytes(tmp_path), "video/mp4")},
                             data={"metadata": json.dumps({"muse_reply": "x" * 5000})})
    assert r.status_code == 200
    assert len(mb.task_history[0]["muse_reply"]) == 2000 and "extra_images" not in mb.task_history[0]


def test_failed_agent_task_is_not_retried(fleet):
    """Chạy thật 28/10/2026: việc giao nhiều bước lỗi lúc tải bị bridge tự giao lại (vid_01 rồi vid_02) -> Muse làm
    trọn lần thứ hai. Mỗi lần tốn tới 6 video: lỗi thì dừng, chủ dự án tự bấm làm lại."""
    online("muse_acc_vid_01", "muse_acc_vid_02")
    task = mb.enqueue_task({"mode": "agent-video", "route_kind": "video", "prompt": "brief"})
    poll(fleet["client"], task["assigned_account"])
    r = fleet["client"].post(f"/api/muse-bridge/tasks/{task['task_id']}/fail",
                             json={"task_id": task["task_id"], "error": "NO_FINAL: Không tải được video cuối"})
    assert r.status_code == 200 and r.json()["auto_failover"] is False
    assert not mb.pending_tasks and mb.task_history[0]["status"] == "failed"
