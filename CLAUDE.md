# Story Studio — hướng dẫn cho agent

Studio dựng video YouTube (storyboard, true-crime, truyện tranh) chạy trên máy, giao diện web `http://localhost:8000`.
Đọc file này trước mọi việc. Bản đồ tính năng: `FEATURE_MAP.md`. Nhật ký và checklist việc: `TASKS.md`.

Cách đọc các nhãn trong file:
- **[Nguyên văn chủ dự án]**: lời của chủ dự án. Giữ nguyên từng chữ, không viết lại, không tóm tắt, không suy diễn thêm ý.
- **[Đề xuất của agent — chưa duyệt]**: agent viết ra để chủ dự án duyệt hoặc sửa. Chưa phải quyết định; khi được duyệt, chủ dự án bỏ nhãn.
- Phần không nhãn: sự thật về code hiện tại, kiểm được bằng lệnh hoặc đọc code. Code đổi thì sửa theo.

## 1. Mục đích project

**[Nguyên văn chủ dự án]** (22/10/2026)

> Mục đích của dự án này là tôi sẽ làm các video youtube về truyện chữ và dự án truyện từ các vụ án có thật, sau đó sẽ mở rộng thêm. Mục tiêu là xây nhiều kênh Youtube bằng AI, mỗi video dài ít nhất phải 20 phút trở lên. Nội dung thì tôi sẽ lấy từ các bộ truyện lightnovel có thật, nếu cần remake thì tôi sẽ bấm remake, còn không thì cứ bê y nguyên truyện vào. Còn vụ án tôi cũng tìm kiếm, sau đó AI sẽ gạch ra dàn ý để viết lại, loại bỏ tên người trong vụ án, địa điểm... để từ vụ án thật nghe giông truyện hơn. Các ảnh / video được generate bằng AI, cụ thể là dùng Muse và gemini 3.1 phải có sự đồng nhất về nhân vật, phong cảnh, sau đó đưa cho tôi prompt để tôi bấm generate luôn. Nhìn chung chỉ cần đầu vào là nội dung video muốn làm, qua hàng loạt quy trình ngầm thì tôi bấm generate và ra được video youtube ít nhất là 15 - 20 phút, dài thì 40-50 phút hoặc tùy độ dài của nội dung

**[Nguyên văn chủ dự án]** (22/10/2026, về độ dài video)

> Mức tối thiểu là 15 phút

### 1.1 Đối chiếu mục đích với code hiện tại — [Đề xuất của agent — chưa duyệt]

Agent ghi ngày 22/10/2026 để biết còn cách mục đích bao xa; đây là sự thật về code, không phải quyết định. Sửa code thì cập nhật bảng này.

| Ý trong mục đích | Code hiện tại | Khoảng cách |
|---|---|---|
| Truyện chữ: "bê y nguyên", "cần remake thì bấm remake" (remake là kể kiểu review: câu 1 mục 1.2) | Nút 1-Click (`#btn-step1-process-script`) gửi bài qua LLM với quy tắc "review và tóm tắt truyện", ngôi thứ ba (`script_splitter.py`, quy tắc cho bài tiếng Việt). Cửa sổ Kịch bản AI (`#btn-submit-script-split`) chia offline, giữ nguyên chữ. Chuyển thể light novel thành podcast tiếng Anh chỉ có qua API (`POST /api/novel/ingest-chapter`) | Luồng 1-Click hiện chỉ có remake; chưa có lựa chọn "bê nguyên văn" trên luồng này. Quy tắc review hiện có chữ "tóm tắt" nên bài ra dễ ngắn hơn bài gốc |
| Truyện chữ làm cả bản Anh và Việt (câu 3 mục 1.2) | Nút tạo bản tiếng Anh (`#btn-create-en-version`) chỉ hiện với dự án vụ án bản Việt | Truyện chữ chưa tạo được bản ngôn ngữ thứ hai từ giao diện |
| Vụ án thật: AI lập dàn ý, viết lại, bỏ tên người và địa điểm | Luồng C trong `FEATURE_MAP.md`: phân tích từng đoạn, đặt tên hư cấu, duyệt dàn ý, kiểm lọt tên thật (`case_adaptation_checks.py`), bản Việt và bản Anh | Đã có; đo thật 22/10/2026 qua test `live` |
| Mỗi video tối thiểu 15 phút, dài 40–50 phút hoặc tuỳ nội dung | True-crime chọn 8/15/20/30 phút, mặc định 20 (`#tc-duration-select`). Truyện chữ không có mục tiêu số phút: dài ngắn theo bài và nhịp (`#step1-pacing-select`) | Lựa chọn 8 phút thấp hơn mức tối thiểu, giữ lại để thử (câu 7 mục 1.2); chưa có lựa chọn 40–50 phút; truyện chữ chưa nhắm được độ dài, chưa cảnh báo khi dưới 15 phút và chưa có nút "ghép chương / remake cho dài ra" (câu 2 mục 1.2; ưu tiên ghép chương: câu 8) |
| Ảnh/video bằng Muse và Gemini 3.1, đồng nhất nhân vật và phong cảnh | Nguồn ảnh: Muse (mặc định) và 9router Gemini 3.1 Flash Image (`NINEROUTER_IMAGE_MODEL`). Nhân vật: mô tả nhân vật (`character_anchor`, nhân vật mẫu), ảnh tham chiếu, phong cách chung của dự án. Phong cảnh: mỗi cảnh có mô tả bối cảnh riêng do LLM viết | Chưa có bước khoá bối cảnh dùng chung như khoá nhân vật. Cách "lưới 9 ô" của luồng dòng lệnh cũ đã gỡ ngày 22/10/2026 (commit `768a44f`, còn trong lịch sử git) vì giao diện không dùng tới |
| Đưa prompt để chủ dự án bấm generate | Mỗi cảnh có prompt ảnh, prompt video và nút Muse riêng (mục 2.3 `FEATURE_MAP.md`) | Luồng 1-Click hiện tự tạo ảnh ngay sau khi chia cảnh (`generate_initial_images` bật sẵn), tốn lượt Muse/9router mà không chờ bấm. Chủ dự án: tạm làm từng bước, chốt workflow rồi mới chuyển thành 1-Click (câu 4 mục 1.2) |
| Ảnh tĩnh có chuyển động nhẹ; cần thì xuất video riêng 5 hoặc 10 giây (câu 5 mục 1.2) | Ảnh: chuyển động nhẹ khi dựng (`build_zoompan_filter()`). Video: Fleet Runner nhận 5 hoặc 10 giây (`clamp_video_duration()`), nhưng nút "Muse Video" luôn gửi 5 giây (`generateSceneWithMuse()`); clip ngắn hơn lời thoại thì lặp lại khi dựng (`render_scene_video()`) | Chưa chọn được video 10 giây; chưa báo khi lời thoại dài hơn clip |
| Đầu vào là nội dung, quy trình ngầm, bấm là ra video | Luồng A và C trong `FEATURE_MAP.md`; nút Sản xuất video dài (`#btn-produce-long-video`) tự thu giọng, tạo ảnh còn thiếu, dựng và ghép | Đã có khung; độ dài và cách giữ nguyên văn như hai dòng trên |
| Nhiều kênh YouTube; kênh theo loại nội dung, tính sau; tự đăng lên YouTube (câu 6 mục 1.2) | Mỗi dự án độc lập; gói SEO và thumbnail theo từng dự án; không có phần đăng YouTube | Chưa có khái niệm "kênh" trong code (để sau); không cần làm phần đăng YouTube |

### 1.2 Trả lời của chủ dự án về quy trình (22/10/2026)

Cột câu hỏi do agent viết (tóm tắt câu đã hỏi trong chat). Cột trả lời là **[Nguyên văn chủ dự án]**.

| # | Câu hỏi của agent | Trả lời — [Nguyên văn chủ dự án] |
|---|---|---|
| 1 | "Remake" là viết lại văn phong nhưng giữ cốt truyện, hay kể kiểu review như nút 1-Click đang làm? | Remake là kể kiểu dạng review truyện đó. |
| 2 | Truyện ngắn quá, không đủ 15 phút thì làm gì: ghép nhiều chương, remake cho dài ra, hay chỉ cần app cảnh báo? | App sẽ cảnh báo trước và có nút lựa chọn ghép chương hoặc remake cho dài ra |
| 3 | Truyện chữ làm tiếng Việt, tiếng Anh hay cả hai? | Làm cả 2 bản Anh và Việt |
| 4 | "Bấm generate": một nút cho cả video, hay xem prompt từng cảnh rồi mới bấm? (nút 1-Click hiện tự tạo ảnh ngay) | Tôi thấy cơ chế 1 click tiện nhưng tiềm ẩn rủi ro là ảnh / video không theo 1 workflow hoàn chỉnh, hiện tại thì cứ làm theo từng bước đã. sau này khi đã chốt được workflow rồi thì mới chuyển thành 1 click |
| 5 | Hình mỗi cảnh: ảnh tĩnh có chuyển động nhẹ hay video Muse 5 giây? | Cứ cho ảnh tĩnh có chuyển động nhẹ, nếu cần video riêng thì tôi sẽ xuất video, mà video có cả 5s với 10s đó, đừng chỉ cố định trong 5 giây, lỡ thoại dài hơn thì còn biết |
| 6 | Mỗi kênh gắn với gì? Tự đăng lên YouTube hay muốn app đăng? | Tôi muốn tự đăng lên youtube. Còn mỗi kênh gắn với gì thì tôi không hiểu lắm, chắc là loại nội dung đi. Kênh chuyên về truyện, chuyên về án, chuyên về review này kia thì tính sau. |
| 7 | Lựa chọn 8 phút của vụ án: bỏ đi hay giữ lại để thử cho rẻ quota? | Giữ lại để thử trước. |
| 8 | "Remake cho dài ra" làm thế nào, khi quy tắc review hiện có chữ "tóm tắt" nên bài ra thường ngắn hơn truyện gốc? | Tôi nghĩ là remake cho dài ra thì cơ bản là thêm ý nhận xét ngoài lề thôi. nhưng ưu tiên gộp chương hơn là cố làm dài rồi thành nhạt nhẽo. |

### 1.3 Quy trình làm video — [Đề xuất của agent; chủ dự án xác nhận tạm 22/10/2026: "Tạm thời là đúng ý tôi rồi"]

Agent suy ra từ mục 1 và 1.2. Cuối mỗi bước ghi tình trạng code hiện tại (có / thiếu / lệch); chi tiết ở bảng 1.1.

Đầu vào: nội dung video muốn làm.

- Nhánh truyện chữ (light novel có thật):
  1. Dán truyện — có.
  2. Chọn bê nguyên văn hoặc remake (kể kiểu review) — remake có; lựa chọn bê nguyên văn thiếu.
  3. Ước độ dài; dưới 15 phút thì cảnh báo và cho chọn ghép chương (ưu tiên) hoặc remake cho dài ra (thêm nhận xét ngoài lề) — thiếu.
- Nhánh vụ án thật:
  1. Chủ dự án tự tìm vụ, dán bài — có.
  2. AI gạch dàn ý, chủ dự án duyệt dàn ý; chọn 8/15/20/30 phút — có.
  3. AI viết lại, bỏ tên người và địa điểm, kiểm lọt tên thật — có.
- Phần chung sau khi hai nhánh gộp lại:
  4. Chia cảnh (chạy ngầm) — có.
  5. Đồng nhất nhân vật và phong cảnh — nhân vật có; khoá phong cảnh dùng chung thiếu.
  6. Prompt ảnh/video cho từng cảnh (Muse, Gemini 3.1) — có.
  7. Chủ dự án bấm generate từng bước — lệch: nút 1-Click đang tự tạo ảnh ngay.
  8. Ảnh tĩnh có chuyển động nhẹ; video riêng 5 hoặc 10 giây khi cần — thiếu: nút Muse Video cố định 5 giây.
  9. Bản tiếng Anh dùng lại ảnh của bản Việt — vụ án có; truyện chữ thiếu.
  10. Giọng đọc, dựng, ghép từng bản — có.
  11. Chủ dự án tự đăng YouTube; tiêu đề, mô tả, thumbnail có sẵn để chép — có.
- Để sau: kênh theo loại nội dung (câu 6 mục 1.2).

## 2. Nguyên tắc

### 2.1 Thiết kế kiểu Dune — [Nguyên văn chủ dự án]

> Nguyên tắc thiết kế kiểu Dune — đường đúng phải cần ÍT quyết định hơn đường tắt; phụ thuộc/mẫu bị cấm phải làm test hoặc CI báo lỗi tự động chứ không chỉ ghi nhắc; mỗi loại dữ liệu chỉ có MỘT nơi được ghi; việc mới thì thêm file/thành phần riêng thay vì sửa chen vào file dùng chung; ngoại lệ phải hẹp, ghi rõ lý do và được duyệt như thay đổi kiến trúc.

### 2.2 Tư duy — [Nguyên văn chủ dự án]

> Nguyên tắc tư duy: mục đích project và các quyết định trong CLAUDE.md giữ NGUYÊN VĂN lời của tôi — bạn được đề xuất và làm dày, nhưng không tự viết lại ý và không tự chốt các quyết định mang tính tư duy (viết ra chính là lúc tư duy, phần đó là của tôi).

### 2.3 Tra bản đồ trước — [Nguyên văn chủ dự án]

> mọi việc làm/tái hiện lỗi/kiểm chứng đều phải tra FEATURE_MAP.md trước, cấm đoán đường.

## 3. Lệnh

| Việc | Lệnh |
|---|---|
| Chạy app | `run.bat` (hoặc `.venv\Scripts\python.exe run.py`), mở `http://localhost:8000`. Tự bật Fleet Runner |
| Python | luôn `.venv\Scripts\python.exe` (Python 3.14), không dùng `python` hệ thống; in tiếng Việt thì thêm `-X utf8` |
| Cài thư viện | `.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt` (phiên bản đã ghim); Playwright thêm `.venv\Scripts\python.exe -m playwright install chromium` |
| Kiểm tra nhanh (hook tự chạy mỗi lần commit) | `.venv\Scripts\python.exe tools\check.py`: Ruff so với mốc, cú pháp JS, test kiến trúc, test FEATURE_MAP (khoảng 15 giây) |
| Kiểm tra đầy đủ (trước khi gộp `master`) | `.venv\Scripts\python.exe tools\check.py --full`: thêm cả bộ test mặc định |
| Cài hook trước commit (một lần mỗi bản sao repo) | `.venv\Scripts\python.exe tools\check.py --install-hook`. Không bỏ qua hook bằng `--no-verify` |
| Test một file | `.venv\Scripts\python.exe -m pytest tests\test_xxx.py -q` |
| Bộ test mặc định (offline) | `.venv\Scripts\python.exe -m pytest -q` (`pytest.ini` bỏ qua test cờ `live`; test không gắn cờ mà gọi mạng, 9router, VieNeu hay server 8000 thì bị chặn và báo lỗi; còn dự án rác trong `projects/` thì báo lỗi) |
| Test gọi dịch vụ thật | chỉ khi được yêu cầu: `.venv\Scripts\python.exe -m pytest -m live -q` (Edge-TTS, 9router, VieNeu); riêng `tests/test_case_adaptation_live.py` cần thêm `STORY_STUDIO_LIVE=1` |
| Sửa bớt lỗi Ruff cũ | sửa xong chạy `.venv\Scripts\python.exe tools\check.py --shrink-ruff-baseline` để hạ mốc `tools/ruff_baseline.json`. Không có lệnh nâng mốc |
| Kiểm giao diện | server thử cổng 8010 theo `.claude/launch.json` (tắt hàng việc phân tích và tự bật Fleet Runner), mở bằng trình duyệt trong app, dùng dự án thử `?project_id=proj_ea5b04db`. Không khởi động lại server 8000 đang dùng chung |
| Build CSS | thêm class Tailwind mới: `cd tools\tailwind`, `npm install --cache .npm-cache`, `npm run build` → `backend/static/tailwind.css` |
| Đóng gói bán | `.venv\Scripts\python.exe tools\build_release.py` → `dist/` (lấy theo danh sách cho phép, tự chặn bí mật) |
| Lint | Ruff (`ruff.toml`), chạy qua `tools/check.py`. Kiểm kiểu dữ liệu và CI trên GitHub: chưa có |

Công cụ ngoài: ffmpeg/ffprobe trong PATH, `uv` (giọng VieNeu), Chrome hoặc Edge, 9router ở `127.0.0.1:20128`.

## 4. Kiến trúc hiện tại

- **Tầng:** `backend/routers/` nhận HTTP và kiểm đầu vào → `backend/services/` xử lý → `backend/models/` (Pydantic). Giao diện chỉ gọi `/api/...`. `backend/main.py` ghép router, phục vụ `/static`, WebSocket `/ws/render/{render_id}`, chạy hàng việc phân tích vụ án.
- **Cấu hình:** `backend/config.py` đọc `.env` (đường dẫn, 9router, cổng, mặc định). **Kiểm đầu vào:** `backend/security.py` (`is_safe_id`, `require_safe_id`, `is_within`, `validate_path_ids`, giới hạn upload, chỉ nhận truy cập từ máy này).
- **Hai kiểu code:** mảng true-crime (`services/case_*.py`, `routers/true_crime.py`, `routers/language_versions.py`) ghi file an toàn, có khoá, đọc ghi đĩa ở luồng phụ, test cô lập, gọi LLM theo từng bước nhỏ có kiểm. Mảng cũ (`routers/api.py`, `project_service.py`, dịch vụ ảnh/giọng/video) chưa như vậy.
- **Giao diện:** `backend/static/index.html` + `app.js` (màn chính) + `true_crime.js` (cửa sổ Hồ Sơ Kỳ Án, dùng biến toàn cục của `app.js`, nạp sau). CSS Tailwind build sẵn; FontAwesome và Google Fonts vẫn tải từ CDN.
- **Tiến trình:** web server (8000); hàng việc phân tích trong server (khoá `projects/_cases/.worker.lock`); Fleet Runner riêng (`backend/runners/muse_fleet_runner.py`, khoá `backend/runners/.fleet_runner.lock`); 9router (20128) và VieNeu (5005, dùng chung với douyin-movie-studio) là chương trình ngoài.

Nơi ghi từng loại dữ liệu (hiện tại):

| Dữ liệu | Ở đâu | Nơi ghi đúng | Chỗ còn ghi tắt |
|---|---|---|---|
| Dự án | `projects/<proj_id>/project.json` + `images/`, `videos/`, `audio/`, `renders/` | `project_service.save_project()` (ghi an toàn qua `services/safe_files.py`); file hỏng thì `get_project()` báo `ProjectUnreadableError`, API trả 409 | — (gom xong 22/10/2026). Còn thiếu khoá: hai nơi cùng đọc-sửa-ghi một dự án thì bản lưu sau thắng |
| Vụ án true-crime | `projects/_cases/<case_id>/` | `services/case_store.py` (ghi an toàn) | — |
| Tài khoản Muse | `backend/config/muse_fleet_accounts.json` | `routers/muse_bridge.py` và Fleet Runner (hai nơi) | — |
| Ảnh/video Muse | `backend/static/muse_outputs/` + bản sao trong dự án | `complete_task()` | — |
| Cấu hình | `.env` (mẫu đủ biến: `.env.example`), `backend/config.py` | `config.py` (công tắc đọc lúc gọi: `env_flag()`) | — (còn 3 file có lý do: tiến trình riêng `vieneu_server.py`, `single_instance.py`, `muse_fleet_runner.py`) |

## 5. Đường cấm — [Đề xuất của agent — chưa duyệt]

Lập từ đợt rà soát 21/10/2026. Cột cuối liệt kê chỗ còn vi phạm để agent **không chép theo**; sửa chúng là việc riêng.

Máy kiểm tự động (chạy trong `tools/check.py` và hook trước commit):
- dòng 1, 5, 6, 7, 9 (phần `showToast`), 10, 13, 14: `tests/test_architecture.py` (vi phạm cũ ghi thành ngoại lệ đếm đúng số lần; biến môi trường phải có trong `.env.example`);
- dòng 2 (phần `except: pass`) và 8 (phần `open`, `subprocess` trong hàm async): Ruff, so với mốc `tools/ruff_baseline.json`;
- dòng 11: `tests/conftest.py` (mọi test chạy trong thư mục tạm, chặn mạng và dịch vụ thật nếu không gắn cờ `live`, báo dự án rác) và `tests/test_test_isolation.py`;
- dòng 3, 4, 12 và phần còn lại của dòng 2, 8, 9: **chưa có máy kiểm**, dựa vào người duyệt.

| # | Mẫu cấm | Làm thay | Vì sao | Còn vi phạm ở |
|---|---|---|---|---|
| 1 | Ghi `projects/<proj_id>/project.json` ở ngoài `project_service` (mở file ghi thẳng) | `project_service.save_project()` | nhiều nơi cùng ghi, ghi thẳng: ghi dở là hỏng file | — |
| 2 | Bắt lỗi rồi trả `None` hay `pass`, khiến "lỗi" thành "không có" | để lỗi nổi lên, hoặc ghi log và báo rõ | từng gặp: `get_project()` trả `None` khi file hỏng → lần lưu sau ghi đè thành dự án rỗng (đã sửa 22/10/2026) | các chỗ `try/except: pass` còn trong mốc Ruff (`tools/ruff_baseline.json`, luật S110) |
| 3 | "Thành công giả": giá trị bịa, link mẫu, mock báo xong, nhánh chỉ có `pass` | báo lỗi rõ hoặc đánh dấu thất bại | người dùng và agent tưởng đã xong | — (đã gặp và sửa 22/10/2026: `get_audio_duration()` đoán 3 giây khi thiếu ffprobe, nhập truyện tranh gán ảnh không có) |
| 4 | Âm thầm chuyển sang dịch vụ tính tiền khi dịch vụ miễn phí lỗi | ghi lý do và hiện cho người dùng thấy | tốn tiền mà không ai biết | `image_service.generate_image()` (Muse lỗi rơi sang 9router) |
| 5 | Viết thêm client gọi 9router/LLM | dùng `services/case_adaptation_llm.py` (có thử lại, chờ khi 9router bận) | đang có 4 client, chỉ 1 biết thử lại | `script_splitter.py`, `storyboard_engine.py` |
| 6 | `os.getenv` ngoài `config.py` | thêm biến vào `config.py` và `.env.example` | biến rải rác thì khó biết app cần gì; từng gặp `DEFAULT_VOICE` trong `.env` không có tác dụng (sửa 22/10/2026) | — (3 file tiến trình riêng, ghi lý do trong `tests/test_architecture.py`) |
| 7 | Tự kiểm id/đường dẫn bằng regex riêng hoặc `str.startswith` | `security.py` | tự viết dễ sai (`proj_a` khớp nhầm `proj_ab`, đã gặp ở `complete_task()`, sửa 22/10/2026) | — |
| 8 | Đọc ghi đĩa, `subprocess`, ffmpeg, OpenCV chạy thẳng trong route `async def` | `asyncio.to_thread` như `routers/true_crime.py` | server khựng, WebSocket và heartbeat của Fleet Runner bị trễ | vài chỗ `open()`/kiểm file nhỏ trong `routers/api.py`, `routers/muse_bridge.py` (mốc Ruff); việc nặng (OpenCV, PIL thumbnail) đã chuyển sang luồng phụ 22/10/2026 |
| 9 | Chèn chữ từ server hoặc người dùng vào `innerHTML`/`showToast()` mà chưa lọc | `escapeHtml()` / `tcEsc()` | chèn được mã HTML vào trang | `innerHTML` dựng từ dữ liệu máy chủ ngoài thông báo (chưa rà hết) |
| 10 | Gắn một sự kiện hai lần (onclick trong HTML và `addEventListener`) | chọn một cách | chạy hai lần (đã gặp: nút bước tải SEO hai lần, đã sửa) | — |
| 11 | Test ghi vào `projects/` thật, gọi LLM/Muse/Edge-TTS thật mà không gắn cờ, bật trình duyệt hay Fleet Runner | `tmp_path`, fixture `isolated_projects_dir`, LLM giả (`tests/case_adaptation_fakes.py`); test thật đặt tên `*_live*` và cần `STORY_STUDIO_LIVE=1` | mất dữ liệu, tốn quota, đụng tài khoản thật | — (từ 22/10/2026 mọi test ghi vào thư mục tạm) |
| 12 | Xoá vĩnh viễn dữ liệu người dùng (`shutil.rmtree`, `unlink`) | chuyển vào Thùng rác, hoặc hỏi trước | không lấy lại được | `project_service.delete_project()`, `clear_all_gallery()` |
| 13 | `services/` import từ `routers/` | đưa phần dùng chung xuống `services/` | vòng phụ thuộc; import kéo theo ghi file cấu hình | `image_service.py` (import `routers.muse_bridge`) |
| 14 | Đường dẫn tuyệt đối của máy này, hay trỏ sang dự án khác | đường dẫn từ `config.py` | hỏng trên máy khách; `tools/build_release.py` chặn | `thumbnail_service.py` (`C:\Windows\Fonts`); vài chuỗi hợp lệ có ghi lý do trong `tests/test_architecture.py` |

Code mới nên theo mẫu của mảng true-crime (mục 4), không theo mảng cũ.

## 6. Quy tắc làm việc của agent

**[Nguyên văn chủ dự án]**

> làm trên branch, không push thẳng main, làm xong phải tự kiểm chứng bằng bằng chứng

**Làm dày — [Đề xuất của agent — chưa duyệt]**
- **Nhánh:** repo chưa có remote, nhánh chính tên `master` (là "main" trong quy tắc trên). Mỗi việc một nhánh mới từ `master`, tên tiếng Việt không dấu. Commit trên nhánh; chỉ gộp vào `master` khi chủ dự án đồng ý; không push lên đâu khi chưa được bảo.
- **Trước khi sửa:** tra `FEATURE_MAP.md`; nói rõ sẽ sửa những file nào; việc dài thì ghi checklist vào `TASKS.md` và tick khi xong.
- **Bằng chứng tối thiểu:**
  - test liên quan và `tools/check.py --full`, ghi số đạt/lỗi và thời gian;
  - đổi giao diện: mở server thử 8010, bấm đúng phần tử ghi trong `FEATURE_MAP.md`, xem console và log server;
  - đổi giọng, ảnh, video: mở hoặc nghe file thật, không chỉ nhìn mã thoát hay dung lượng file;
  - ghi kết quả vào `TASKS.md`.

  Chưa có bằng chứng thì báo "chưa kiểm chứng", không báo "xong".
- **Sau khi chạy test:** bộ test tự cô lập `projects/` và tự báo dự án rác; chạy thử bằng cách khác (server thử, script) thì tự so danh sách `projects/` trước và sau.
- **Dữ liệu cần giữ:**
  - Không sửa hay xoá 3 mục MẪU: `proj_crime_52c3a5e8`, `proj_crime_8329b12d`, `_cases/case_7dcf6158`. Dự án để thử là `proj_ea5b04db`.
  - Dọn thì chuyển vào Thùng rác, chỉ khi đã được duyệt.
- **Bí mật:** không in, không chép `.env`. Không commit `backend/chrome_profiles/` (phiên đăng nhập Muse thật) và `backend/config/muse_fleet_accounts.json`.
- **Quota:**
  - Mọi thao tác ghi **LLM**, **Muse**, **Ảnh trả phí** trong `FEATURE_MAP.md` đều tốn thật: ghi số lần gọi và thời gian, không chạy lặp vô ích.
  - Server thử phải tắt hàng việc phân tích, nếu không nó tự chạy tiếp các vụ đang dở.
- **Commit:** tiếng Việt theo kiểu `<vùng>: <mô tả>`, mỗi thay đổi một commit.
- **Chỗ đặt file:** không thêm script ở gốc dự án; test đặt trong `tests/`, công cụ đặt trong `tools/`, file tạm đặt trong `.cache/`. Không sửa file ngoài thư mục dự án khi chưa hỏi.
- **Thư viện tuỳ chọn:** `openai`, `faster-whisper`, `av` có thể chưa cài, code tự bỏ qua; thiếu chúng không phải lỗi.

## 7. Bảng định tuyến: loại việc → quy trình

Cột "Quy trình" để trống, chủ dự án điền ở giai đoạn sau. Cột "Nhận biết" là **[Đề xuất của agent — chưa duyệt]**.

| Loại việc | Nhận biết | Quy trình |
|---|---|---|
| Sửa lỗi | có hành vi sai, tái hiện được theo `FEATURE_MAP.md` | |
| Tính năng mới | thêm thứ người dùng thấy hoặc dùng được | |
| Sửa giao diện | đổi `index.html`, `app.js`, `true_crime.js`, `tailwind.css` | |
| Pipeline LLM | chia cảnh, phân tích vụ án, viết lời, bản tiếng Anh, prompt | |
| Muse / Fleet Runner | tài khoản, hàng việc, runner, gallery | |
| Giọng đọc | Edge-TTS, VieNeu, phụ đề | |
| Dựng video | ffmpeg, chuyển cảnh, ghép, nhạc nền | |
| Dữ liệu dự án | đổi schema, cách lưu, di chuyển dữ liệu cũ | |
| Dọn dẹp / tái cấu trúc | không đổi hành vi | |
| Nâng thư viện, Python | sửa `requirements*.txt`, `.venv` | |
| Đóng gói bản bán | `tools/build_release.py`, nội dung gói | |
| Thay đổi kiến trúc, xin ngoại lệ đường cấm | chạm mục 4 hoặc mục 5 | |
| Tài liệu agent | `CLAUDE.md`, `FEATURE_MAP.md` | |
