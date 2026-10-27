# Video cao trào theo bảng nhân vật — kế hoạch code

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Video cảnh cao trào giữ đúng nhân vật: mỗi nhân vật của dự án vụ án có một bảng nhân vật đủ góc do chủ dự án duyệt; mỗi cảnh làm trong một side chat Muse của một tài khoản video, tài khoản đó vẽ cả ảnh 9-grid lẫn clip.

**Architecture:** Thêm dịch vụ bảng nhân vật (`services/character_sheets.py`, một file dữ liệu riêng mỗi dự án). Fleet Runner và muse_bridge học thêm 4 việc: chạy việc ảnh trên tài khoản video, ghim việc vào đúng tài khoản sở hữu chat, mở lại chat cũ theo địa chỉ, đính kèm nhiều ảnh, và báo lỗi ngay khi Muse trả lời bằng chữ. `services/climax_video.py` đổi luồng: kiểm bảng nhân vật đã duyệt → grid trong chat của cảnh → chủ dự án duyệt grid → clip trong cùng chat.

**Tech Stack:** Python 3.14, FastAPI, Playwright (Fleet Runner), PIL, ffmpeg; giao diện JS thuần + Tailwind build sẵn.

**Spec:** quyết định của chủ dự án trong chat 27–28/10/2026 (ghi lại ở mục "Quyết định đã chốt" ngay dưới) và bằng chứng thăm dò Muse ở `TASKS.md` (mục "Video cho cảnh cao trào…").

## Quyết định đã chốt (chủ dự án, 27–28/10/2026)

- Bảng nhân vật đủ góc làm **một lần cho cả dự án**, mỗi nhân vật một bảng, chủ dự án duyệt trước khi dùng.
- **Một side chat cho mỗi cảnh**: ảnh grid và mọi clip của cảnh nằm chung chat (không mở chat mới cho từng ảnh).
- Tài khoản **video** tự vẽ ảnh grid — **chỉ cho video cao trào**; ảnh thường của các cảnh vẫn đi tài khoản ảnh như cũ.
- Prompt tả kỹ nhân vật, có định nghĩa từng góc (trước, trái, phải, sau, trên).
- Ví dụ đã duyệt: cô gái đầu tròn trắng (Thẩm Nhã Uyên, vụ Trạm Dung) — "Tóc ôm cả phía sau đầu từ đỉnh đầu xuống vai; nhìn thẳng thấy viền tóc đen quanh đỉnh và hai bên mặt tròn trắng." Bảng lần 2 (`.cache/climax_try/tham_do/bang2/bang_nhan_vat_2.jpg`) được duyệt "dùng được".

## Sự thật đo được (thăm dò Muse 27–28/10/2026, tài khoản `muse_acc_vid_02`)

- Tài khoản video vẽ được ảnh 2K 16:9 (78 s – 4 phút).
- Side chat có địa chỉ riêng `https://muse.ai/thread/<uuid>` (lúc mới mở là `/thread/new`, có địa chỉ thật sau tin nhắn đầu); mở lại địa chỉ đó thấy đủ lịch sử.
- Đính kèm 2 ảnh trong một tin nhắn: được.
- Trong một chat, Muse làm lần lượt từng tin nhắn; tin gửi khi Muse còn bận sẽ được làm sau đó.
- Muse trả lời bằng chữ khi lỗi (2 lần "hệ thống quá tải (503)") — runner hiện chỉ chờ media nên mất trọn thời gian chờ.
- Ảnh đính kèm hiện lại trong tin nhắn đã gửi, cùng cỡ với ảnh kết quả: phải loại theo nội dung (hash) mọi ảnh đính kèm, không chỉ ảnh đầu.
- Lời tự kiểm của Muse không đáng tin (2 lần nói "nhất quán" khi chưa đúng).
- Dữ liệu sẵn có: `CaseEntity.appearance_en` (19 người ở vụ Trạm Dung); prompt ảnh mỗi cảnh chứa gần nguyên văn câu `appearance_en` của người được vẽ (cảnh 12 ↔ person_2), còn nối qua `covers_event_ids` → `TimelineEvent.entity_ids` thì lệch (cảnh 12 ra person_1).

## Global Constraints

- Không gọi LLM ở bất kỳ bước nào của tính năng này; prompt ghép bằng khuôn trong code.
- `services/` không import `routers/` (`muse_call` truyền vào như hiện nay).
- Đầu vào gửi Muse phải nằm trong `projects/` hoặc `backend/static/`.
- Không ghi `project.json` ngoài `project_service.save_project()`; dữ liệu bảng nhân vật chỉ `services/character_sheets.py` ghi, vào `projects/<id>/characters/characters.json` (ghi an toàn qua `services/safe_files.py`).
- Không xoá file người dùng (ảnh bảng cũ giữ lại theo phiên bản `sheet_v<n>.jpg`).
- Test offline, Muse giả; chạy Muse thật chỉ khi chủ dự án cho phép, ghi số lượt.
- Theo `CLAUDE.md` mục 5 và 6 (đọc ghi đĩa và ffmpeg trong route qua `asyncio.to_thread`, `escapeHtml()` cho chữ chèn vào HTML, một sự kiện click gắn một lần, commit `<vùng>: <mô tả>` tiếng Việt).

## Review Focus

- Chat dùng lại sau một lần quá giờ: kết quả muộn của việc trước hiện ra sau khi đã đánh dấu media cũ → bị nhận nhầm là kết quả việc mới. Mong đợi: chat bị đánh dấu "bẩn", việc sau mở chat mới (đính kèm lại bảng nhân vật). Test ở Task 5.
- Muse trả lời bằng chữ báo lỗi (503, "không tạo được") mà không có media. Mong đợi: việc thất bại sau tối đa `MUSE_REPLY_GRACE_SEC` giây, lý do là đúng câu Muse viết. Test ở Task 2.
- Tài khoản sở hữu chat bị khoá quota hoặc offline. Mong đợi: việc **không** bị chuyển sang tài khoản khác; thất bại rõ "tài khoản X của chat không dùng được", lần chạy sau mở chat mới trên tài khoản khác. Test ở Task 1 và Task 5.
- Cảnh có nhân vật chưa có bảng được duyệt, hoặc không đoán ra nhân vật nào. Mong đợi: không gọi Muse, báo rõ tên nhân vật thiếu / "chưa chọn nhân vật cho cảnh". Test ở Task 5.
- Giao diện tự lưu đè trạng thái do server ghi. Mong đợi: dữ liệu bảng nhân vật nằm ở file riêng nên không bị PUT dự án đè; trạng thái cảnh vẫn gộp như hiện nay (`mergeServerSceneMedia()`). Test ở Task 3.

---

## Cấu trúc file

| File | Việc |
|---|---|
| `backend/routers/muse_bridge.py` (sửa) | `route_kind`, `pin_account`, trả `thread_url`/`muse_reply` về người gọi |
| `backend/runners/muse_fleet_runner.py` (sửa) | mở chat theo `thread_url`, nhiều đính kèm, `raw_prompt`, loại ảnh đính kèm theo hash, dừng sớm khi Muse báo lỗi bằng chữ |
| `backend/services/character_sheets.py` (mới) | danh sách nhân vật từ kế hoạch vụ án, đoán nhân vật của cảnh, thiết kế + prompt bảng nhân vật, vẽ/duyệt bảng, ghép "bảng diễn viên" cho một cảnh |
| `backend/routers/character_sheets.py` (mới) | API bảng nhân vật |
| `backend/static/character_sheets.js` (mới) | cửa sổ Bảng nhân vật (Bước 2) |
| `backend/services/climax_video.py` (sửa) | luồng mới theo chat của cảnh, duyệt grid |
| `backend/routers/climax_video.py`, `backend/static/climax_video.js` (sửa) | duyệt grid, nhân vật của cảnh trên thẻ |
| `tests/test_muse_threads.py`, `tests/test_character_sheets.py` (mới), `tests/test_climax_video.py` (sửa) | test |

---

### Task 1: muse_bridge — việc ảnh trên tài khoản video, ghim tài khoản, trả địa chỉ chat

**Files:**
- Modify: `backend/routers/muse_bridge.py` (`assign_task_account()`, `_pick_task_for_account()`, `poll_task()`, `complete_task()`, `enqueue_and_wait_muse_task()`)
- Test: `tests/test_muse_threads.py`

**Interfaces:**
- Produces (trường mới của task dict, mọi trường đều tuỳ chọn, thiếu thì hành vi y như cũ):
  - `route_kind: "image" | "video"` — loại tài khoản nhận việc; mặc định `task_kind(mode)`.
  - `pin_account: bool` — `True` thì chỉ `assigned_account` được nhận, không bao giờ chuyển (bỏ qua `REASSIGN_AFTER_SEC`).
  - `thread_url: str | None` — chat Muse cần mở lại (chỉ nhận `https://muse.ai/thread/<uuid>`).
  - `attachments: list[str]` — đường dẫn ảnh đính kèm theo thứ tự (trong `projects/` hoặc `backend/static/`).
  - `raw_prompt: bool` — runner gửi `prompt` nguyên văn, không bọc khuôn.
  - Kết quả `enqueue_and_wait_muse_task()` (đã có `executed_by` = tài khoản chạy việc) có thêm `thread_url` và `muse_reply` (chữ trả lời cuối của Muse, ≤ 2000 ký tự) lấy từ `metadata` runner nộp.
- Hàm mới: `routing_kind(task: dict) -> str`.

- [ ] **Step 1: Viết test hỏng**

```python
def test_image_task_routed_to_video_account_when_route_kind_video(): ...
    # task mode text-to-image, route_kind "video", assigned_account "muse_acc_vid_02"
    # -> assign_task_account giữ muse_acc_vid_02; _pick_task_for_account("muse_acc_vid_02", "video") trả đúng index
    # -> _pick_task_for_account("muse_acc_img_01", "image") trả -1
def test_pinned_task_never_reassigned(): ...
    # pin_account True, tài khoản gán offline, queued_at = now - 10 * REASSIGN_AFTER_SEC
    # -> tài khoản video khác poll vẫn nhận -1
def test_pinned_task_with_unusable_account_fails_fast(): ...
    # enqueue_and_wait_muse_task: pin_account True, tài khoản bị khoá -> RuntimeError chứa "tài khoản" và account_id, không chờ
def test_thread_url_must_be_muse_thread(): ...
    # thread_url "https://evil.example/x" -> ValueError; "https://muse.ai/thread/2d353dc3-3d3d-44b3-a3e7-51f54a295757" -> giữ nguyên
def test_complete_returns_thread_url_and_reply(): ...
    # POST /tasks/{id}/complete với metadata {"thread_url": ..., "muse_reply": "..."} -> task trong task_history có hai khoá đó
```

- [ ] **Step 2:** Chạy `.venv\Scripts\python.exe -m pytest tests\test_muse_threads.py -q` → FAIL.
- [ ] **Step 3:** Cài đặt. `routing_kind()` thay `task_kind(t.get("mode"))` ở mọi chỗ chọn tài khoản/poll; kiểm `thread_url` bằng regex chặt `^https://muse\.ai/thread/[0-9a-f-]{36}$` (đây là URL ngoài, không phải id/đường dẫn nên không thuộc `security.py`); `attachments` mỗi phần tử phải `is_within(PROJECTS_DIR, STATIC_DIR)` và tồn tại, sai thì `ValueError`.
- [ ] **Step 4:** Chạy lại test → PASS; chạy `tests\test_muse_fleet_routing.py` → vẫn PASS.
- [ ] **Step 5:** Commit `muse: việc ảnh chạy được trên tài khoản video, ghim tài khoản theo chat, trả địa chỉ chat`.

### Task 2: Fleet Runner — mở lại chat, nhiều đính kèm, prompt nguyên văn, dừng khi Muse báo lỗi

**Files:**
- Modify: `backend/runners/muse_fleet_runner.py` (`execute_task_with_browser()` và hàm thuần mới)
- Test: `tests/test_muse_threads.py` (phần runner, chỉ test hàm thuần; luồng trình duyệt kiểm bằng chạy thật ở Task 7)

**Interfaces:**
- Consumes: các trường task ở Task 1.
- Produces:
  - `MUSE_REPLY_GRACE_SEC = 45` — Muse đã trả lời bằng chữ chứa từ báo lỗi mà 45 s sau vẫn không có media thì thất bại.
  - `muse_reply_error(text_before: str, text_now: str) -> str | None` — phần chữ mới của Muse nếu có từ báo lỗi (`503`, `quá tải`, `overload`, `không tạo được`, `chưa tạo được`, `can't`, `cannot`, `error`, `lỗi`), không thì `None`.
  - `task_attachments(task) -> list[str]` — `attachments` nếu có, không thì một phần tử như cũ (`input_image_url` cho video, `reference_image_path` cho ảnh).
  - `MusePromptFormatter.build_prompt(task, has_attachment: bool) -> str` — `raw_prompt` thì trả `task["prompt"]` nguyên văn, không thì gọi `format_video_prompt()`/`format_image_prompt()` như cũ.
  - `metadata` nộp khi xong (cả khi lỗi `MUSE_REPLIED_ERROR`) có `thread_url = page.url` và `muse_reply`.
  - Lỗi mới: `TaskFailure("THREAD_OPEN_FAILED", ...)`, `TaskFailure("MUSE_REPLIED_ERROR", <câu Muse>)`.
  - Guard tài khoản: so `acc.type` với `task.get("route_kind") or kind`.

- [ ] **Step 1: Viết test hỏng**

```python
def test_muse_reply_error_detects_new_overload_text():
    before = "…👍"
    now = before + "\nVideo 5s thì chưa tạo được. Lệnh tạo video báo lỗi hệ thống quá tải (503)"
    assert "503" in muse_reply_error(before, now)
def test_muse_reply_error_ignores_old_text_and_normal_reply():
    assert muse_reply_error("lỗi 503 cũ", "lỗi 503 cũ") is None
    assert muse_reply_error("", "Bảng character sheet đã xong.") is None
def test_task_attachments_keeps_order_and_falls_back():
    assert task_attachments({"attachments": ["a.jpg", "b.jpg"], "mode": "image-to-video"}) == ["a.jpg", "b.jpg"]
    assert task_attachments({"mode": "image-to-video", "input_image_url": "x.jpg"}) == ["x.jpg"]
def test_raw_prompt_is_sent_verbatim():
    # MusePromptFormatter.build_prompt(task, has_attachment=True) với raw_prompt True trả đúng task["prompt"]
def test_route_kind_lets_video_account_run_image_task(): ...
```

- [ ] **Step 2:** Chạy → FAIL.
- [ ] **Step 3:** Cài đặt trong `execute_task_with_browser()`:
  - có `thread_url` thì `page.goto(thread_url)`, cuộn hết log, không bấm "New side chat"; không mở được hoặc không thấy ô chat thì `THREAD_OPEN_FAILED`.
  - không có `thread_url` thì mở chat mới như cũ.
  - đính kèm lần lượt mọi ảnh của `task_attachments()`; `reject_hashes` gồm hash **mọi** ảnh đính kèm (cả việc video).
  - `raw_prompt` thì gửi nguyên văn qua hàm `build_prompt()` (tách ra từ hai nhánh `format_*_prompt`).
  - trong vòng chờ: mỗi lượt đọc chữ của `[role=log]`, `muse_reply_error()` khác `None` liên tục `MUSE_REPLY_GRACE_SEC` giây mà chưa có media hợp lệ thì `MUSE_REPLIED_ERROR`.
  - khi xong hoặc lỗi: gửi `thread_url` và `muse_reply` trong metadata.
- [ ] **Step 4:** Chạy test → PASS; `tests\test_muse_fleet_runner*.py` → PASS.
- [ ] **Step 5:** Commit `muse: runner mở lại side chat theo địa chỉ, đính kèm nhiều ảnh, dừng sớm khi Muse báo lỗi bằng chữ`.

### Task 3: Dịch vụ bảng nhân vật

**Files:**
- Create: `backend/services/character_sheets.py`
- Test: `tests/test_character_sheets.py`

**Interfaces:**
- Consumes: `case_store.load_plan(case_id)`, `CaseEntity`, `project_service`, `safe_files`, Task 1 (`route_kind`, `pin_account`, `thread_url`, `attachments`, `raw_prompt`), `muse_call` truyền vào.
- Produces:
  - `SheetStatus = Literal["draft", "drawing", "review", "approved", "failed"]`
  - Model Pydantic `CharacterSheet`: `entity_id, name_vi, role, design_en, status, sheet_path: str | None, versions: list[str], account_id: str | None, thread_url: str | None, error: str | None, feedback: list[str]`.
  - Model `ProjectCast`: `characters: dict[str, CharacterSheet]`, `scene_cast: dict[str, list[str]]` (scene_id → entity_id, chủ dự án đã sửa thì ghi đè đoán tự động).
  - `load_cast(project_id) -> ProjectCast` (chưa có file thì dựng từ kế hoạch vụ án: mọi `CaseEntity` kind "person", `design_en = default_design(entity, style)`, status "draft").
  - `save_cast(project_id, cast)` — nơi duy nhất ghi `projects/<id>/characters/characters.json`, có khoá file như `case_store`.
  - `default_design(entity: CaseEntity, style_id: str) -> str` — `appearance_en` + câu nhân vật của phong cách (lấy từ `STYLE_PRESETS[style]["prompt_suffix"]`, phần tả nhân vật) + `HAIR_RULE_EN` (xem dưới).
  - `HAIR_RULE_EN` — khuôn tóc mặc định (theo quyết định 28/10, chủ dự án sửa từng người được): "Hair grows from the very top of the head (the crown) and covers the whole back half of the head down to <length>. FRONT view: a hair rim is visible around the top and both sides of the white face. SIDE views: front half white face, back half hair from crown to nape. BACK view: only hair, no white. TOP view: front half white, back half hair."
  - `guess_scene_cast(scene: Scene, characters: list[CharacterSheet], appearance: dict[str, str]) -> list[str]` — entity_id có câu `appearance_en` khớp với `scene.image_prompt` (cửa sổ 6 từ liên tiếp trùng, chuẩn hoá thường/dấu câu), thứ tự xuất hiện trong prompt.
  - `scene_cast(project, cast) -> dict[str, list[str]]` — `cast.scene_cast` nếu chủ dự án đã sửa, không thì đoán.
  - `sheet_prompt(sheet: CharacterSheet) -> str` — tiếng Việt mở đầu "tạo cho tôi 1 hình ảnh 2K tỉ lệ 16:9:" + khuôn bố cục đã thử thật (hàng 1: toàn thân FRONT, LEFT SIDE, BACK, RIGHT SIDE; hàng 2: đầu FRONT, LEFT SIDE, BACK, RIGHT SIDE, TOP; nền xám trơn, không chữ) + `design_en` + từng dòng `feedback` dạng "Bản trước SAI: …".
  - `async draw_sheet(project_id, entity_id, muse_call, reference_image: Path) -> CharacterSheet` — việc `mode="text-to-image"`, `route_kind="video"`, `raw_prompt=True`, `attachments=[reference_image]`; lần vẽ lại dùng lại `thread_url` + `account_id` (`pin_account=True`) để Muse thấy bản sai trước; lưu `characters/<entity_id>/sheet_v<n>.jpg`, status "review".
  - `approve_sheet(project_id, entity_id) -> CharacterSheet`; `reject_sheet(project_id, entity_id, feedback: str) -> CharacterSheet` (thêm feedback, status "draft").
  - `set_design(project_id, entity_id, design_en: str)`, `set_scene_cast(project_id, scene_id, entity_ids: list[str])`.
  - `cast_board(project_id, entity_ids: list[str]) -> Path` — ghép các bảng đã duyệt thành một ảnh 16:9 (`characters/board_<hash>.jpg`), giữ 2 ảnh đính kèm mỗi tin nhắn (chỉ đo được 2).

- [ ] **Step 1: Viết test hỏng** (dữ liệu giả theo `tests/case_adaptation_fakes.py`, kế hoạch vụ án 3 người)

```python
def test_load_cast_builds_people_from_case_plan(isolated_projects_dir): ...   # 3 người, status draft, design có HAIR_RULE_EN
def test_guess_scene_cast_matches_appearance_words(): ...
    # image_prompt chứa "elderly East Asian forensic examiner in his late 60s with silver-streaked hair" -> ["person_2"]
def test_guess_scene_cast_empty_when_no_match(): ...
def test_owner_scene_cast_overrides_guess(isolated_projects_dir): ...
def test_sheet_prompt_contains_layout_design_and_feedback(): ...
    # có "LEFT SIDE", "TOP", design_en, "Bản trước SAI: tóc"
def test_draw_sheet_reuses_thread_and_pins_account_on_redraw(isolated_projects_dir): ...
    # lần 1: task không thread_url, route_kind video, raw_prompt True, attachments=[ảnh cảnh]
    # Muse giả trả thread_url + executed_by; lần 2 (sau reject_sheet): task có thread_url đó, pin_account True, assigned_account đó
    # file sheet_v1.jpg và sheet_v2.jpg đều còn
def test_project_put_does_not_touch_cast_file(client): ...   # PUT /api/projects/{id} không đổi characters.json
def test_cast_board_requires_approved_sheets(isolated_projects_dir): ...   # có người chưa duyệt -> ValueError nêu tên
```

- [ ] **Step 2:** Chạy `.venv\Scripts\python.exe -m pytest tests\test_character_sheets.py -q` → FAIL.
- [ ] **Step 3:** Cài đặt theo Interfaces.
- [ ] **Step 4:** Chạy → PASS; `tools\check.py` → ĐẠT.
- [ ] **Step 5:** Commit `nhân vật: bảng nhân vật đủ góc cho dự án vụ án (vẽ trên tài khoản video, duyệt, vẽ lại trong cùng chat)`.

### Task 4: API và cửa sổ Bảng nhân vật

**Files:**
- Create: `backend/routers/character_sheets.py` (gắn vào `backend/main.py`), `backend/static/character_sheets.js` (nạp trong `index.html`)
- Modify: `backend/static/index.html` (nút `#btn-character-sheets` cạnh `#btn-climax-video-pick`, cửa sổ `#modal-character-sheets`), `tools/build_release.py` (thêm file JS)
- Test: `tests/test_character_sheets.py` (phần API)

**Interfaces:**
- Consumes: Task 3.
- Produces API (id kiểm bằng `security.py`; đọc ghi đĩa qua `asyncio.to_thread`):
  - `GET /api/projects/{project_id}/characters` → `{"characters": [...], "scene_cast": {scene_id: [...]}, "needed": [entity_id có mặt trong cảnh đang chọn làm video]}`
  - `PUT /api/projects/{project_id}/characters/{entity_id}` body `{"design_en": str}`
  - `POST /api/projects/{project_id}/characters/{entity_id}/draw` (chạy nền, 409 nếu đang vẽ) — ảnh tham chiếu: ảnh cảnh đầu tiên có người đó trong `scene_cast`.
  - `POST .../characters/{entity_id}/approve`, `POST .../characters/{entity_id}/reject` body `{"feedback": str}` (bắt buộc, ≤ 500 ký tự)
  - `PUT /api/projects/{project_id}/scenes/{scene_id}/cast` body `{"entity_ids": [...]}`
  - `GET /api/projects/{project_id}/characters/{entity_id}/sheet` → ảnh bảng hiện tại.
- Giao diện: chỉ hiện với dự án vụ án; mỗi nhân vật cần cho video cao trào một thẻ: tên, vai, ô sửa `design_en`, ảnh bảng, nút "Vẽ bảng", "Duyệt", "Vẽ lại" (ô ghi chỗ sai, bắt buộc); nhãn trạng thái; chữ từ máy chủ qua `escapeHtml()`.

- [ ] **Step 1:** Test API hỏng: 404 dự án không có, 400 id sai, 400 vẽ lại không có ghi chú, 409 vẽ khi đang vẽ, luồng draw → review → reject → draw → approve với Muse giả.
- [ ] **Step 2:** Chạy → FAIL. **Step 3:** Cài đặt. **Step 4:** Test PASS; kiểm giao diện trên server thử 8010 với dự án thử dựng bằng ảnh giả và file `characters.json` tạo sẵn đủ các trạng thái (draft, review, approved, failed) — không bấm "Vẽ bảng" vì sẽ gọi Muse; bấm `#btn-character-sheets`, sửa thiết kế, Duyệt, Vẽ lại thiếu ghi chú (phải báo lỗi); xem console và log server, so `projects/` trước–sau.
- [ ] **Step 5:** Commit `nhân vật: cửa sổ Bảng nhân vật ở Bước 2 (sửa thiết kế, vẽ, duyệt, vẽ lại có ghi chú)`.

### Task 5: Video cao trào theo chat của cảnh, có duyệt grid

**Files:**
- Modify: `backend/services/climax_video.py`, `backend/routers/climax_video.py`
- Test: `tests/test_climax_video.py`

**Interfaces:**
- Consumes: Task 1–3 (`scene_cast`, `cast_board`, `CharacterSheet.design_en`, kết quả Muse có `thread_url`, `muse_reply`).
- Produces:
  - Trạng thái `metadata["climax_video"]` thêm: `"grid_review"` (chờ chủ dự án duyệt grid), các khoá `thread_url`, `account_id`, `thread_dirty: bool`, `grid_path`.
  - `grid_prompt(scene, project, first_grid, cast: list[CharacterSheet]) -> str` — giữ các ý cũ (3x3, viền trắng, không chữ, `STYLE_LOCK_EN`) + từng nhân vật: tên vai trò + `design_en`; câu "the second attached image is the character reference board: every character must match it from every angle".
  - `clip_prompt(scene, panel, next_panel, cast) -> str` — mẫu D của chủ dự án: "Subtle motion only: … STRICT STYLE LOCK: …" + khoá từng nhân vật bằng `design_en` + `CLIP_CAMERA_EN` + `Avoid:`; gửi `raw_prompt=True` với đầu "tạo cho tôi 1 video 5s:".
  - `async run_scene_grid(project_id, scene_id, muse_call) -> dict` — kiểm cảnh có nhân vật (không có: failed "Chưa chọn nhân vật cho cảnh") và mọi bảng đã duyệt (thiếu: failed nêu tên, không gọi Muse) → việc grid `route_kind="video"`, `attachments=[ảnh cảnh, cast_board]`, `thread_url` của cảnh nếu có và không bẩn (kèm `pin_account`) → lưu grid, status `"grid_review"`.
  - `approve_grid(project_id, scene_id)`; `reject_grid(project_id, scene_id, feedback)` (vẽ lại trong cùng chat, feedback vào prompt).
  - `async run_scene_clips(project_id, scene_id, muse_call) -> dict` — chỉ chạy khi grid đã duyệt; mỗi clip `attachments=[ô, cast_board]`, cùng `thread_url`, `pin_account=True`; phần chỉnh màu, kiểm, ghép, gắn vào cảnh giữ như cũ.
  - Quy tắc chat bẩn: việc nào trong chat quá giờ (`TimeoutError`) hoặc `THREAD_OPEN_FAILED` → `thread_dirty=True`; việc kế tiếp của cảnh mở chat mới (không `thread_url`), đính kèm lại ảnh cảnh/ô + `cast_board`.
  - API mới: `POST /api/projects/{project_id}/climax-video/scenes/{scene_id}/grid/approve`, `.../grid/reject` body `{"feedback": str}`, `GET .../scenes/{scene_id}/grid`; `POST .../climax-video/run` chạy grid cho cảnh "selected"/"failed" và clip cho cảnh đã duyệt grid.
  - `run_scene_climax_video()` giữ tên cho tương thích: gọi grid rồi dừng ở `"grid_review"`.

- [ ] **Step 1: Viết test hỏng** (Muse giả trả `thread_url`, `executed_by`)

```python
def test_scene_without_cast_fails_without_muse(...): ...
def test_unapproved_sheet_blocks_grid_and_names_character(...): ...      # "Thẩm Nhã Uyên" trong error, muse.tasks == []
def test_grid_runs_on_video_account_with_scene_image_and_cast_board(...): ...
    # task: mode text-to-image, route_kind video, raw_prompt True, attachments == [ảnh cảnh, board], status sau: grid_review
def test_clips_wait_for_grid_approval(...): ...
def test_clips_reuse_scene_thread_and_pin_account(...): ...                # mọi việc clip cùng thread_url, pin_account True
def test_timeout_marks_thread_dirty_and_next_task_opens_new_chat(...): ...
def test_reject_grid_redraws_in_same_thread_with_feedback(...): ...
def test_clip_prompt_locks_each_character_design(...): ...                 # design_en của từng nhân vật, CLIP_CAMERA_EN, "Avoid:"
```

- [ ] **Step 2:** Chạy → FAIL. **Step 3:** Cài đặt; sửa test cũ chỗ hợp đồng đổi (grid giờ dừng ở `grid_review`). **Step 4:** `pytest tests\test_climax_video.py -q` → PASS.
- [ ] **Step 5:** Commit `video cao trào: làm trong side chat của cảnh trên tài khoản video, đính kèm bảng nhân vật, duyệt grid trước khi làm clip`.

### Task 6: Giao diện thẻ cảnh — nhân vật của cảnh, duyệt grid

**Files:**
- Modify: `backend/static/climax_video.js`
- Test: kiểm tay trên server thử 8010 (giao diện chưa có test tự động)

**Interfaces:**
- Consumes: Task 4–5 API.
- Produces: trên thẻ cảnh (dự án vụ án): chip nhân vật (bấm để sửa danh sách, gọi `PUT .../scenes/{scene_id}/cast`); khi `"grid_review"`: ảnh grid nhỏ bấm phóng to, nút "Duyệt grid", "Vẽ lại grid" (ô ghi chỗ sai); nút `#btn-climax-video-run` đổi chữ theo việc tiếp theo ("Vẽ grid cho N cảnh" / "Làm clip cho N cảnh đã duyệt grid").

- [ ] **Step 1:** Làm theo Interfaces, dựng DOM bằng `textContent` như hiện nay.
- [ ] **Step 2:** Kiểm trên server thử 8010 với dự án thử ảnh giả và trạng thái tạo sẵn; console không lỗi ngoài lỗi cố ý; `projects/` trước–sau như nhau.
- [ ] **Step 3:** Cập nhật `FEATURE_MAP.md` (nút, cửa sổ, API mới, ghi **Muse** cho vẽ bảng / grid / clip), `CLAUDE.md` bảng 1.1 dòng ảnh/video, `TASKS.md`.
- [ ] **Step 4:** `.venv\Scripts\python.exe tools\check.py --full` → ĐẠT, ghi số test và thời gian.
- [ ] **Step 5:** Commit `video cao trào: thẻ cảnh hiện nhân vật và duyệt grid; cập nhật bản đồ tính năng`.

### Task 7: Chạy thật trên Muse (chỉ khi chủ dự án cho phép)

- [ ] Khởi động lại máy bằng **Restart** trước (lần trước `AppXSvc` giữ 9,6 GB, Chrome không tải nổi Muse).
- [ ] Repo thật tạm chuyển nhánh như lần 27/10; bản sao dự án Trạm Dung; dùng bảng đã duyệt của Thẩm Nhã Uyên (`bang_nhan_vat_2.jpg`) làm bảng duyệt sẵn; vẽ bảng cho người còn thiếu của cảnh chọn thử.
- [ ] Cảnh thử: 28 (một nhân vật đầu tròn) và 41 (nhiều nhân vật). Soi từng khung grid và clip theo danh sách (đầu, mặt, tóc từng góc, áo, quần, giày), gửi ảnh cho chủ dự án duyệt.
- [ ] Ghi số lượt Muse, thời gian, lỗi Muse trả bằng chữ vào `TASKS.md`; đưa repo thật về `master`.

---

## Điều cần chủ dự án xác nhận trước khi làm

1. `HAIR_RULE_EN` (tóc mọc từ đỉnh, phủ nửa sau đầu) làm **mặc định cho mọi nhân vật** của phong cách "Hoạt hình 2D rùng rợn", sửa từng người khi khác (vd người hói, tóc búi)?
2. Có thêm bước **duyệt grid** trước khi làm clip (Task 5–6) không, hay grid đạt máy kiểm là làm clip luôn?
3. Gộp bảng của nhiều nhân vật thành **một ảnh "bảng diễn viên"** để giữ 2 ảnh đính kèm mỗi tin nhắn (mới đo được tối đa 2), chấp nhận được không?
