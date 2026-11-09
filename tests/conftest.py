"""
Cấu hình chung cho pytest.

- Không cho test tự khởi động Fleet Runner thật (tránh mở profile Chrome và gửi prompt lên tài khoản Muse thật).
- Sao lưu và khôi phục muse_fleet_accounts.json vì nhiều test ghi vào cấu hình tài khoản.
- Không cho test tự bật worker phân tích vụ án (STORY_STUDIO_DISABLE_CASE_WORKER).
- Mọi test ghi dự án vào thư mục tạm (đổi PROJECTS_DIR ở mọi module); fixture isolated_projects_dir trả đường dẫn đó.
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

# Thư mục tạm của test (tmp_path) đặt trong .cache trên ổ dự án, không trên ổ C (gần đầy). pytest vẫn đánh số
# pytest-N cho từng lượt chạy nên hai lượt chạy cùng lúc không giẫm lên nhau; .cache bị git và gói bán bỏ qua.
_TEST_TMP_ROOT = ROOT / ".cache" / "pytest-tmp"
_TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("PYTEST_DEBUG_TEMPROOT", str(_TEST_TMP_ROOT))

# --------------------------------------------------------------------------- chặn mạng cho test không gắn cờ live
_LOOPBACK_NAMES = {"localhost", "::1", "0.0.0.0", "::"}
# Dịch vụ thật chạy trên chính máy này: 9router, CLI Proxy, server giọng VieNeu, server Story Studio đang dùng
_REAL_LOCAL_PORTS = {20128, 8317, 5005, 8000}


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


REAL_PROJECTS_DIR = PROJECTS_ROOT.resolve()
REAL_COMIC_SLICES_DIR = (BACKEND_DIR / "static" / "comic_slices").resolve()


def _redirect_everywhere(monkeypatch, attr: str, real: Path, new: Path) -> None:
    """Nhiều module giữ bản sao riêng của đường dẫn (`from config import PROJECTS_DIR`), kể cả file test:
    đổi ở MỌI module đã nạp đang trỏ vào thư mục thật."""
    for module in list(sys.modules.values()):
        namespace = getattr(module, "__dict__", None)
        value = namespace.get(attr) if isinstance(namespace, dict) else None
        if isinstance(value, Path) and value.resolve() == real:
            monkeypatch.setattr(module, attr, new)


@pytest.fixture(autouse=True)
def _isolated_data_dirs(tmp_path, monkeypatch) -> Path:
    """Mọi test (kể cả cờ live) ghi dự án và ảnh cắt truyện tranh vào thư mục tạm, không bao giờ vào projects/ hay
    backend/static/comic_slices thật. Module nạp sau đó lấy đường dẫn từ config (đã đổi) nên cũng thấy thư mục tạm."""
    import main  # noqa: F401 — nạp mọi module backend để đổi hết các bản sao đường dẫn

    projects = tmp_path / "isolated_projects"   # tên riêng: vài test tự tạo tmp_path/"projects" của mình
    projects.mkdir()
    slices = tmp_path / "isolated_comic_slices"
    slices.mkdir()
    _redirect_everywhere(monkeypatch, "PROJECTS_DIR", REAL_PROJECTS_DIR, projects)
    _redirect_everywhere(monkeypatch, "COMIC_SLICES_DIR", REAL_COMIC_SLICES_DIR, slices)
    return projects


@pytest.fixture
def isolated_projects_dir(_isolated_data_dirs) -> Path:
    """Thư mục projects tạm của test (mọi test đều đã được cô lập; fixture này để test lấy đường dẫn)."""
    return _isolated_data_dirs
