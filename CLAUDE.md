# Story Studio — hướng dẫn cho agent

Studio dựng video YouTube (storyboard, true-crime, truyện tranh) chạy trên máy, giao diện web `http://localhost:8000`.
Đọc file này trước mọi việc. Bản đồ tính năng: `FEATURE_MAP.md`. Nhật ký và checklist việc: `TASKS.md`.

Cách đọc các nhãn trong file:
- **[Nguyên văn chủ dự án]**: lời của chủ dự án. Giữ nguyên từng chữ, không viết lại, không tóm tắt, không suy diễn thêm ý.
- **[Đề xuất của agent — chưa duyệt]**: agent viết ra để chủ dự án duyệt hoặc sửa. Chưa phải quyết định; khi được duyệt, chủ dự án bỏ nhãn.
- Phần không nhãn: sự thật về code hiện tại, kiểm được bằng lệnh hoặc đọc code. Code đổi thì sửa theo.

## 1. Mục đích project

**[Nguyên văn chủ dự án]** — chủ dự án sẽ viết phần này.

> (chưa có — agent không tự điền, không suy ra từ code, TASKS.md hay ghi nhớ)

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
- dòng 11 (phần gọi mạng và dự án rác): `tests/conftest.py`;
- dòng 3, 4, 12 và phần còn lại của dòng 2, 8, 9, 11: **chưa có máy kiểm**, dựa vào người duyệt.

| # | Mẫu cấm | Làm thay | Vì sao | Còn vi phạm ở |
|---|---|---|---|---|
| 1 | Ghi `projects/<proj_id>/project.json` ở ngoài `project_service` (mở file ghi thẳng) | `project_service.save_project()` | nhiều nơi cùng ghi, ghi thẳng: ghi dở là hỏng file | — |
| 2 | Bắt lỗi rồi trả `None` hay `pass`, khiến "lỗi" thành "không có" | để lỗi nổi lên, hoặc ghi log và báo rõ | từng gặp: `get_project()` trả `None` khi file hỏng → lần lưu sau ghi đè thành dự án rỗng (đã sửa 22/10/2026) | các chỗ `try/except: pass` còn trong mốc Ruff (`tools/ruff_baseline.json`, luật S110) |
| 3 | "Thành công giả": giá trị bịa, link mẫu, mock báo xong, nhánh chỉ có `pass` | báo lỗi rõ hoặc đánh dấu thất bại | người dùng và agent tưởng đã xong | `tts_service.get_audio_duration()` (thiếu ffprobe thì coi là 3 giây), `import_comic_panels_to_storyboard()` (chép ảnh lỗi vẫn gán ảnh) |
| 4 | Âm thầm chuyển sang dịch vụ tính tiền khi dịch vụ miễn phí lỗi | ghi lý do và hiện cho người dùng thấy | tốn tiền mà không ai biết | `image_service.generate_image()` (Muse lỗi rơi sang 9router) |
| 5 | Viết thêm client gọi 9router/LLM | dùng `services/case_adaptation_llm.py` (có thử lại, chờ khi 9router bận) | đang có 4 client, chỉ 1 biết thử lại | `script_splitter.py`, `storyboard_engine.py` |
| 6 | `os.getenv` ngoài `config.py` | thêm biến vào `config.py` và `.env.example` | biến rải rác thì khó biết app cần gì; từng gặp `DEFAULT_VOICE` trong `.env` không có tác dụng (sửa 22/10/2026) | — (3 file tiến trình riêng, ghi lý do trong `tests/test_architecture.py`) |
| 7 | Tự kiểm id/đường dẫn bằng regex riêng hoặc `str.startswith` | `security.py` | tự viết dễ sai (`proj_a` khớp nhầm `proj_ab`, đã gặp ở `complete_task()`, sửa 22/10/2026) | — |
| 8 | Đọc ghi đĩa, `subprocess`, ffmpeg, OpenCV chạy thẳng trong route `async def` | `asyncio.to_thread` như `routers/true_crime.py` | server khựng, WebSocket và heartbeat của Fleet Runner bị trễ | `routers/api.py` |
| 9 | Chèn chữ từ server hoặc người dùng vào `innerHTML`/`showToast()` mà chưa lọc | `escapeHtml()` / `tcEsc()` | chèn được mã HTML vào trang | `innerHTML` dựng từ dữ liệu máy chủ ngoài thông báo (chưa rà hết) |
| 10 | Gắn một sự kiện hai lần (onclick trong HTML và `addEventListener`) | chọn một cách | chạy hai lần (đã gặp: nút bước tải SEO hai lần, đã sửa) | — |
| 11 | Test ghi vào `projects/` thật, gọi LLM/Muse/Edge-TTS thật mà không gắn cờ, bật trình duyệt hay Fleet Runner | `tmp_path`, fixture `isolated_projects_dir`, LLM giả (`tests/case_adaptation_fakes.py`); test thật đặt tên `*_live*` và cần `STORY_STUDIO_LIVE=1` | mất dữ liệu, tốn quota, đụng tài khoản thật | `tests/test_api.py` (xoá dự án `default_preview`), `tests/test_comic.py`, 9 file ghi `projects/` |
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
- **Sau khi chạy test:** bộ test tự báo dự án rác; chạy test lẻ bằng cách khác thì tự so danh sách `projects/` trước và sau.
- **Dữ liệu cần giữ:**
  - Không sửa hay xoá 3 mục MẪU: `proj_crime_52c3a5e8`, `proj_crime_8329b12d`, `_cases/case_7dcf6158`. Dự án để thử là `proj_ea5b04db`.
  - Dọn thì chuyển vào Thùng rác, chỉ khi đã được duyệt.
- **Bí mật:** không in, không chép `.env`. Không commit `backend/chrome_profiles/` (phiên đăng nhập Muse thật) và `backend/config/muse_fleet_accounts.json`.
- **Quota:**
  - Mọi thao tác ghi **LLM**, **Muse**, **Ảnh trả phí** trong `FEATURE_MAP.md` đều tốn thật: ghi số lần gọi và thời gian, không chạy lặp vô ích.
  - Server thử phải tắt hàng việc phân tích, nếu không nó tự chạy tiếp các vụ đang dở.
- **Commit:** tiếng Việt theo kiểu `<vùng>: <mô tả>`, mỗi thay đổi một commit.
- **Chỗ đặt file:** không thêm script ở gốc dự án; test đặt trong `tests/`, công cụ đặt trong `tools/`, file tạm đặt trong `.cache/`. Không sửa file ngoài thư mục dự án khi chưa hỏi.
- **Thư viện tuỳ chọn:** `openai`, `faster-whisper`, `av`, `rembg` có thể chưa cài, code tự bỏ qua; thiếu chúng không phải lỗi.

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
