"""Khoá cứng của CLAUDE.md mục 6.1 làm bằng hook git (tools/check.py --install-hook).

- dòng 1: không commit thẳng lên master/main (hook pre-commit, phần chặn viết thẳng trong hook);
- dòng 10: dòng đầu commit dạng "<vùng>: <mô tả>" (hook commit-msg gọi commit_message_problem).
Hook pre-commit được chạy thật bằng git trong một repo tạm. Test cũng kiểm hook của repo này đã cài đúng bản,
vì hook chưa cài thì khoá không có tác dụng.
"""
import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("story_studio_check", ROOT / "tools" / "check.py")
assert _spec and _spec.loader
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

# Khi chính test này chạy trong hook của repo thật, git đặt sẵn GIT_INDEX_FILE, GIT_DIR...: phải bỏ đi để không đụng repo thật
_CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


@pytest.fixture
def temp_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.org", *args], cwd=repo,
                              env=_CLEAN_ENV, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=60)

    assert git("init", "-q", "-b", "master").returncode == 0
    assert git("commit", "-q", "--allow-empty", "-m", "khởi tạo: repo thử").returncode == 0
    hooks = Path(git("rev-parse", "--git-path", "hooks").stdout.strip())
    hooks = hooks if hooks.is_absolute() else repo / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "pre-commit").write_text(check.hook_script("pre-commit"), encoding="utf-8", newline="\n")
    return git


@pytest.mark.skipif(shutil.which("git") is None, reason="không có git")
def test_pre_commit_hook_blocks_commit_on_master(temp_repo):
    result = temp_repo("commit", "-q", "--allow-empty", "-m", "thử: commit thẳng lên master")
    assert result.returncode != 0
    assert "Không commit thẳng lên master" in result.stdout + result.stderr
    assert temp_repo("rev-list", "--count", "master").stdout.strip() == "1"


@pytest.mark.skipif(shutil.which("git") is None, reason="không có git")
def test_pre_commit_hook_allows_work_branch_and_merging_into_master(temp_repo):
    assert temp_repo("switch", "-q", "-c", "viec-moi").returncode == 0
    assert temp_repo("commit", "-q", "--allow-empty", "-m", "thử: commit trên nhánh").returncode == 0
    assert temp_repo("switch", "-q", "master").returncode == 0
    assert temp_repo("merge", "-q", "--no-ff", "--no-commit", "viec-moi").returncode == 0
    finish = temp_repo("commit", "-q", "-m", "Merge branch 'viec-moi'")  # kết thúc gộp: hook thấy MERGE_HEAD nên cho qua
    assert finish.returncode == 0, finish.stdout + finish.stderr


@pytest.mark.parametrize("message", [
    "tts_service: thử lại khi Edge-TTS lỗi",
    "CLAUDE.md: ghi nguyên văn quyết định\n\nCo-Authored-By: X <x@example.org>",
    "# dòng chú thích của git\ngiao diện: sửa nút Lưu",
    "Merge branch 'khoa-cung-mem'",
    "Revert \"tests: thêm test\"",
])
def test_good_commit_messages_pass(message):
    assert check.commit_message_problem(message) is None


@pytest.mark.parametrize("message", [
    "sửa lỗi",  # không có vùng
    "project.json chỉ ghi qua project_service.save_project(): bỏ các chỗ gọi",  # vùng quá dài (c116f07)
    "Bỏ thư mục cache cài đặt (.cache) khỏi git",  # afaadab
    ": thiếu vùng",
    "",
])
def test_bad_commit_messages_are_blocked(message):
    assert check.commit_message_problem(message)


@pytest.mark.skipif(not (ROOT / ".git").is_dir(), reason="bản đóng gói không có git")
@pytest.mark.parametrize("name", sorted(check.HOOKS))
def test_git_hooks_are_installed(name):
    hook = ROOT / ".git" / "hooks" / name
    assert hook.exists() and hook.read_text(encoding="utf-8") == check.hook_script(name), (
        f"Hook {name} chưa cài hoặc là bản cũ, khoá cứng không có tác dụng. Chạy: "
        ".venv\\Scripts\\python.exe tools\\check.py --install-hook")
