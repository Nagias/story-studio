"""Khoá cứng của CLAUDE.md mục 6.1 làm bằng hook git (tools/check.py --install-hook).

- dòng 1: không commit thẳng lên master/main (hook pre-commit gọi branch_problem);
- dòng 10: dòng đầu commit dạng "<vùng>: <mô tả>" (hook commit-msg gọi commit_message_problem).
Test cũng kiểm hook đã được cài đúng bản, vì hook chưa cài thì khoá không có tác dụng.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("story_studio_check", ROOT / "tools" / "check.py")
assert _spec and _spec.loader
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


@pytest.mark.parametrize("branch", ["master", "main"])
def test_commit_on_main_branch_is_blocked(branch):
    problem = check.branch_problem(branch, merging=False)
    assert problem and "git switch -c" in problem


def test_finishing_a_merge_on_master_is_allowed():
    assert check.branch_problem("master", merging=True) is None


@pytest.mark.parametrize("branch", ["khoa-cung-mem", "muc-toi-thieu-15-phut", None])
def test_commit_on_work_branch_is_allowed(branch):
    assert check.branch_problem(branch, merging=False) is None


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
