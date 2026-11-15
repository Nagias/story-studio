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
              "current-project-title": None,
              "muse-fleet-pool-grid": "accounts", "muse-fleet-pool-container": "accounts",
              "btn-muse-refresh-accounts": "accounts", "btn-copy-start-fleet-cmd": "accounts",
              "btn-copy-setup-accounts-cmd": "accounts", "muse-modal-status-text": "accounts",
              "muse-reconnect-assistant": "accounts",
              "muse-gallery-grid": "gallery", "muse-gallery-count": "gallery", "btn-clear-all-gallery": "gallery",
              "muse-progress-card": "gallery", "muse-scene-chips": "gallery", "muse-gallery-placeholder": "gallery"}


def test_projects_gallery_accounts_pages_are_real_pages():
    h = INDEX_HTML
    # nút dự án ở thanh bên đã gỡ (15/11/2026); tên dự án đang mở chỉ hiển thị ở thanh trên
    assert 'id="btn-project-dropdown"' not in h
    assert not inside(h, "current-project-title", "ws-sidebar") and page_of(h, "current-project-title") is None
    top_h = h[h.index('<header class="ws-top">'):h.index("</header>")]
    assert 'id="current-project-title"' in top_h
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


PLACEMENT |= {"idea-genre-cards": "idea", "idea-style-cards": "idea", "step1-content-kind": "idea",
              "step1-script-textarea": "idea", "step1-style-select": "idea", "step1-language-select": "idea",
              "step1-case-duration": "idea", "btn-step1-process-script": "idea", "step1-comic-dropzone": "idea",
              "btn-step1-process-comic": "idea", "step1-pacing-select": "idea", "btn-idea-options": "idea"}


def test_genres_declare_three_live_templates():
    js = (ROOT / "backend" / "static" / "genres.js").read_text(encoding="utf-8")
    for code in ("'story'", "'case'", "'comic'"):
        assert f"code: {code}" in js
    assert js.count("enabled: false") == 3


def test_idea_page_engine_select_is_in_hidden_store():
    assert inside(INDEX_HTML, "step1-engine-select", HIDDEN_STORE)


def test_idea_page_options_drawer_holds_pacing():
    assert inside(INDEX_HTML, "step1-pacing-select", "idea-options-block")


def test_genres_loaded_between_app_and_true_crime_and_shipped():
    h = INDEX_HTML
    tag = lambda name: h.index(f'<script src="/static/{name}.js')
    assert tag("app") < tag("genres") < tag("true_crime")
    src = (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8")
    assert src.count("backend/static/genres.js") >= 2


def test_genres_js_has_no_raw_text_in_html():
    js = (ROOT / "backend" / "static" / "genres.js").read_text(encoding="utf-8")
    assert "escapeHtml" in js and "window.projectGenre" in js and "window.renderGenreCards" in js


def test_genres_texts_match_the_preview():
    import re
    js = (ROOT / "backend" / "static" / "genres.js").read_text(encoding="utf-8")
    preview = (ROOT / "docs" / "superpowers" / "specs" / "2026-11-15-giao-dien-gon-ban-xem-thu.html").read_text(encoding="utf-8")
    for name in ("Truyện chữ", "Vụ án có thật", "Truyện tranh"):
        assert f"name: '{name}'" in js and f'name: "{name}"' in preview, name
    for key in ("desc", "rewrite"):
        for text in re.findall(rf'{key}: "([^"]+)"', preview.split("const GENRES")[1].split("};")[0]):
            assert text in js, text


def test_genres_sync_hidden_kind_on_load():
    js = (ROOT / "backend" / "static" / "genres.js").read_text(encoding="utf-8")
    assert "savedKind" in js and "applyStep1ContentKind()" in js


PLACEMENT |= {"tc-progress": "script", "tc-outline-review": "script", "btn-tc-outline-approve": "script",
              "tc-review": "script", "tc-entity-table": "script", "tc-warnings": "script",
              "tc-evidence-canvas": "script", "btn-tc-create-vi": "script", "tc-voice-vi": "script",
              "tc-voice-en": "script", "btn-create-en-version": "publish", "btn-cancel-en-version": "publish", "tc-input-error": "idea",
              "tc-time-estimate": "idea", "ws-case-note": "script"}


def test_case_inputs_kept_hidden_for_existing_code():
    for i in ("tc-case-text", "tc-duration-select", "tc-visual-style", "tc-vision-engine", "step1-engine-select"):
        assert inside(INDEX_HTML, i, HIDDEN_STORE), i


def test_case_blocks_sit_in_their_script_tabs():
    for i in ("tc-progress", "btn-tc-resume", "btn-tc-new-case", "tc-outline-review"):
        assert inside(INDEX_HTML, i, "script-tab-outline"), i
    for i in ("tc-review", "btn-tc-create-vi", "tc-create-hint"):
        assert inside(INDEX_HTML, i, "script-tab-names"), i
    for i in ("tc-voice-vi", "tc-voice-en"):
        assert inside(INDEX_HTML, i, "script-tab-voice"), i
    assert page_of(INDEX_HTML, "ws-case-banner") is None   # dải chung, hiện trên Hình mẫu, Cảnh, Dựng


def test_case_tabs_follow_tracked_case():
    js = (ROOT / "backend" / "static" / "true_crime.js").read_text(encoding="utf-8")
    assert "showPage('script')" in js and "tcSyncCaseTabs" in js
    # tcStartFromStep1 vẫn gửi phân tích (nút Phân tích của cửa sổ cũ đã gỡ)
    start = js.index("async function tcStartFromStep1(")
    assert "await tcAnalyze();" in js[start:js.index("\n}\n", start)]
    ws = (ROOT / "backend" / "static" / "workspace.js").read_text(encoding="utf-8")
    assert "ws-case-note" in ws and "ws-case-banner" in ws and "escapeHtml(" in ws


def test_every_static_asset_has_a_version_query():
    """Trình duyệt giữ bản cũ của file JS/CSS trong bộ nhớ đệm: mỗi tham chiếu phải có ?v= để đổi file là nạp bản mới."""
    import re
    refs = re.findall(r'(?:src|href)="(/static/[^"]+\.(?:js|css)(?:\?[^"]*)?)"', INDEX_HTML)
    assert len(refs) >= 10
    missing = [r for r in refs if "?v=" not in r]
    assert not missing, f"thiếu ?v=: {missing}"


def test_page_change_closes_the_drawer():
    ws = (ROOT / "backend" / "static" / "workspace.js").read_text(encoding="utf-8")
    body = ws[ws.index("function showPage("):ws.index("// ---------- Vụ án đang theo dõi")]
    assert "closeDrawer()" in body
    sp = (ROOT / "backend" / "static" / "scenes_publish_page.js").read_text(encoding="utf-8")
    assert "closeDrawer" not in sp and "pausePlayback()" in sp


def test_publish_page_does_not_fake_a_render():
    """Đường cấm 3: lúc chưa dựng không được hiện vòng quay, 15% hay 'đã hoàn tất'; trình phát chỉ có khi có video."""
    h = INDEX_HTML
    progress = h[h.index('id="step-view-3"'):h.index('id="step-view-4"')]
    assert "fa-spin" not in progress and "Chưa dựng" in progress
    assert 'id="producer-percent-text" class="text-xl font-extrabold text-slate-700 font-mono">0%<' in progress
    assert "Video đã hoàn tất quy trình kết xuất" not in h
    assert inside(h, "cinema-video-player", "publish-final-video")
    assert inside(h, "btn-cinema-download-video", "publish-final-video")
    tag = h[h.index('id="publish-final-video"') - 10:h.index('id="publish-final-video"') + 80]
    assert " hidden" in tag
    assert page_of(h, "publish-no-video") == "publish"
    app = (ROOT / "backend" / "static" / "app.js").read_text(encoding="utf-8")
    load = app[app.index("async function loadCinemaYouTubePackage("):]
    load = load[:load.index("\nasync function ")]
    assert "story_final.mp4" not in load and "renderFinalVideoBlock(project)" in load
    final = app[app.index("function finalVideoOf("):app.index("function renderFinalVideoBlock(")]
    assert "final_video_path" in final and "final_video_url" in final


def test_render_state_follows_the_open_project():
    app = (ROOT / "backend" / "static" / "app.js").read_text(encoding="utf-8")
    full = app[app.index("function renderFullUI("):app.index("function formatDisplayVoice(")]
    assert "paintProducerForCurrentProject()" in full
    listen = app[app.index("function listenToProduceProgress("):app.index("// ================= MODAL 4")]
    assert "AppState.produceState.renderId !== renderId" in listen
    assert "AppState.currentProject.id" not in listen   # URL lấy theo dự án đang dựng, không theo dự án đang mở


def test_space_only_toggles_playback_on_scenes_or_preview():
    app = (ROOT / "backend" / "static" / "app.js").read_text(encoding="utf-8")
    body = app[app.index("function handleGlobalKeydown("):app.index("// ================= SCENE CRUD")]
    assert "closest('button, a, input, textarea, select" in body and "currentPage() === 'scenes'" in body


def test_hidden_sidebar_and_drawer_leave_tab_order():
    css = (ROOT / "backend" / "static" / "workspace.css").read_text(encoding="utf-8")
    collapsed = css[css.index("body.ws-collapsed .ws-sidebar"):]
    assert "visibility: hidden" in collapsed[:200]
    drawer = css[css.index(".ws-drawer {"):css.index(".ws-drawer-head")]
    assert "visibility: hidden" in drawer and "visibility: visible" in drawer


def test_script_list_waits_while_typing():
    js = (ROOT / "backend" / "static" / "script_page.js").read_text(encoding="utf-8")
    body = js[js.index("function renderScriptList("):js.index("window.renderScriptList")]
    assert "rowIsFocused(box)" in body and "page !== 'script'" in body
    assert "'focusout'" in js


def test_comic_projects_may_skip_look_page():
    js = (ROOT / "backend" / "static" / "genres.js").read_text(encoding="utf-8")
    assert "hasCaseTabs" not in js and "onPageShow('look', paintLookSkipNote)" in js
    assert page_of(INDEX_HTML, "look-skip-note") == "look"
    assert "Truyện tranh: hình đã có sẵn, có thể bỏ qua bước này." in INDEX_HTML


def test_case_banner_follows_case_status():
    ws = (ROOT / "backend" / "static" / "workspace.js").read_text(encoding="utf-8")
    for text in ("chờ duyệt dàn ý", "đã phân tích xong, tạo dự án ở Kịch bản", "bị dừng, xem ở Kịch bản"):
        assert text in ws, text
    tc = (ROOT / "backend" / "static" / "true_crime.js").read_text(encoding="utf-8")
    assert "status: p ? status : null" in tc


def test_backend_footer_shows_the_real_port():
    app = (ROOT / "backend" / "static" / "app.js").read_text(encoding="utf-8")
    assert "Port 8000)\"" not in app and "window.location.port" in app
