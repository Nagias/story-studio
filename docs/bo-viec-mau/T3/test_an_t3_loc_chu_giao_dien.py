"""Test ẩn bổ sung của bộ việc mẫu T3 (docs/bo-viec-mau): chỉ chép vào tests/ của bản chấm, không thuộc bộ test dự án.

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
