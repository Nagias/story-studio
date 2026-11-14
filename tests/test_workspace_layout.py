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


PLACEMENT |= {"scene-list-container": "scenes", "btn-auto-gen-all": "scenes", "btn-climax-video-pick": "scenes",
              "btn-climax-video-run": "scenes", "btn-regen-all-images": "scenes", "btn-preview-play-toggle": "scenes",
              "btn-produce-from-board": "publish", "select-bgm": "publish", "select-transition": "publish",
              "select-subtitle-style": "publish", "toggle-hardsub": "publish", "toggle-audio-ducking": "publish",
              "cinema-video-player": "publish", "btn-yt-seo-generate": "publish",
              "btn-scenes-more": "scenes", "btn-scenes-preview": "scenes", "btn-render-settings": "publish",
              "render-settings": "publish", "bgm-upload-input": "publish", "producer-log-console": "publish"}


def test_scenes_page_is_only_pictures_and_publish_page_holds_render_settings():
    h = INDEX_HTML
    assert inside(h, "btn-regen-all-images", "scenes-more-popover")
    assert inside(h, "btn-preview-play-toggle", "scenes-preview-block")
    assert inside(h, "select-bgm", "render-settings") and inside(h, "select-subtitle-style", "render-settings")
    # Bước 3 thu gọn: nhật ký nằm trong <details>, nút Dựng không còn nằm trong cột phải cũ
    assert inside(h, "producer-log-console", "publish-log-details")
    assert not inside(h, "btn-produce-from-board", "step-view-2")
    assert page_of(h, "board-asset-readiness") == "publish"


def test_drawer_sources_are_hidden_on_page_but_shown_in_drawer():
    css = (ROOT / "backend" / "static" / "workspace.css").read_text(encoding="utf-8")
    assert ".ws-drawer-src" in css and ".ws-drawer-body .ws-drawer-src" in css
    import re
    for i in ("scenes-preview-block", "render-settings"):
        tag = re.search(r'<[^>]*id="%s"[^>]*>' % i, INDEX_HTML).group(0)
        assert "ws-drawer-src" in tag, i


def test_scenes_publish_page_script_loaded_after_app_and_shipped():
    h = INDEX_HTML
    assert h.index("/static/app.js") < h.index("/static/scenes_publish_page.js")
    src = (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8")
    assert src.count("backend/static/scenes_publish_page.js") >= 2


PLACEMENT |= {"project-list-items": "projects", "btn-create-project": "projects", "new-project-name-input": "projects",
              "btn-project-dropdown": None,
              "muse-fleet-pool-grid": "accounts", "muse-fleet-pool-container": "accounts",
              "btn-muse-refresh-accounts": "accounts", "btn-copy-start-fleet-cmd": "accounts",
              "btn-copy-setup-accounts-cmd": "accounts", "muse-modal-status-text": "accounts",
              "muse-reconnect-assistant": "accounts",
              "muse-gallery-grid": "gallery", "muse-gallery-count": "gallery", "btn-clear-all-gallery": "gallery",
              "muse-progress-card": "gallery", "muse-scene-chips": "gallery", "muse-gallery-placeholder": "gallery"}


def test_projects_gallery_accounts_pages_are_real_pages():
    h = INDEX_HTML
    assert inside(h, "btn-project-dropdown", "ws-sidebar") and page_of(h, "btn-project-dropdown") is None
    assert not inside(h, "btn-project-dropdown", "ws-top-right-x")
    assert "Tạm thời mở cửa sổ" not in h and "onclick=\"openMuseModal()\"" not in h
    assert "openProjectModal()\"" not in h
    # trạng thái Muse ở bên phải thanh trên, bấm mở trang Tài khoản
    top = h[h.index('<header class="ws-top">'):h.index("</header>")]
    assert 'id="btn-muse-cloud-status"' in top and 'id="header-muse-status-text"' in top


def test_gallery_attach_strip_and_return_to_scenes():
    h = INDEX_HTML
    assert page_of(h, "muse-attach-strip") == "gallery" and page_of(h, "btn-muse-attach-cancel") == "gallery"
    app = (ROOT / "backend" / "static" / "app.js").read_text(encoding="utf-8")
    body = app[app.index("function openMuseModalForScene("):]
    assert "showPage('gallery')" in body[:600] or "openMuseModal(" in body[:300]
    att = app[app.index("async function attachMediaToScene("):]
    att = att[:att.index("\nasync function runSceneBatch")]
    assert "showPage('scenes')" in att and "closeMuseModal" not in att


def test_startup_restore_skips_projects_gallery_accounts():
    app = (ROOT / "backend" / "static" / "app.js").read_text(encoding="utf-8")
    i = app.index("const savedPage = rememberedPage(")
    assert "['projects', 'gallery', 'accounts'].includes(savedPage)" in app[i:i + 600]
    assert "10 tài khoản" not in app
