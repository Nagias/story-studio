"""Chủ dự án 13/11/2026: hai tài khoản video thay phiên nhau, chạy song song cho nhanh; mỗi cảnh làm trọn trên đúng một
tài khoản ("không được 1 cảnh mà chia sang 2 tài khoản lại lệch nhân vật")."""
import asyncio

from routers import climax_video as climax_router
from services import climax_video as cv


def _fake_accounts(monkeypatch, accounts):
    monkeypatch.setattr(climax_router, "usable_online_accounts", lambda kind: list(accounts))
    monkeypatch.setattr(climax_router, "WORKER_STAGGER_S", 0)
    monkeypatch.setattr(climax_router, "_scene_owners", lambda pid, ids, accs: {})


def test_scenes_alternate_between_accounts_one_account_per_scene(monkeypatch):
    _fake_accounts(monkeypatch, ["acc_a", "acc_b"])
    log = []

    async def fake_run(pid, sid, muse_call, account=None):
        log.append((sid, account))
        await asyncio.sleep(0.01)
        return {"status": "ready"}
    monkeypatch.setattr(climax_router.climax_video, "run_scene_climax_video", fake_run)
    scenes = [f"scene_{i:03d}" for i in range(1, 7)]
    asyncio.run(climax_router._run_all("proj_x", scenes))
    assert sorted(s for s, _ in log) == scenes                      # mỗi cảnh chạy đúng một lần
    by_account = {a: [s for s, x in log if x == a] for a in ("acc_a", "acc_b")}
    assert len(by_account["acc_a"]) == 3 and len(by_account["acc_b"]) == 3   # thay phiên, chia đều
    assert all(a in ("acc_a", "acc_b") for _, a in log)


def test_account_that_hits_limit_stops_other_continues(monkeypatch):
    _fake_accounts(monkeypatch, ["acc_a", "acc_b"])
    log = []

    async def fake_run(pid, sid, muse_call, account=None):
        log.append((sid, account))
        await asyncio.sleep(0.01)
        if account == "acc_a":
            return {"status": "failed", "error": "Muse task failed: QUOTA_EXCEEDED: Muse không tạo được video nào "
                                                  "(hạn mức video): bị chặn ở cổng hạn mức"}
        return {"status": "ready"}
    monkeypatch.setattr(climax_router.climax_video, "run_scene_climax_video", fake_run)
    asyncio.run(climax_router._run_all("proj_x", ["s1", "s2", "s3", "s4"]))
    assert [s for s, a in log if a == "acc_a"] == ["s1"]               # hết lượt: nghỉ ngay, không lấy cảnh mới
    assert sorted(s for s, a in log if a == "acc_b") == ["s2", "s3", "s4"]
    assert len(log) == 4                                              # cảnh lỗi không bị chuyển sang tài khoản kia


def test_scene_thread_pins_given_account_and_drops_other_accounts_chat():
    old = {"thread_url": "https://muse.ai/thread/abc", "account_id": "acc_old"}
    thread = cv.SceneThread(old, "acc_b")
    task = thread.apply({})
    assert task["assigned_account"] == "acc_b" and task["pin_account"] is True
    assert "thread_url" not in task                                   # chat của tài khoản khác: mở chat mới
    thread.drop(switch_account=True)                                  # lỗi giữa chừng: vẫn ghim đúng tài khoản
    again = thread.apply({})
    assert again["assigned_account"] == "acc_b" and again["pin_account"] is True
    assert "avoid_accounts" not in again


def test_scene_thread_keeps_own_chat_on_same_account():
    old = {"thread_url": "https://muse.ai/thread/abc", "account_id": "acc_b"}
    task = cv.SceneThread(old, "acc_b").apply({})
    assert task == {"assigned_account": "acc_b", "pin_account": True, "thread_url": "https://muse.ai/thread/abc"}


def test_without_given_account_behaviour_unchanged():
    old = {"thread_url": "https://muse.ai/thread/abc", "account_id": "acc_old"}
    task = cv.SceneThread(old).apply({})
    assert task == {"thread_url": "https://muse.ai/thread/abc", "assigned_account": "acc_old", "pin_account": True}


def test_scene_started_on_an_account_goes_back_to_that_account(monkeypatch):
    """Gặp 13/11/2026: cảnh 052 bắt đầu trên vp_01, server tắt giữa chừng; lần chạy lại hàng chỉ còn cảnh đó và tài khoản
    kia vào trước nên nhận mất. Cảnh đã có chủ thì chỉ chủ làm tiếp."""
    _fake_accounts(monkeypatch, ["acc_a", "acc_b"])
    monkeypatch.setattr(climax_router, "_scene_owners",
                        lambda pid, ids, accs: {"s1": "acc_b", "s2": None, "s3": "acc_b"})
    log = []

    async def fake_run(pid, sid, muse_call, account=None):
        log.append((sid, account))
        await asyncio.sleep(0.01)
        return {"status": "ready"}
    monkeypatch.setattr(climax_router.climax_video, "run_scene_climax_video", fake_run)
    asyncio.run(climax_router._run_all("proj_x", ["s1", "s2", "s3"]))
    got = dict(log)
    assert got["s1"] == "acc_b" and got["s3"] == "acc_b"           # cảnh có chủ: đúng chủ, dù acc_a vào trước
    assert got["s2"] == "acc_a"                                    # cảnh chưa có chủ: tài khoản rảnh nhận
    assert len(log) == 3


def test_scene_owners_reads_saved_account_and_ignores_unusable_ones(isolated_projects_dir):
    from models.schemas import Project, Scene
    from services import project_service
    scenes = [Scene(id="s1", order=1, text="a", metadata={"climax_video": {"account_id": "acc_b"}}),
              Scene(id="s2", order=2, text="b", metadata={"climax_video": {"account_id": "acc_khoa"}}),
              Scene(id="s3", order=3, text="c")]
    project_service.ensure_project_dirs("proj_owner01")
    project_service.save_project(Project(id="proj_owner01", name="Thử", scenes=scenes))
    owners = climax_router._scene_owners("proj_owner01", ["s1", "s2", "s3"], ["acc_a", "acc_b"])
    assert owners == {"s1": "acc_b", "s2": None, "s3": None}
