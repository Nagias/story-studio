"""Bật Fleet Runner tự động chỉ ở một nơi (runners/autostart.py), tôn trọng công tắc tắt, theo đúng cổng server.

Lỗi cũ (rà soát 21/10/2026): run.py tự viết lại việc bật runner và bỏ qua STORY_STUDIO_DISABLE_FLEET_AUTOSTART, nên test
chạy run.py bật Fleet Runner thật (hồ sơ Muse đã đăng nhập). Runner cũng luôn gọi cổng 8000, kể cả khi server chạy cổng khác.
Không spawn tiến trình thật: subprocess.Popen được thay bằng bản ghi lại lệnh.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run  # noqa: E402
from routers import muse_bridge  # noqa: E402
from runners import autostart, single_instance  # noqa: E402


@pytest.fixture
def popen_calls(monkeypatch):
    calls = []

    class FakeProc:
        def poll(self):
            return None

    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        return FakeProc()

    monkeypatch.setattr(autostart.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(single_instance, "is_runner_running", lambda: False)
    return calls


def test_disabled_switch_blocks_every_entry_point(popen_calls, monkeypatch):
    monkeypatch.setenv("STORY_STUDIO_DISABLE_FLEET_AUTOSTART", "1")
    assert autostart.start_fleet_runner_daemon(port=8000) is None
    run.start_fleet_runner_daemon()
    muse_bridge.fleet_runner_proc = None
    muse_bridge.ensure_local_fleet_runner()
    assert popen_calls == []


def test_runner_already_running_is_not_spawned_again(popen_calls, monkeypatch):
    monkeypatch.delenv("STORY_STUDIO_DISABLE_FLEET_AUTOSTART", raising=False)
    monkeypatch.setattr(single_instance, "is_runner_running", lambda: True)
    assert autostart.start_fleet_runner_daemon(port=8000) is None
    assert popen_calls == []


def test_spawned_runner_points_at_the_server_port(popen_calls, monkeypatch):
    monkeypatch.delenv("STORY_STUDIO_DISABLE_FLEET_AUTOSTART", raising=False)
    assert autostart.start_fleet_runner_daemon(port=8123) is not None
    cmd = popen_calls[-1]
    assert "--daemon" in cmd
    assert cmd[cmd.index("--url") + 1] == "http://127.0.0.1:8123/api/muse-bridge"


def test_run_py_and_muse_bridge_use_the_shared_starter(popen_calls, monkeypatch):
    monkeypatch.delenv("STORY_STUDIO_DISABLE_FLEET_AUTOSTART", raising=False)
    monkeypatch.setattr(run, "PORT", 8124)
    run.start_fleet_runner_daemon()
    monkeypatch.setattr(muse_bridge, "fleet_runner_proc", None)
    muse_bridge.ensure_local_fleet_runner()
    urls = [cmd[cmd.index("--url") + 1] for cmd in popen_calls]
    assert urls[0] == "http://127.0.0.1:8124/api/muse-bridge"
    assert len(urls) == 2
