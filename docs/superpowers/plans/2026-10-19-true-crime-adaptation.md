# Chuyển thể vụ án thật song ngữ: kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thay luồng true-crime đang chạy theo khuôn bằng luồng LLM (9router), gồm nhiều việc nhỏ chạy tuần tự. Từ một vụ án thật, luồng này cho ra kế hoạch chuyển thể song ngữ Việt/Anh, dự án bản Việt, và bản Anh dùng chung hình.

**Architecture:**
- **Phân tích là một hàng việc lưu trên đĩa** (`projects/_cases/<case_id>/pipeline.json`). Hàng gồm: đọc từng đoạn → gộp tên → đặt tên hư cấu → dàn ý → với mỗi nhịp lần lượt viết lời Việt, lời Anh, prompt → ráp và kiểm tra.
- **Một worker** chạy trong server, mỗi lúc chỉ làm một việc. Mỗi việc là một lần gọi LLM hẹp, đầu ra được code kiểm ngay; đầu ra mỏng thì gọi lại kèm lý do.
- **Dựng dự án và tạo bản Anh** là module riêng. Router `true_crime.py` được viết lại.
- **Giao diện** true-crime tách sang `static/true_crime.js`.

**Tech Stack:** FastAPI, pydantic v2, httpx, PIL, asyncio, JS thuần + Tailwind build sẵn, pytest. Không thêm thư viện.

**Spec:** `docs/superpowers/specs/2026-10-19-true-crime-adaptation-design.md`. Đọc kỹ mục 6 và mục 7.1a–7.5. Người thực hiện đọc cả spec lẫn kế hoạch này.

## Global Constraints

- **LLM:**
  - Chỉ gọi qua 9router: `POST {NINEROUTER_BASE_URL}/chat/completions`, model `NINEROUTER_LLM_MODEL` (`backend/config.py`), payload luôn có `"stream": False`.
  - Không fallback offline.
  - **Mỗi lúc chỉ có một lần gọi LLM** cho phân tích. Các việc chạy tuần tự, theo đúng thứ tự trong hàng việc.
- **Một việc nhỏ:**
  - Thử tối đa `MAX_ATTEMPTS = 3`. Từ lần thứ 2 trở đi, nối thêm vào cuối prompt: `\n\nLẦN TRƯỚC BỊ LOẠI VÌ: {lý do}. Hãy làm lại đầy đủ, không tóm gọn.`
  - Lỗi `auth`/`no_credentials`/`http` từ 9router thì không thử lại.
- **Ngưỡng mặc định** (spec 7.1a–7.4):

  | Ngưỡng | Giá trị |
  |---|---|
  | Kích thước đoạn | `chunk_chars = 3000` |
  | Số sự việc mỗi đoạn (đoạn ≥ 150 từ) | ≥ 1 cho mỗi 250 từ |
  | Độ dài tóm tắt sự việc | ≥ 12 từ |
  | Số cảnh mỗi nhịp | 2–6 |
  | Độ dài `narration_vi` | 25–80 từ |
  | Độ dài `narration_en` | 20–70 từ |
  | Độ dài `image_prompt` | ≥ 20 từ |

- **Thời lượng và số cảnh:**
  - số cảnh mục tiêu: `{8: (35, 40), 15: (50, 60), 20: (70, 80), 30: (100, 120)}`;
  - tổng số cảnh không vượt mục tiêu quá 20%;
  - bài vào tối đa `200_000` ký tự;
  - cảnh video tối đa `15%`.
- **Câu miễn trừ** (cảnh 1), nguyên văn:
  - vi: `Câu chuyện dựa trên một vụ án có thật; tên người và địa danh đã được thay đổi.`
  - en: `This story is based on a real case; names of people and places have been changed.`
- **Giọng mặc định:** tiếng Việt là voice `vieneu-*` đầu tiên trong `/api/voices`; tiếng Anh là `en-US-AndrewMultilingualNeural`.
- **Python:** `.venv/Scripts/python.exe` (3.14). Lệnh test: `".venv/Scripts/python.exe" -m pytest tests/<file> -q`.
- **Bảo mật:**
  - Không in hay chép `.env`.
  - Route nhận id dùng `require_safe_id`/`validate_path_ids`; đường dẫn kiểm bằng `is_within` (`backend/security.py`).
- **Test offline:**
  - Mock LLM, chạy trong thư mục tạm qua fixture `isolated_projects_dir`.
  - Worker tự khởi động bị tắt bằng `STORY_STUDIO_DISABLE_CASE_WORKER=1`, đặt trong `tests/conftest.py`.
- **Test thật** với 9router và Muse được phép thoải mái (người dùng cho ngày 19/10/2026), đặt trong `tests/test_case_adaptation_live.py`. File này skip nếu không có `STORY_STUDIO_LIVE=1`.
- **Git:**
  - Commit tiếng Việt, theo kiểu `<khu vực>: <mô tả>`, dòng cuối `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - Mỗi commit chỉ `git add` file của task, không đổi nhánh (có phiên khác cùng làm trong folder).
- **Dữ liệu:** dữ liệu vụ án nằm ở `projects/_cases/<case_id>/`, không ghi vào `backend/static/`.

## Review Focus

1. **LLM trả JSON bọc trong ```` ```json ```` hoặc có chữ thừa trước/sau.** Vẫn phải đọc được. JSON hỏng thật thì thử lại, rồi báo lỗi rõ. Test ở Task 2.
2. **Tên thật viết khác đi:** viết hoa toàn bộ, bỏ dấu, hoặc chỉ là tên gọi ("ông Hùng"). Vẫn phải bắt được. Khi chuỗi đó nằm trong một tên hư cấu thì không được báo nhầm. Test ở Task 3.
3. **LLM "lười":** trả ít cảnh hơn yêu cầu, viết lời quá ngắn, bỏ sót sự việc được giao, hoặc gộp nhiều sự việc làm một.
   - Đầu ra phải bị loại và gọi lại kèm lý do.
   - Hỏng 3 lần thì hàng việc dừng, thông báo nêu đúng tên việc hỏng.
   - Test ở Task 4 và Task 5.
4. **Server khởi động lại giữa lúc phân tích.** Hàng việc chạy tiếp từ việc chưa xong, không gọi LLM lại cho việc đã xong. Test ở Task 6.
5. **Người dùng đặt tên hư cấu trùng tên hư cấu khác, hoặc trùng tên thật.** Phải bị từ chối, trả 400. Test ở Task 8.

---

### Task 1: Schema, lưu trữ, hàng việc, fixture test, baseline

**Files:**
- Create: `backend/models/case_adaptation_schemas.py`
- Create: `backend/services/case_store.py`
- Modify: `tests/conftest.py`: thêm env `STORY_STUDIO_DISABLE_CASE_WORKER=1` và fixture `isolated_projects_dir`
- Modify: `TASKS.md`: thêm mục "Chuyển thể vụ án song ngữ" với checklist 11 task
- Test: `tests/test_case_adaptation_store.py`

**Interfaces:**
- Produces (schemas):
  - `Lang = Literal["vi","en"]`
  - `CaseEntity(id: str, kind: Literal["person","place","organization","identifier"], real_names: list[str], role: str = "other", alias_vi: str, alias_en: str, gender: str = "", age_range: str = "", appearance_en: str = "", notes: str = "")`
  - `TimelineEvent(id: str, order: int, chunk_index: int, time_label: str = "", summary: str, entity_ids: list[str] = [])`
  - `CaseEvidence(id: str, kind: str = "clue", label_vi: str, label_en: str, description_vi: str = "", description_en: str = "", entity_ids: list[str] = [])`
  - `CaseRelation(id: str, source_id: str, target_id: str, relation_type: str = "suspect_link", label_vi: str = "", label_en: str = "")`
  - `CaseBible(source_language: str, culture: str, solved: bool = True, title_vi: str, title_en: str, logline_vi: str = "", logline_en: str = "", entities: list[CaseEntity], timeline: list[TimelineEvent], evidence: list[CaseEvidence] = [], relations: list[CaseRelation] = [], setting_notes_en: str = "")`
  - `StoryPart(id: str, kind: Literal["hook","setup","discovery","investigation","twist","resolution","open_questions","epilogue"], summary_vi: str, event_ids: list[str], scene_count: int)`: mỗi `StoryPart` là một **nhịp**.
  - `CaseOutline(supported_minutes: int, parts: list[StoryPart])`
  - `SceneFlag(kind: Literal["unknown_name","date","missing_text","bad_reveal"], field: str, detail: str)`
  - `AdaptedScene(order: int, part_id: str, narration_vi: str, narration_en: str, visual_kind: Literal["image","video","board","disclaimer"], board_reveal: list[str] = [], covers_event_ids: list[str] = [], image_prompt: str = "", video_prompt: str = "", camera_motion: str = "zoom_in", narrative_beat: str = "", sfx_cue: list[str] = [], bgm_energy: str = "tension_buildup", flags: list[SceneFlag] = [])`
  - `CaseAdaptationPlan(case_id: str, created_at: str, model: str, target_minutes: int, visual_style: str, languages: list[Lang] = ["vi","en"], bible: CaseBible, parts: list[StoryPart], scenes: list[AdaptedScene], warnings: list[str] = [])`
  - `StepKind = Literal["extract_chunk","cluster_names","assign_aliases","build_outline","write_vi","write_en","write_prompts","assemble"]`
  - `PipelineStep(id: str, kind: StepKind, params: dict = {}, status: Literal["pending","running","done","failed"] = "pending", attempts: int = 0, error: str = "")`
  - `CasePipeline(case_id: str, status: Literal["running","done","failed"] = "running", target_minutes: int, visual_style: str, chunk_chars: int = 3000, created_at: str, updated_at: str, steps: list[PipelineStep])`
  - Hằng số: `DISCLAIMER`, `TARGET_SCENES`, `MAX_SOURCE_CHARS`, `MAX_VIDEO_RATIO`, `MAX_ATTEMPTS` (giá trị theo Global Constraints).
- Produces (store). Mọi hàm gọi `require_safe_id(case_id)`; id không hợp lệ thì raise `ValueError`.
  - `cases_dir() -> Path`: `project_service.PROJECTS_DIR / "_cases"`, đọc tại lúc gọi.
  - `new_case_id() -> str`: dạng `case_<8 hex>`.
  - `save_plan`/`load_plan`
  - `save_source`/`load_source`
  - `save_chunks(case_id, list[str])`/`load_chunks`
  - `save_pipeline(p)`/`load_pipeline(case_id)`
  - `list_pipelines() -> list[CasePipeline]`: sắp theo `created_at`.
  - `save_step_output(case_id, step_id, data: dict)`/`load_step_output(case_id, step_id) -> dict | None`
  - Mọi file JSON đều ghi UTF-8.
- Produces (conftest): `isolated_projects_dir(tmp_path, monkeypatch) -> Path`. Monkeypatch `services.project_service.PROJECTS_DIR` và `config.PROJECTS_DIR` sang `tmp_path/"projects"`, tạo sẵn thư mục.

- [ ] **Step 1: Đo baseline.** Chạy bộ test offline sau, ghi số pass/fail vào `TASKS.md`. Liệt kê `projects/` trước và sau khi chạy, rồi dọn những gì test cũ vừa sinh ra:

  ```bash
  ".venv/Scripts/python.exe" -m pytest tests/test_adversarial_qa.py tests/test_api.py tests/test_case_fictionalizer.py tests/test_character_consistency.py tests/test_comic.py tests/test_gate_gout_regressions.py tests/test_image.py tests/test_investigation_board.py tests/test_muse_fleet_routing.py tests/test_muse_fleet_runner.py tests/test_muse_fleet_runner_media.py tests/test_no_fake_success_and_motion_render.py tests/test_open_folder.py tests/test_project_sync.py tests/test_true_crime_e2e.py tests/test_true_crime_router.py tests/test_youtube_storyboard_spec.py tests/test_youtube_studio_v2_improvements.py -q
  ```
- [ ] **Step 2: Viết test fail.**
  - `test_plan_roundtrip`: `save_plan` rồi `load_plan`, kết quả bằng nhau.
  - `test_pipeline_roundtrip_and_listing_order`: lưu 2 pipeline với `created_at` khác nhau; `list_pipelines()` trả theo thứ tự cũ trước.
  - `test_step_output_and_chunks_roundtrip`: ghi rồi đọc lại đúng, giữ nguyên dấu tiếng Việt.
  - `test_cases_dir_hidden_from_project_list`: `project_service.list_projects() == []`.
  - `test_rejects_unsafe_case_id`: `load_plan("../x")` raise `ValueError`.
- [ ] **Step 3: Chạy test, phải fail. Step 4: Viết code. Step 5: Chạy `tests/test_case_adaptation_store.py`, phải PASS.**
- [ ] **Step 6: Commit** `case_adaptation: schema, lưu trữ projects/_cases và hàng việc phân tích`.

---

### Task 2: Client LLM qua 9router

**Files:**
- Create: `backend/services/case_adaptation_llm.py`
- Test: `tests/test_case_adaptation_llm.py`

**Interfaces:**
- Produces:
  - `class LLMError(Exception)`: khởi tạo `LLMError(kind, user_message)`; `kind ∈ {"auth","no_credentials","timeout","network","http","invalid_json"}`; `str(err) == user_message`.
  - `RETRYABLE_KINDS = {"timeout","network","invalid_json"}`
  - `async def call_llm_json(system: str, user: str, *, temperature: float = 0.4, timeout: float = 240.0, client: httpx.AsyncClient | None = None) -> Any`
  - `LLMCall = Callable[..., Awaitable[Any]]`

- [ ] **Step 1: Viết test fail.** Dùng `httpx.MockTransport`, gọi qua `asyncio.run`:
  - `test_payload_has_stream_false`: `stream is False`, `model == config.NINEROUTER_LLM_MODEL`.
  - `test_parses_fenced_json`: content ```` "```json\n{\"a\": 1}\n```" ```` → `{"a": 1}`.
  - `test_parses_json_with_extra_text`: content `"Đây là kết quả:\n[1, 2]\nHết."` → `[1, 2]`.
  - `test_invalid_json_raises`: content không phải JSON → `kind == "invalid_json"`.
  - `test_401_maps_to_auth`: trả 401 → `kind == "auth"`, `"401"` có trong `user_message`.
  - `test_no_credentials_maps`: trả 404 với body có `No active credentials` → `kind == "no_credentials"`, `"kết nối Gemini"` có trong `user_message`.
  - `test_timeout_maps`: transport raise `httpx.ReadTimeout` → `kind == "timeout"`.
- [ ] **Step 2: Chạy test, phải fail.**
- [ ] **Step 3: Viết code.** Lấy `choices[0].message.content`, bóc fence rồi `json.loads`. Nếu lỗi thì lấy khối `{…}` hoặc `[…]` lớn nhất rồi thử lại. Thiếu key hoặc base URL thì raise `LLMError("auth", …)`. Không bao giờ log key.
- [ ] **Step 4: Chạy test, phải PASS. Step 5: Commit** `case_adaptation: client LLM 9router (stream:false, lỗi rõ ràng)`.

---

### Task 3: Kiểm lọt tên, ngày tháng, áp tên hư cấu

**Files:**
- Create: `backend/services/case_adaptation_checks.py`
- Test: `tests/test_case_adaptation_checks.py`

**Interfaces:**
- Consumes: schemas; `AnonymizerShield().extract_pii_candidates(text)["persons"]` (`services/case_fictionalizer.py`).
- Produces:
  - `fold(text) -> str`: chữ thường, bỏ dấu, `đ` thành `d`.
  - `ForbiddenName(real, entity_id | None, alias_vi | None, alias_en | None)` (dataclass)
  - `build_forbidden_names(bible, source_text) -> list[ForbiddenName]`: gồm `real_names` của mọi entity, cộng tên regex bắt được trên bài gốc mà chưa có trong entity nào.
  - `apply_aliases(text, forbidden, lang) -> tuple[str, list[str]]`
  - `find_unknown_names(text, forbidden, aliases: list[str]) -> list[str]`
  - `find_dates(text) -> list[str]`
  - `check_plan(plan, source_text) -> CaseAdaptationPlan`: tính lại `flags` và `warnings`.
  - `has_blocking_flags(plan) -> bool`
- **So khớp:**
  - So trên chuỗi đã `fold`, theo ranh giới từ `(?<!\w)…(?!\w)`.
  - Bỏ qua chỗ khớp nằm trọn trong một vị trí xuất hiện của alias.
  - Bỏ qua tên thật chỉ có một âm tiết và ngắn hơn 3 ký tự.
  - `check_plan` quét: tiêu đề, `narration_vi`/`narration_en`, `image_prompt`, `video_prompt`, nhãn evidence/relation. Bỏ qua cảnh `disclaimer`.

- [ ] **Step 1: Viết test fail:**

  ```python
  def test_leak_variants_are_caught():
      fb = [ForbiddenName("Nguyễn Văn Hùng", "e1", "Trịnh Quang Vũ", "Trinh Quang Vu")]
      for t in ["NGUYỄN VĂN HÙNG bước vào", "Nguyen Van Hung walked in", "ông nguyễn văn hùng."]:
          new, replaced = apply_aliases(t, fb, "vi")
          assert "Hùng" not in new and "Hung" not in new and replaced

  def test_alias_containing_real_fragment_not_flagged():
      fb = [ForbiddenName("Lâm", None, None, None), ForbiddenName("Vũ Đình Trọng", "e3", "Phan Đức Lâm", "Phan Duc Lam")]
      assert find_unknown_names("Phan Đức Lâm im lặng.", fb, ["Phan Đức Lâm"]) == []

  def test_dates_found_but_times_kept():
      assert find_dates("Đêm ngày 15 tháng 10 năm 2021, lúc 23:30") == ["ngày 15 tháng 10 năm 2021"]
      assert find_dates("On October 7, 2014 at 02:21") == ["October 7, 2014"]
      assert find_dates("Cuộc gọi lúc 02:21, ba ngày sau") == []
      assert find_dates("giữa thập niên 2010") == []
  ```

  Thêm các test sau:
  - `test_year_alone_flagged`: `find_dates` của `"năm 2014"` và của `"in 2014"` đều khác rỗng.
  - `test_check_plan_autoreplaces_known_and_flags_unknown`:
    - tên đã có alias xuất hiện trong `narration_en` → được thay, `warnings` có câu chứa `Đã tự thay`;
    - tên chỉ regex bắt được xuất hiện trong `narration_vi` → cảnh có flag `unknown_name`, `has_blocking_flags` là True.
  - `test_check_plan_flags_missing_text_and_bad_reveal`: `narration_en` rỗng → flag `missing_text`; `board_reveal` chứa id lạ → flag `bad_reveal`.
  - `test_country_names_not_flagged`: `"Đài Loan"` và `"cảnh sát"` không bị đánh dấu.
  - `test_unrevealed_evidence_warns`: evidence không xuất hiện trong `board_reveal` của cảnh nào → có warning chứa id của nó.
- [ ] **Step 2: Chạy test, phải fail.**
- [ ] **Step 3: Viết code.**
  - Regex ngày tiếng Việt: `ngày \d{1,2} tháng \d{1,2}( năm \d{4})?`, `\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?`, `năm \d{4}`.
  - Regex ngày tiếng Anh: tháng (đầy đủ hoặc viết tắt) kèm ngày và/hoặc năm; `in \d{4}`; năm `19xx`/`20xx` đứng riêng, trừ khi nằm trong "thập niên", "decade" hoặc "…'s".
  - Không coi `\d{1,2}:\d{2}` là ngày.
- [ ] **Step 4: Chạy test, phải PASS. Step 5: Commit** `case_adaptation: kiểm lọt tên thật, ngày tháng và tự áp tên hư cấu`.

---

### Task 4: Bộ chạy một việc, cùng các việc G1–G4 (từ bài gốc tới hồ sơ)

**Files:**
- Create: `backend/services/case_adaptation_prompts.py` (phần G2–G4)
- Create: `backend/services/case_adaptation_steps.py`
- Create: `tests/case_adaptation_fakes.py`
- Create: thư mục `tests/fixtures/case_adaptation/`, gồm:
  - `dossier.txt`: chép chuỗi `SAMPLE_REAL_CRIME_DOSSIER` từ `tests/test_true_crime_e2e.py` hiện tại;
  - `EXTRACT_0.json`, `EXTRACT_1.json`, `CLUSTER.json`, `ALIASES.json`.
- Test: `tests/test_case_adaptation_steps_bible.py`

**Interfaces:**
- Consumes: Task 1–3.
- Produces (prompts): mỗi hàm trả user prompt, **dòng đầu là marker**:
  - `extract_prompt(chunk: str, index: int, total: int, known_names: list[str]) -> str`, marker `TASK: EXTRACT <index>`;
  - `cluster_prompt(names: list[dict]) -> str`, marker `TASK: CLUSTER`;
  - `aliases_prompt(groups: list[dict], opening_excerpt: str) -> str`, marker `TASK: ALIASES`;
  - `SYSTEM_PROMPT: str` dùng chung cho mọi bước. Nội dung bám spec mục 6 và 7.10: giữ sự thật; kịch tính hoá "như phim"; giữ tên nước và tên chung của cơ quan; năm thành thời kỳ; Hán-Việt cho vi, pinyin cho en; không máu me; chỉ trả JSON.
- Produces (steps):
  - `class StepRejected(Exception)`: `reason: str`, là lý do sẽ gửi lại cho LLM.
  - `class StepFailed(Exception)`: `user_message: str`, có tên việc và lý do.
  - `async def ask_validated(user: str, validate: Callable[[Any], T], *, llm: LLMCall, temperature: float = 0.4, step_label: str) -> T`. Thử tối đa `MAX_ATTEMPTS` lần. `StepRejected`, `pydantic.ValidationError` và `LLMError` có `kind ∈ RETRYABLE_KINDS` thì thử lại kèm lý do. `LLMError` loại khác thì đổi thành `StepFailed` ngay.
  - `chunk_source(text: str, max_chars: int) -> list[str]`: cắt theo đoạn văn; đoạn nào quá dài thì cắt theo câu.
  - `initial_steps(n_chunks: int) -> list[PipelineStep]`: các việc `extract_00…`, rồi `cluster`, `aliases`, `outline`.
  - `@dataclass StepResult(output: dict, new_steps: list[PipelineStep] = field(default_factory=list))`
  - `async def run_step(pipeline: CasePipeline, step: PipelineStep, *, llm: LLMCall | None = None) -> StepResult`. Phân việc theo `step.kind`. Không truyền `llm` thì lấy `case_adaptation_llm.call_llm_json` tại lúc gọi.
- **Hành vi từng việc:**
  - `extract_chunk` (`params={"index": i}`):
    - đầu vào là chunk thứ i và các tên đã gặp ở output `extract_*` trước;
    - output `{"names":[{name,kind,role,context}], "events":[{summary,time_label,names}], "evidence":[{label_vi,label_en,description_vi,description_en,names}], "relations":[{source_name,target_name,relation_type,label_vi,label_en}]}`;
    - loại khi: đoạn ≥ 150 từ mà số sự việc < `ceil(words/250)`, hoặc có tóm tắt sự việc < 12 từ.
  - `cluster_names`:
    - đầu vào là mọi tên khác nhau, gom từ các output extract;
    - output `{"groups":[{id,kind,role,real_names}]}`;
    - loại khi có tên đầu vào không nằm trong nhóm nào, hoặc nằm trong nhiều hơn một nhóm.
  - `assign_aliases`:
    - đầu vào là các nhóm và 1.500 ký tự đầu bài;
    - LLM trả `{culture, solved, title_vi, title_en, logline_vi, logline_en, setting_notes_en, entities:[{id, alias_vi, alias_en, gender, age_range, appearance_en}]}`;
    - code ghép thành `CaseBible`: event id `ev_<chunk>_<n>`, order theo (chunk, vị trí trong chunk); tên ánh xạ sang entity bằng `fold`; relation nào không ánh xạ được thì bỏ;
    - loại khi: alias rỗng, alias trùng nhau, hoặc `fold(alias)` trùng một tên thật;
    - output là `bible.model_dump()`.
- Produces (fakes): `make_fake_llm(overrides: dict | None = None) -> tuple[LLMCall, list[str]]`.
  - Đọc marker ở dòng đầu user prompt, rồi trả `fixtures/case_adaptation/<marker, dấu cách đổi thành _>.json`.
  - `overrides[marker]` có thể là: một giá trị, một `Exception`, hoặc list (trả lần lượt từng phần tử).
  - Danh sách marker đã gọi được ghi lại theo thứ tự.
  - Test tạo pipeline với `chunk_chars=900`, để `dossier.txt` cắt thành đúng 2 đoạn.

- [ ] **Step 1: Viết fixture.** Tên thật trong dossier: "Nguyễn Văn Hùng"/"ông Hùng", "Lê Thị Mai"/"bà Mai", "Vũ Đình Trọng"/"ông Trọng", "Cảng Tân Hải", "Đường Lê Lợi", "Hải Phòng", "Công ty Vận tải Biển Đông", "15B1-987.65", "0912345678". Các file JSON phải đủ ngưỡng ở Global Constraints. `ALIASES.json` đặt alias cho mọi nhóm, ví dụ "Trịnh Quang Vũ"/"Trinh Quang Vu".
- [ ] **Step 2: Viết test fail:**
  - `test_chunk_source_respects_paragraphs`: không chunk nào dài quá `max_chars`; nối các chunk lại thì giữ đủ mọi câu.
  - `test_extract_lazy_output_retried_with_reason`: override `EXTRACT 0` = `[{"names":[], "events":[{"summary":"Có án mạng.", …}], …}, <fixture>]`. Kết quả: thành công; prompt lần 2 chứa `LẦN TRƯỚC BỊ LOẠI VÌ`.
  - `test_extract_fails_after_three_lazy_attempts`: cả 3 lần đều mỏng → `StepFailed`; `user_message` có chữ `đọc đoạn 1`.
  - `test_cluster_rejects_missing_name`: nhóm thiếu tên "bà Mai" → gọi lại.
  - `test_aliases_builds_bible`: chạy lần lượt `extract_00`, `extract_01`, `cluster`, `aliases` qua `run_step`. Kiểm:
    - `CaseBible.model_validate(output)` hợp lệ;
    - mọi event có `entity_ids` trỏ tới entity có thật;
    - `title_vi` không chứa "Hùng".
  - `test_aliases_rejects_alias_equal_real_name`: override `ALIASES` đặt `alias_vi` = `"Lê Thị Mai"` → gọi lại.
  - `test_no_credentials_not_retried`: `EXTRACT 0` raise `LLMError("no_credentials","…")` → `StepFailed`; marker này chỉ được gọi 1 lần.
- [ ] **Step 3: Chạy test, phải fail. Step 4: Viết prompts G2–G4 và `case_adaptation_steps.py`. Step 5: Chạy test, phải PASS.**
- [ ] **Step 6: Commit** `case_adaptation: chạy từng việc nhỏ có kiểm và thử lại; đọc đoạn, gộp tên, đặt tên hư cấu`.

---

### Task 5: Các việc G5–G7 (dàn ý, viết cảnh theo nhịp, ráp kế hoạch)

**Files:**
- Modify: `backend/services/case_adaptation_prompts.py` (thêm prompt G5–G6 và `rewrite_en_prompt`)
- Modify: `backend/services/case_adaptation_steps.py`
- Create fixture: `OUTLINE.json`, `WRITE_VI_p1.json`, `WRITE_EN_p1.json`, `PROMPTS_p1.json`, và bộ tương tự cho `p2`
- Test: `tests/test_case_adaptation_steps_story.py`

**Interfaces:**
- Produces (prompts):
  - `outline_prompt(bible, target_minutes, target_scenes: tuple[int,int]) -> str`, marker `TASK: OUTLINE`
  - `write_vi_prompt(bible, part, events, source_chunks: list[str], prev_scenes: list[dict]) -> str`, marker `TASK: WRITE_VI <part_id>`
  - `write_en_prompt(bible, part, vi_scenes, source_chunks) -> str`, marker `TASK: WRITE_EN <part_id>`
  - `prompts_prompt(bible, part, scenes, visual_style) -> str`, marker `TASK: PROMPTS <part_id>`
  - `rewrite_en_prompt(bible, items: list[tuple[int,str]]) -> str`, marker `TASK: REWRITE_EN`
- Produces (steps, mở rộng `run_step`):
  - `build_outline`:
    - output `CaseOutline`;
    - loại khi: có event không nằm trong nhịp nào; `scene_count` ngoài khoảng 2–6; tổng > `target_max * 1.2`; hoặc tổng < `target_min` trong khi `supported_minutes >= target_minutes`;
    - `new_steps`: với mỗi nhịp, theo thứ tự `write_vi_<pid>`, `write_en_<pid>`, `write_prompts_<pid>`; cuối cùng là `assemble`.
  - `write_vi` (`params={"part_id"}`):
    - đoạn gốc đưa vào: các chunk chứa event của nhịp; `prev_scenes`: 2 cảnh cuối của nhịp trước;
    - output `{"scenes":[{narration_vi, visual_kind, board_reveal, covers_event_ids}]}`;
    - loại khi: số cảnh ≠ `scene_count`; có lời ngoài khoảng 25–80 từ; các `covers_event_ids` gộp lại thiếu event của nhịp; có id lạ trong `board_reveal`.
  - `write_en`: output `{"scenes":[{narration_en}]}`; loại khi số cảnh lệch, hoặc có lời ngoài khoảng 20–70 từ.
  - `write_prompts`: output `{"scenes":[{image_prompt, video_prompt, camera_motion, narrative_beat, sfx_cue, bgm_energy}]}`; loại khi số cảnh lệch, `image_prompt` < 20 từ, hoặc cảnh `video` thiếu `video_prompt`.
  - `assemble` (code, không gọi LLM):
    - chèn cảnh miễn trừ làm cảnh 1, đánh số lại;
    - `camera_motion` không thuộc `video_service.CAMERA_MOTIONS` thì đổi thành `"zoom_in"`;
    - số cảnh video vượt `floor(MAX_VIDEO_RATIO * n)` thì đổi phần dư thành `image` (giữ `video_prompt`);
    - nếu `supported_minutes < target_minutes`: thêm warning `Bài chỉ đủ tư liệu cho khoảng {n} phút (bạn chọn {m} phút).`;
    - chạy `check_plan(plan, load_source(case_id))` rồi `save_plan`; output `{"case_id": …}`.
  - `async def rewrite_english(bible, items, *, llm=None) -> dict[int, str]`: đi qua `ask_validated`; loại khi thiếu order, hoặc có lời ngoài khoảng 20–70 từ.

- [ ] **Step 1: Viết fixture.**
  - Outline có `supported_minutes: 2`. Nhịp `p1` (kind `hook`, 3 cảnh) và `p2` (kind `resolution`, 3 cảnh); hai nhịp gộp lại phủ hết các event của `ALIASES` bible.
  - `p2` có một cảnh `board` reveal cả 3 evidence, và một cảnh `video`.
  - `PROMPTS_p2` có một `camera_motion: "warp_speed"`.
- [ ] **Step 2: Viết test fail.** Mỗi test có helper chạy toàn bộ hàng việc với LLM giả.
  - `test_full_pipeline_produces_plan`:
    - 7 cảnh; `scenes[0].visual_kind == "disclaimer"`, `narration_vi == DISCLAIMER["vi"]`;
    - thứ tự marker: `EXTRACT 0, EXTRACT 1, CLUSTER, ALIASES, OUTLINE, WRITE_VI p1, WRITE_EN p1, PROMPTS p1, WRITE_VI p2, WRITE_EN p2, PROMPTS p2`;
    - không có flag.
  - `test_short_material_warns`: `target_minutes=8` → warning chứa `khoảng 2 phút`.
  - `test_outline_lazy_retried`: lần đầu override outline thiếu một event → được gọi lại, rồi thành công.
  - `test_write_vi_too_few_scenes_retried`: override `WRITE_VI p1` = `[<2 cảnh>, <fixture>]` → thành công, và prompt lần 2 chứa `LẦN TRƯỚC BỊ LOẠI VÌ`.
  - `test_write_vi_missing_event_rejected`: cả 3 lần `covers_event_ids` đều thiếu cùng một event → `StepFailed`, `user_message` có chữ `lời Việt`.
  - `test_invalid_camera_normalized_and_video_capped`:
    - cảnh có `"warp_speed"` sau ráp thành `"zoom_in"`;
    - override để mọi cảnh p2 là `video` → số cảnh video ≤ 1.
  - `test_rewrite_english_returns_map`: override `REWRITE_EN` → kết quả là `{3: "..."}`.
- [ ] **Step 3: Chạy test, phải fail. Step 4: Viết code. Step 5: Chạy test, phải PASS.**
- [ ] **Step 6: Commit** `case_adaptation: dàn ý, viết lời Việt/Anh và prompt theo từng nhịp, ráp kế hoạch`.

---

### Task 6: Worker chạy hàng việc tuần tự

**Files:**
- Create: `backend/services/case_worker.py`
- Modify: `backend/main.py` (trong `lifespan`: chạy `recover_interrupted()`, rồi khởi động `worker_loop`; tắt khi shutdown; bỏ qua nếu `STORY_STUDIO_DISABLE_CASE_WORKER=1`)
- Test: `tests/test_case_worker.py`

**Interfaces:**
- Consumes: store (Task 1), `run_step`, `StepFailed`, `chunk_source`, `initial_steps` (Task 4–5).
- Produces:
  - `def start_analysis(raw_report: str, target_minutes: int, visual_style: str, *, chunk_chars: int = 3000) -> str`:
    - kiểm độ dài; bài rỗng hoặc quá dài thì raise `CaseInputError(ValueError)`;
    - lưu source, chunks và pipeline; trả `case_id`.
  - `async def run_next_step(*, llm: LLMCall | None = None) -> bool`: chọn pipeline `running` cũ nhất còn việc `pending`, rồi chạy **một** việc:
    - trước khi chạy: đặt `running`, `attempts += 1`, lưu;
    - thành công: lưu output, đặt `done`, nối `new_steps`; hết việc `pending` thì pipeline thành `done`;
    - gặp `StepFailed`: việc thành `failed` (lưu `error`), pipeline thành `failed`.
    - Trả `False` khi không còn việc nào.
  - `def recover_interrupted() -> int`: các việc `running` trở về `pending`; trả số việc đã đổi.
  - `async def worker_loop(stop: asyncio.Event, idle_sleep: float = 1.0) -> None`
  - `def resume_pipeline(case_id) -> CasePipeline`: việc `failed` về `pending`, `attempts=0`, pipeline về `running`.
  - `def pipeline_progress(p: CasePipeline) -> dict`: trả `{"status","step_label","steps_done","steps_total","error"}`. `step_label` tiếng Việt, ví dụ `Đang đọc đoạn 2/5`, `Đang gộp tên nhân vật`, `Đang đặt tên hư cấu`, `Đang lên dàn ý`, `Đang viết lời Việt, nhịp 1/2`, `Đang viết lời Anh, nhịp 1/2`, `Đang viết prompt hình, nhịp 1/2`, `Đang ráp và kiểm tra`.

- [ ] **Step 1: Viết test fail** (`isolated_projects_dir`, LLM giả):
  - `test_runs_all_steps_sequentially`: gọi `run_next_step` lặp lại tới khi trả False → pipeline `done`, `load_plan(case_id)` có 7 cảnh.
  - `test_restart_resumes_without_repeating`:
    - chạy 4 việc; đặt tay việc thứ 5 thành `running` (mô phỏng server tắt giữa chừng);
    - `recover_interrupted() == 1`; chạy tiếp tới hết;
    - mỗi marker trong 4 việc đầu chỉ được gọi đúng 1 lần.
  - `test_failure_stops_then_resume`:
    - `WRITE_VI p1` mỏng cả 3 lần → pipeline `failed`, `pipeline_progress()["error"]` có chữ `lời Việt`, và `run_next_step()` trả False;
    - bỏ override, gọi `resume_pipeline` → chạy tiếp tới `done`.
  - `test_one_llm_call_at_a_time`:
    - hai pipeline cùng chạy qua `worker_loop` với LLM giả có `await asyncio.sleep(0.01)` và đếm số lần gọi đồng thời;
    - số đồng thời tối đa là 1; pipeline cũ hơn xong trước.
  - `test_progress_labels`: ngay sau `start_analysis`, `step_label == "Đang đọc đoạn 1/2"`.
  - `test_start_analysis_rejects_empty_and_too_long`
- [ ] **Step 2: Chạy test, phải fail. Step 3: Viết code và sửa `main.py`. Step 4: Chạy test, phải PASS.**
- [ ] **Step 5: Commit** `case_adaptation: worker chạy hàng việc tuần tự, chạy tiếp sau khi khởi động lại`.

---

### Task 7: Bảng ghim theo ngôn ngữ, tạo dự án, tạo bản ngôn ngữ khác

**Files:**
- Modify: `backend/services/investigation_board_engine.py`: `render_polaroid_card` (khoảng dòng 480) dùng `node.metadata.get("badge_label")` nếu có; thêm `NODE_TYPE_LABELS_EN`.
- Create: `backend/services/case_project_builder.py`
- Test: `tests/test_case_project_builder.py`

**Interfaces:**
- Consumes: Task 1, 3, 5 (`rewrite_english`); `get_cumulative_board_state`, `render_board_image`, `assign_fixed_anchor_layout`, `get_font`; `project_service._get_project_dir`, `_ensure_project_subdirs`, `_save_project`, `get_project`, `get_scene_media_paths`.
- Produces:
  - `NODE_TYPE_LABELS_EN = {"victim": "VICTIM", "suspect": "SUSPECT", "weapon": "WEAPON", "clue": "CLUE", "forensic_report": "FORENSICS", "location": "SCENE", "timeline_event": "TIMELINE"}`
  - `BOARD_TITLE = {"vi": "Hồ sơ điều tra", "en": "Case file"}`
  - `plan_board_items(plan, lang) -> tuple[list[EvidenceNode], list[RelationEdge]]`:
    - `appearance_scene_order` = order của cảnh đầu tiên reveal id đó;
    - `label` theo ngôn ngữ; với `en` thì đặt `metadata["badge_label"]`;
    - toạ độ đặt bằng `assign_fixed_anchor_layout`.
  - `render_board_scene(plan, scene_order, lang, out_path) -> Path`: dùng `get_cumulative_board_state(SimpleNamespace(nodes=…, edges=…), scene_order)`, đặt `title = BOARD_TITLE[lang]`.
  - `render_disclaimer_card(text, out_path) -> Path`: ảnh 1920×1080 nền tối, chữ trắng căn giữa.
  - `class BlockingFlagsError(Exception)`, `class LanguageVersionError(ValueError)`
  - `create_project_from_plan(plan, language, voice, *, visual_style=None, image_provider="meta_muse_cloud", voices=None) -> Project`
  - `async def create_language_version(project_id, language, voice=None, *, llm=None) -> tuple[Project, list[int]]`
- **Quy tắc dựng dự án** (spec 7.7):
  - id dự án `proj_crime_<8 hex>`, id cảnh `scene_{order:03d}`.
  - `text = narration_<lang>`.
  - Chép thẳng sang Scene: `image_prompt`, `video_prompt`, `camera_motion`, `sfx_cue`, `bgm_energy`.
  - `metadata` của cảnh: `case_id`, `narration={"vi","en"}`, `narration_source=text`, `visual_kind`, `board_reveal`, `narrative_beat`.
  - `shot_type`: `B_ROLL_BOARD` cho cảnh `board`, `A_ROLL_NOIR` cho các loại còn lại.
  - Cảnh `board` và `disclaimer`: ảnh vẽ thẳng vào `images/scene_NNN.jpg`, `status="imaged"`, `status_image="ready"`, `image_url=/api/projects/{pid}/media/images/scene_NNN.jpg`.
  - Dự án: `name = title_<lang>`; `bgm_overall_genre="mysterious_dark"`; `metadata = {"case_id","language","sibling_project_ids": [],"voices"}`.
  - Plan còn flag chặn thì raise `BlockingFlagsError`.
- **Quy tắc tạo bản ngôn ngữ khác:**
  - Chép `images/*` và `videos/*_muse.mp4`, đổi đường dẫn và URL sang dự án mới.
  - Xoá audio, srt, segment, final video và thumbnail.
  - Cảnh có `text == narration_source` và đã có `narration[language]` thì dùng lời đó.
  - Các cảnh còn lại gom lại, gọi `rewrite_english` **một lần**, với bible lấy từ `load_plan(metadata.case_id)`. Không có plan thì raise `LanguageVersionError`.
  - Vẽ lại cảnh `board` và `disclaimer` theo ngôn ngữ mới.
  - `voice = voice or metadata.voices[language] or "en-US-AndrewMultilingualNeural"`.
  - Liên kết hai chiều qua `sibling_project_ids`, lưu cả hai dự án.
  - Dự án không có `case_id` hoặc không có `narration` → raise `LanguageVersionError("Dự án này không được tạo từ kế hoạch chuyển thể.")`.

- [ ] **Step 1: Viết test fail.** Plan lấy từ helper chạy hàng việc giả ở Task 6.
  - `test_create_vi_project`:
    - số cảnh khớp plan; `scenes[0].text == DISCLAIMER["vi"]`;
    - file ảnh của cảnh board tồn tại;
    - `metadata["language"] == "vi"`;
    - cảnh video giữ `video_prompt`.
  - `test_create_blocked_by_flags`: có flag chặn → `BlockingFlagsError`.
  - `test_board_items_english_labels`: với `"en"`, `badge_label` thuộc `NODE_TYPE_LABELS_EN.values()` và `label` là `label_en`.
  - `test_language_version_copies_media_and_switches_text`:
    - tạo file giả `videos/scene_003_muse.mp4`;
    - bản `en` có file đó, có lời Anh, `voice == "en-US-AndrewMultilingualNeural"`;
    - hai dự án liên kết hai chiều; `rewritten == []`; không lần gọi `REWRITE_EN` nào.
  - `test_language_version_rewrites_changed_scenes`:
    - sửa `text` cảnh 3 và thêm một cảnh mới ở bản vi; override `REWRITE_EN` trả lời cho đúng hai order đó;
    - `rewritten == [3, <order mới>]`; gọi `REWRITE_EN` đúng 1 lần; hai cảnh đó dùng lời được trả về.
  - `test_language_version_twice_creates_two_projects`
  - `test_language_version_rejects_plain_project`
- [ ] **Step 2: Chạy test, phải fail. Step 3: Viết code. Step 4: Chạy `tests/test_case_project_builder.py` và `tests/test_investigation_board.py`, phải PASS.**
- [ ] **Step 5: Commit** `case_adaptation: dựng dự án từ kế hoạch, bảng ghim theo ngôn ngữ, tạo bản tiếng Anh`.

---

### Task 8: API, bỏ luồng cũ

**Files:**
- Create: `backend/services/case_jobs.py`: job trong bộ nhớ, chỉ dùng cho việc tạo bản ngôn ngữ khác.
- Rewrite: `backend/routers/true_crime.py`
- Create: `backend/routers/language_versions.py` (prefix `/api/projects`), include trong `backend/main.py`.
- Modify:
  - `backend/security.py`: thêm `"job_id"` vào `PATH_ID_PARAMS`;
  - `backend/services/case_fictionalizer.py`: bỏ `JubenshaMatrix`, `ForeshadowingLedgerManager`, `YouTubeReviewerScriptGenerator`, `CaseFictionalizerEngine`; giữ `AnonymizerShield`, các regex và danh sách tên mẫu.
- Rewrite tests:
  - `tests/test_true_crime_router.py`: giữ `test_neo_noir_style_and_camera_motion`;
  - `tests/test_true_crime_e2e.py`;
  - `tests/test_case_fictionalizer.py`: chỉ còn test `AnonymizerShield`.

**Interfaces:**
- Produces (jobs): `create_job(kind) -> str` (dạng `job_<8 hex>`), `update_job(job_id, **fields)`, `get_job(job_id) -> dict | None`.
- Produces (routes `/api/true-crime`), theo bảng ở spec 7.8:
  - `POST /analyze`: body `{raw_report, target_minutes=8, visual_style="neo_noir_silhouette"}`, gọi `start_analysis` → `{case_id}`. Bài rỗng → 400; quá dài → 413.
  - `GET /cases/{case_id}/progress`: trả `pipeline_progress`; không có case → 404.
  - `POST /cases/{case_id}/resume`
  - `GET /cases/{case_id}`: trả plan; chưa xong → 409 với `detail` `Đang phân tích, chưa có kế hoạch.`
  - `PUT /cases/{case_id}/entities`:
    - body `{"updates":[{id,alias_vi,alias_en}], "additions":[{kind,real_names,alias_vi,alias_en}]}`;
    - thay alias cũ bằng alias mới theo ranh giới từ, rồi `check_plan(plan, load_source(case_id))` và lưu;
    - alias trùng hoặc `fold` trùng một tên thật → 400.
  - `PUT /cases/{case_id}/scenes/{order}`: body `{narration_vi?, narration_en?}` → `check_plan`, lưu. Order lạ hoặc là cảnh miễn trừ → 400.
  - `POST /cases/{case_id}/create-project`: body `{language, voice, voices?, visual_style?, image_provider="meta_muse_cloud"}` → `{project_id, redirect_url}`. Gặp `BlockingFlagsError` → 409, `detail` liệt kê order các cảnh bị đánh dấu.
  - `GET /jobs/{job_id}`: không có job → 404.
  - `POST /render-board-scene/{scene_id}`: body `{case_id, language}`, vẽ vào `projects/_cases/<case_id>/boards/board_<NNN>_<lang>.jpg` → `{image_path}`.
- Produces (route `/api/projects`): `POST /{project_id}/create-language-version`:
  - body `{language="en", voice=None}` → `{job_id}`; chạy qua `BackgroundTasks`;
  - xong thì `result = {project_id, rewritten_orders}`; gặp `LanguageVersionError` thì job failed với chính thông báo đó.
- Bỏ `/fictionalize`, `/create-project` (route cũ) và `_CASE_PLAN_CACHE`.

- [ ] **Step 1: Viết test fail.** Dùng `TestClient(app)`, `isolated_projects_dir`, monkeypatch `case_adaptation_llm.call_llm_json` bằng LLM giả. Worker tắt trong test, nên test gọi `asyncio.run(case_worker.run_next_step())` lặp lại tới khi trả False.
  - `test_analyze_then_progress_then_case`:
    - POST → có `case_id`; progress báo `running`;
    - chạy hết các việc → progress báo `done`; GET case trả 7 cảnh.
  - `test_case_not_ready_409`
  - `test_failed_pipeline_and_resume_route`
  - `test_empty_and_too_long_report`: kiểm mã 400 và 413.
  - `test_entities_update_and_validation`:
    - đổi alias nạn nhân → lời vi chỉ còn alias mới;
    - alias trùng → 400;
    - alias = `"Nguyễn Văn Hùng"` → 400.
  - `test_scene_edit_then_create_project`:
    - ghi tên thật chỉ regex bắt được vào `narration_vi` → create-project 409;
    - sửa sạch → 200; `GET /api/projects/{id}` đủ số cảnh.
  - `test_create_language_version_route`: job `done`, `result.project_id` khác id dự án vi.
  - `test_old_routes_removed`: POST `/api/true-crime/fictionalize` → 404 hoặc 405.
  - `test_path_ids_validated`: GET `/api/true-crime/cases/..%2Fx` không bao giờ trả 200.
- [ ] **Step 2: Chạy test, phải fail. Step 3: Viết code.**
- [ ] **Step 4: Chạy `tests/test_true_crime_router.py`, `tests/test_true_crime_e2e.py`, `tests/test_case_fictionalizer.py`, phải PASS.**
- [ ] **Step 5: Commit** `true_crime: API hàng việc phân tích, sửa tên/cảnh, tạo dự án và bản ngôn ngữ; bỏ luồng 70/30 cũ`.

---

### Task 9: Giao diện modal Hồ Sơ Kỳ Án

**Files:**
- Create: `backend/static/true_crime.js`: toàn bộ code true-crime (`TrueCrimeState`, `EvidenceBoardRenderer`, `initTrueCrimeStudio`…) chuyển sang đây.
- Modify:
  - `backend/static/app.js`: xoá khối `// ================= TRUE CRIME STUDIO …` (khoảng dòng 5622–6905), cùng `API.trueCrimeFictionalize` và `API.trueCrimeCreateProject`; giữ lời gọi `initTrueCrimeStudio()`;
  - `backend/static/index.html`: modal `#modal-true-crime` (khoảng dòng 2010–2260); thêm `<script src="/static/true_crime.js?v=1.0.0"></script>` ngay sau `app.js`;
  - `tools/build_release.py`: thêm `backend/static/true_crime.js` vào danh sách file cho phép và vào bộ quét `ui_file`.

**Interfaces:**
- Consumes: routes ở Task 8; các global của `app.js` là `showToast`, `escapeHtml`, `switchProject`, `switchStep`, `AppState`; `GET /api/voices` (field `id`, `locale`).
- Produces (global JS): `initTrueCrimeStudio()`, `openTrueCrimeModal()`, `closeTrueCrimeModal()`, `refreshLanguageVersionButton(project)` (thân hàm viết ở Task 10).
- Mọi request đi qua `tcFetch(url, options)`. Lỗi HTTP thì throw `Error(detail)`. Không có nhánh nào dựng dữ liệu giả.

- [ ] **Step 1: Sửa HTML của modal.**
  - Bỏ thanh trượt 70/30, các tab "Ma trận" và "Phục bút", các `<option>` cảnh viết cứng, và mọi `onclick="handleAnalyzeAndGoToBoard()"`.
  - Thêm `#tc-voice-vi`, `#tc-voice-en`, khối tiến độ `#tc-progress` (gồm câu `step_label`, thanh `steps_done/steps_total` và nút `#btn-tc-resume` chỉ hiện khi `failed`), khối `#tc-warnings`.
  - Màn xem lại gồm: `#tc-entity-table` (input alias vi/en, nút "Thêm tên"), `#tc-outline`, `#tc-scene-review` (hai textarea vi/en cho mỗi cảnh; cảnh có flag viền đỏ kèm lý do).
  - Nút `#btn-tc-create-vi`.
  - Chỉ dùng class đã có trong `tailwind.css`. Thiếu thì build lại theo AGENTS.md và commit kèm `tailwind.css`.
- [ ] **Step 2: Viết luồng.**
  - POST `/analyze`, rồi cứ 2 giây GET progress một lần.
  - `failed` → hiện `error` và nút "Thử lại" (POST resume). Gặp 404 → dừng hỏi.
  - `done` → GET case, vẽ màn xem lại.
  - Canvas bảng ghim vẽ từ **bản sao** `bible.evidence`/`relations`.
  - Sửa alias → PUT entities. Sửa lời (blur) → PUT scene. Cả hai vẽ lại theo plan trả về.
  - `#btn-tc-create-vi` bị `disabled` khi còn flag. Bấm → POST create-project (gửi `voices` của cả hai select) → `switchProject` → `switchStep(2)`. Server trả 409 thì toast danh sách cảnh.
  - Hai select giọng lấy từ `/api/voices`, lọc theo `locale`.
  - Nút hồ sơ mẫu chỉ nạp chữ vào ô nhập.
  - Hiện ước lượng thời gian: `Phân tích chạy từng bước nhỏ, có thể mất 10–30 phút; bạn có thể đóng modal, mở lại sẽ thấy tiến độ.` Lưu `case_id` đang chạy vào `localStorage`, để mở lại modal vẫn theo dõi tiếp được.
- [ ] **Step 3: Kiểm tra tĩnh.**
  - `node --check` hai file JS.
  - Grep `app.js` không còn `buildDeterministicTrueCrimePlan`, `trueCrimeFictionalize`, `normalizeBoardData`.
  - Grep `index.html` không còn `onclick="handleAnalyzeAndGoToBoard`.
  - `".venv/Scripts/python.exe" tools/build_release.py` qua hết kiểm tra.
- [ ] **Step 4: Kiểm bằng mắt, với 9router thật** (được phép).
  - Chạy server tạm cổng 8010 (`".venv/Scripts/python.exe" -c "import sys; sys.path.insert(0,'backend'); import uvicorn; uvicorn.run('main:app', host='127.0.0.1', port=8010)"`, chạy ngầm).
  - Mở `http://127.0.0.1:8010/#true-crime` trong trình duyệt tích hợp, dán `tests/fixtures/case_adaptation/dossier.txt`, chọn 8 phút. Kiểm:
    - tiến độ chạy từng bước;
    - mỗi lần bấm chỉ gửi một request;
    - màn xem lại hiện bảng tên và lời song ngữ;
    - tạo được dự án bản Việt.
  - Tắt server tạm khi xong.
- [ ] **Step 5: Commit** `giao diện true-crime: modal mới (tiến độ từng bước, xem lại song ngữ, sửa tên/lời), tách ra true_crime.js`.

---

### Task 10: Nút "Tạo bản tiếng Anh"

**Files:**
- Modify:
  - `backend/static/index.html`: nút `#btn-create-en-version` (ẩn sẵn), cạnh `#btn-produce-long-video` (khoảng dòng 255);
  - `backend/static/true_crime.js`: thân hàm `refreshLanguageVersionButton`;
  - `backend/static/app.js`: trong `switchProject`, sau khi gán `AppState.currentProject`, gọi `window.refreshLanguageVersionButton?.(AppState.currentProject)`.

- [ ] **Step 1: Viết hàm.**
  - Hiện nút khi `metadata.case_id` có giá trị và `metadata.language === "vi"`.
  - Bấm → lưu dự án bằng hàm lưu có sẵn → POST create-language-version → hỏi trạng thái job.
  - Job xong → toast `Đã tạo bản tiếng Anh. Viết lại lời cho cảnh: …` (hoặc `không cảnh nào cần viết lại`), rồi `switchProject(result.project_id)`.
  - Job lỗi → toast nguyên văn lỗi.
- [ ] **Step 2: Kiểm tra.**
  - `node --check`.
  - Trên server tạm: tạo bản Anh thật từ dự án ở Task 9; dự án mới có lời Anh và giọng `en-US-AndrewMultilingualNeural`.
  - Mở một dự án thường thì nút bị ẩn.
- [ ] **Step 3: Commit** `giao diện: nút tạo bản tiếng Anh từ dự án true-crime`.

---

### Task 11: Hồi quy toàn bộ và chạy thật cả chuỗi

**Files:**
- Create: `tests/test_case_adaptation_live.py`: skip nếu không có `STORY_STUDIO_LIVE=1`. Chạy `dossier.txt` qua 9router thật với worker; kiểm plan không có flag và không có tên thật nào trong lời vi/en.
- Modify: `TASKS.md`

- [ ] **Step 1: Hồi quy.** Chạy bộ test offline ở Task 1 Step 1, cộng 7 file test mới. Kết quả không được tệ hơn baseline. Dọn `projects/` nếu test cũ sinh ra dự án.
- [ ] **Step 2: Test thật ngắn.** `STORY_STUDIO_LIVE=1 ".venv/Scripts/python.exe" -m pytest tests/test_case_adaptation_live.py -q`, phải PASS. Ghi số lần gọi và thời gian chạy.
- [ ] **Step 3: Chạy thật vụ Nhũ Cô.**
  - Khôi phục `_archive_2026-10-19/case_input_text.txt` từ Thùng rác vào `.cache/samples/nhu_co.txt`. `.cache/` đã có trong `.gitignore` và bị chặn khỏi gói.
  - Chạy qua giao diện (server cổng 8000, hoặc server tạm), chọn 8 phút.
  - Ghi vào `TASKS.md`: thời gian, số việc, số lần bị loại phải gọi lại, số cảnh, các cảnh báo, có lọt tên thật không (grep lời kể theo danh sách tên trong bài), có đủ sự kiện chính không.
- [ ] **Step 4: Chạy tiếp bằng Muse.** Tạo dự án bản Việt; tạo ảnh Muse cho 3 cảnh `image` và 1 clip cho cảnh `video`; đọc giọng VieNeu 3 cảnh; tạo bản Anh, đọc giọng 3 cảnh. Gửi người dùng đánh giá chất lượng lời Việt, lời Anh và hình.
- [ ] **Step 5: Commit** `TASKS.md: hoàn thành chuyển thể vụ án song ngữ` (gồm cả `tests/test_case_adaptation_live.py`).
