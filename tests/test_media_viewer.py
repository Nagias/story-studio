"""Xem lớn ảnh/video (backend/static/media_viewer.js): kiểm tĩnh việc nạp, gắn thuộc tính và lớp phủ không chặn chuột."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "backend" / "static"


def _read(name):
    return (STATIC / name).read_text(encoding="utf-8")


def test_media_viewer_loaded_after_app_and_shipped():
    h = _read("index.html")
    assert h.index("/static/app.js") < h.index("/static/media_viewer.js")
    assert "window.openMediaViewer" in _read("media_viewer.js")
    assert (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8").count("backend/static/media_viewer.js") >= 2


def test_scene_card_media_carries_viewer_attributes():
    app = _read("app.js")
    assert app.count("data-viewer-src=") >= 3  # ảnh, video, nút Xem lớn
    assert 'data-viewer-kind="video"' in app and 'data-viewer-kind="image"' in app
    assert 'onclick="openMediaViewer' not in app  # chỉ uỷ quyền sự kiện, không gắn hai cách


def test_scene_action_overlay_lets_clicks_through():
    assert "ws-scene-actions" in _read("app.js")
    css = _read("workspace.css")
    assert ".ws-scene-actions { pointer-events: none; }" in css
    assert "pointer-events: auto" in css


def test_sheet_images_use_viewer_with_new_tab_fallback():
    for name in ("character_sheets.js", "location_sheets.js", "climax_video.js"):
        src = _read(name)
        assert "bindMediaViewerLink" in src and "a.href" in src, name
