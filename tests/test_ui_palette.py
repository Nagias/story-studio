"""Giao diện gọn: không dùng màu trang trí (tím, xanh dương, hồng...). Chỉ đỏ/vàng/xanh lá cho trạng thái."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "backend" / "static"
DECOR = re.compile(
    r"\b(?:bg|text|border|ring|from|via|to|shadow)-(?:indigo|violet|purple|fuchsia|pink|rose|sky|cyan|teal|blue|lime)-\d{2,3}\b"
    r"|\bbg-gradient-to-"
)
FILES = [STATIC / "index.html", *sorted(STATIC.glob("*.js"))]


def test_no_decorative_colors_left():
    hits = {f.name: DECOR.findall(f.read_text(encoding="utf-8")) for f in FILES}
    hits = {k: sorted(set(v)) for k, v in hits.items() if v}
    assert not hits, f"Còn lớp màu trang trí (dùng lớp ws-* hoặc màu kẽm): {hits}"
