"""
Cấu hình chung cho pytest.

- Không cho test tự khởi động Fleet Runner thật (tránh mở profile Chrome và gửi prompt lên tài khoản Muse thật).
- Sao lưu và khôi phục muse_fleet_accounts.json vì nhiều test ghi vào cấu hình tài khoản.
"""
import os
import shutil
from pathlib import Path

import pytest

os.environ["STORY_STUDIO_DISABLE_FLEET_AUTOSTART"] = "1"

ROOT = Path(__file__).resolve().parent.parent
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
