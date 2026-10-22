"""Máy kiểm quy tắc của chủ dự án ở CLAUDE.md mục 2.4: lỗi vi phạm từ 3 lần trở lên thì phải là khoá cứng.

Đọc bảng 5.1 (đường cấm) và 6.1 (quy tắc làm việc) trong CLAUDE.md:
- mỗi điều cấm ở mục 5 đều phải được phân loại (đủ số dòng);
- cột "Khoá" chỉ nhận: cứng / cứng một phần / mềm;
- dòng "mềm" mà "Số lần vi phạm" từ 3 trở lên: báo lỗi, phải làm khoá cứng;
- dòng "cứng" phải trỏ tới lệnh kiểm có thật (file có thật; `file::hàm` thì hàm phải có trong file).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
LOCKS = {"cứng", "cứng một phần", "mềm"}
HARD_THRESHOLD = 3


def _table_after(heading: str) -> list:
    lines = CLAUDE_MD.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(heading))
    rows, in_table = [], False
    for ln in lines[start + 1:]:
        if ln.startswith("#"):
            break
        if ln.startswith("|"):
            in_table = True
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if cells[0].isdigit():
                rows.append(cells)
        elif in_table:
            break
    return rows


def _check_table(heading: str) -> list:
    problems = []
    for cells in _table_after(heading):
        no, lock, checker, count = cells[0], cells[1], cells[2], cells[3]
        if lock not in LOCKS:
            problems.append(f"{heading.strip()} dòng {no}: cột Khoá phải là một trong {sorted(LOCKS)}, đang là {lock!r}")
            continue
        m = re.match(r"\d+", count)
        if not m:
            problems.append(f"{heading.strip()} dòng {no}: cột Số lần vi phạm phải là số, đang là {count!r}")
            continue
        if lock == "mềm" and int(m.group()) >= HARD_THRESHOLD:
            problems.append(f"{heading.strip()} dòng {no}: vi phạm {m.group()} lần mà vẫn là khoá mềm. Theo mục 2.4 phải chuyển "
                            "thành khoá cứng (test hoặc hook chặn tự động)")
        if lock != "mềm":
            refs = re.findall(r"`([^`]+)`", checker)
            if not refs:
                problems.append(f"{heading.strip()} dòng {no}: khoá {lock} mà không ghi lệnh kiểm nào")
            for ref in refs:
                path, _, func = ref.partition("::")
                target = ROOT / path
                if not target.exists():
                    problems.append(f"{heading.strip()} dòng {no}: lệnh kiểm `{ref}` không có file {path}")
                elif func and not re.search(rf"^\s*(async\s+)?def {re.escape(func)}\(", target.read_text(encoding="utf-8"), re.M):
                    problems.append(f"{heading.strip()} dòng {no}: lệnh kiểm `{ref}` không có hàm {func} trong {path}")
    return problems


def test_every_forbidden_pattern_is_classified():
    forbidden = [c for c in _table_after("## 5. ")]
    classified = [c[0] for c in _table_after("### 5.1 ")]
    assert classified == [c[0] for c in forbidden], (
        "Bảng 5.1 phải phân loại khoá cứng/mềm cho đủ và đúng thứ tự mọi dòng của bảng đường cấm mục 5")


def test_working_rules_table_is_numbered():
    numbers = [c[0] for c in _table_after("### 6.1 ")]
    assert numbers == [str(i) for i in range(1, len(numbers) + 1)] and numbers, "Bảng 6.1 phải đánh số 1, 2, 3… liền nhau"


def test_rules_violated_three_times_are_hard_locks():
    problems = _check_table("### 5.1 ") + _check_table("### 6.1 ")
    assert not problems, "CLAUDE.md mục 2.4 (khoá cứng/mềm):\n" + "\n".join("  " + p for p in problems)
