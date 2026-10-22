"""Khoá cứng của CLAUDE.md mục 6.1 làm bằng test (phần không cần hook git).

Dòng 11: không thêm script ở gốc dự án (đã phải xoá 3 lần: run_studio.py, run_studio.bat, run_all_tests.py).
Test đặt trong tests/, công cụ trong tools/, file tạm trong .cache/.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ROOT_SCRIPTS = {"run.py", "run.bat", "setup_muse_accounts.bat", "start_muse_fleet.bat"}
_SCRIPT_SUFFIXES = {".py", ".bat", ".cmd", ".ps1", ".sh", ".js", ".vbs"}


def test_no_new_scripts_in_project_root():
    extra = sorted(p.name for p in ROOT.iterdir()
                   if p.is_file() and p.suffix.lower() in _SCRIPT_SUFFIXES and p.name not in ALLOWED_ROOT_SCRIPTS)
    assert not extra, ("CLAUDE.md mục 6: không thêm script ở gốc dự án. Test để trong tests/, công cụ trong tools/, "
                       "file tạm trong .cache/. Đang có thêm: " + ", ".join(extra))
