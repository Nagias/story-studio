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


PRIMARY_IDS = [
    "btn-cinema-download-video", "btn-generate-custom-thumbnail", "btn-yt-seo-research", "btn-yt-seo-generate",
    "btn-yt-seo-save", "btn-produce-from-board", "btn-auto-gen-all", "btn-climax-video-run",
    "btn-tc-outline-approve", "btn-tc-create-vi", "btn-create-project", "btn-step1-process-script",
    "btn-step1-process-comic",
]


def test_primary_buttons_use_pill_class():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    bad = []
    for i in PRIMARY_IDS:
        m = re.search(r'<(?:button|a)\b[^>]*\bid="%s"[^>]*>' % re.escape(i), html)
        if not m or "ws-btn-primary" not in m.group(0):
            bad.append(i)
    assert not bad, f"Nút chính chưa dùng ws-btn-primary: {bad}"


def test_no_colored_shadows_outside_status():
    colored = re.compile(r"\bshadow-(?!(?:red|amber|emerald)-)[a-z]+-\d{2,3}(?:/\d+)?\b")
    hits = {f.name: sorted(set(colored.findall(f.read_text(encoding="utf-8")))) for f in FILES}
    hits = {k: v for k, v in hits.items() if v}
    assert not hits, hits
