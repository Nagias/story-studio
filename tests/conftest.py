"""
Cấu hình chung cho pytest.

- Không cho test tự khởi động Fleet Runner thật (tránh mở profile Chrome và gửi prompt lên tài khoản Muse thật).
- Sao lưu và khôi phục muse_fleet_accounts.json vì nhiều test ghi vào cấu hình tài khoản.
- Không cho test tự bật worker phân tích vụ án (STORY_STUDIO_DISABLE_CASE_WORKER).
- Fixture isolated_projects_dir: đổi PROJECTS_DIR sang thư mục tạm để test không ghi vào projects/ thật.
"""
import os
import shutil
import sys
from pathlib import Path

import pytest

os.environ["STORY_STUDIO_DISABLE_FLEET_AUTOSTART"] = "1"
os.environ["STORY_STUDIO_DISABLE_CASE_WORKER"] = "1"

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
ACCOUNTS_FILE = ROOT / "backend" / "config" / "muse_fleet_accounts.json"


@pytest.fixture(scope="session", autouse=True)
def _protect_fleet_accounts_config(tmp_path_factory):
    backup = None
    if ACCOUNTS_FILE.exists():
        backup = tmp_path_factory.mktemp("fleet_cfg") / ACCOUNTS_FILE.name
        shutil.copy2(ACCOUNTS_FILE, backup)
    yield
    if backup is not None:
        shutil.copy2(backup, ACCOUNTS_FILE)


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
