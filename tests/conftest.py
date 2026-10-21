"""
Cấu hình chung cho pytest.

- Không cho test tự khởi động Fleet Runner thật (tránh mở profile Chrome và gửi prompt lên tài khoản Muse thật).
- Sao lưu và khôi phục muse_fleet_accounts.json vì nhiều test ghi vào cấu hình tài khoản.
- Không cho test tự bật worker phân tích vụ án (STORY_STUDIO_DISABLE_CASE_WORKER).
- Fixture isolated_projects_dir: đổi PROJECTS_DIR sang thư mục tạm để test không ghi vào projects/ thật.
- Mọi test ghi ảnh cắt truyện tranh vào thư mục tạm (COMIC_SLICES_DIR), không vào backend/static/comic_slices.
- Test không gắn cờ `live` không được gọi mạng hay dịch vụ thật trên máy (9router, VieNeu, server 8000): gọi là bị chặn
  và test báo lỗi. Test cần dịch vụ thật thì gắn `@pytest.mark.live` (chạy bằng `pytest -m live`).
- Chạy xong mà projects/ có thư mục mới thì phiên test báo lỗi (test để lại dự án rác).
"""
import asyncio
import os
import shutil
import socket
import sys
from pathlib import Path

import pytest

os.environ["STORY_STUDIO_DISABLE_FLEET_AUTOSTART"] = "1"
os.environ["STORY_STUDIO_DISABLE_CASE_WORKER"] = "1"

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
ACCOUNTS_FILE = ROOT / "backend" / "config" / "muse_fleet_accounts.json"
PROJECTS_ROOT = ROOT / "projects"
if str(BACKEND_DIR) not in sys.path:  # test import thẳng config, services, routers… như code trong backend/
    sys.path.insert(0, str(BACKEND_DIR))

# --------------------------------------------------------------------------- chặn mạng cho test không gắn cờ live
_LOOPBACK_NAMES = {"localhost", "::1", "0.0.0.0", "::"}
# Dịch vụ thật chạy trên chính máy này: 9router, server giọng VieNeu, server Story Studio đang dùng
_REAL_LOCAL_PORTS = {20128, 5005, 8000}


class NetworkBlocked(ConnectionRefusedError):
    """Lỗi giống "dịch vụ không chạy", để code đang test đi nhánh xử lý lỗi bình thường."""


def _is_loopback(host) -> bool:
    h = str(host).strip("[]").lower()
    return h in _LOOPBACK_NAMES or h.startswith("127.")


class _NetworkGuard:
    def __init__(self):
        self.attempts: list[str] = []

    def check(self, host, port) -> None:
        if host is None:
            return
        try:
            port = int(port) if port is not None else None
        except (TypeError, ValueError):
            port = None
        if _is_loopback(host) and port not in _REAL_LOCAL_PORTS:
            return
        where = f"{host}:{port}" if port is not None else str(host)
        self.attempts.append(where)
        raise NetworkBlocked(f"Test không gắn cờ live mà gọi {where}")

    def install(self, monkeypatch) -> None:
        guard = self
        real_getaddrinfo = socket.getaddrinfo
        real_connect = socket.socket.connect
        real_connect_ex = socket.socket.connect_ex
        real_create_connection = asyncio.base_events.BaseEventLoop.create_connection

        def getaddrinfo(host, port, *args, **kwargs):
            if host is not None and not _is_loopback(host):
                guard.check(host, port)
            return real_getaddrinfo(host, port, *args, **kwargs)

        def connect(self, address):
            if isinstance(address, tuple) and len(address) >= 2:
                guard.check(address[0], address[1])
            return real_connect(self, address)

        def connect_ex(self, address):
            if isinstance(address, tuple) and len(address) >= 2:
                guard.check(address[0], address[1])
            return real_connect_ex(self, address)

        async def create_connection(self, protocol_factory, host=None, port=None, *args, **kwargs):
            guard.check(host, port)
            return await real_create_connection(self, protocol_factory, host, port, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
        monkeypatch.setattr(socket.socket, "connect", connect)
        monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
        monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "create_connection", create_connection)


@pytest.fixture(autouse=True)
def _block_real_services(request, monkeypatch):
    """Test thường: chặn mạng ngoài và cổng dịch vụ thật trên máy, không tự bật VieNeu. Test gắn cờ live thì bỏ qua."""
    if request.node.get_closest_marker("live"):
        yield
        return
    monkeypatch.setenv("STORY_STUDIO_DISABLE_VIENEU_AUTOSTART", "1")
    guard = _NetworkGuard()
    guard.install(monkeypatch)
    yield
    if guard.attempts:
        shown = ", ".join(sorted(set(guard.attempts))[:5])
        pytest.fail(f"Test không gắn cờ live mà gọi mạng/dịch vụ thật ({shown}). Dùng dữ liệu giả, "
                    f"hoặc gắn @pytest.mark.live nếu test cần dịch vụ thật.", pytrace=False)


# --------------------------------------------------------------------------- không để lại dự án rác
def _project_entries() -> set[str]:
    try:
        return {p.name for p in PROJECTS_ROOT.iterdir()}
    except FileNotFoundError:
        return set()


def pytest_sessionstart(session):
    session.config._projects_before = _project_entries()


def pytest_sessionfinish(session, exitstatus):
    before = getattr(session.config, "_projects_before", None)
    if before is None:
        return
    leftovers = sorted(_project_entries() - before)
    session.config._projects_leftovers = leftovers
    if leftovers and session.exitstatus == 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    leftovers = getattr(config, "_projects_leftovers", None)
    if leftovers:
        terminalreporter.section("Dự án rác do test để lại", red=True)
        terminalreporter.write_line("Thư mục mới trong projects/ sau khi chạy test: " + ", ".join(leftovers))
        terminalreporter.write_line("Test phải ghi vào thư mục tạm (fixture isolated_projects_dir) hoặc tự dọn sau khi chạy.")


@pytest.fixture(scope="session", autouse=True)
def _protect_fleet_accounts_config(tmp_path_factory):
    backup = None
    if ACCOUNTS_FILE.exists():
        backup = tmp_path_factory.mktemp("fleet_cfg") / ACCOUNTS_FILE.name
        shutil.copy2(ACCOUNTS_FILE, backup)
    yield
    if backup is not None:
        shutil.copy2(backup, ACCOUNTS_FILE)


@pytest.fixture(autouse=True)
def _isolated_comic_slices_dir(tmp_path, monkeypatch) -> Path:
    """Ảnh cắt truyện tranh của test ghi vào thư mục tạm, không để lại thư mục rác trong backend/static/comic_slices.
    config, comic_slicer và routers.api đều giữ bản COMIC_SLICES_DIR riêng (import theo tên) nên đổi cả ba."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    import config
    from routers import api
    from services import comic_slicer

    slices = tmp_path / "comic_slices"
    slices.mkdir()
    for module in (config, comic_slicer, api):
        monkeypatch.setattr(module, "COMIC_SLICES_DIR", slices)
    return slices


@pytest.fixture
def isolated_projects_dir(tmp_path, monkeypatch) -> Path:
    """Thư mục projects tạm: mọi code đọc PROJECTS_DIR qua project_service/config đều thấy thư mục này."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    import config
    from services import project_service

    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(project_service, "PROJECTS_DIR", projects)
    monkeypatch.setattr(config, "PROJECTS_DIR", projects)
    return projects
