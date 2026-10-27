"""Các lỗi người duyệt độc lập tìm ra trong video cao trào theo bảng nhân vật (28/10/2026).

1. Runner coi chính prompt (khung chat hiện lại) là lời Muse báo lỗi.
2. Mọi tài khoản video đều bị tránh thì việc treo tới hết giờ chờ; tự thử lại của bridge không biết tránh.
3. Giao diện tự lưu bản dự án cũ đè mất trạng thái duyệt grid của server.
4. "Chọn cảnh cao trào" xoá cảnh đã duyệt grid nhưng làm clip lỗi.
6. Đường dẫn grid trong project.json trỏ ra ngoài thư mục làm việc.
"""
import asyncio
import json
import time

import pytest

import routers.api as api
import routers.muse_bridge as mb
from models.schemas import Scene
from runners import muse_fleet_runner as runner
from services import climax_video as cv
from services import project_service
from tests.test_climax_video import FakeMuse, _climax_project, _scene_now, client  # noqa: F401
from tests.test_muse_fleet_routing import online
from tests.test_muse_threads import fleet  # noqa: F401


# --------------------------------------------------------------------------------------- 1. lời Muse báo lỗi
PROMPT = ("tạo cho tôi 1 video 5s. Ghi chú của chủ dự án: grid trước gặp lỗi tay, tránh terror quá đà, "
          "không được báo lỗi 503 kiểu cũ. Giữ nguyên nhân vật như bảng.")


def test_prompt_echoed_in_chat_is_not_taken_as_muse_error():
    before = "Bảng nhân vật đã xong."
    now = before + "\nBạn\n" + PROMPT + "\nMuse\nĐã tạo video 5 giây, nhân vật giữ đúng bảng, không có error nào."
    assert runner.muse_reply_error(before, now, PROMPT) is None


def test_muse_error_after_prompt_is_still_caught():
    before = "Bảng nhân vật đã xong."
    now = before + "\n" + PROMPT + "\nDịch vụ tạo video hiện không khả dụng, bạn thử lại sau nhé."
    err = runner.muse_reply_error(before, now, PROMPT)
    assert err and "không khả dụng" in err and "Ghi chú của chủ dự án" not in err


def test_prompt_shown_with_different_spacing_is_still_stripped():
    before = ""
    shown = PROMPT.replace(". ", ".\n\n")          # khung chat xuống dòng khác prompt gửi đi
    assert runner.muse_reply_error(before, shown + "\nXong rồi.", PROMPT) is None


def test_unknown_new_part_is_ignored_rather_than_guessed():
    """Chat cuộn mất phần đầu (không bắt đầu bằng chữ cũ) và không thấy prompt: không đoán bừa là lỗi."""
    assert runner.muse_reply_error("chữ cũ đã cuộn mất", "lỗi 503 từ hôm qua... Đã tạo xong.", PROMPT) is None


# ------------------------------------------------------------------------------- 2. hết tài khoản không bị tránh
def test_all_online_video_accounts_avoided_fails_fast(fleet):  # noqa: F811
    online("muse_acc_vid_01", "muse_acc_vid_02")
    started = time.time()
    with pytest.raises(RuntimeError) as err:
        asyncio.run(mb.enqueue_and_wait_muse_task({"mode": "image-to-video", "prompt": "x", "input_image_url": "/static/a.jpg",
                                                   "avoid_accounts": ["muse_acc_vid_01", "muse_acc_vid_02"]}, timeout=5))
    assert "vừa lỗi" in str(err.value) and time.time() - started < 2
    assert not mb.pending_tasks


def test_bridge_retry_never_moves_task_to_avoided_account(fleet):  # noqa: F811
    online("muse_acc_vid_01", "muse_acc_vid_02")
    assert mb.pick_fallback_account("video", exclude="muse_acc_vid_01", avoid=["muse_acc_vid_02"]) is None
    assert mb.pick_fallback_account("video", exclude="muse_acc_vid_01")["account_id"] == "muse_acc_vid_02"


def test_success_clears_avoid_list():
    thread = cv.SceneThread({"avoid_accounts": ["muse_acc_vid_01"]})
    thread.remember({"thread_url": "https://muse.ai/thread/2d353dc3-3d3d-44b3-a3e7-51f54a295757",
                     "executed_by": "muse_acc_vid_02"})
    assert thread.state()["avoid_accounts"] == []


@pytest.mark.parametrize("code", ["PROFILE_IN_USE", "SESSION_EXPIRED", "BROWSER_ERROR"])
def test_broken_account_errors_switch_account(code):
    assert cv._muse_error_switch_account(RuntimeError(f"{code}: hồ sơ Chrome đang mở"))


# ------------------------------------------------------------------- 3. tự lưu giao diện không đè trạng thái server
def test_project_put_keeps_server_climax_state(isolated_projects_dir):
    project = _climax_project(duration=4.0)
    pid, sid = project.id, "scene_003"
    asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=FakeMuse(pid, sid)))
    stale = [s.model_copy(deep=True) for s in project_service.get_project(pid).scenes]   # giao diện giữ bản lúc này
    cv.approve_grid(pid, sid)                                                             # rồi chủ dự án duyệt grid
    stale.append(Scene(id="scene_009", order=9, text="cảnh nhân bản",
                       metadata={"climax_video": {"status": "ready", "grid_approved": True}}))
    api._keep_server_media(project_service.get_project(pid), stale)
    by_id = {s.id: s for s in stale}
    assert by_id[sid].metadata["climax_video"]["status"] == cv.GRID_APPROVED
    assert "climax_video" not in by_id["scene_002"].metadata or \
        by_id["scene_002"].metadata["climax_video"] == _scene_now(pid, "scene_002").metadata.get("climax_video")
    assert "climax_video" not in by_id["scene_009"].metadata                             # cảnh mới không mang trạng thái


# --------------------------------------------------------------- 4. chọn lại cảnh không xoá grid đã duyệt mà lỗi clip
def test_pick_keeps_failed_scene_with_approved_grid(client):  # noqa: F811
    project = _climax_project(duration=4.0)
    pid, sid = project.id, "scene_003"
    asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=FakeMuse(pid, sid)))
    cv.approve_grid(pid, sid)
    asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=FakeMuse(pid, sid, clip_plan=lambda n: "error")))
    state = _scene_now(pid, sid).metadata["climax_video"]
    assert state["status"] == "failed" and state["grid_approved"] is True
    assert client.post(f"/api/projects/{pid}/climax-video/pick").status_code == 200
    after = _scene_now(pid, sid).metadata["climax_video"]
    assert after["grid_approved"] is True and after["grid_paths"] == state["grid_paths"]


# ----------------------------------------------------------------------------- 6. đường dẫn grid ngoài thư mục cảnh
def test_grid_path_outside_scene_work_dir_is_refused(isolated_projects_dir, tmp_path):
    project = _climax_project(duration=4.0)
    pid, sid = project.id, "scene_003"
    asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=FakeMuse(pid, sid)))
    cv.approve_grid(pid, sid)
    outside = tmp_path / "la.jpg"
    outside.write_bytes(b"x")
    p = project_service.get_project(pid)
    for s in p.scenes:
        if s.id == sid:
            s.metadata["climax_video"]["grid_paths"] = [str(outside)]
    project_service.save_project(p)
    muse = FakeMuse(pid, sid)
    result = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
    assert result["status"] == "failed" and "ngoài thư mục" in result["error"]
    assert muse.tasks == []
    json.dumps(result)   # trạng thái vẫn ghi được
