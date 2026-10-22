"""Kiểm tra tự động của Story Studio: một lệnh cho cả agent lẫn hook trước commit.

Cách dùng (luôn bằng Python của .venv):
    .venv\\Scripts\\python.exe tools\\check.py                       bản nhanh (~15 s): Ruff, cú pháp JS, test kiến trúc, test FEATURE_MAP
    .venv\\Scripts\\python.exe tools\\check.py --full                bản đầy đủ: thêm cả bộ test mặc định (bỏ test cờ live), ~8 phút
    .venv\\Scripts\\python.exe tools\\check.py --install-hook        cài 2 hook git (khoá cứng, CLAUDE.md mục 6.1):
        pre-commit: chặn commit thẳng lên master/main, rồi chạy bản nhanh
        commit-msg: chặn dòng đầu commit sai dạng "<vùng>: <mô tả>"
    .venv\\Scripts\\python.exe tools\\check.py --shrink-ruff-baseline  sau khi sửa bớt lỗi Ruff cũ: hạ mốc cho khớp

Ruff so với mốc tools/ruff_baseline.json (lỗi có từ trước, đếm theo file và luật): lỗi mới thì chặn. Không có lệnh
nâng mốc: thêm ngoại lệ phải sửa tay file mốc và được duyệt như thay đổi kiến trúc (CLAUDE.md mục 2.1).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tools" / "ruff_baseline.json"
HOOK_DIR = ROOT / ".git" / "hooks"
HOOK_MARK = "# cài bởi tools/check.py --install-hook"
# Khoá cứng CLAUDE.md mục 6.1 dòng 1: không commit thẳng lên master/main (kết thúc một lần gộp nhánh thì được).
# Viết thẳng trong hook, không gọi Python: bản tools/check.py của nhánh đang mở có thể là bản cũ chưa có khoá này
# (đã gặp 22/10/2026: commit thử lọt vào master vì master còn check.py cũ).
BRANCH_GUARD = (
    'branch=$(git symbolic-ref --short -q HEAD)\n'
    'case "$branch" in\n'
    '  master|main)\n'
    '    if [ ! -f "$(git rev-parse --git-path MERGE_HEAD)" ]; then\n'
    '      echo "[LỖI] Không commit thẳng lên $branch (CLAUDE.md mục 6.1 dòng 1). Tạo nhánh cho việc này rồi commit ở đó:'
    ' git switch -c ten-viec-khong-dau. Gộp vào $branch chỉ khi chủ dự án đồng ý."\n'
    '      exit 1\n'
    '    fi\n'
    '    ;;\n'
    'esac\n')
HOOKS = {
    "pre-commit": BRANCH_GUARD + '[ -f tools/check.py ] || exit 0\n'
                  'exec ".venv/Scripts/python.exe" -X utf8 tools/check.py\n',
    "commit-msg": '[ -f tools/check.py ] || exit 0\n'
                  'grep -q -- "--commit-msg" tools/check.py || exit 0\n'
                  'exec ".venv/Scripts/python.exe" -X utf8 tools/check.py --commit-msg "$1"\n',
}
JS_FILES = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "backend" / "static").glob("*.js"))
FAST_TESTS = ["tests/test_architecture.py", "tests/test_feature_map.py", "tests/test_working_rules.py",
              "tests/test_git_guards.py", "tests/test_guardrail_policy.py"]
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
_SUBJECT_OK = re.compile(r"^[^\s:][^:\n]{0,39}: \S")
_SUBJECT_GIT = re.compile(r"^(Merge |Revert |fixup! |squash! |amend! )")


def commit_message_problem(message: str) -> str | None:
    """Khoá cứng CLAUDE.md mục 6.1 dòng 10: dòng đầu commit dạng '<vùng>: <mô tả>' (vùng tối đa 40 ký tự)."""
    lines = [ln for ln in message.splitlines() if not ln.startswith("#")]
    subject = next((ln for ln in lines if ln.strip()), "")
    if _SUBJECT_GIT.match(subject) or _SUBJECT_OK.match(subject):
        return None
    return ("Dòng đầu commit phải theo dạng '<vùng>: <mô tả>' bằng tiếng Việt (CLAUDE.md mục 6), vùng tối đa 40 ký tự, "
            f"ví dụ 'tts_service: thử lại khi Edge-TTS lỗi'. Đang là: {subject[:90]!r}")


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, env=ENV, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def _ruff_counts() -> Counter:
    proc = _run([sys.executable, "-m", "ruff", "check", "--output-format", "json", "--no-cache", "--exit-zero"], 120)
    if proc.returncode != 0 or not proc.stdout.strip().startswith("["):
        raise RuntimeError("Không chạy được Ruff. Cài: .venv\\Scripts\\python.exe -m pip install -r backend\\requirements-dev.txt\n"
                           + (proc.stderr or proc.stdout)[-800:])
    counts = Counter()
    for item in json.loads(proc.stdout):
        rel = Path(item["filename"]).resolve().relative_to(ROOT).as_posix()
        counts[(rel, item["code"] or "E999")] += 1
    return counts


def _load_baseline() -> Counter:
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    return Counter({(f, code): n for f, codes in data.items() for code, n in codes.items()})


def _save_baseline(counts: Counter) -> None:
    data: dict[str, dict[str, int]] = {}
    for (f, code), n in sorted(counts.items()):
        if n > 0:
            data.setdefault(f, {})[code] = n
    BASELINE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def check_ruff() -> tuple[bool, str]:
    if not BASELINE.exists():
        return False, f"Thiếu file mốc {BASELINE.relative_to(ROOT)}"
    current, base = _ruff_counts(), _load_baseline()
    new = {k: (current[k], base.get(k, 0)) for k in current if current[k] > base.get(k, 0)}
    fixed = {k: (current.get(k, 0), base[k]) for k in base if current.get(k, 0) < base[k]}
    lines = [f"  {f}: {code} có {got} chỗ, mốc cho phép {ok}" for (f, code), (got, ok) in sorted(new.items())]
    if new:
        return False, ("Lỗi Ruff mới (xem bằng: .venv\\Scripts\\python.exe -m ruff check <file>):\n" + "\n".join(lines))
    note = f"{sum(current.values())} lỗi cũ trong mốc, không có lỗi mới"
    if fixed:
        note += f"; đã sửa bớt {sum(b - a for a, b in fixed.values())} lỗi cũ: chạy --shrink-ruff-baseline để hạ mốc"
    return True, note


def check_js() -> tuple[bool, str]:
    node = shutil.which("node")
    if not node:
        return False, "Không thấy Node.js trong PATH (cần để kiểm cú pháp JS)"
    errors = []
    for js in JS_FILES:
        proc = _run([node, "--check", js], 60)
        if proc.returncode != 0:
            errors.append(f"  {js}:\n{proc.stderr.strip()[-600:]}")
    return (not errors), ("\n".join(errors) if errors else f"{len(JS_FILES)} file JS đúng cú pháp")


def check_pytest(args: list[str], timeout: int) -> tuple[bool, str]:
    proc = _run([sys.executable, "-X", "utf8", "-m", "pytest", "-q", "-p", "no:cacheprovider", *args], timeout)
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    summary = tail[-1] if tail else proc.stderr.strip()[-300:]
    if proc.returncode != 0:
        failed = [ln for ln in tail if ln.startswith(("FAILED", "ERROR"))]
        return False, "\n".join(["  " + ln for ln in failed[-15:]] + [f"  {summary}"])
    return True, summary


def hook_script(name: str) -> str:
    # Hook dùng chung cho mọi nhánh; phần Python chạy theo bản tools/check.py của nhánh đang mở
    return "#!/bin/sh\n" + HOOK_MARK + "\n" + HOOKS[name]


def install_hook() -> int:
    for name in HOOKS:
        path = HOOK_DIR / name
        if path.exists() and HOOK_MARK not in path.read_text(encoding="utf-8", errors="replace"):
            print(f"Đã có hook khác ở {path}; không ghi đè. Gộp tay nếu cần.")
            return 1
    for name in HOOKS:
        (HOOK_DIR / name).write_text(hook_script(name), encoding="utf-8", newline="\n")
    print(f"Đã cài hook git: {', '.join(HOOKS)} trong {HOOK_DIR.relative_to(ROOT)} "
          "(chặn commit thẳng lên master, chặn commit sai định dạng, chạy bản nhanh mỗi lần commit)")
    return 0


def shrink_baseline() -> int:
    current, base = _ruff_counts(), _load_baseline()
    shrunk = Counter({k: min(n, current.get(k, 0)) for k, n in base.items()})
    over = {k: current[k] for k in current if current[k] > base.get(k, 0)}
    _save_baseline(shrunk)
    print(f"Mốc Ruff: {sum(base.values())} → {sum(shrunk.values())} lỗi cũ.")
    if over:
        print("Vẫn còn lỗi mới vượt mốc (không được đưa vào mốc, phải sửa):")
        for (f, code), n in sorted(over.items()):
            print(f"  {f}: {code} {n} chỗ")
        return 1
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Kiểm tra tự động của Story Studio")
    parser.add_argument("--full", action="store_true", help="chạy thêm cả bộ test mặc định (~8 phút)")
    parser.add_argument("--install-hook", action="store_true", help="cài hook trước commit")
    parser.add_argument("--shrink-ruff-baseline", action="store_true", help="hạ mốc Ruff sau khi sửa bớt lỗi cũ")
    parser.add_argument("--init-ruff-baseline", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--commit-msg", metavar="FILE", help="dùng trong hook: kiểm dòng đầu commit")
    args = parser.parse_args()

    if args.commit_msg:
        problem = commit_message_problem(Path(args.commit_msg).read_text(encoding="utf-8", errors="replace"))
        if problem:
            print("[LỖI] " + problem)
            return 1
        return 0
    if args.install_hook:
        return install_hook()
    if args.shrink_ruff_baseline:
        return shrink_baseline()
    if args.init_ruff_baseline:  # chỉ dùng một lần khi tạo mốc đầu tiên
        if BASELINE.exists():
            print("Đã có mốc; không tạo lại (chỉ được hạ bằng --shrink-ruff-baseline).")
            return 1
        _save_baseline(_ruff_counts())
        print(f"Đã tạo mốc {BASELINE.relative_to(ROOT)}")
        return 0

    steps = [("Ruff (so với mốc)", check_ruff),
             ("Cú pháp JS", check_js),
             ("Test kiến trúc + FEATURE_MAP", lambda: check_pytest(FAST_TESTS, 300))]
    if args.full:
        steps.append(("Cả bộ test mặc định (bỏ cờ live)", lambda: check_pytest([], 1800)))

    ok_all = True
    for name, fn in steps:
        start = time.time()
        try:
            ok, detail = fn()
        except Exception as e:  # lỗi của chính bước kiểm (thiếu công cụ, quá giờ) cũng là trượt
            ok, detail = False, f"{type(e).__name__}: {e}"
        ok_all &= ok
        print(f"[{'ĐẠT' if ok else 'LỖI'}] {name} ({time.time() - start:.0f} s): {detail if ok else ''}")
        if not ok:
            print(detail)
    print("Kết quả: ĐẠT" if ok_all else "Kết quả: CÓ LỖI — sửa xong mới commit (không dùng --no-verify)")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
