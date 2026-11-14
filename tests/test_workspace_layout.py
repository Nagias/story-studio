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


PLACEMENT |= {"btn-add-scene": "script", "select-voice": "script", "btn-preview-voice-sample": "script",
              "btn-regen-all-voices": "script", "script-scene-list": "script"}


def test_scene_text_is_edited_in_one_place():
    app = (ROOT / "backend" / "static" / "app.js").read_text(encoding="utf-8")
    start = app.index("function renderSceneList(")
    body = app[start:app.index("\nfunction ", start + 10)]
    page = (ROOT / "backend" / "static" / "script_page.js").read_text(encoding="utf-8")
    for fn in ("updateSceneText(", "updateSceneTextLive(", "moveScene(", "duplicateScene(", "deleteScene(",
               "playSceneVoice(", "seekSceneAudio(", "regenerateSceneVoice("):
        assert fn not in body and fn in page, fn


def test_script_page_has_tabs_and_blocks():
    from tests.ui_html import inside
    for i in ("script-tab-lines", "script-tab-voice", "script-scene-list"):
        assert page_of(INDEX_HTML, i) == "script", i
    assert inside(INDEX_HTML, "btn-add-scene", "script-tab-lines")
    assert inside(INDEX_HTML, "script-scene-list", "script-tab-lines")
    assert inside(INDEX_HTML, "select-voice", "script-tab-voice")
    assert inside(INDEX_HTML, "btn-regen-all-voices", "script-tab-voice")
    for t in ("outline", "names", "lines", "voice"):
        assert f'data-tab="{t}"' in INDEX_HTML


def test_script_page_loaded_after_app_and_shipped():
    h = INDEX_HTML
    assert h.index("/static/app.js") < h.index("/static/script_page.js")
    src = (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8")
    assert src.count("backend/static/script_page.js") >= 2


def test_no_window_lookup_of_const_globals_of_app_js():
    """AppState và DOM là `const` ở app.js, không phải thuộc tính của window: window.AppState luôn là undefined."""
    bad = [p.name for p in (ROOT / "backend" / "static").glob("*.js") if p.name != "app.js"
           and any(s in p.read_text(encoding="utf-8") for s in ("window.AppState", "window.DOM"))]
    assert not bad, f"dùng window.AppState/window.DOM (luôn undefined): {bad}"


def test_scenes_page_rerenders_cards_when_shown():
    src = (ROOT / "backend" / "static" / "script_page.js").read_text(encoding="utf-8")
    assert "onPageShow('scenes'" in src and "renderSceneList()" in src


PLACEMENT |= {"modal-character-sheets": "look", "modal-location-sheets": "look", "select-project-style": "look",
              "btn-look-change-style": "look", "select-image-provider": "look"}


def test_style_popover_warns_about_old_prompts():
    assert "Mô tả ảnh của các cảnh đã viết theo phong cách cũ" in INDEX_HTML
