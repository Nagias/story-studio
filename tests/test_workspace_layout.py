"""Kiểm bố cục giao diện gọn: mỗi id nằm đúng trang."""
from pathlib import Path

from tests.ui_html import INDEX_HTML, NAV_ORDER, inside, page_of

ROOT = Path(__file__).resolve().parent.parent

# id -> mã trang (giá trị data-page); None là nằm ngoài mọi trang (ví dụ thanh bên). Task sau thêm dòng.
PLACEMENT: dict[str, str | None] = {}
PLACEMENT |= {"step-view-1": "idea", "step-view-2": "scenes", "step-view-3": "publish", "step-view-4": "publish"}

HIDDEN_STORE = "ws-hidden-inputs"


def test_each_id_sits_on_its_page():
    wrong = {i: (page_of(INDEX_HTML, i), p) for i, p in PLACEMENT.items() if page_of(INDEX_HTML, i) != p}
    assert not wrong, f"id nằm sai trang (đang ở, phải ở): {wrong}"


def test_ui_html_reader():
    h = '<div data-page="a"><section id="s"><input id="i"><p id="p">x</p></section></div><div id="o"></div>'
    assert page_of(h, "p") == "a" and page_of(h, "i") == "a" and page_of(h, "o") is None
    assert inside(h, "p", "s") and not inside(h, "o", "s")
    nav = '<button class="ws-nav" data-go="b"></button><a class="x ws-nav" data-go="a"></a><i class="ws-nav-x" data-go="c"></i>'
    assert NAV_ORDER(nav) == ["b", "a"]


def test_sidebar_order():
    assert NAV_ORDER(INDEX_HTML) == ["idea", "script", "look", "scenes", "publish", "projects", "gallery", "accounts"]


def test_workspace_assets_loaded_in_order():
    h = INDEX_HTML
    assert h.index("/static/tailwind.css") < h.index("/static/workspace.css")
    assert h.index("/static/workspace.js") < h.index("/static/app.js")
    assert "Be+Vietnam+Pro" in h and "family=Inter" not in h


def test_release_ships_workspace_files():
    src = (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8")
    assert src.count("backend/static/workspace.css") >= 1 and src.count("backend/static/workspace.js") >= 2
