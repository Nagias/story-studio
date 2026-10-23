"""Test ẩn bổ sung của bộ việc mẫu T3 (docs/bo-viec-mau): chỉ chép vào tests/ của bản chấm, không thuộc bộ test dự án.

Yêu cầu 1 của đề: showToast() lọc chữ từ lỗi, máy chủ, tên file, tài khoản Muse.
Yêu cầu 2 của đề: thẻ trong thư viện ảnh Muse lọc mọi giá trị lấy từ máy chủ.
Yêu cầu 3 của đề: escapeHtml() nhận mọi kiểu giá trị.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parent.parent / "backend" / "static" / "app.js"
_TOP_FUNCTION = re.compile(r"^(?:async\s+)?function\s+\w+\s*\(", re.MULTILINE)
_SERVER_VALUES = re.compile(r"\b(?:mediaUrl|sceneId|taskId|downloadUrl)\b|\.(?:output_path|task_id|media_url|file_url)\b")
# Cách lọc hợp lệ: escapeHtml/tcEsc; encodeURIComponent cũng được (kết quả không có < > " &), vd dựng link tải
# `/download/${encodeURIComponent(id)}` rồi lọc cả link khi chèn (gặp ở lần đo điểm gốc 23/10/2026, trước đó bị chấm oan).
_ESCAPED_CALL = re.compile(r"\b(?:escapeHtml|tcEsc|encodeURIComponent)\(")


def _balanced_end(text: str, open_at: int, open_ch: str, close_ch: str) -> int:
    depth, i = 0, open_at
    while i < len(text):
        depth += 1 if text[i] == open_ch else -1 if text[i] == close_ch else 0
        i += 1
        if depth == 0:
            return i
    raise AssertionError("ngoặc không cân trong app.js")


def _strip_escaped(expr: str) -> str:
    out, i = [], 0
    while True:
        m = _ESCAPED_CALL.search(expr, i)
        if not m:
            return "".join(out) + expr[i:]
        out.append(expr[i:m.start()])
        i = _balanced_end(expr, m.end() - 1, "(", ")")


def _gallery_region(source: str) -> str:
    at = source.find('gallery-card-')
    assert at >= 0, "không tìm thấy thẻ thư viện ảnh Muse (gallery-card-) trong app.js"
    starts = [m.start() for m in _TOP_FUNCTION.finditer(source)]
    begin = max((s for s in starts if s < at), default=0)
    end = min((s for s in starts if s > at), default=len(source))
    return source[begin:end]


def test_the_thu_vien_muse_loc_moi_gia_tri_tu_may_chu():
    region = _gallery_region(APP_JS.read_text(encoding="utf-8"))
    problems = []
    for m in re.finditer(r"\$\{", region):
        expr = region[m.end():_balanced_end(region, m.end() - 1, "{", "}") - 1]
        if _SERVER_VALUES.search(_strip_escaped(expr)):
            problems.append("${" + " ".join(expr.split())[:100] + "}")
    assert not problems, "Giá trị từ máy chủ chèn vào HTML thư viện ảnh Muse mà chưa qua escapeHtml():\n" + "\n".join(problems)


# Yêu cầu 1. Thay test_architecture.py::test_toasts_escape_untrusted_text của lần sửa thật (viec.json, "bo_cham"):
# bộ quét đó chỉ nhìn dòng showToast(), nên chấm oan biến đã lọc ngay lúc gán (`const errText = escapeHtml(...)`, có sẵn
# trong code gốc). Gặp ở lần đo 2026-10-23-skill-tu-nap: bài làm để nguyên, đáp án lọc thêm lần nữa (`&` thành `&amp;`).
_UNTRUSTED_IN_TOAST = re.compile(r"err\.message|\.detail\b|\berrText\b|\berrMsg\b|file\.name|\baid\b|\baccLabel\b")
_TOAST_VARIABLES = ("errText", "errMsg", "aid", "accLabel")
_ESCAPED_ONLY = re.compile(r"\b(?:escapeHtml|tcEsc)\(")


def _strip_escaped_only(expr: str) -> str:
    out, i = [], 0
    while True:
        m = _ESCAPED_ONLY.search(expr, i)
        if not m:
            return "".join(out) + expr[i:]
        out.append(expr[i:m.start()])
        i = _balanced_end(expr, m.end() - 1, "(", ")")


def _escaped_at_assignment(lines: list, toast_at: int, name: str, function_start: int) -> bool:
    """Lần gán gần nhất của biến (trong cùng hàm, trước dòng thông báo) là escapeHtml(...)/tcEsc(...)."""
    assign = re.compile(rf"(?:\b(?:const|let|var)\s+|(?<![\w.]))\b{name}\s*=(?!=)\s*(.*)")
    for line in reversed(lines[function_start:toast_at]):
        m = assign.search(line)
        if m:
            return bool(re.match(r"(?:escapeHtml|tcEsc)\(", m.group(1)))
    return False


def _unescaped_toasts(source: str) -> list:
    lines = source.splitlines()
    starts = [source.count("\n", 0, m.start()) for m in _TOP_FUNCTION.finditer(source)]
    found = []
    for idx, line in enumerate(lines):
        if "showToast(" not in line:
            continue
        rest = _strip_escaped_only(line)
        function_start = max((s for s in starts if s <= idx), default=0)
        for name in _TOAST_VARIABLES:
            if re.search(rf"\b{name}\b", rest) and _escaped_at_assignment(lines, idx, name, function_start):
                rest = re.sub(rf"\b{name}\b", "", rest)
        if _UNTRUSTED_IN_TOAST.search(rest):
            found.append((idx + 1, line.strip()))
    return found


def test_thong_bao_loc_chu_tu_loi_may_chu_va_nguoi_dung():
    problems = [f"  {path.name}:{no}: {text[:140]}" for path in (APP_JS, APP_JS.with_name("true_crime.js"))
                for no, text in _unescaped_toasts(path.read_text(encoding="utf-8"))]
    assert not problems, ("showToast() hiển thị HTML; chữ từ lỗi, máy chủ hay máy người dùng phải qua "
                          "escapeHtml()/tcEsc() (tại chỗ, hoặc ngay lúc gán biến):\n" + "\n".join(problems))


def test_bo_quet_thong_bao_nhan_bien_loc_luc_gan_va_bat_cho_chua_loc():
    src = """function a() {
  const errText = escapeHtml(String(t.error));
  showToast(`Lỗi: ${errText}`, "error");
}
function b(errText) {
  showToast(`Lỗi: ${errText}`, "error");
  showToast(`Lỗi: ${escapeHtml(err.message)}`, "error");
  showToast(`Lỗi: ${err.message}`, "error");
}
"""
    assert [no for no, _ in _unescaped_toasts(src)] == [6, 8]


def _escape_function_source(source: str) -> str:
    m = re.search(r"^function\s+escapeHtml\s*\(", source, re.MULTILINE) or \
        re.search(r"^(?:const|let|var)\s+escapeHtml\s*=", source, re.MULTILINE)
    assert m, "không tìm thấy hàm escapeHtml trong app.js"
    brace = source.index("{", m.end())
    return source[m.start():_balanced_end(source, brace, "{", "}")]


@pytest.mark.skipif(shutil.which("node") is None, reason="cần Node.js để chạy thử hàm JS")
def test_escapehtml_nhan_moi_kieu_gia_tri():
    fn = _escape_function_source(APP_JS.read_text(encoding="utf-8"))
    script = fn + """
const cases = [0, 12.5, null, undefined, new Error('<b>x</b>'), '<img src=x onerror="a()">', 'Bình thường & đẹp'];
console.log(JSON.stringify(cases.map(v => escapeHtml(v))));
"""
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, f"escapeHtml văng lỗi với giá trị không phải chuỗi:\n{proc.stderr[-800:]}"
    zero, number, null, undef, err, html, normal = json.loads(proc.stdout)
    assert (zero, number, null, undef) == ("0", "12.5", "", "")
    assert "<" not in err and "x" in err
    assert "<" not in html and '"' not in html
    assert normal.startswith("Bình thường &amp;") and normal.endswith("đẹp")
