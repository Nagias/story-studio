# Giao diện gọn kiểu ElevenLabs — kế hoạch code

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng lại lớp giao diện của Story Studio thành 5 trang theo thứ tự làm video (Ý tưởng → Kịch bản và giọng → Hình mẫu → Cảnh → Dựng và xuất bản) cộng 3 trang Dự án, Thư viện Muse, Tài khoản và kết nối; mỗi tính năng ở đúng một chỗ; giữ nguyên mọi tính năng, API, dữ liệu.

**Architecture:** Giữ toàn bộ JS xử lý và mọi id phần tử; dựng khung mới (thanh bên, thanh trên, vùng giữa, ngăn kéo) trong `index.html` và dời từng khối HTML cũ vào đúng trang. Điều hướng ở file mới `workspace.js`, giao diện ở file mới `workspace.css` (CSS viết tay, không build Tailwind). Hai test bố cục đọc `index.html` làm khoá cứng: id cũ không được mất ngoài danh sách gỡ đã duyệt, và mỗi id nằm đúng trang.

**Tech Stack:** HTML/CSS/JS thuần (không thêm thư viện), FastAPI, pytest, Node.js (chỉ để `tools/check.py` kiểm cú pháp JS).

**Spec:** `docs/superpowers/specs/2026-11-15-giao-dien-gon-design.md` (bản xem thử: `docs/superpowers/specs/2026-11-15-giao-dien-gon-ban-xem-thu.html`)

## Global Constraints

- Nhánh `giao-dien-gon` (tách từ `master` 0fd5e35). Không commit lên `master`, không `--no-verify`. Commit tiếng Việt dạng `giao diện: <mô tả>`, mỗi task ít nhất một commit.
- Python: `.venv\Scripts\python.exe`, in tiếng Việt thêm `-X utf8`.
- Không đổi hành vi của API, service, dữ liệu dự án. Phần máy chủ mới duy nhất: `backend/routers/connections.py` (Task 11).
- Mọi id có trong `tests/data/ui_ids_truoc_giao_dien_gon.txt` phải còn trong `index.html`, trừ id ghi trong `REMOVED` của `tests/test_ui_ids_preserved.py`, mỗi id kèm lý do trỏ về mục 4.2 spec.
- Mọi id mà JS gọi bằng chuỗi cố định (`getElementById('…')`, `tcEl('…')`, `el('…')`) phải có trong `index.html` hoặc trong `JS_BUILT_IDS` của cùng test. Gỡ một id khỏi HTML thì gỡ luôn chỗ JS gọi nó.
- Màu: vùng làm việc `#FFFFFF`; thanh bên `#F9FAFB`; mặt phụ `#F4F4F5`; đường kẻ `1px solid #E4E4E7`; nút chính `background:#09090B; color:#FFFFFF; border-radius:9999px; padding:8px 16px; font-size:13px; font-weight:500`; nút phụ viền `1px solid #E4E4E7`, rê chuột `#F4F4F5`. Không đổ bóng nặng. Màu đỏ/vàng/xanh lá chỉ dùng cho trạng thái lỗi/cảnh báo/đạt.
- Chữ: `'Be Vietnam Pro', sans-serif` toàn app (Google Fonts, thay `Inter`). Điều hướng 13–14px nặng 500 màu `#52525B`, đang chọn `#09090B` nền `#F4F4F5` bo 6px; nhãn nhóm 11–12px nặng 500 `#A1A1AA`; tiêu đề trang 20–24px nặng 600 `letter-spacing:-0.02em` màu `#09090B`; chữ thân 14–15px `line-height:1.6` màu `#18181B`.
- Khung: thanh bên 240px thu gọn được, biểu tượng SVG 16px nét 1.5px; thanh trên cao 52px, kẻ dưới `1px solid #E4E4E7`; vùng giữa `max-width:1100px` canh giữa; thẻ bo 12px viền `#E4E4E7`; trang khoá 100vh, chỉ vùng giữa và ngăn kéo cuộn.
- Tên 8 trang (id `page-<mã>`, `data-page="<mã>"`), đúng thứ tự trên thanh bên: `idea` "Ý tưởng", `script` "Kịch bản và giọng", `look` "Hình mẫu", `scenes` "Cảnh", `publish` "Dựng và xuất bản", `projects` "Dự án", `gallery` "Thư viện Muse", `accounts` "Tài khoản và kết nối" (ghim đáy).
- Chữ từ máy chủ hay người dùng chèn vào HTML phải qua `escapeHtml()` (đường cấm 9; file JS mới bị test kiểm với ngoại lệ 0).
- Một sự kiện chỉ gắn một cách (đường cấm 10): khối dời đi mang `onclick` thì không thêm `addEventListener` cho cùng nút.
- localStorage đọc ghi trong try/catch; trang vẫn chạy khi bị chặn.
- Không bấm thật nút tốn tiền (LLM, Muse, ảnh trả phí) khi kiểm; không sửa 3 mục MẪU (`proj_crime_52c3a5e8`, `proj_crime_8329b12d`, `_cases/case_7dcf6158`), chỉ mở xem.
- `FEATURE_MAP.md` sửa trong cùng commit với code đổi chỗ hay gỡ id (test `tests/test_feature_map.py` bắt tên không còn trong code).

## Review Focus

1. Đang theo dõi một vụ chưa tạo dự án trong lúc dự án X đang mở: trang Kịch bản chỉ hiện việc của vụ (Dàn ý, Tên hư cấu, Giọng đọc của vụ); Hình mẫu, Cảnh, Dựng vẫn là của X kèm dải "Vụ mới đang phân tích"; sửa trên các trang đó chỉ ghi vào X. Kiểm ở Task 8.
2. Tải lại trang (F5) khi vụ đang phân tích → app tự mở trang Kịch bản, tiếp tục hỏi tiến độ (vụ lưu trong localStorage `story_studio_true_crime_case_id`). Kiểm ở Task 8.
3. `Esc` khi đang gõ trong ô nhập chỉ thoát ô; khi không gõ thì đóng ngăn kéo hay ô nổi đang mở, không đổi trang. Kiểm ở Task 2.
4. Màn 1024px và thanh bên thu gọn: không trang nào tràn ngang. Kiểm ở Task 12 cho đủ 8 trang.
5. Chọn ảnh/video từ Thư viện Muse cho một cảnh (`openMuseModalForScene()`) → gắn xong thì quay về trang Cảnh, đúng cảnh đó có ảnh mới. Kiểm ở Task 6 (giả lập trả lời máy chủ, không gọi Muse).

---

### Task 1: Khoá cứng giữ id và test bố cục

**Files:**
- Create: `tests/data/ui_ids_truoc_giao_dien_gon.txt` (mỗi dòng một id, sắp xếp, lấy từ `backend/static/index.html` ở commit 0fd5e35: 327 id)
- Create: `tests/ui_html.py`
- Create: `tests/test_ui_ids_preserved.py`
- Create: `tests/test_workspace_layout.py`
- Modify: `TASKS.md` (thêm mục checklist của kế hoạch này, 12 task)

**Interfaces:**
- Produces: `tests/ui_html.py`
  - `ids_in(html: str) -> set[str]`
  - `ancestors(html: str, element_id: str) -> list[dict[str, str]]` — thuộc tính của từng thẻ cha, gần nhất trước; `KeyError` nếu không có id.
  - `page_of(html: str, element_id: str) -> str | None` — giá trị `data-page` của thẻ cha gần nhất có thuộc tính đó.
  - `inside(html: str, element_id: str, container_id: str) -> bool`
  - Bộ đọc dùng `html.parser` của thư viện chuẩn, bỏ qua thẻ rỗng (`input`, `img`, `br`, `meta`, `link`, `hr`, `source`), gặp thẻ đóng thì gỡ ngăn xếp tới đúng thẻ mở.
  - `js_fixed_ids() -> dict[str, list[str]]` — id mà các file `backend/static/*.js` gọi bằng chuỗi cố định, kèm tên file.
- Produces: `tests/test_ui_ids_preserved.py` có `REMOVED: dict[str, str]` (id → lý do) và `JS_BUILT_IDS: set[str]`; task sau thêm vào đây.
- Produces: `tests/test_workspace_layout.py` có `PLACEMENT: dict[str, str | None]` (id → mã trang; `None` là nằm ngoài mọi trang, ví dụ thanh bên) và `HIDDEN_STORE = "ws-hidden-inputs"`; task sau thêm dòng vào `PLACEMENT`.

- [ ] **Step 1: Tạo file id gốc**

Run: `.venv\Scripts\python.exe -X utf8 -c "import re,pathlib;h=pathlib.Path('backend/static/index.html').read_text(encoding='utf-8');pathlib.Path('tests/data').mkdir(exist_ok=True);pathlib.Path('tests/data/ui_ids_truoc_giao_dien_gon.txt').write_text(chr(10).join(sorted(set(re.findall(r'\sid=\"([^\"]+)\"',h))))+chr(10),encoding='utf-8')"`
Expected: file có đúng 327 dòng.

- [ ] **Step 2: Viết test**

```python
# tests/test_ui_ids_preserved.py
def test_no_id_lost_except_approved_removals():
    before = set(BASELINE.read_text(encoding="utf-8").split())
    lost = before - ids_in(INDEX_HTML) - set(REMOVED)
    assert not lost, f"Mất id không có trong danh sách gỡ (spec mục 4.2): {sorted(lost)}"

def test_removed_ids_are_really_gone():
    assert not (set(REMOVED) & ids_in(INDEX_HTML))

def test_every_fixed_js_id_exists():
    missing = {i: files for i, files in js_fixed_ids().items() if i not in ids_in(INDEX_HTML) | JS_BUILT_IDS}
    assert not missing, f"JS gọi id mà trang không có: {missing}"

# tests/test_workspace_layout.py
def test_each_id_sits_on_its_page():
    wrong = {i: (page_of(INDEX_HTML, i), p) for i, p in PLACEMENT.items() if page_of(INDEX_HTML, i) != p}
    assert not wrong, f"id nằm sai trang (đang ở, phải ở): {wrong}"

def test_ui_html_reader():   # tự kiểm bộ đọc trên một đoạn HTML nhỏ
    h = '<div data-page="a"><section id="s"><input id="i"><p id="p">x</p></section></div><div id="o"></div>'
    assert page_of(h, "p") == "a" and page_of(h, "i") == "a" and page_of(h, "o") is None
    assert inside(h, "p", "s") and not inside(h, "o", "s")
```

`js_fixed_ids()` đặt trong `tests/ui_html.py`: quét `backend/static/*.js` theo regex `(?:getElementById|tcEl|\bel)\(\s*['"]([\w-]+)['"]\s*\)`, trả `dict[id, list[tên file]]`. Lúc này `REMOVED = {}`, `JS_BUILT_IDS = set()`, `PLACEMENT = {}`.

- [ ] **Step 3: Chạy test**

Run: `.venv\Scripts\python.exe -m pytest tests\test_ui_ids_preserved.py tests\test_workspace_layout.py -q`
Expected: 5 passed (trang hiện tại khớp file gốc; đã đo 15/11: 309 id JS gọi cố định, thiếu 0).

- [ ] **Step 4: Ghi checklist vào `TASKS.md`** (tiêu đề "TASKS — giao diện gọn (15/11/2026, nhánh `giao-dien-gon`)", 12 dòng `- [ ]` theo 12 task, dòng đầu trỏ spec và plan).

- [ ] **Step 5: Commit**

```bash
git add tests/data/ui_ids_truoc_giao_dien_gon.txt tests/ui_html.py tests/test_ui_ids_preserved.py tests/test_workspace_layout.py TASKS.md
git commit -m "giao diện: khoá cứng giữ id và test bố cục cho giao diện gọn"
```

---

### Task 2: Khung mới (thanh bên, thanh trên, 8 trang, ngăn kéo)

**Files:**
- Create: `backend/static/workspace.css`, `backend/static/workspace.js`
- Modify: `backend/static/index.html` (đầu trang 157–270, vỏ 4 bước, thanh trạng thái đáy 1291–1314)
- Modify: `backend/static/app.js` (`switchStep()` ở dòng ~3486)
- Modify: `tools/build_release.py` (`REQUIRED_FILES` dòng ~35, danh sách file giao diện dòng ~191)
- Modify: `FEATURE_MAP.md` (mục 1, 2.1)
- Test: `tests/test_workspace_layout.py`, `tests/test_ui_ids_preserved.py`

**Interfaces:**
- Produces (`workspace.js`, gắn lên `window`):
  - `showPage(name: string): void` — `name` là một trong 8 mã trang; bỏ thuộc tính `hidden` của `#page-<name>`, gắn `hidden` cho 7 trang kia; đặt `aria-current="page"` cho nút `[data-go=<name>]`; cập nhật `#ws-crumb`; cuộn `#ws-canvas` về đầu; gọi các móc của trang (`onPageShow(name, fn)`); nhớ trang theo dự án ở localStorage khoá `ws_page_<project_id>`.
  - `onPageShow(name: string, fn: () => void): void` — đăng ký móc, chạy mỗi lần trang được mở.
  - `openDrawer(title: string, contentEl: HTMLElement): void`, `closeDrawer(): void` — ngăn kéo `#ws-drawer`; nội dung là khối HTML có sẵn trong trang, được dời vào ngăn khi mở và trả về chỗ cũ khi đóng.
  - `currentPage(): string`
- Produces (`index.html`): `#ws-sidebar`, 8 nút `.ws-nav[data-go]`, `#btn-ws-toggle-sidebar`, `#ws-crumb`, `#ws-search`, `#ws-save-state`, `#ws-canvas`, `#ws-drawer`, `#ws-drawer-title`, `#ws-drawer-body`, `#btn-ws-drawer-close`, 8 thẻ `<section id="page-<mã>" data-page="<mã>">`, khối ẩn `<div id="ws-hidden-inputs" hidden>`.
- Produces (`app.js`): `switchStep(n)` giữ tên, chỉ còn: đặt `AppState.currentStep = n` rồi gọi `showPage({1:'idea', 2:'scenes', 3:'publish', 4:'publish'}[n])`. Bước 4 gọi `loadCinemaYouTubePackage()` chuyển thành móc `onPageShow('publish', …)`.

- [ ] **Step 1: Thêm vào test**

```python
# test_workspace_layout.py
PLACEMENT |= {"step-view-1": "idea", "step-view-2": "scenes", "step-view-3": "publish", "step-view-4": "publish"}

def test_sidebar_order():
    assert NAV_ORDER(INDEX_HTML) == ["idea", "script", "look", "scenes", "publish", "projects", "gallery", "accounts"]

def test_workspace_assets_loaded_in_order():
    h = INDEX_HTML
    assert h.index("/static/tailwind.css") < h.index("/static/workspace.css")
    assert h.index("/static/workspace.js") < h.index("/static/app.js")
    assert "Be+Vietnam+Pro" in h and "family=Inter" not in h

def test_release_ships_workspace_files():
    src = Path("tools/build_release.py").read_text(encoding="utf-8")
    assert src.count("backend/static/workspace.css") >= 1 and src.count("backend/static/workspace.js") >= 2
```

`NAV_ORDER(html)` trong `tests/ui_html.py`: danh sách `data-go` của các phần tử có class `ws-nav`, theo thứ tự xuất hiện. Thêm vào `REMOVED`: `step-nav-1`…`step-nav-4` (lý do: "spec 4.2: thay bằng thanh bên").

- [ ] **Step 2: Chạy, thấy đỏ**

Run: `.venv\Scripts\python.exe -m pytest tests\test_workspace_layout.py tests\test_ui_ids_preserved.py -q`
Expected: FAIL (`test_each_id_sits_on_its_page`, `test_sidebar_order`, `test_workspace_assets_loaded_in_order`, `test_release_ships_workspace_files`, `test_removed_ids_are_really_gone`).

- [ ] **Step 3: Viết `workspace.css`** — biến màu, chữ ở Global Constraints làm biến CSS trên `:root`; các lớp `ws-shell`, `ws-sidebar`, `ws-nav`, `ws-micro`, `ws-top`, `ws-canvas`, `ws-page`, `ws-h1`, `ws-lede`, `ws-btn`, `ws-btn-primary`, `ws-btn-ghost`, `ws-card`, `ws-drawer`, `ws-tabs`, `ws-tab`. Lấy giá trị từ bản xem thử (`<style>` của file `docs/superpowers/specs/2026-11-15-giao-dien-gon-ban-xem-thu.html`). Đặt `body { font-family: 'Be Vietnam Pro', sans-serif; }` thay khối `font-family: 'Inter'` trong `<style>` của `index.html`.

- [ ] **Step 4: Viết `workspace.js`** theo Interfaces; thêm: nút `#btn-ws-toggle-sidebar` thu/mở (`body.ws-collapsed`, nhớ ở localStorage `ws_sidebar_collapsed`); màn dưới 860px tự thu; `Esc` (gắn một lần) đóng ngăn kéo nếu đang mở, trừ khi tiêu điểm đang ở `input`, `textarea`, `select`, `[contenteditable]` (khi đó để `handleGlobalKeydown()` xử lý như cũ); ô `#ws-search` tìm theo số cảnh hoặc chữ trong `scene.text` của `AppState.currentProject.scenes`, Enter thì `showPage('scenes')`, đặt `AppState.selectedSceneIndex` và cuộn tới thẻ cảnh.

- [ ] **Step 5: Dựng khung trong `index.html`** — thay đầu trang cũ bằng thanh bên + thanh trên; `#step-view-1` vào `#page-idea`, `#step-view-2` vào `#page-scenes`, `#step-view-3` rồi `#step-view-4` vào `#page-publish`; bỏ class `hidden` ban đầu của 4 khối bước (ẩn hiện giờ theo trang); `#page-script`, `#page-look` tạm có tiêu đề và câu "Đang chuyển tính năng về đây"; `#page-projects`, `#page-gallery`, `#page-accounts` tạm có nút mở cửa sổ cũ tương ứng (`openProjectModal()`, `openMuseModal()`). Các nút hành động cũ của đầu trang (`#btn-open-true-crime-modal`, `#btn-muse-cloud-status`, `#btn-open-comic-modal`, `#btn-open-master-storyboard-modal`, `#btn-open-script-modal`, `#btn-save-project`, `#btn-create-en-version`, `#btn-produce-long-video`) và `#btn-project-dropdown` tạm đặt ở phải thanh trên dạng nút biểu tượng (các task sau dời hoặc gỡ). `#backend-status-dot`, `#backend-status-text` vào đáy thanh bên. Nạp `workspace.css` sau `tailwind.css`, `workspace.js` trước `app.js`; đổi link Google Fonts sang `Be+Vietnam+Pro:wght@400;500;600;700` (giữ JetBrains Mono).

- [ ] **Step 6: Sửa `switchStep()`** theo Interfaces; xoá phần đổi class của `step-nav-*`.

- [ ] **Step 7: `tools/build_release.py`** — thêm `workspace.css`, `workspace.js` vào `REQUIRED_FILES` (kèm chú thích) và `workspace.js` vào bộ file giao diện được quét ở dòng ~191.

- [ ] **Step 8: Chạy test**

Run: `.venv\Scripts\python.exe -m pytest tests\test_workspace_layout.py tests\test_ui_ids_preserved.py tests\test_feature_map.py tests\test_architecture.py -q`
Expected: PASS hết.

- [ ] **Step 9: Kiểm trên trình duyệt** — mở server thử `preview_start {name: "story-studio-8010"}`, `?project_id=proj_ea5b04db`. Bấm 8 mục thanh bên: đúng trang hiện, `aria-current` đúng một mục; Bước 1, 2, 3, 4 cũ chạy trong trang mới (bấm thẻ cảnh, phát thử, mở cửa sổ Muse); thu thanh bên; gõ "3" vào ô tìm rồi Enter → trang Cảnh, cảnh 003 được chọn; mở một ô nhập, gõ, bấm `Esc` → chỉ thoát ô (Review Focus 3). `read_console_messages` không lỗi. So `projects/` trước và sau không đổi.

- [ ] **Step 10: Sửa `FEATURE_MAP.md`** mục 1 (cách điều hướng, `showPage()`), 2.1 (thanh bên thay thanh bước) rồi commit

```bash
git add backend/static/workspace.css backend/static/workspace.js backend/static/index.html backend/static/app.js tools/build_release.py FEATURE_MAP.md tests/
git commit -m "giao diện: khung mới thanh bên, thanh trên, 8 trang, ngăn kéo"
```

---

### Task 3: Trang Kịch bản và giọng (phần chung cho mọi thể loại)

**Files:**
- Create: `backend/static/script_page.js`
- Modify: `backend/static/index.html` (dời `#btn-add-scene` từ thanh trên của Bước 2; dời khối giọng đọc dòng ~788–827 và `#btn-regen-all-voices`)
- Modify: `backend/static/app.js` (khuôn thẻ cảnh trong `renderSceneList()`: bỏ ô sửa lời, nút sắp xếp cảnh và phần giọng từng cảnh (nghe, tua, thu lại), thay bằng một dòng lời kể chỉ đọc, tối đa 2 dòng)
- Modify: `tools/build_release.py`, `FEATURE_MAP.md` (mục 2.3)
- Test: `tests/test_workspace_layout.py`

**Interfaces:**
- Consumes: `showPage`, `onPageShow` (Task 2); `updateSceneText(index, text)`, `updateSceneTextLive(index, text)`, `moveScene(index, dir)`, `duplicateScene(index)`, `deleteScene(index)`, `handleAddScene()`, `playSceneVoice(…)`, `seekSceneAudio(…)`, `regenerateSceneVoice(index)`, `handleRegenAllVoices()` (app.js, giữ nguyên; đọc chữ ký thật của `playSceneVoice`, `seekSceneAudio` trong khuôn của `renderSceneList()` rồi gọi y như thẻ cảnh đang gọi).
- Produces: `window.renderScriptList(): void` — vẽ danh sách lời kể vào `#script-scene-list`; mỗi dòng: số cảnh, ô sửa lời (`input` gọi `updateSceneTextLive`, `change` gọi `updateSceneText`), thời lượng, nút nghe giọng và thanh tua của cảnh, thanh công cụ khi di chuột (lên, xuống, nhân bản, xoá, thu lại giọng). Sau mỗi thao tác đổi cấu trúc thì gọi lại chính nó.
- Produces (`index.html`): trong `#page-script` có thanh thẻ `.ws-tabs` với 4 thẻ `data-tab="outline|names|lines|voice"` (2 thẻ đầu ẩn cho tới Task 8), khối `#script-tab-lines` (chứa `#btn-add-scene`, `#script-scene-list`), khối `#script-tab-voice`.

- [ ] **Step 1: Thêm vào test**

```python
PLACEMENT |= {"btn-add-scene": "script", "select-voice": "script", "btn-preview-voice-sample": "script",
              "btn-regen-all-voices": "script", "script-scene-list": "script"}

def test_scene_text_is_edited_in_one_place():
    app = Path("backend/static/app.js").read_text(encoding="utf-8")
    body = app[app.index("function renderSceneList("):app.index("\nfunction ", app.index("function renderSceneList(") + 10)]
    page = Path("backend/static/script_page.js").read_text(encoding="utf-8")
    for fn in ("updateSceneText(", "updateSceneTextLive(", "moveScene(", "deleteScene(", "playSceneVoice(", "regenerateSceneVoice("):
        assert fn not in body and fn in page, fn
```

- [ ] **Step 2: Chạy, thấy đỏ** — Run: `.venv\Scripts\python.exe -m pytest tests\test_workspace_layout.py -q` → Expected: FAIL ở hai test trên.

- [ ] **Step 3: Viết `script_page.js`** theo Interfaces; đăng ký `onPageShow('script', renderScriptList)`; chữ lời kể chèn qua `escapeHtml()`. Nạp sau `app.js` trong `index.html`; thêm vào `tools/build_release.py` như Task 2 Step 7.

- [ ] **Step 4: Dời khối HTML và sửa khuôn thẻ cảnh** như phần Files.

- [ ] **Step 5: Chạy test** — Run: `.venv\Scripts\python.exe -m pytest tests\test_workspace_layout.py tests\test_ui_ids_preserved.py tests\test_architecture.py tests\test_feature_map.py tests\test_review_voice_pacing.py -q` → Expected: PASS.

- [ ] **Step 6: Kiểm trên trình duyệt** (`proj_ea5b04db`): sửa lời cảnh 1 → sang trang Cảnh thấy dòng chỉ đọc đổi theo; đợi 2 giây, `read_network_requests` có `PUT /api/projects/proj_ea5b04db`; thêm cảnh, nhân bản, đổi chỗ, xoá (rồi Ctrl+Z không có — trả lại bằng tay: xoá cảnh vừa thêm) → danh sách hai trang khớp nhau; nghe thử giọng mẫu. Không bấm "Thu lại giọng" (tốn Edge-TTS/VieNeu). Console không lỗi. Cuối bước: `project.json` của `proj_ea5b04db` có đúng số cảnh như trước khi thử.

- [ ] **Step 7: Sửa `FEATURE_MAP.md`, commit**

```bash
git commit -am "giao diện: trang Kịch bản và giọng, sửa lời kể ở một chỗ"
```
(nhớ `git add backend/static/script_page.js` trước)

---

### Task 4: Trang Hình mẫu

**Files:**
- Modify: `backend/static/index.html` (nội dung `#modal-character-sheets`, `#modal-location-sheets` thành khối trong `#page-look`; dòng phong cách dự án + ô nổi chứa `#select-project-style`)
- Modify: `backend/static/character_sheets.js` (dòng ~183–204), `backend/static/location_sheets.js` (dòng ~214–235), `backend/static/workspace.js`
- Modify: `FEATURE_MAP.md` (mục 2.6.8, 2.6.9, 2.3 dòng Nâng cao)
- Test: `tests/test_workspace_layout.py`, `tests/test_ui_ids_preserved.py`

**Interfaces:**
- Consumes: `window.refreshCharacterSheets()`, `window.refreshLocationSheets()` (đã có).
- Produces: `#look-style-line` (chữ tên phong cách của dự án, lấy từ nhãn `<option>` đang chọn của `#select-project-style`), `#btn-look-change-style` mở ô nổi `#look-style-popover` chứa `#select-project-style` và câu cảnh báo nguyên văn của spec mục 4.4.
- Hai khối mang lại id `modal-character-sheets`, `modal-location-sheets` (để code hiện có tìm được) nhưng là `<section>` luôn hiện trong trang.
- Trong mỗi file `character_sheets.js`, `location_sheets.js`: tách `open()` thành `start()` (nạp danh sách + bắt đầu vòng hỏi lại như `open()` đang làm, không đụng class `hidden`) và `close()` thành `stop()` (dừng vòng hỏi, không ẩn gì). Xuất `window.startCharacterSheets`, `window.stopCharacterSheets`, `window.startLocationSheets`, `window.stopLocationSheets`. Chỗ đang gọi `close()` khi đổi dự án và khi bấm `Esc` đổi thành `stop()`, rồi nếu trang Hình mẫu đang mở thì `start()` lại cho dự án mới. Giữ `window.refreshCharacterSheets`, `window.refreshLocationSheets` cho chỗ khác đang gọi.

- [ ] **Step 1: Thêm vào test**

```python
PLACEMENT |= {"modal-character-sheets": "look", "modal-location-sheets": "look", "select-project-style": "look",
              "btn-look-change-style": "look", "select-image-provider": "look"}
REMOVED |= {"btn-character-sheets": "spec 4.2/4.1: Hình mẫu là một trang, không còn nút mở cửa sổ",
            "btn-location-sheets": "như trên",
            "btn-close-character-sheets": "như trên", "btn-close-location-sheets": "như trên"}

def test_style_popover_warns_about_old_prompts():
    assert "Mô tả ảnh của các cảnh đã viết theo phong cách cũ" in INDEX_HTML
```

- [ ] **Step 2: Chạy, thấy đỏ** (`test_each_id_sits_on_its_page`, `test_removed_ids_are_really_gone`, `test_style_popover_warns_about_old_prompts`).

- [ ] **Step 3: Dời khối, sửa hai file JS** — bỏ các dòng gắn/ẩn hiện `#btn-character-sheets`, `#btn-location-sheets`, `#btn-close-*`; điều kiện `usable()` cũ chuyển thành: không dùng được thì khối hiện câu lý do thay cho danh sách. `workspace.js`: `onPageShow('look', () => { startCharacterSheets(); startLocationSheets(); renderLookStyleLine(); })`; khi mở trang khác thì gọi hai hàm `stop…()`. Dời `#select-image-provider` vào `#page-look` cạnh dòng phong cách (spec 4.5).

- [ ] **Step 4: Chạy test** — Run: `.venv\Scripts\python.exe -m pytest tests\test_workspace_layout.py tests\test_ui_ids_preserved.py tests\test_one_flow.py tests\test_case_project_builder.py tests\test_feature_map.py tests\test_architecture.py -q` → Expected: PASS (hai test phong cách cũ không đổi vẫn đạt).

- [ ] **Step 5: Kiểm trên trình duyệt**: `proj_ea5b04db` và mở xem `proj_crime_52c3a5e8` → trang Hình mẫu hiện danh sách nhân vật, bối cảnh như cửa sổ cũ; đổi dự án khi đang ở Hình mẫu → danh sách đổi theo dự án mới, trang không bị ẩn; bấm `Esc` → trang vẫn hiện; bấm "Đổi" → ô nổi có cảnh báo, `Esc` đóng; không bấm "Vẽ bảng", "Tìm bối cảnh" (tốn Muse, LLM). Console không lỗi.

- [ ] **Step 6: Sửa `FEATURE_MAP.md`, commit** — `giao diện: trang Hình mẫu gom nhân vật, bối cảnh, phong cách dự án`.

---

### Task 5: Trang Cảnh và trang Dựng và xuất bản

**Files:**
- Modify: `backend/static/index.html` (cột phải của Bước 2 dòng ~647–997; Bước 3 dòng ~1000–1086; Bước 4)
- Modify: `backend/static/app.js` (`startProduceLongVideo()`: sau khi xếp việc dựng gọi `showPage('publish')` qua `switchStep(3)` như cũ; bỏ gắn sự kiện `#btn-producer-goto-cinema`)
- Modify: `FEATURE_MAP.md` (mục 2.3, 2.4, 2.5)
- Test: `tests/test_workspace_layout.py`, `tests/test_ui_ids_preserved.py`

**Interfaces:**
- Consumes: `openDrawer`, `closeDrawer`, `onPageShow` (Task 2).
- Produces (`index.html`):
  - Trang Cảnh: thanh tỉ lệ (giữ nguyên chỗ hiện của `climax_video.js`), `#btn-climax-video-pick`, `#btn-climax-video-run`, `#btn-auto-gen-all` (nhãn "Tạo ảnh còn thiếu"), nút phụ `#btn-scenes-more` mở ô nổi chứa `#btn-regen-all-images`; nút `#btn-scenes-preview` mở ngăn kéo chứa khối Live Studio Player (dòng ~650–740, gồm `#btn-preview-play-toggle`).
  - Trang Dựng: `#btn-produce-from-board` (nút chính), `#btn-render-settings` mở ngăn kéo chứa khối `#render-settings` (`#select-bgm`, `#bgm-upload-input`, `#toggle-audio-ducking`, `#toggle-hardsub`, `#select-transition`, `#select-subtitle-style`); khối tiến độ (Bước 3 thu gọn: thanh, 5 giai đoạn, nhật ký trong `<details>`); thành phẩm và gói YouTube (Bước 4).

- [ ] **Step 1: Thêm vào test**

```python
PLACEMENT |= {"scene-list-container": "scenes", "btn-auto-gen-all": "scenes", "btn-climax-video-pick": "scenes",
              "btn-climax-video-run": "scenes", "btn-regen-all-images": "scenes", "btn-preview-play-toggle": "scenes",
              "btn-produce-from-board": "publish", "select-bgm": "publish", "select-transition": "publish",
              "select-subtitle-style": "publish", "toggle-hardsub": "publish", "toggle-audio-ducking": "publish",
              "cinema-video-player": "publish", "btn-yt-seo-generate": "publish"}
REMOVED |= {"btn-producer-goto-cinema": "spec 4.2: Bước 3 gộp vào trang Dựng, không cần nút sang rạp chiếu"}
```

- [ ] **Step 2: Chạy, thấy đỏ.**

- [ ] **Step 3: Dời khối** như Files/Interfaces. Khối dời vào ngăn kéo nằm sẵn trong trang (ẩn) và được `openDrawer()` dời vào ngăn khi mở, trả lại khi đóng, nên `page_of()` của chúng vẫn là trang của nó.

- [ ] **Step 4: Chạy test** — như Task 4 Step 4, thêm `tests\test_video_share_gate.py` → Expected: PASS.

- [ ] **Step 5: Kiểm trên trình duyệt** (`proj_ea5b04db`): ngăn xem thử phát được cảnh 1 có tiếng; đổi nhạc nền, kiểu phụ đề trong ngăn Tuỳ chỉnh dựng → `PUT` lưu; trang Dựng hiện video thành phẩm cũ và phát được; bấm "Dựng video" với giả lập trả lời máy chủ trong trình duyệt (`javascript_tool` thay `fetch` cho `produce-long-video` trả 409 `VIDEO_SHARE_LOW`) → hộp hỏi bản nháp hiện, chọn không → không ghi file. Không dựng thật. Console không lỗi.

- [ ] **Step 6: Sửa `FEATURE_MAP.md`, commit** — `giao diện: trang Cảnh chỉ còn hình, trang Dựng gom thiết lập dựng và tiến độ`.

---

### Task 6: Trang Dự án, Thư viện Muse, Tài khoản (phần Muse)

**Files:**
- Modify: `backend/static/index.html` (`#modal-project-manager` dòng ~1645; `#modal-muse-cloud` dòng ~1776–1987)
- Modify: `backend/static/app.js` (`openProjectModal()` ~4254, `openMuseModal()` ~4877, `openMuseModalForScene()` ~2632, `attachMediaToScene()`, `closeAllModals()` ~4365)
- Modify: `FEATURE_MAP.md` (mục 2.1, 2.6.1, 2.6.6)
- Test: `tests/test_workspace_layout.py`, `tests/test_ui_ids_preserved.py`

**Interfaces:**
- `openProjectModal()` → `showPage('projects')` + nạp danh sách như cũ. `openMuseModal()` → `showPage('accounts')` + nạp tài khoản như cũ. `openMuseModalForScene(index)` → nhớ cảnh đang gắn (biến sẵn có của hàm), `showPage('gallery')`, hiện dải "Đang chọn ảnh cho cảnh NNN · Huỷ"; `attachMediaToScene()` xong thì `showPage('scenes')`.
- Ô chọn dự án đầu thanh bên (`#btn-project-dropdown` dời vào đây) mở trang Dự án.
- Phần tài khoản (`#muse-fleet-pool-container` và các khối quanh nó, hai nút chép lệnh, `#btn-muse-refresh-accounts`, trạng thái `#muse-modal-status-*`) vào `#page-accounts`. Phần thư viện (`#muse-gallery-grid`, `#muse-gallery-count`, `#btn-clear-all-gallery`, `#muse-progress-card`, `#muse-scene-chips`, `#muse-gallery-placeholder`) vào `#page-gallery`. `#btn-muse-cloud-status` dời thành chữ trạng thái Muse ở phải thanh trên, bấm mở trang Tài khoản.

- [ ] **Step 1: Thêm vào test**

```python
PLACEMENT |= {"project-list-items": "projects", "btn-create-project": "projects", "btn-project-dropdown": None,
              "muse-fleet-pool-grid": "accounts", "btn-muse-refresh-accounts": "accounts",
              "muse-gallery-grid": "gallery", "btn-clear-all-gallery": "gallery"}
REMOVED |= {"modal-project-manager": "spec 4.1: cửa sổ thành trang Dự án",
            "modal-muse-cloud": "spec 4.1: cửa sổ tách thành trang Tài khoản và trang Thư viện Muse",
            "btn-close-project-modal": "như trên", "btn-close-muse-modal": "như trên",
            "btn-close-muse-modal-footer": "như trên"}
```

(`btn-project-dropdown` nằm ở thanh bên, ngoài mọi trang: `page_of` trả `None`.)

- [ ] **Step 2: Chạy, thấy đỏ.**

- [ ] **Step 3: Dời khối, sửa 5 hàm** theo Interfaces; `closeAllModals()` bỏ hai cửa sổ đã gỡ.

- [ ] **Step 4: Chạy test** — như Task 4 Step 4, thêm `tests\test_muse_fleet_routing.py` → Expected: PASS.

- [ ] **Step 5: Kiểm trên trình duyệt**: trang Dự án liệt kê dự án, bấm `proj_ea5b04db` mở đúng dự án; trang Tài khoản hiện các tài khoản Muse như cửa sổ cũ (đọc, không bấm chọn tài khoản); trang Thư viện hiện ảnh; trên trang Cảnh mở "Chọn từ Thư viện" của cảnh 2 → sang Thư viện có dải đang chọn → bấm một ảnh với `fetch` giả lập trả lời `PUT` → về trang Cảnh (Review Focus 5); sau đó tải lại dự án, `project.json` không đổi. Không bấm "Xoá toàn bộ thư viện".

- [ ] **Step 6: Sửa `FEATURE_MAP.md`, commit** — `giao diện: trang Dự án, Thư viện Muse, tài khoản Muse thay cho hai cửa sổ`.

---

### Task 7: Khuôn thể loại và trang Ý tưởng

**Files:**
- Create: `backend/static/genres.js`
- Modify: `backend/static/index.html` (Bước 1 dòng ~274–587)
- Modify: `backend/static/app.js` (`applyStep1ContentKind()`; phần đọc nhân vật kiểu cũ của Bước 1: `DOM.step1CharName`, `DOM.step1CharAnchor`, `AppState.characterReferenceImage` và các hàm ảnh tham chiếu dòng ~3630–3670, chỗ gửi `charRefImage` dòng ~3747)
- Modify: `tools/build_release.py`, `FEATURE_MAP.md` (mục 2.2, 3.A, 3.B)
- Test: `tests/test_workspace_layout.py`, `tests/test_ui_ids_preserved.py`, `tests/test_one_flow.py` (không sửa, phải vẫn đạt)

**Interfaces:**
- Produces `window.GENRES: Array<{code: 'story'|'case'|'comic'|string, name: string, desc: string, rewriteNote: string, hasCaseTabs: boolean, skipLook: boolean, enabled: boolean, contentKind?: 'story'|'case'}>` — ba mục bật (`story`, `case`, `comic`) và ba mục `enabled:false` ("Tổng hợp tin tức", "Video kiến thức", "Tổng hợp video ngắn"). Chữ `name`, `desc`, `rewriteNote` lấy nguyên văn từ `GENRES` của bản xem thử.
- Produces `window.projectGenre(project): 'story'|'case'|'comic'` — `case` nếu `project.metadata?.case_id`; `comic` nếu có cảnh mang `metadata.source === 'comic_slicer'`; còn lại `story`.
- Produces `window.renderGenreCards(): void` — vẽ thẻ vào `#idea-genre-cards`; bấm thẻ bật: đặt `#step1-content-kind` = `contentKind` và phát sự kiện `change` (để `applyStep1ContentKind()` chạy như cũ); thẻ `comic` ẩn khối dán chữ, hiện khối truyện tranh (`#step1-comic-dropzone` …, `#btn-step1-process-comic`); thẻ còn lại ngược lại.
- Thẻ phong cách `#idea-style-cards`: mỗi `<option>` của `#step1-style-select` một thẻ; bấm thẻ đặt giá trị cho ô (ô giữ nguyên trong HTML, ẩn bằng class).
- Ngăn "Tuỳ chọn" (`#btn-idea-options` → `openDrawer`) chứa `#step1-pacing-select`. `#step1-engine-select` vào `#ws-hidden-inputs` (giữ mặc định Muse; `handleStep1ProcessScript()` vẫn đọc nó, spec 4.5).
- `#step1-language-select` vẫn chỉ hiện với truyện chữ (`data-step1-kind="story"` như hiện nay).

- [ ] **Step 1: Thêm vào test**

```python
PLACEMENT |= {"idea-genre-cards": "idea", "idea-style-cards": "idea", "step1-content-kind": "idea",
              "step1-script-textarea": "idea", "step1-style-select": "idea", "step1-language-select": "idea",
              "step1-case-duration": "idea", "btn-step1-process-script": "idea", "step1-comic-dropzone": "idea",
              "btn-step1-process-comic": "idea", "step1-pacing-select": "idea"}
REMOVED |= {i: "spec 4.2: nhân vật chính kiểu cũ, app tự bỏ khi có bảng nhân vật" for i in
            ("step1-char-preset-select", "step1-char-name", "step1-char-anchor", "step1-char-ref-file-input",
             "step1-char-ref-url", "btn-step1-char-ref-apply-url", "btn-step1-char-ref-remove")}
# + các id con khác của khối ảnh tham chiếu (dòng ~438–515) mà bước 1 của Task 1 đã chép vào file gốc
REMOVED |= {"btn-step1-open-true-crime": "spec 4.2: không còn cửa sổ Hồ Sơ Kỳ Án để mở"}

def test_genres_declare_three_live_templates():
    js = Path("backend/static/genres.js").read_text(encoding="utf-8")
    for code in ("'story'", "'case'", "'comic'"):
        assert f"code: {code}" in js
    assert js.count("enabled: false") == 3
```

- [ ] **Step 2: Chạy, thấy đỏ.**

- [ ] **Step 3: Viết `genres.js`** theo Interfaces (nạp sau `app.js`, trước `true_crime.js`; thêm vào `tools/build_release.py`); dựng trang Ý tưởng theo bản xem thử; gỡ khối nhân vật kiểu cũ của Bước 1 và phần JS chỉ phục vụ nó (`handleStep1ProcessScript()` thôi gửi ảnh tham chiếu và tên/mô tả nhân vật cũ; mọi trường khác giữ nguyên).

- [ ] **Step 4: Chạy test** — Run: `.venv\Scripts\python.exe -m pytest tests\test_workspace_layout.py tests\test_ui_ids_preserved.py tests\test_one_flow.py tests\test_case_project_builder.py tests\test_feature_map.py tests\test_architecture.py -q` → Expected: PASS.

- [ ] **Step 5: Kiểm trên trình duyệt**: bấm lần lượt 3 thẻ thể loại → ô `#step1-content-kind` đổi giá trị, nhãn nút chính đổi như cũ (`#step1-process-label`), vụ án hiện ô số phút, truyện tranh hiện khu thả ảnh; 3 thẻ "Sau này" không bấm được; bấm thẻ phong cách → giá trị `#step1-style-select` đổi. Bấm nút chính với `fetch` giả lập: truyện chữ → yêu cầu `POST /api/projects/create-from-script` có `style_preset` đúng thẻ đã chọn; không gửi thật.

- [ ] **Step 6: Sửa `FEATURE_MAP.md`, commit** — `giao diện: trang Ý tưởng chọn thể loại bằng khuôn, phong cách hình ở một chỗ`.

---

### Task 8: Hồ Sơ Kỳ Án vào trang Kịch bản

**Files:**
- Modify: `backend/static/index.html` (`#modal-true-crime` dòng ~1988–2330)
- Modify: `backend/static/true_crime.js` (`openTrueCrimeModal()` ~2111, `closeTrueCrimeModal()` ~2127, `initTrueCrimeStudio()`, `tcStartFromStep1()` ~418, `refreshLanguageVersionButton()`)
- Modify: `backend/static/workspace.js` (dòng `#ws-case-note` và dải `#ws-case-banner` khi đang theo dõi vụ)
- Modify: `FEATURE_MAP.md` (mục 2.6.7, 3.C)
- Test: `tests/test_workspace_layout.py`, `tests/test_ui_ids_preserved.py`

**Interfaces:**
- Consumes: `showPage`, `onPageShow`, `projectGenre` (Task 2, 7).
- Thẻ "Dàn ý" (`#script-tab-outline`) chứa `#tc-progress`, `#btn-tc-resume`, `#btn-tc-new-case`, `#tc-outline-review`; thẻ "Tên hư cấu" (`#script-tab-names`) chứa `#tc-review` (bảng tên, thêm tên, cảnh báo, bảng ghim, sửa lời từng cảnh) và `#btn-tc-create-vi`, `#tc-create-hint`. Hai thẻ chỉ hiện khi `TrueCrimeState.caseId` có giá trị (đang theo dõi vụ chưa tạo dự án); khi đó thẻ "Lời kể theo cảnh" ẩn. `tcDetach()` chạy xong thì hai thẻ ẩn, thẻ lời kể hiện lại.
- `#tc-case-text`, `#tc-duration-select`, `#tc-visual-style`, `#tc-vision-engine` vào `#ws-hidden-inputs` (giữ nguyên là ô và đủ lựa chọn). `#tc-input-error`, `#tc-time-estimate` vào trang Ý tưởng dưới ô dán, hiện khi thể loại là vụ án. `#tc-voice-vi`, `#tc-voice-en` vào `#script-tab-voice`, chỉ hiện khi đang theo dõi vụ chưa tạo dự án (khi đó `#select-voice` ẩn). `#btn-create-en-version` vào trang Dựng (nút này không gửi giọng; máy chủ dùng giọng đã nhớ lúc tạo bản Việt).
- `openTrueCrimeModal()` giữ tên: `showPage('script')`, chọn thẻ Dàn ý, rồi làm đúng phần nạp như cũ (giọng, đọc `caseId` từ localStorage, vẽ tiến độ, vẽ duyệt, bắt đầu hỏi nếu cần, vẽ bảng ghim). `TrueCrimeState.modalOpen` = trang Kịch bản đang mở; `onPageShow` của các trang khác gọi phần dừng của `closeTrueCrimeModal()` (dừng hỏi, ẩn chú thích bảng ghim). `tcStartFromStep1()` không đổi gì ngoài việc `openTrueCrimeModal()` giờ là chuyển trang.
- Khi tải trang mà localStorage có `story_studio_true_crime_case_id` của vụ chưa tạo dự án và URL không có `project_id`: mở trang Kịch bản (Review Focus 2).
- Khi `TrueCrimeState.caseId` có giá trị: trang `script` hiện dòng `#ws-case-note` ("Đang làm vụ mới. Dự án đang mở là «tên dự án»: xem ở Hình mẫu, Cảnh, Dựng", tên qua `escapeHtml()`); trang `look`, `scenes`, `publish` hiện dải `#ws-case-banner` ("Vụ mới đang phân tích NN%: xem ở Kịch bản", bấm thì `showPage('script')`), số phần trăm lấy từ `TrueCrimeState.progress` mỗi lần `tcRenderProgress()` chạy.

- [ ] **Step 1: Thêm vào test**

```python
PLACEMENT |= {"tc-progress": "script", "tc-outline-review": "script", "btn-tc-outline-approve": "script",
              "tc-review": "script", "tc-entity-table": "script", "tc-warnings": "script",
              "tc-evidence-canvas": "script", "btn-tc-create-vi": "script", "tc-voice-vi": "script",
              "tc-voice-en": "script", "btn-create-en-version": "publish", "tc-input-error": "idea",
              "tc-time-estimate": "idea", "ws-case-note": "script"}
REMOVED |= {"modal-true-crime": "spec 4.2: Hồ Sơ Kỳ Án vào trang Kịch bản",
            "btn-open-true-crime-modal": "như trên", "btn-close-true-crime-modal": "như trên",
            "btn-cancel-true-crime-modal": "như trên", "btn-tc-analyze": "spec 4.2: trùng nút chính trang Ý tưởng",
            "btn-tc-sample-1": "spec 4.2: nút mẫu gỡ hẳn", "btn-tc-sample-2": "như trên", "btn-tc-sample-3": "như trên"}

def test_case_inputs_kept_hidden_for_existing_code():
    for i in ("tc-case-text", "tc-duration-select", "tc-visual-style", "tc-vision-engine", "step1-engine-select"):
        assert inside(INDEX_HTML, i, HIDDEN_STORE), i
```

Trước khi gỡ `#btn-tc-analyze`: xác nhận `tcAnalyze()` vẫn được `tcStartFromStep1()` gọi (dòng ~431), chỉ bỏ dòng gắn sự kiện của nút.

- [ ] **Step 2: Chạy, thấy đỏ.**

- [ ] **Step 3: Dời khối, sửa `true_crime.js`, `workspace.js`** theo Interfaces.

- [ ] **Step 4: Chạy test** — như Task 7 Step 4, thêm `tests\test_true_crime_router.py tests\test_true_crime_e2e.py` → Expected: PASS.

- [ ] **Step 5: Kiểm trên trình duyệt** (giả lập máy chủ bằng `javascript_tool`, không gọi LLM):
  1. Mở `proj_crime_52c3a5e8` (chỉ xem): trang Kịch bản có 4 thẻ; thẻ Tên hư cấu hiện bảng tên và bảng ghim vẽ được; trang Dựng có nút bản tiếng Anh như cũ.
  2. Mở `proj_ea5b04db`: chỉ 2 thẻ.
  3. Đặt localStorage `story_studio_true_crime_case_id` = `case_7dcf6158`, mở app không có `project_id` → tự vào trang Kịch bản, có yêu cầu `GET /api/true-crime/cases/case_7dcf6158/progress` hoặc `…/case_7dcf6158` (Review Focus 2); trang Kịch bản chỉ có thẻ của vụ và dòng `#ws-case-note`; bấm Hình mẫu, Cảnh, Dựng → là của dự án đang mở, có dải `#ws-case-banner` (Review Focus 1); sang trang khác rồi đợi 5 giây → không còn yêu cầu hỏi tiến độ. Xoá khoá localStorage sau khi thử. (Vụ mẫu đã xong nên không có lượt LLM nào chạy; không bấm "Thử lại".)
  4. Console không lỗi; `projects/_cases/case_7dcf6158` không đổi (so giờ sửa file trước và sau).

- [ ] **Step 6: Sửa `FEATURE_MAP.md`, commit** — `giao diện: Hồ Sơ Kỳ Án thành thẻ Dàn ý, Tên hư cấu trong trang Kịch bản`.

---

### Task 9: Gỡ các cửa sổ và nút trùng còn lại

**Files:**
- Modify: `backend/static/index.html` (`#modal-comic-slicer` ~1318, `#modal-script-importer` ~1473, `#modal-character-editor` ~1594, `#modal-master-storyboard` ~1676; thẻ `#character-consistency-card` ~742; nút đầu trang còn lại; một nút tải thumbnail)
- Modify: `backend/static/app.js` (`openComicModal()`, `handleStartSlice()`, `handleImportComicToStoryboard()`, `openScriptModal()`, `handleSubmitScriptSplit()`, `openCharacterModal()`, `handleSaveCharacter()`, `initMasterStoryboardSpec()`, `closeAllModals()`, các mục `DOM.*` trỏ tới phần đã gỡ)
- Modify: `FEATURE_MAP.md` (bỏ mục 2.6.2–2.6.5; thêm `POST /api/storyboard/deconstruct`, `POST /api/storyboard/import`, `POST /api/projects/{project_id}/split-script`, `POST /api/split-script`, `POST /api/comic/slice` vào mục 4 "chỉ có API" nếu giao diện không còn gọi)
- Test: `tests/test_ui_ids_preserved.py`

**Interfaces:**
- Hàm chỉ phục vụ phần gỡ thì xoá. Hàm dùng chung với luồng truyện tranh của Bước 1 (ví dụ `loadComicSample()`, trạng thái `AppState.comicState`) thì giữ: trước khi xoá một hàm, `grep` tên hàm trong `backend/static/` và chỉ xoá khi không còn chỗ gọi ngoài phần đã gỡ.
- Nút "Nhập kịch bản truyện" của danh sách cảnh rỗng (khuôn trong `renderSceneList()`, dòng ~1264, đang gọi `openScriptModal()`) đổi thành nút "Về trang Ý tưởng" gọi `showPage('idea')`.
- `#btn-save-project` gỡ; `Ctrl+S` (`handleGlobalKeydown()`) giữ; `#ws-save-state` hiện "Đang lưu…" / "Đã lưu" theo `ProjectSync` (`ProjectSync.dirty`, `ProjectSync.inFlight`).
- `#btn-produce-long-video` gỡ khỏi thanh trên (spec 4.2), giữ `#btn-produce-from-board`.
- Giữ `#btn-cinema-download-thumbnail`, gỡ `#btn-download-thumbnail-direct` (lý do: nút giữ nằm cùng hàng các nút tải khác của thành phẩm).

- [ ] **Step 1: Thêm vào `REMOVED`** mọi id nằm trong 4 cửa sổ và thẻ `#character-consistency-card` (lấy tự động từ file gốc theo khoảng dòng của từng khối trong `index.html` bản 0fd5e35, dán vào test dạng danh sách cố định, mỗi nhóm một lý do trỏ spec 4.2), cùng `btn-open-comic-modal`, `btn-open-master-storyboard-modal`, `btn-open-script-modal`, `btn-edit-character`, `btn-save-project`, `btn-produce-long-video`, `btn-download-thumbnail-direct`.

- [ ] **Step 2: Chạy, thấy đỏ** (`test_removed_ids_are_really_gone`).

- [ ] **Step 3: Gỡ HTML và JS** theo Interfaces.

- [ ] **Step 4: Chạy bộ đầy đủ** — Run: `.venv\Scripts\python.exe tools\check.py --full` → Expected: đạt hết (`test_every_fixed_js_id_exists` bắt chỗ JS còn gọi id đã gỡ).

- [ ] **Step 5: Kiểm trên trình duyệt**: luồng truyện tranh của trang Ý tưởng với ảnh mẫu (`#btn-step1-sample-grid`) cắt được khung (OpenCV, không tốn tiền), dừng trước khi nhập vào dự án; `Ctrl+S` lưu (`PUT` xuất hiện); chữ "Đã lưu" đổi đúng. Console không lỗi.

- [ ] **Step 6: Commit** — `giao diện: gỡ bốn cửa sổ và các nút trùng theo danh sách đã duyệt`.

---

### Task 10: Dọn màu trang trí sang hệ đen trắng xám

**Files:**
- Modify: `backend/static/index.html`, `backend/static/app.js` (khuôn HTML trong JS, nhất là `renderSceneList()`), `true_crime.js`, `climax_video.js`, `character_sheets.js`, `location_sheets.js`, `youtube_seo.js`, `scene_muse_video.js`, `workspace.css`
- Create: `tests/test_ui_palette.py`

**Interfaces:**
- Lớp màu trang trí cấm: chuỗi khớp `\b(?:bg|text|border|ring|from|via|to|shadow)-(?:indigo|violet|purple|fuchsia|pink|rose|sky|cyan|teal|blue|lime)-\d{2,3}\b` và `\bbg-gradient-to-` trong `index.html` và mọi `backend/static/*.js`. Màu trạng thái `red|amber|emerald|green|yellow|orange` được phép. Nút chính dùng `ws-btn-primary`, nút phụ `ws-btn`/`ws-btn-ghost`, thẻ `ws-card`.

- [ ] **Step 1: Viết test**

```python
def test_no_decorative_colors_left():
    hits = {f.name: DECOR.findall(f.read_text(encoding="utf-8")) for f in FILES}
    hits = {k: sorted(set(v)) for k, v in hits.items() if v}
    assert not hits, f"Còn lớp màu trang trí (dùng lớp ws-* hoặc màu kẽm): {hits}"
```

- [ ] **Step 2: Chạy, thấy đỏ** (ghi số chỗ ban đầu vào `TASKS.md`).

- [ ] **Step 3: Thay lớp màu** từng file; nút chính sang `ws-btn-primary`; bỏ đổ bóng nặng (`shadow-lg`, `shadow-xl`, `shadow-2xl`).

- [ ] **Step 4: Chạy** — Run: `.venv\Scripts\python.exe tools\check.py --full` → Expected: đạt hết, kể cả `test_ui_palette.py`.

- [ ] **Step 5: Kiểm trên trình duyệt**: chụp 8 trang ở 1280x720, xem từng ảnh: không còn màu tím/xanh trang trí, chữ đọc rõ, trạng thái lỗi vẫn đỏ, cảnh báo vẫn vàng (thẻ cảnh "Clip gần như đứng hình" của `proj_crime_03b5d8c5` nếu có, chỉ mở xem).

- [ ] **Step 6: Commit** — `giao diện: bỏ màu trang trí, dùng hệ đen trắng xám`.

---

### Task 11: Trang Tài khoản và kết nối — trạng thái kết nối

**Files:**
- Create: `backend/routers/connections.py`
- Create: `tests/test_connections_router.py`
- Modify: `backend/main.py` (thêm `app.include_router(connections_router)` sau dòng ~122)
- Modify: `backend/static/workspace.js` (hoặc file mới `backend/static/connections.js` nếu `workspace.js` quá 300 dòng; thêm vào `tools/build_release.py`)
- Modify: `backend/static/index.html` (`#page-accounts`), `FEATURE_MAP.md` (mục 2.1, thêm dòng trang Tài khoản; mục 4 nếu cần)

**Interfaces:**
- `GET /api/connections/status` → `{"llm": {"base_url": str, "has_key": bool, "text_model": str, "image_model": str}, "youtube": {"has_key": bool}, "image_provider_default": str, "vieneu": {"port_open": bool}}`. Đọc giá trị qua `config.py`; tên biến cụ thể người làm lấy từ `config.py` (khoá 9router/CLI Proxy, model chữ, model ảnh, `YOUTUBE_API_KEY`, nguồn ảnh mặc định). `vieneu.port_open`: thử nối TCP `127.0.0.1:5005` tối đa 0,3 giây trong `asyncio.to_thread` (đường cấm 8).
- `POST /api/connections/llm-ping` → `{"ok": bool, "seconds": float, "error": str | None}`; một lần gọi rất ngắn qua `services/case_adaptation_llm.py` (đường cấm 5), lỗi thì `ok=false` và câu lỗi, không ném 500.
- Giao diện: khối `#accounts-connections` vẽ trạng thái; nút `#btn-connections-ping` ghi "Gọi thử (tốn 1 lượt AI)"; Edge-TTS hiện "Cần mạng, không kiểm trước". Tài khoản Muse hiện thêm `blocked_until` (giờ địa phương) và `block_reason` nếu `GET /api/muse-bridge/accounts` có trả.

- [ ] **Step 1: Viết test**

```python
def test_status_never_returns_secret(client, monkeypatch):
    monkeypatch.setattr(config, "<tên biến khoá LLM trong config.py>", "sk-bi-mat-123")
    r = client.get("/api/connections/status")
    assert r.status_code == 200 and r.json()["llm"]["has_key"] is True
    assert "sk-bi-mat-123" not in r.text

def test_status_without_keys(client, monkeypatch):   # khoá rỗng → has_key False, không lỗi

def test_ping_reports_llm_failure_without_500(client, monkeypatch):
    # thay hàm gọi LLM của case_adaptation_llm bằng hàm ném lỗi → 200, ok False, error có chữ lỗi

def test_ping_reports_success_time(client, monkeypatch):   # hàm giả trả ngay → ok True, seconds >= 0
```

`client` theo cách các test router hiện có tạo `TestClient` (xem `tests/test_true_crime_router.py`); không gọi mạng (`tests/conftest.py` chặn).

- [ ] **Step 2: Chạy, thấy đỏ** — Run: `.venv\Scripts\python.exe -m pytest tests\test_connections_router.py -q` → Expected: FAIL (404).

- [ ] **Step 3: Viết router, ghép vào `main.py`, vẽ khối giao diện.**

- [ ] **Step 4: Chạy** — Run: `.venv\Scripts\python.exe tools\check.py --full` → Expected: đạt hết.

- [ ] **Step 5: Kiểm trên trình duyệt** (server 8010 đọc `.env` thật): trang Tài khoản báo đúng cổng, có khoá (đúng/sai so với `.env`, **không in khoá ra chat**), trạng thái VieNeu khớp `Test-NetConnection 127.0.0.1 -Port 5005`. Bấm "Gọi thử" **một lần** (1 lượt LLM, ghi vào `TASKS.md`), kết quả có thời gian.

- [ ] **Step 6: Commit** — `giao diện: trang Tài khoản và kết nối báo trạng thái AI, YouTube, VieNeu`.

---

### Task 12: Kiểm chứng cuối và tài liệu

**Files:**
- Modify: `TASKS.md`, `FEATURE_MAP.md` (dòng "Cập nhật lần cuối"), `CLAUDE.md` mục 4 dòng "Giao diện" (thêm `workspace.js`, `workspace.css`, `script_page.js`, `genres.js`) và bảng 1.1 dòng "Đầu vào là nội dung…" (phần sự thật về code)
- Create: `.cache/giao_dien_gon/` (ảnh chụp, không commit)

- [ ] **Step 1: Bộ kiểm đầy đủ** — Run: `.venv\Scripts\python.exe tools\check.py --full` → Expected: đạt hết; ghi số test đạt và thời gian vào `TASKS.md`.

- [ ] **Step 2: Đóng gói thử** — Run: `.venv\Scripts\python.exe tools\build_release.py` → Expected: không báo thiếu file `/static/…`; xoá gói thử trong `dist/` sau khi xem (chuyển vào Thùng rác nếu cần dọn).

- [ ] **Step 3: Đi trọn luồng không tốn tiền trên server 8010** với `proj_ea5b04db`: Ý tưởng (xem) → Kịch bản (sửa lời một cảnh rồi sửa lại như cũ, nghe giọng mẫu) → Hình mẫu (xem) → Cảnh (xem thử có tiếng, mở ngăn một cảnh) → Dựng (xem thành phẩm, mở gói SEO, xem thumbnail) → Dự án → Thư viện → Tài khoản. Console không lỗi; log server (`preview_logs`, mức lỗi) không lỗi; `projects/` trước và sau giống nhau.

- [ ] **Step 4: Chụp 8 trang** ở 1280x720, 1920x1080 và 1024x768 có thanh bên thu gọn vào `.cache/giao_dien_gon/`; kiểm từng trang không tràn ngang (`document.documentElement.scrollWidth <= innerWidth`) (Review Focus 4).

- [ ] **Step 5: Sửa tài liệu** như phần Files; commit `tài liệu: giao diện gọn, cập nhật bản đồ tính năng và CLAUDE.md mục 4`.

- [ ] **Step 6: Báo chủ dự án**: gửi ảnh chụp, số test, danh sách id đã gỡ; hỏi có gộp nhánh `giao-dien-gon` vào `master` không (chỉ gộp khi được đồng ý).
