# Video cao trào giao việc nhiều bước cho Muse + tóc nhân vật nữ — kế hoạch code

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pha làm clip của nút video cao trào gửi Muse một yêu cầu nhiều bước mỗi cảnh (Muse tự chia đoạn, tự kiểm, tự làm lại, gửi một video cuối + ảnh cảnh đã sửa tóc), và nhân vật nữ của phong cách đầu tròn luôn có tóc dày trên đỉnh đầu.

**Architecture:** Bản giao việc dựng bằng khuôn trong `services/climax_brief.py` (không gọi LLM). Fleet Runner thêm chế độ `agent-video`: chờ Muse viết xong lượt (dòng `done_token` ở cuối, chữ đứng yên), lấy video cuối và các ảnh mới, nộp qua `complete_task` (thêm ô file phụ). `climax_video.run_scene_clips()` thay vòng lặp từng clip bằng một lần gọi này, kiểm file bằng ffprobe, thay ảnh cảnh (giữ bản dự phòng).

**Tech Stack:** Python 3.14, FastAPI, Playwright (runner), ffmpeg/ffprobe, numpy/OpenCV, pytest; giao diện JS thuần.

**Spec:** `docs/superpowers/specs/2026-10-28-video-cao-trao-giao-viec-muse-design.md`

## Global Constraints

- Làm trên nhánh `video-cao-trao-giao-viec`, không commit lên `master`; commit tiếng Việt dạng `<vùng>: <mô tả>`; không `--no-verify`.
- Python luôn `.venv\Scripts\python.exe`; in tiếng Việt thêm `-X utf8`.
- Test không gọi Muse, không bật trình duyệt, không ghi `projects/` thật (fixture `isolated_projects_dir`, Muse giả).
- `os.getenv` chỉ trong `config.py`; biến mới phải có trong `.env.example`.
- Chữ từ server/Muse chèn vào HTML phải qua `escapeHtml()`.
- Ngân sách mỗi yêu cầu Muse: tối đa 6 video và 4 ảnh. Độ dài mục tiêu: `min(lời kể, 24)` giây.
- Câu quy tắc tóc (nguyên văn, mục 3.1 spec): `Female characters always have thick, full hair covering most of the top of the head: a generous mass of hair on the crown that frames the white face, then falls to the length given in the design; never a bald round head with only a little hair at the nape.`
- Quy tắc tóc chỉ áp cho phong cách `horror_cartoon_2d`, người `gender == "female"`.
- Chờ tối đa `MUSE_AGENT_WAIT_MIN` phút (mặc định 45).
- Ghi file dự án chỉ qua `project_service.save_project()` (đường cấm số 1).

## Review Focus

1. Báo cáo của Muse có chữ "lỗi", "loại", "failed" (Muse kể clip nó đã loại) → runner không được coi là Muse báo lỗi và bỏ ngang. Test ở Task 4.
2. `done_token` nằm ngay trong prompt mình gửi → không được coi là xong ngay khi vừa gửi. Test ở Task 4.
3. Muse gửi cả ảnh cảnh sửa tóc lẫn ảnh góc sau lưng → chỉ ảnh giống ảnh cảnh cũ mới được thay vào; không có ảnh nào đủ giống thì giữ ảnh cũ. Test ở Task 5.
4. Bấm "Làm lại" hai lần → bản dự phòng `*.truoc_sua_toc.jpg` vẫn là ảnh gốc ban đầu, không bị ghi đè bằng ảnh đã sửa. Test ở Task 5.
5. Hết giờ chờ hay Muse lỗi → chat của cảnh bị đánh dấu bẩn, lần sau mở chat mới; kết quả về muộn không ghi đè cảnh. Test ở Task 5 (chat bẩn); bridge đã có `abandoned` cho kết quả muộn.

---

### Task 1: Nhánh làm việc từ `master` + code của `thu-video-cao-trao`

**Files:** không tạo file mới; toàn bộ code của nhánh `thu-video-cao-trao` trừ commit `3bef9ee`.

**Interfaces:**
- Produces: nhánh `video-cao-trao-giao-viec` có bảng nhân vật, chat riêng mỗi cảnh, pha lưới, và vẫn giữ `.claude/skills/`, `.claude/agents/`.

- [ ] **Step 1:** `git switch -c video-cao-trao-giao-viec ke-hoach-giao-viec-muse`
- [ ] **Step 2:** Lấy từng commit, bỏ `3bef9ee`: `git cherry-pick 5c35596 b4e936d 49bf9ea baf25de b9ad601 9eaac9d 268c85f ae0f863 c17968b 52a2c9e d7fadb8 2a2da93 c862ee2 06e8408 433a52c e3b34f3 52ab83c 18988bc 4c3b436 e70f290 c6fe7e8 37be568 b363b9c 5f44fc8` (đúng thứ tự cũ → mới, không có `3bef9ee`). Xung đột thì giữ phần của nhánh, trừ `.claude/` giữ của `master`.
- [ ] **Step 3:** Kiểm còn đội agent: `git ls-files .claude/skills .claude/agents | wc -l` → 11.
- [ ] **Step 4:** `.venv\Scripts\python.exe tools\check.py --full` → `Kết quả: ĐẠT`.

### Task 2: Quy tắc tóc nhân vật nữ

**Files:**
- Modify: `backend/services/image_service.py` (thêm hằng số, nối vào `prompt_suffix` của `horror_cartoon_2d`)
- Modify: `backend/services/character_sheets.py` (`sheet_prompt`, hàm mới `hair_rule_for`)
- Test: `tests/test_female_hair_rule.py`

**Interfaces:**
- Produces: `image_service.FEMALE_HAIR_RULE_EN: str` (câu nguyên văn ở Global Constraints); `image_service.ROUND_HEAD_STYLES = ("horror_cartoon_2d",)`; `character_sheets.hair_rule_for(project: Project, entity_id: str) -> str` (trả câu quy tắc hoặc `""`); `character_sheets.sheet_prompt(sheet: CharacterSheet, hair_rule: str = "") -> str`.

- [ ] **Step 1: Viết test hỏng**

```python
def test_round_head_style_suffix_has_female_hair_rule():
    assert FEMALE_HAIR_RULE_EN in STYLE_PRESETS["horror_cartoon_2d"]["prompt_suffix"]
    assert all(FEMALE_HAIR_RULE_EN not in p["prompt_suffix"] for k, p in STYLE_PRESETS.items() if k != "horror_cartoon_2d")

def test_hair_rule_only_for_female_in_round_head_project(isolated_projects_dir):
    # dự án vụ án giả, style horror_cartoon_2d, person_1 female, person_2 male
    assert hair_rule_for(project, "person_1") == FEMALE_HAIR_RULE_EN
    assert hair_rule_for(project, "person_2") == ""
    # cùng người nữ, dự án style "anime" -> ""

def test_sheet_prompt_adds_rule_once_and_says_it_wins():
    p = sheet_prompt(sheet_with_old_back_half_hair_design, FEMALE_HAIR_RULE_EN)
    assert p.count(FEMALE_HAIR_RULE_EN) == 1
    assert "overrides" in p   # câu dẫn: "This hair rule overrides any other hair placement in the design:"
    assert sheet_prompt(sheet_with_old_back_half_hair_design) == sheet_prompt_before_change   # không có rule -> như cũ
```

- [ ] **Step 2:** `.venv\Scripts\python.exe -m pytest tests\test_female_hair_rule.py -q` → FAIL (chưa có tên).
- [ ] **Step 3:** Cài đặt. `hair_rule_for` lấy style từ `project` (trường style đang dùng ở `default_design`), gender từ `case_people(project)`. `sheet_prompt` thêm dòng `This hair rule overrides any other hair placement in the design: <rule>` ngay sau khối thiết kế, chỉ khi `hair_rule` khác rỗng và chưa có trong `design_en`. Chỗ gọi `sheet_prompt` hiện có truyền `hair_rule_for(project, sheet.entity_id)`.
- [ ] **Step 4:** Chạy lại test → PASS; `pytest tests\test_character_sheets.py -q` → PASS.
- [ ] **Step 5:** Commit `nhân vật: nhân vật nữ phong cách đầu tròn luôn có tóc dày trên đỉnh đầu`.

### Task 3: Bản giao việc cho Muse

**Files:**
- Create: `backend/services/climax_brief.py`
- Test: `tests/test_climax_brief.py`

**Interfaces:**
- Consumes: `hair_rule_for` (Task 2); `CharacterSheet.design_en`, `name_vi`.
- Produces: `AGENT_MAX_VIDEOS = 6`, `AGENT_MAX_IMAGES = 4`, `AGENT_MAX_SECONDS = 24`, `NEW_SCENE_IMAGE_TAG = "ANH_CANH_MOI"`; `target_seconds(narration_sec: float) -> int` (làm tròn lên, tối thiểu 5, tối đa 24); `scene_brief(project: Project, scene: Scene, people: list[CharacterSheet], grid_count: int, done_token: str) -> str`.

- [ ] **Step 1: Viết test hỏng**

```python
def test_brief_has_every_rule_and_ends_with_token(isolated_projects_dir):
    b = scene_brief(project, scene, [nu, nam], grid_count=1, done_token="XONG-t123")
    assert b.rstrip().splitlines()[-1].endswith("XONG-t123")
    for must in ["6 video", "4 ảnh", "không clip nào", "xoay", "góc sau", "mỗi giây", "khung cuối",
                 "mặt người", scene.text.strip(), nu.name_vi, nam.name_vi, "ANH_CANH_MOI", "chỉ một video"]:
        assert must in b
    assert b.count(FEMALE_HAIR_RULE_EN) == 1      # một người nữ -> một lần
    assert f"{target_seconds(scene_seconds)} giây" in b

def test_target_seconds_bounds():
    assert target_seconds(3.2) == 5 and target_seconds(11.9) == 12 and target_seconds(80) == 24

def test_brief_lists_attachments_in_order():
    # "Ảnh 1" = ảnh cảnh, "Ảnh 2" = bảng diễn viên, "Ảnh 3".."Ảnh 2+grid_count" = lưới
    assert "Ảnh 3" in scene_brief(..., grid_count=1, ...) and "Ảnh 4" in scene_brief(..., grid_count=2, ...)
```

- [ ] **Step 2:** `pytest tests\test_climax_brief.py -q` → FAIL.
- [ ] **Step 3:** Viết `scene_brief`. Khung chữ theo bản giao việc của thí nghiệm 2 (`.cache/thu-muse-28-lan2/tien_do.txt`, phần trên dòng kết thúc), thay phần chia clip viết sẵn bằng: "Tự lập danh sách clip từ lời kể và lưới (ô nào góc trước/nghiêng, ô nào góc sau), ghi danh sách vào báo cáo". Có đủ: vai trò từng ảnh đính kèm; lời kể + số giây mục tiêu; mỗi người một dòng thiết kế (`design_en`, cắt 600 ký tự) + quy tắc tóc nếu `hair_rule_for` khác rỗng; luật không xoay người trong clip; đoạn quay lưng bắt đầu từ ảnh góc sau vẽ riêng; ảnh cảnh khác bảng nhân vật (tóc) thì vẽ lại ảnh cảnh trước, gửi kèm trong tin cuối và ghi `ANH_CANH_MOI: có`; tự kiểm mỗi giây + khung cuối với tiêu chí loại của spec; cử động ít hay chạy tại chỗ vẫn đạt, mặt người thì không bao giờ đạt; ngân sách 6 video/4 ảnh; giao chỉ một video cuối + báo cáo; dòng cuối là `done_token`.
- [ ] **Step 4:** Test → PASS.
- [ ] **Step 5:** Commit `video cao trào: bản giao việc nhiều bước cho Muse (khuôn trong code, không gọi LLM)`.

### Task 4: Fleet Runner chế độ `agent-video`

**Files:**
- Create: `backend/runners/muse_agent_turn.py` (hàm thuần, test được không cần trình duyệt)
- Modify: `backend/runners/muse_fleet_runner.py` (`execute_task_with_browser`: nhánh `mode == "agent-video"`; `complete_task_to_backend`: gửi thêm file phụ)
- Test: `tests/test_muse_agent_turn.py`

**Interfaces:**
- Consumes: task do Task 5 tạo: `{"mode": "agent-video", "route_kind": "video", "raw_prompt": True, "prompt": str, "attachments": [str, ...], "agent": {"done_token": str, "wait_sec": int, "target_seconds": int}, "thread_url"?, "pin_account"?}`.
- Produces:
  - `turn_done(text_before: str, text_now: str, prompt: str, token: str) -> bool` — đúng khi phần chữ mới (sau `text_before`, đã bỏ chính `prompt`) kết thúc bằng `token` sau khi bỏ khoảng trắng.
  - `STREAMING_JS` — trả `true` khi còn phần tử `[data-hatch-markdown-streaming="true"]` trong `[role=log]`.
  - `pick_final_video(srcs: list[str]) -> Optional[str]` — phần tử cuối hoặc `None`.
  - Kết quả nộp: file chính = video cuối; `extras` = ảnh mới (tối đa 4, đã qua `validate_image_bytes`, đổi JPEG 16:9); meta thêm `muse_reply` (tối đa 8000 ký tự), `media_count: {"video": int, "image": int}`, `warnings: list[str]`.
  - Mã lỗi: `AGENT_TIMEOUT` (hết `wait_sec`), `NO_FINAL` (xong lượt mà không có video mới), `MUSE_REPLIED_ERROR` chỉ khi Muse dừng lượt **không** có `done_token` và câu cuối khớp `muse_reply_error`.

- [ ] **Step 1: Viết test hỏng**

```python
def test_token_inside_prompt_is_not_done():
    p = "...Dòng cuối ghi: XONG-t1"
    assert not turn_done("", "You:\n" + p, p, "XONG-t1")

def test_done_when_new_text_ends_with_token():
    p = "brief ... XONG-t1"
    assert turn_done("", "You:\n" + p + "\nĐã xong.\nXONG-t1\n", p, "XONG-t1")
    assert not turn_done("", "You:\n" + p + "\nXONG-t1 rồi mình làm tiếp clip 2", p, "XONG-t1")

def test_report_words_like_loi_do_not_end_the_turn():
    p = "brief XONG-t1"
    now = "You:\n" + p + "\nClip 1 LOẠI: lỗi đầu trắng, tạo lại..."
    assert not turn_done("", now, p, "XONG-t1")
    assert agent_failure("", now, p, "XONG-t1", turn_finished=False) is None   # Muse còn đang làm -> chưa phải lỗi

def test_pick_final_video():
    assert pick_final_video(["a", "b"]) == "b" and pick_final_video([]) is None
```

  (`agent_failure(text_before, text_now, prompt, token, turn_finished) -> Optional[str]` cũng thuộc `muse_agent_turn.py`: trả câu lỗi chỉ khi `turn_finished` và không có token và `muse_reply_error` khớp.)
- [ ] **Step 2:** `pytest tests\test_muse_agent_turn.py -q` → FAIL.
- [ ] **Step 3:** Viết `muse_agent_turn.py`, rồi nhánh `agent-video` trong runner: dùng lại mở chat/đính kèm/gửi nguyên văn hiện có; vòng chờ mỗi `SCAN_INTERVAL_SEC`: bấm "Cho phép" như cũ, lưu `thread_url`, coi lượt xong khi `turn_done` và `STREAMING_JS` sai và chữ đứng yên 90 giây; quá `wait_sec` → `AGENT_TIMEOUT` (kèm 400 ký tự cuối Muse nói, như lỗi hiện có). Xong lượt: `FIND_NEW_MEDIA_JS` cho `"video"` và `"image"` với `pre_srcs` lúc gửi; video qua `CANDIDATE_STABLE_CHECKS`, `validate_video_file(path, 2 * target_seconds + 1)`; nhiều video → lấy cuối, thêm cảnh báo `"Tin cuối có N video, lấy video cuối"`; video > 6 hay ảnh > 4 → cảnh báo vượt ngân sách. `complete_task_to_backend` gửi các ảnh phụ dưới tên trường `extras`.
- [ ] **Step 4:** Test → PASS; `pytest tests\test_muse_threads.py tests\test_muse_fleet_runner_media.py -q` → PASS.
- [ ] **Step 5:** Commit `muse: runner chế độ giao việc nhiều bước (chờ Muse xong lượt, lấy video cuối và ảnh mới)`.

### Task 5: Bridge nhận kết quả và pha clip mới

**Files:**
- Modify: `backend/config.py`, `.env.example` (`MUSE_AGENT_WAIT_MIN`, mặc định 45)
- Modify: `backend/routers/muse_bridge.py` (`_task_timeout`, `complete_task` nhận `extras`, `muse_reply` 8000 ký tự cho `agent-video`, chuyển `media_count`, `warnings`, `extra_images` vào kết quả)
- Modify: `backend/services/climax_video.py` (`run_scene_clips` mới; bỏ `_make_clip`, `clip_prompt`, `match_clip_colors`, `check_clip`, `concat_clips`, `CLIP_*`, `MIN_FIRST_SIMILARITY` nếu không còn ai dùng)
- Modify: `backend/routers/climax_video.py` (endpoint làm lại)
- Modify: `tests/test_climax_video.py` (bỏ test của phần đã xoá, thêm test mới)
- Test: `tests/test_climax_agent_phase.py`

**Interfaces:**
- Consumes: `scene_brief`, `target_seconds`, `AGENT_MAX_*` (Task 3); dạng task/kết quả của Task 4.
- Produces:
  - `config.MUSE_AGENT_WAIT_MIN: int`.
  - `climax_video.check_agent_video(path: Path, target_seconds: int) -> float` — trả độ dài; có hình, `5 <= độ dài <= 2*target+1`, sai thì `ClimaxVideoError`.
  - `climax_video.choose_scene_image(old: Path, candidates: list[Path]) -> Optional[Path]` — ảnh giống `old` nhất theo `_ssim_global` trên ảnh xám 320×180, chỉ nhận khi `>= SCENE_IMAGE_MIN_SIMILARITY = 0.45` và tỉ lệ 16:9 (±3%).
  - `climax_video.replace_scene_image(project_id: str, scene_id: str, new: Path) -> Path` — chép ảnh cũ sang `images/<scene_id>.truoc_sua_toc.jpg` nếu chưa có, ghi ảnh mới đè đúng `image_path` (giữ tên file), lưu qua `project_service.save_project()`; trả đường dẫn bản dự phòng.
  - Trạng thái cảnh khi xong: `status="ready"`, `muse_report: str`, `media_count`, `warnings`, `scene_image_updated: bool`, `backup_image: str?`.
  - `POST /api/projects/{project_id}/climax-video/scenes/{scene_id}/redo` → cảnh đang `ready` hoặc `failed` mà `grid_approved` → `status="grid_approved"`, `thread_dirty=True`; đang chạy → 409.

- [ ] **Step 1: Viết test hỏng** (Muse giả trả dict kết quả như bridge, ffmpeg thật tạo video thử)

```python
def test_agent_phase_sends_one_brief_and_marks_ready(isolated_projects_dir):
    calls = []  # Muse giả ghi task, trả video 12 s + 2 ảnh (một giống ảnh cảnh, một khác hẳn)
    state = asyncio.run(run_scene_clips(pid, sid, fake_muse))
    assert len(calls) == 1 and calls[0]["mode"] == "agent-video"
    assert calls[0]["attachments"][:2] == [scene_image, board] and calls[0]["agent"]["target_seconds"] == 12
    assert calls[0]["prompt"].rstrip().endswith(calls[0]["agent"]["done_token"])
    assert state["status"] == "ready" and state["scene_image_updated"] is True and state["muse_report"]

def test_choose_scene_image_ignores_back_view_and_keeps_old_when_none_similar(tmp_path): ...
def test_redo_twice_keeps_original_backup(isolated_projects_dir): ...   # bản dự phòng = ảnh gốc ban đầu
def test_bad_video_fails_keeps_image_and_marks_chat_dirty(isolated_projects_dir): ...  # video 2 s -> failed, thread_dirty
def test_muse_timeout_marks_chat_dirty(isolated_projects_dir): ...
def test_agent_task_timeout_uses_config(monkeypatch):
    assert _task_timeout({"mode": "agent-video"}) == config.MUSE_AGENT_WAIT_MIN * 60 + 120
def test_complete_task_saves_extra_images(client): ...   # multipart: file + 2 extras -> result["extra_images"] có 2 đường dẫn trong muse_outputs
def test_api_redo_409_while_running_and_resets_state(client): ...
```

- [ ] **Step 2:** `pytest tests\test_climax_agent_phase.py -q` → FAIL.
- [ ] **Step 3:** Cài đặt. `run_scene_clips`: kiểm lưới đã duyệt như cũ → `_cast_for` → `done_token = f"XONG-{uuid4().hex[:8]}"` → task như Interfaces của Task 4 với `wait_sec = MUSE_AGENT_WAIT_MIN * 60`, `attachments = [ảnh cảnh, bảng diễn viên, *lưới đã duyệt]`, đi qua `_muse(muse_call, thread, task)` có sẵn; gọi bằng `enqueue_and_wait_muse_task(task, timeout=wait_sec + 120)`. Kết quả: `_keep_copy` video → `check_agent_video` → chép thành `motion_video` → `choose_scene_image` trên `extra_images` → `replace_scene_image` nếu có → `_mark_ready` với các khoá trạng thái mới. Lỗi: `failed` + `thread_dirty=True` (trong `SceneThread.state()` hay `_merge_climax`). `complete_task`: trường `extras: list[UploadFile] = File(default=[])`, tối đa 4, mỗi file qua `read_upload_limited` và kiểm là ảnh; lưu `muse_outputs/<task_id>_extra_<n>.jpg`. Xoá hàm cũ không còn ai gọi; `tools/check.py` báo hàm chết thì xoá theo.
- [ ] **Step 4:** Test mới → PASS; `pytest tests\test_climax_video.py tests\test_climax_review_fixes.py tests\test_muse_threads.py -q` → PASS (đã sửa test của phần bị thay).
- [ ] **Step 5:** Commit `video cao trào: pha clip giao một việc nhiều bước cho Muse, thay ảnh cảnh đã sửa tóc (giữ bản cũ)`.

### Task 6: Giao diện và bản đồ tính năng

**Files:**
- Modify: `backend/static/climax_video.js` (thẻ cảnh: báo cáo Muse thu gọn, cảnh báo, nút làm lại; tăng số phiên bản script trong `index.html`)
- Modify: `FEATURE_MAP.md` (endpoint redo, chế độ `agent-video`, tốn **Muse** tối đa 6 video + 4 ảnh mỗi cảnh), `CLAUDE.md` mục 1.1 (dòng ảnh/video: sự thật code mới)
- Test: `tests/test_architecture.py` (đã có: escape, gắn sự kiện một lần, FEATURE_MAP khớp endpoint)

**Interfaces:**
- Consumes: trạng thái cảnh và endpoint redo của Task 5.
- Produces: phần tử `[data-climax-report="<scene_id>"]` (chữ báo cáo, `escapeHtml`), `[data-climax-redo="<scene_id>"]` (nút "Làm lại cảnh này", hỏi `confirm` có ghi "tối đa 6 video + 4 ảnh Muse"), nhãn cảnh báo khi `warnings` khác rỗng, nhãn "Đã thay ảnh cảnh (bản cũ: …)" khi `scene_image_updated`.

- [ ] **Step 1:** Thêm phần tử và gọi `POST .../redo` rồi `.../run`; mọi chữ từ server qua `escapeHtml()`.
- [ ] **Step 2:** `.venv\Scripts\python.exe tools\check.py` → `Kết quả: ĐẠT` (cú pháp JS, kiến trúc, FEATURE_MAP).
- [ ] **Step 3:** Bấm thử trên server thử 8010 (`.claude/launch.json`), dự án thử ảnh giả, Muse giả trả video + ảnh: thẻ cảnh hiện báo cáo, nút làm lại hỏi xác nhận, ảnh cảnh đổi và có bản dự phòng; console không lỗi ngoài lỗi cố ý; so danh sách `projects/` trước và sau.
- [ ] **Step 4:** Commit `video cao trào: thẻ cảnh hiện báo cáo Muse, cảnh báo ngân sách và nút làm lại`.

### Task 7: Kiểm chứng cuối và chạy thật

**Files:** `TASKS.md` (ghi kết quả)

- [ ] **Step 1:** `.venv\Scripts\python.exe tools\check.py --full` → `Kết quả: ĐẠT`; ghi số test đạt và thời gian.
- [ ] **Step 2:** Chạy thật (tốn **Muse**): server thử 8010, bản sao `proj_crime_thucaotrao`, cảnh 28 rồi cảnh 41, mỗi cảnh một lần bấm. Trước cảnh 41: duyệt lại lưới của cảnh (đang "chờ duyệt grid"). Ghi mỗi cảnh: số video/ảnh Muse báo, thời gian, danh sách clip Muse tự chia.
- [ ] **Step 3:** Trích khung mỗi giây hai video, xem bằng mắt theo chống mục tiêu của spec (không khung nào mặt người; tóc nữ trên đỉnh đầu; không đĩa trắng sau tóc); xem ảnh cảnh đã thay và bản dự phòng.
- [ ] **Step 4:** Mời giám khảo (`.claude/agents/giam-khao.md`, skill `cham-cheo`) chấm nhánh; sửa tới khi ĐẠT (tối đa 3 vòng).
- [ ] **Step 5:** Ghi kết quả vào `TASKS.md`, commit `tài liệu: ghi kết quả chạy thật giao việc nhiều bước cho Muse (cảnh 28, 41)`. Không gộp `master` khi chủ dự án chưa đồng ý.
