"""Tài khoản Muse nhận cả việc ảnh lẫn video (type "both").

Chủ dự án 17/11/2026: "Mấy tài khoản anh để lại generate được cả video và img nên dùng cả đi". Tài khoản "both" nhận
việc ảnh và video ở cả hai đầu: cầu nối Muse (routers/muse_bridge.py: chọn tài khoản, nhận việc khi hỏi) và Fleet Runner
(runners/muse_fleet_runner.py: chọn tài khoản rảnh, kiểm định tuyến). Tài khoản chỉ một loại vẫn không nhận loại kia.
"""
import sys
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers import muse_bridge as mb  # noqa: E402
from runners.muse_fleet_runner import FleetAccount, MuseFleetRunner  # noqa: E402

BOTH = {"account_id": "acc_both", "type": "both", "profile_dir": "chrome_profiles/acc_both"}
IMG = {"account_id": "acc_img", "type": "image", "profile_dir": "chrome_profiles/acc_img"}
VID = {"account_id": "acc_vid", "type": "video", "profile_dir": "chrome_profiles/acc_vid"}


@pytest.fixture
def fleet(monkeypatch):
    accounts = [dict(BOTH), dict(IMG), dict(VID)]
    monkeypatch.setattr(mb, "muse_accounts", accounts)
    monkeypatch.setattr(mb, "pending_tasks", [])
    monkeypatch.setattr(mb, "is_account_profile_installed", lambda acc: True)
    monkeypatch.setattr(mb, "is_account_online", lambda aid: True)
    monkeypatch.setattr(mb, "save_muse_accounts", lambda accs: None)
    return accounts


def test_kinds_and_serves():
    assert mb.account_kinds(BOTH) == ("image", "video") and mb.account_kind(BOTH) == "both"
    assert mb.serves(BOTH, "image") and mb.serves(BOTH, "video")
    assert mb.serves(IMG, "image") and not mb.serves(IMG, "video")
    assert mb.serves(VID, "video") and not mb.serves(VID, "image")
    caps_both = {"capabilities": ["text-to-image", "image-to-video"]}
    assert mb.account_kind(caps_both) == "both"                       # suy từ capabilities khi thiếu type
    assert mb.account_kind({"capabilities": []}) is None and not mb.serves(None, "image")


def test_both_account_picks_image_and_video_tasks_single_kind_does_not(fleet):
    mb.pending_tasks.extend([{"task_id": "t_vid", "mode": "agent-video", "assigned_account": "acc_both"},
                             {"task_id": "t_img", "mode": "text-to-image", "assigned_account": "acc_both"}])
    assert mb._pick_task_for_account("acc_both", mb.account_kinds(BOTH)) == 0
    mb.pending_tasks.pop(0)
    assert mb._pick_task_for_account("acc_both", mb.account_kinds(BOTH)) == 0       # rồi tới việc ảnh
    mb.pending_tasks[:] = [{"task_id": "t_vid", "mode": "agent-video", "assigned_account": "acc_both",
                            "queued_at": time.time() - 10_000}]
    assert mb._pick_task_for_account("acc_img", mb.account_kinds(IMG)) == -1        # tài khoản ảnh không nhận video


def test_assign_and_fallback_use_both_accounts(fleet):
    task = mb.assign_task_account({"mode": "text-to-video", "assigned_account": "acc_both"})
    assert task["assigned_account"] == "acc_both"                                  # tài khoản "both" được giữ
    task = mb.assign_task_account({"mode": "text-to-image", "assigned_account": "acc_vid"})
    assert task["assigned_account"] in ("acc_both", "acc_img")                     # tài khoản video không vẽ ảnh
    assert mb.pick_fallback_account("video", exclude="acc_vid")["account_id"] == "acc_both"
    assert mb.is_kind_online("image") and mb.usable_online_accounts("video") == ["acc_both", "acc_vid"]


def test_block_both_account_moves_both_active_flags(fleet):
    fleet[0].update(is_active_for_image=True, is_active_for_video=True)
    mb.block_account("acc_both", "QUOTA_EXCEEDED: hết lượt tuần", seconds=60)
    assert mb.is_account_blocked(fleet[0])
    by_id = {a["account_id"]: a for a in fleet}
    assert by_id["acc_img"]["is_active_for_image"] and by_id["acc_vid"]["is_active_for_video"]
    assert not fleet[0]["is_active_for_image"] and not fleet[0]["is_active_for_video"]


def test_runner_both_account_serves_both_and_routes():
    acc = FleetAccount({"account_id": "acc_both", "type": "both"})
    assert acc.type == "both" and acc.serves("image") and acc.serves("video")
    assert set(acc.capabilities) >= {"text-to-image", "image-to-video"}
    inferred = FleetAccount({"account_id": "x", "capabilities": ["text-to-image", "text-to-video"]})
    assert inferred.type == "both"
    runner = MuseFleetRunner()
    runner.accounts = {"acc_both": acc, "acc_img": FleetAccount({"account_id": "acc_img", "type": "image"})}
    for a in runner.accounts.values():
        a.status = "ready"
    assert runner.select_available_account("image-to-video", require_login=False).account_id == "acc_both"
    assert runner.select_available_account("text-to-image", require_login=False) is not None
    assert not runner.accounts["acc_img"].serves("video")
