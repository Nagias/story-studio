# TASKS — sửa 3 lỗi chung (2026-10-19)

Bản gốc các file trước khi sửa: `.backup/2026-10-19-fixes/`.
Không đụng phần true-crime (case_fictionalizer, true_crime router, modal true-crime trong app.js).

## Việc 1 — Lỗi bị che (thất bại vẫn báo thành công)
- [x] image_service: chuỗi tự động chỉ còn Muse → 9router → báo lỗi; provider lạ báo lỗi
- [x] api.py: gen-image / create-from-script / auto-gen / render không đặt ready khi ảnh lỗi; trả provider + fallback_reason
- [x] gen-voice (và các chỗ tự sinh giọng): lưu fallback giọng vào scene.metadata, trả về cho UI
- [x] /voices/{id}/sample: không cache bản Edge dưới tên vieneu-*
- [x] app.js: bỏ ảnh demo khi lỗi, bỏ thay ảnh hỏng bằng demo, bỏ project placeholder, split-script dùng result.project, toast lưu đúng, bỏ API.updateProject, Muse video lỗi báo lỗi, badge sẵn sàng đúng, cảnh báo giọng dự phòng

## Việc 2 — Video Muse không vào bản dựng cuối
- [x] Muse video lưu `videos/{scene}_muse.mp4`, đánh dấu cảnh dùng video
- [x] render-preview / render / produce-long-video dùng clip làm đầu vào, segment ra `videos/{scene}.mp4`, lặp clip cho đủ độ dài giọng
- [x] video_service: thêm logger
- [x] Chuẩn hoá âm thanh segment 48 kHz stereo

## Việc 3 — Giao diện lệch dữ liệu với server
- [x] Liệt kê thay đổi cho người dùng trước khi sửa
- [x] Server là bản chính: tải từ server khi mở, tự lưu (debounce), lưu trước khi sản xuất / tạo task Muse
- [x] Task Muse xong: gộp kết quả, không ghi đè chỉnh sửa (+ PUT không xoá media server khi client gửi trống)
- [x] localStorage chỉ giữ tuỳ chọn giao diện + id dự án cuối (bản cũ được đẩy lên server một lần)
- [x] Upload ảnh/video lên server thay vì data URL / blob (`POST /projects/{id}/scenes/{scene}/upload-media`)
- [x] Project có field `settings`; BGM/ducking/hardsub ghi cả trường thật

## Kiểm chứng
- [x] Test mới cho việc 1, 2 (`tests/test_no_fake_success_and_motion_render.py`) và việc 3 (`tests/test_project_sync.py`)
- [x] Kiểm thật ffmpeg: clip 2s lặp đủ 6s, mọi đoạn 48 kHz stereo, ghép `-c copy` đúng tổng thời lượng
- [x] Kiểm giao diện (server tạm cổng 8010, không bấm Muse): tạo dự án, tự lưu, tải lại, upload ảnh, lỗi ảnh hiện badge
- [x] Tập test offline không tệ hơn baseline: 100 pass / 12 fail (baseline 74 / 12, đúng 12 lỗi cũ, không lỗi mới)
- [x] Dọn dữ liệu test tạo ra

## Test thật trên Muse (21:12–21:27, server cổng 8000 đang chạy, dự án thử `proj_ea5b04db` "ZZ Thử Muse")
- [x] 1-Click Bước 1: 5 cảnh, Muse vẽ đủ 5 ảnh (16:9, 1920–2560 px) trong ~5 phút, không cảnh nào phải dự phòng
- [x] Nút Muse Video cảnh 2: clip lưu `videos/scene_2_6857_muse.mp4`, cảnh chuyển sang chế độ video, giao diện gộp kết quả
- [x] Giọng VieNeu: thất bại → Edge HoaiMy, có `metadata.voice_fallback` và badge "Đang dùng giọng dự phòng"
- [x] Tự lưu: đổi giọng/BGM trên giao diện → server có ngay, dữ liệu clip Muse không bị ghi đè
- [x] Sản xuất video dài: xong ~1 phút; video cuối 22,42 s (khớp tổng cảnh), 48 kHz stereo; khung hình cảnh 2 trùng clip Muse
- [x] Phát hiện: key 9router trong `.env` bị từ chối (HTTP 401 Invalid API key) → chia cảnh rơi về offline, prompt ảnh là mẫu chung
- [x] Sửa thêm: chia cảnh offline giờ có `fallback_reason` (script_splitter) + `project.metadata.scene_analysis`, giao diện cảnh báo (cần khởi động lại server để chạy)
- [x] Sửa thêm: `LongVideoProduceRequest.image_provider` mặc định `None` (trước là "9router_gemini", ghi đè ngầm provider Muse/mock của dự án khi sản xuất)
- [x] Test lại các file chạm phần vừa sửa: 30 + 28 pass (adversarial, comic, vox, 2 file test mới), dọn comic_slices test tạo
- [ ] Cần người dùng: cập nhật `NINEROUTER_API_KEY` trong `.env`
- [x] Cài VieNeu lên ổ D (người dùng đồng ý): `.cache/uv` (gói, 658 MB) + `.cache/huggingface` (model, 581 MB), Python 3.11 qua uv; ổ C không đổi. `.cache/` đã trong .gitignore, build_release chặn thêm
- [x] Giữ model trong RAM: `backend/services/vieneu_server.py` (từ douyin), `tts_service.ensure_vieneu_server()` tự bật ở 127.0.0.1:5005 với cache trên ổ D; CLI (26 s/cảnh) và Edge chỉ còn là dự phòng, lý do dự phòng ghi đủ
- [x] Kiểm chứng thật: bật server 39,9 s; câu đầu 13,7 s, các câu sau 5–7 s; route gen-voice cảnh 3 `proj_ea5b04db` với vieneu-MaiAnh → 200, không có `voice_fallback`; test mới 31 pass
- [x] storyboard_engine: thêm `stream: false` (thiếu thì 9router trả body không phải JSON) và nâng timeout 45 s → 240 s (Gemini high mất ~85–100 s); chạy thật 84,7 s ra 9 cảnh bằng LLM; test payload có stream False
- [x] Khởi động lại server cổng 8000 (run.py --no-browser, giữ fleet runner + server VieNeu): VieNeu qua app 5 s không fallback; 9router chia cảnh 27 s ra 5 cảnh bằng LLM

# TASKS — dọn dẹp & đóng gói bán (2026-10-19, phiên 2)

File rác chuyển vào `_archive_2026-10-19/` (giữ cấu trúc, xem `MANIFEST.txt`), chưa xoá gì.

- [x] Chuyển rác ở gốc: 31 PNG QA, `test_drone_frame.jpg`, `test_*.mp3/.srt/.words.json`, `case_input_text.txt`, `qa_test_report.json`, script debug Muse, `test_*.py` lẻ, `run_full_novel_test.py`, `backend/test_*.py`, `public/qa-screenshots/`, `comic_slices/`, `output/`
- [x] `backend/static`: 4 ảnh preview, `test_comic/{ltr,rtl,strip}_out/`, `demo_images/test_*.jpg` (giữ `test_comic/test_grid.jpg` + `test_strip.jpg` vì app.js `loadComicSample` còn dùng)
- [x] `comic_slicer.py`: ghi vào `COMIC_SLICES_DIR` thay vì `os.getcwd()/comic_slices`
- [x] `.gitignore`, `.env.example` (đủ biến, không có key), `README.md`
- [x] `tools/build_release.py`: whitelist -> `dist/story-studio-<ngày>.zip`, tự kiểm rồi FAIL nếu lọt `.env`/chrome_profiles/log/pycache/key/IP 100./đường dẫn máy
- [x] Kiểm chứng: build ra zip 5,23 MB qua hết kiểm tra; zip "bẩn" giả bị bắt đủ; gói giải nén import + GET `/`, static, `/api/muse-bridge/accounts` đều 200; `test_muse_fleet_routing.py` + `test_muse_fleet_runner_media.py` 33 pass; `test_comic.py` 6 pass

# TASKS — hoàn thiện & làm gọn dự án (2026-10-19, phiên 3)

- [x] Bước 7: log cũ `backend/muse_fleet_runner.log.1` (33,8 MB) vào Thùng rác
- [x] Ghim phiên bản `backend/requirements.txt` (== bản đang chạy), thêm `requirements-dev.txt` (pytest), bỏ `aiofiles` không dùng
- [x] Sửa 12 test lỗi sẵn: khôi phục `generate_offline_script` (true-crime crash khi hồ sơ ngắn), video ≤1 phút dùng cảnh 5s, thêm preset `kingdom_shin` + style `roman_legionary_epic` (UI có mà backend thiếu), cảnh toàn cảnh vẫn giữ đặc điểm nhân vật, phong cách lạ dùng `DEFAULT_STYLE`, cập nhật test karaoke/style cũ
- [x] Build Tailwind cục bộ: `tools/tailwind` (3.4.17, đúng bản CDN) -> `backend/static/tailwind.css`, so sánh giao diện khớp bản CDN
- [x] `index.html`: thay script CDN bằng `tailwind.css` (đặt cuối `<head>` như bản CDN); kiểm tra trên trình duyệt: không còn script CDN, không lỗi console
- [x] `/open-folder`: import `_get_project_dir` trong `api.py` + `tests/test_open_folder.py`
- [x] Dọn (vào Thùng rác): 61 dự án test (94 MB) + 11 bảng ghim không dùng (33 MB), cache Chrome 3 profile (~120 MB, kiểm tra cả 3 vẫn đăng nhập Muse), `__pycache__`, cache npm
- [x] Chạy lại test: 128 pass / 0 fail (17 file offline); git init + commit `ffa1c3b`
- [x] Sau commit: `_archive_2026-10-19/` (19 MB), `.backup/` vào Thùng rác

# TASKS — Chuyển thể vụ án song ngữ (2026-10-19, nhánh worktree-true-crime-adaptation)

Thiết kế: `docs/superpowers/specs/2026-10-19-true-crime-adaptation-design.md`. Kế hoạch: `docs/superpowers/plans/2026-10-19-true-crime-adaptation.md`.

- [x] Task 1: Schema, lưu trữ, hàng việc, fixture test, baseline (`559b8a7`..`fc6b647`)
- [x] Task 2: Client LLM qua 9router (`832d695`)
- [x] Task 3: Kiểm lọt tên, ngày tháng, áp tên hư cấu (`82f4eca`..`a8f4c15`)
- [x] Task 4: Bộ chạy một việc, cùng các việc G1–G4 (từ bài gốc tới hồ sơ) (`a5d5c4f`..`623cb2d`)
- [x] Task 5: Các việc G5–G7 (dàn ý, viết cảnh theo nhịp, ráp kế hoạch) (`50d7981`..`aef4b53`)
- [x] Task 6: Worker chạy hàng việc tuần tự, kèm chờ khi 9router bận (`0e07ee1`..`73099b9`)
- [x] Task 7: Bảng ghim theo ngôn ngữ, tạo dự án, tạo bản ngôn ngữ khác (`c7dd101`..`267ae0f`)
- [x] Task 8: API, bỏ luồng cũ (`67fa68f`)
- [x] Task 9: Giao diện modal Hồ Sơ Kỳ Án (`be37212`)
- [x] Task 10: Nút "Tạo bản tiếng Anh" (`3656370`)
- [ ] Task 11: Hồi quy toàn bộ và chạy thật cả chuỗi (bước 1 xong; bước 2, 3 chờ 9router; bước 4 chờ người dùng; xem mục "Task 11" cuối file)

## Baseline trước khi sửa (Task 1, bước 1)
- Bộ offline 18 file (lệnh trong kế hoạch, Task 1): **158 pass / 1 fail**, 332 s. Worktree không có `backend/config/muse_fleet_accounts.json` và `backend/chrome_profiles/`.
- Fail sẵn: `tests/test_gate_gout_regressions.py::test_sec_04_block_arbitrary_file_overwrite_in_muse_complete` (test chờ 200, nhưng `/api/muse-bridge/tasks/create` giờ trả 400 khi `output_path` nằm ngoài projects/muse_outputs). Test cũ lệch với code đã siết, không thuộc nhiệm vụ này.
- Lần chạy sinh ra (đều bị `.gitignore` bỏ qua): `projects/proj_crime_e9e94024`, `projects/proj_crime_fa8cad63`, `backend/static/comic_slices/` (3 thư mục), `backend/static/evidence_boards/` (2 thư mục `case_*`), `backend/config/muse_fleet_accounts.json`, `backend/muse_fleet_runner.log` (rỗng). Trước khi chạy thì chưa có `projects/`, `comic_slices/`, `backend/static/comic_slices/`.
- [ ] Dọn các thư mục trên (chuyển vào Thùng rác): lệnh xoá bị chặn nên chưa dọn

## Task 11: hồi quy và chạy thật (2026-10-20)
- [x] Bước 1, hồi quy offline: 25 file (18 file của baseline + 7 file mới) **466 pass / 1 fail**, 114 s. Tách ra: 18 file cũ **182 pass / 1 fail** (baseline 158 / 1; thêm 24 test từ Task 8–10), 7 file mới **284 pass**. Lỗi duy nhất vẫn là `test_sec_04_block_arbitrary_file_overwrite_in_muse_complete` (có sẵn từ baseline), không lỗi mới. Hai lần chạy không sinh dự án mới trong `projects/`; chỉ sinh 6 thư mục `backend/static/comic_slices/{47718a76,5c5f6a47,c1495ed0,7992f93d,84dc1983,abd0033b}` (gitignored). Sáu thư mục này chưa dọn: chờ người dùng quyết định (chuyển vào Thùng rác).
- [x] Sửa sau review (vòng 1): `case_adaptation_checks` khớp tên nhiều âm tiết trên chuỗi đã bỏ dấu nên từ thường trùng tên thật ("lẻ loi" ~ "Lê Lợi", "tàn hại" ~ "Tân Hải") bị thay nhầm bằng tên hư cấu. Giờ chỉ nhận chỗ khớp viết đúng dấu như tên thật (không phân biệt hoa thường, dấu thanh kiểu cũ/mới coi như một) hoặc hoàn toàn không dấu ("Le Loi"); test mới trong `tests/test_case_adaptation_checks.py`. Test thật dùng chính bộ so khớp này (thêm "Hải Phòng"), thử lại lần gọi kiểm 9router một lần với lỗi tạm thời. Chạy lại 11 file liên quan: 336 pass, 1 skip (test thật).
- [x] Sửa sau review cuối cả nhánh (một đợt): một quy tắc chung `accept_match` cho mọi chỗ tìm tên thật/tên hư cấu trong chữ (kiểm lọt tên, `_TextGuard`, đổi tên hư cấu trên màn xem lại). (1) Hai tên thật chỉ khác dấu ("Nguyễn Văn Hùng"/"Nguyễn Văn Hưng") là hai tên, mỗi tên dùng tên hư cấu của mình, thêm được qua bảng tên; chỗ viết không dấu khớp nhiều người thì thay theo thực thể đứng trước và cảnh báo (không chặn, theo quyết định của người dùng). (2) Tên dài viết sai không che tên ngắn đúng ở cùng chỗ. (3) Tên nhiều chữ phải viết hoa như tên riêng ("cuộc sống hòa bình", "Lâm đồng ý" giữ nguyên; chữ chỉ loại như "đường", "cảng" được viết thường). (4) Đổi tên hư cấu không còn sửa nhầm "Năm ấy", "Hung thủ". (5) Con số nhận dạng và dạng tên Việt trong lời Anh còn sót được ghi vào `check_warnings`; bỏ cue "no" trơn ("nợ"), giữ số tiền, số lượng. (6) Test chặn case_id thoát thư mục kiểm đúng chỗ. 12 file test: 396 pass, 1 skip (baseline 344 pass, 1 skip).
- [ ] Bước 2, test thật ngắn: `tests/test_case_adaptation_live.py` đã viết (bỏ qua nếu không có `STORY_STUDIO_LIVE=1`; gọi nhỏ trước để biết 9router sẵn sàng; chạy `dossier.txt` bằng worker; kiểm hàng việc `done`, kế hoạch không cờ, không tên thật trong lời Việt/Anh và prompt hình). Kiểm logic bằng LLM giả: qua, 11 lần gọi. **Chưa PASS với 9router thật**: 9router đang trả HTTP 503 bọc lỗi Gemini 403 ("reset after 2m"), thử 06:55, 06:59, 07:00 ngày 20/10; đổi sang `ag/gemini-3.7-flash-high` cũng 403, nên lỗi ở tài khoản Gemini (antigravity), không phải một model. Test báo ngay sau 1,7 s "9router chưa sẵn sàng (busy)" thay vì để mỗi việc chờ 15 phút. Chờ 9router: sửa tài khoản Gemini rồi chạy `STORY_STUDIO_LIVE=1 ".venv/Scripts/python.exe" -m pytest tests/test_case_adaptation_live.py -q -s`, ghi số lần gọi và thời gian chạy vào đây.
- [ ] Bước 3, chạy thật vụ Nhũ Cô: đã khôi phục bài (61.526 byte) từ Thùng rác vào `.cache/samples/nhu_co.txt` (chép ra, bản trong Thùng rác còn nguyên; `.cache/` bị `.gitignore` và build_release chặn). Chưa chạy vì 9router đang 503. Chờ 9router. Công cụ chạy sẵn, không nằm trong git: `.cache/samples/run_nhu_co.py <thư mục worktree> 8` (worker + 9router thật, ghi vào `.cache/live_projects/`, in thời gian, số việc, số lần bị loại phải gọi lại kèm lý do, số lần 9router bận, số cảnh, cảnh báo, cờ, tên thật lọt, sự việc chưa được phủ). Cần ghi vào đây: thời gian, số việc, số lần gọi lại, số cảnh, cảnh báo, có lọt tên thật không, có đủ sự kiện chính không.
- [ ] Bước 4, chạy tiếp bằng Muse (ảnh 3 cảnh `image`, 1 clip `video`, giọng VieNeu 3 cảnh, bản Anh và giọng 3 cảnh): **chờ người dùng**, chỉ làm sau khi người dùng quyết định merge và 9router chạy lại được.

# TASKS — sửa nhóm B sau khi gộp chuyển thể vụ án (2026-10-20)
- [x] Mục 1: đổi tên hư cấu trên màn xem lại còn sót dạng của ngôn ngữ kia ("Hùng" trong lời Anh khi đổi "Hùng"/"Hung" → "Dũng"/"Dung"). `case_plan_edits._swaps`: lời Anh đổi cả dạng Việt cũ, lời Việt đổi cả dạng Anh cũ ("Li Xiaolong"), trừ khi dạng Anh trùng dạng Việt lúc bỏ dấu ("Hung hăng" là chữ tiếng Việt, giữ nguyên)
- [x] Mục 2: tên ngắn khớp nhầm trong tên nước, vùng miền ("Việt Nam" → "Việt Tuấn", "Đài Loan", "miền Nam"), ở cả kiểm lọt tên thật lẫn đổi tên hư cấu. `accept_match` bỏ chỗ khớp nằm trọn trong một cụm `_PROTECTED_PHRASES` dài hơn (tên nước nhiều chữ, miền Nam/Bắc/Trung..., Nam Bộ, Tây Nguyên, "nước Đức"...); tên dài chứa cả cụm ("Nguyễn Việt Nam") vẫn bị bắt. Chưa che: tên lễ ("Trung Thu", "Quốc Khánh"), "người Việt", "tiếng Anh" (có thể là một phần tên người, che thì có thể lọt tên thật)
- [x] Mục 3: chạy server lần hai (run.bat hai lần) không được động vào hàng việc phân tích của server đang chạy. Khoá file `projects/_cases/.worker.lock` (dùng chung `runners/single_instance.try_lock_file`): server không giữ được khoá thì không chạy worker và không đưa việc `running` về `pending`. `run.py` hỏi `/api/health` trước: Story Studio đang chạy thì chỉ mở trình duyệt rồi thoát (mã 0), chương trình khác giữ cổng thì báo lỗi (mã 1). Thử thật: lần bật thứ hai thoát sau 0,7 s
- [x] Mục 5: `test_gate_gout_regressions::test_sec_04` cập nhật theo route hiện tại: tạo task với output_path ngoài sandbox bị 400; task cũ có output_path xấu thì kết quả vẫn chỉ lưu vào muse_outputs (thư mục tạm trong test)
- [x] Mục 4: giao diện tạo bản tiếng Anh. Máy chủ: mỗi dự án và ngôn ngữ chỉ một việc chạy (`case_jobs.start_job`, POST trả `already_running`), thêm `GET /api/projects/{id}/language-version-job`. Giao diện (`true_crime.js?v=1.2.0`): tải lại trang thì hỏi việc đang chạy rồi theo dõi tiếp; mỗi lần hỏi tối đa 20 s; mất kết nối ~5 phút hoặc theo dõi quá 60 phút thì thôi theo dõi và báo; nút chỉ hiện biểu tượng dưới 1536px, cả lúc bận. **Còn tồn:** thanh tiêu đề vốn đã tràn khi chưa có nút này (đo: 1366px tràn 322px, đẩy ra ngoài 9-Grid, Kịch bản AI, Lưu, Sản Xuất Video Dài; 1500px tràn 193px, mất Lưu và Sản Xuất Video Dài; 1920px vừa) — cần sắp xếp lại thanh tiêu đề, việc riêng
- [x] Chạy bộ test hồi quy 26 file + `tests/test_run_single_server.py`: 567 pass, 0 fail, 1 skip (test thật 9router), 2 phút 35 giây (trước: 534 pass, 1 fail). Server 8000 khởi động lại (giữ Fleet Runner, VieNeu), modal mở được, console sạch. Test vẫn tạo 3 thư mục `backend/static/comic_slices/` mới (22fc7cfd, 3b64bc19, 4a7cf146), chưa xoá

# TASKS — duyệt dàn ý trước khi viết cảnh (2026-10-20)
- [x] Test trước: trạng thái chờ duyệt sau dàn ý, duyệt, sửa dàn ý (kiểm lại, sinh lại việc viết cảnh), Thử lại không gỡ trạng thái chờ
- [x] Worker + bước: `review`, `edit_outline`, `approve_outline`, `revise_outline`
- [x] API: GET/PUT `/cases/{id}/outline`, POST `/cases/{id}/outline/approve`; lỗi kiểm dàn ý (400) qua `case_redact.hide_real_names`, sai trạng thái 409
- [x] Prompt viết lời Việt: logline, dàn ý mọi nhịp (đánh dấu nhịp đang viết), nhân vật đã xuất hiện ở nhịp trước (bỏ sự việc hook chỉ mượn để gợi), quy tắc 10 cài cắm/trả lời
- [x] Giao diện: màn duyệt dàn ý trong modal True Crime (`true_crime.js?v=1.3.0`, khung trong `index.html`, build lại `tailwind.css`). Thử trên server xem thử cổng 8765 (thư mục projects tạm, LLM giả): chuyển sự việc, lưu sai số cảnh thấy lý do, lưu đúng, chèn/xoá nhịp rỗng, duyệt rồi hỏi tiến độ tiếp; màn 375px không tràn ngang
- [x] Chạy test: 9 file test_case_*.py (trừ live) + test_true_crime_router.py **401 pass**; bộ offline rộng 31 file (mọi tests/test_*.py trừ e2e, live, launcher, live_browser_reality) **627 pass, 0 fail**, 3 phút 31 giây. Chưa chạy e2e và test thật 9router (chưa được yêu cầu); `test_case_adaptation_live.py` đã sửa để tự duyệt dàn ý, mới chỉ thu thập được. Lần chạy sinh 3 thư mục `backend/static/comic_slices/` mới (08139168, 2e16c2b3, 3884948e), chưa xoá
- [x] Theo đề xuất (người dùng giao 2026-10-20, chốt sau): (1) lỗi dàn ý trả bằng lời thường, mỗi lỗi một dòng (`_check_outline` dùng chung cho LLM và người dùng, `_for_user` đổi tên trường JSON); (2) sửa được "Bài đủ tư liệu cho N phút" (1..số phút đã chọn), giới hạn tổng cảnh đổi ngay trên màn duyệt (`scene_limits`), mỗi sự việc vẫn tối đa 2 cảnh; (3) giữ `tailwind.css` build mới (25 class bị bỏ không còn dùng ở đâu); (4) `tests/conftest.py` cho mọi test ghi ảnh cắt truyện tranh vào thư mục tạm, 6 thư mục rác do test tạo đã chuyển vào Thùng rác
- [x] Hồi quy sau các sửa theo đề xuất: 31 file offline 631 pass, 5 fail; cả 5 ở `tests/test_scene_analysis_fallback_reason.py` (file chưa commit của phiên khác, phiên đó đang sửa `script_splitter.py`/`api.py` đúng lúc chạy); chạy riêng file đó và `test_script_splitter_long_text.py` sau đó: 27 pass. Không sinh thư mục mới trong `comic_slices/` hay `projects/`
