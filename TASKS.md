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
- [x] Task 11: Hồi quy toàn bộ và chạy thật cả chuỗi (bước 1 xong; bước 2, 3 chờ 9router; bước 4 chờ người dùng; xem mục "Task 11" cuối file)

## Baseline trước khi sửa (Task 1, bước 1)
- Bộ offline 18 file (lệnh trong kế hoạch, Task 1): **158 pass / 1 fail**, 332 s. Worktree không có `backend/config/muse_fleet_accounts.json` và `backend/chrome_profiles/`.
- Fail sẵn: `tests/test_gate_gout_regressions.py::test_sec_04_block_arbitrary_file_overwrite_in_muse_complete` (test chờ 200, nhưng `/api/muse-bridge/tasks/create` giờ trả 400 khi `output_path` nằm ngoài projects/muse_outputs). Test cũ lệch với code đã siết, không thuộc nhiệm vụ này.
- Lần chạy sinh ra (đều bị `.gitignore` bỏ qua): `projects/proj_crime_e9e94024`, `projects/proj_crime_fa8cad63`, `backend/static/comic_slices/` (3 thư mục), `backend/static/evidence_boards/` (2 thư mục `case_*`), `backend/config/muse_fleet_accounts.json`, `backend/muse_fleet_runner.log` (rỗng). Trước khi chạy thì chưa có `projects/`, `comic_slices/`, `backend/static/comic_slices/`.
- [ ] Dọn các thư mục trên (chuyển vào Thùng rác): lệnh xoá bị chặn nên chưa dọn

## Task 11: hồi quy và chạy thật (2026-10-20)
- [x] Bước 1, hồi quy offline: 25 file (18 file của baseline + 7 file mới) **466 pass / 1 fail**, 114 s. Tách ra: 18 file cũ **182 pass / 1 fail** (baseline 158 / 1; thêm 24 test từ Task 8–10), 7 file mới **284 pass**. Lỗi duy nhất vẫn là `test_sec_04_block_arbitrary_file_overwrite_in_muse_complete` (có sẵn từ baseline), không lỗi mới. Hai lần chạy không sinh dự án mới trong `projects/`; chỉ sinh 6 thư mục `backend/static/comic_slices/{47718a76,5c5f6a47,c1495ed0,7992f93d,84dc1983,abd0033b}` (gitignored). Sáu thư mục này chưa dọn: chờ người dùng quyết định (chuyển vào Thùng rác).
- [x] Sửa sau review (vòng 1): `case_adaptation_checks` khớp tên nhiều âm tiết trên chuỗi đã bỏ dấu nên từ thường trùng tên thật ("lẻ loi" ~ "Lê Lợi", "tàn hại" ~ "Tân Hải") bị thay nhầm bằng tên hư cấu. Giờ chỉ nhận chỗ khớp viết đúng dấu như tên thật (không phân biệt hoa thường, dấu thanh kiểu cũ/mới coi như một) hoặc hoàn toàn không dấu ("Le Loi"); test mới trong `tests/test_case_adaptation_checks.py`. Test thật dùng chính bộ so khớp này (thêm "Hải Phòng"), thử lại lần gọi kiểm 9router một lần với lỗi tạm thời. Chạy lại 11 file liên quan: 336 pass, 1 skip (test thật).
- [x] Sửa sau review cuối cả nhánh (một đợt): một quy tắc chung `accept_match` cho mọi chỗ tìm tên thật/tên hư cấu trong chữ (kiểm lọt tên, `_TextGuard`, đổi tên hư cấu trên màn xem lại). (1) Hai tên thật chỉ khác dấu ("Nguyễn Văn Hùng"/"Nguyễn Văn Hưng") là hai tên, mỗi tên dùng tên hư cấu của mình, thêm được qua bảng tên; chỗ viết không dấu khớp nhiều người thì thay theo thực thể đứng trước và cảnh báo (không chặn, theo quyết định của người dùng). (2) Tên dài viết sai không che tên ngắn đúng ở cùng chỗ. (3) Tên nhiều chữ phải viết hoa như tên riêng ("cuộc sống hòa bình", "Lâm đồng ý" giữ nguyên; chữ chỉ loại như "đường", "cảng" được viết thường). (4) Đổi tên hư cấu không còn sửa nhầm "Năm ấy", "Hung thủ". (5) Con số nhận dạng và dạng tên Việt trong lời Anh còn sót được ghi vào `check_warnings`; bỏ cue "no" trơn ("nợ"), giữ số tiền, số lượng. (6) Test chặn case_id thoát thư mục kiểm đúng chỗ. 12 file test: 396 pass, 1 skip (baseline 344 pass, 1 skip).
- [x] Bước 2, test thật ngắn (**PASS 21/10 07:41–07:51**: 20 lần gọi LLM, 588 s, gọi lại sau khi bị loại 1, 9router bận 0, lỗi khác 1 đã tự thử lại; hàng việc `done`, không cờ, không lọt tên thật; log `.cache/live_runs/dossier_20261021_0741.log`). **Chạy lại 21/10 12:35–12:53: PASS**, 19 lần gọi LLM, 1.033 s, gọi lại sau khi bị loại 0, 9router bận 0, lỗi khác 0 (log `.cache/live_test_2026-10-21.log`; chạy trong thư mục chung đúng lúc một phiên khác bắt đầu sửa `case_adaptation_*`, nên không chắc tuyệt đối là code đã commit). Ghi chép cũ: `tests/test_case_adaptation_live.py` đã viết (bỏ qua nếu không có `STORY_STUDIO_LIVE=1`; gọi nhỏ trước để biết 9router sẵn sàng; chạy `dossier.txt` bằng worker; kiểm hàng việc `done`, kế hoạch không cờ, không tên thật trong lời Việt/Anh và prompt hình). Kiểm logic bằng LLM giả: qua, 11 lần gọi. **Chưa PASS với 9router thật**: 9router đang trả HTTP 503 bọc lỗi Gemini 403 ("reset after 2m"), thử 06:55, 06:59, 07:00 ngày 20/10; đổi sang `ag/gemini-3.7-flash-high` cũng 403, nên lỗi ở tài khoản Gemini (antigravity), không phải một model. Test báo ngay sau 1,7 s "9router chưa sẵn sàng (busy)" thay vì để mỗi việc chờ 15 phút. Chờ 9router: sửa tài khoản Gemini rồi chạy `STORY_STUDIO_LIVE=1 ".venv/Scripts/python.exe" -m pytest tests/test_case_adaptation_live.py -q -s`, ghi số lần gọi và thời gian chạy vào đây.
- [x] Bước 3, chạy thật vụ Nhũ Cô (**21/10 07:52–08:56, xong**: `done` sau 3.817 s = 63,6 phút; 63 việc (17 đoạn đọc, dàn ý 14 nhịp, 42 việc viết); 70 lần gọi LLM, 67 ok, 3 lần trả không phải JSON đã tự gọi lại, 9router bận 0; 8 lần bị loại phải gọi lại (3 JSON hỏng ở đọc đoạn, 1 dàn ý nhịp quá nhiều sự việc, 4 lời Việt quá 80 chữ hoặc quá nhiều sự việc một cảnh); 41 cảnh (25 ảnh, 15 bảng ghim, 1 miễn trừ, **0 video**); không cờ, không lọt tên thật; phủ đủ 178/178 sự việc; 34 tên thật đổi hư cấu, 5 chỗ tự thay tên thật trong nhãn bảng ghim; 41/71 bằng chứng không hiện trên bảng ghim cảnh nào (chỉ cảnh báo). **Lỗi độ dài:** đặt 8 phút nhưng lời Việt 2.958 chữ, lời Anh 1.931 chữ; đo giọng Edge 3 cảnh: Việt 229 chữ/phút ≈ 12,9 phút, Anh 133 chữ/phút ≈ 14,5 phút. Nguyên nhân: `TARGET_SCENES[8] = (35, 40)` cần ~12–14 s mỗi cảnh (~45–53 chữ Việt) nhưng AI viết trung bình 72 chữ vì `VI_WORDS` chỉ loại khi > 80. Log `.cache/live_runs/nhuco_20261021_0752.log`, dữ liệu `.cache/live_projects/_cases/case_7642e1b9`). **Chạy lại 21/10 12:53–13:55 trên bản xuất HEAD `21ac38e`** (`.cache/head_21ac38e`, tách khỏi code đang sửa dở): `done` sau 3.718 s = 62,0 phút; 63 việc; 66 lần gọi LLM (65 ok, 1 JSON hỏng tự gọi lại), 9router bận 0; 4 lần bị loại phải gọi lại (1 JSON hỏng ở đọc đoạn, 1 dàn ý nhịp quá nhiều sự việc, 2 lời Việt quá 80 chữ hoặc quá 5 sự việc một cảnh); thời gian dồn vào viết lời Việt (16 lần, 27 phút), dàn ý 7,7 phút, đọc đoạn 13 phút; 40 cảnh (23 ảnh, 16 bảng ghim, 1 miễn trừ, 0 video); không cờ; **không lọt tên thật** ở 270 đoạn chữ ra sản phẩm (lời Việt/Anh, prompt, tiêu đề, logline, nhãn bằng chứng, nhãn quan hệ); phủ 171/171 sự việc. **Đối chiếu 30 sự kiện chính** (subagent lập độc lập từ bài gốc, 26 cốt lõi, kèm cách gây án và phi tang): đủ 30/30 ở cả lần sáng lẫn lần này, cách gây án và phi tang giữ nguyên từng bước. Cùng lỗi độ dài: lời Việt 2.745 chữ ≈ 12 phút, Anh 1.879 chữ ≈ 14 phút (theo tốc độ Edge đo ở trên). Lỗi nhỏ: cảnh 37 khẳng định quần áo nữ dưới đất "chỉ là đồ cũ bị vứt bỏ từ trước" trong khi bài nói chưa có lời giải; "Đông Nam Á" bị đặt tên hư cấu ("Khu vực Bách Đảo"); còn tên tháng ("giữa tháng mười"); nhãn bằng chứng evd_33 còn "2 tháng 8"/"August 2" (không hiện trên bảng ghim nào lần này, trình kiểm chỉ cảnh báo); 39/71 bằng chứng không hiện trên bảng ghim. Mô tả bằng chứng (dữ liệu nội bộ, không vào dự án hay video) vẫn chứa tên thật và ngày tháng ở 38 mục: đúng thiết kế. Dữ liệu `.cache/live_projects_2026-10-21/_cases/case_a1379b43`, log `.cache/nhu_co_run_2026-10-21.log`. Ghi chép cũ: đã khôi phục bài (61.526 byte) từ Thùng rác vào `.cache/samples/nhu_co.txt` (chép ra, bản trong Thùng rác còn nguyên; `.cache/` bị `.gitignore` và build_release chặn). Chưa chạy vì 9router đang 503. Chờ 9router. Công cụ chạy sẵn, không nằm trong git: `.cache/samples/run_nhu_co.py <thư mục worktree> 8` (worker + 9router thật, ghi vào `.cache/live_projects/`, in thời gian, số việc, số lần bị loại phải gọi lại kèm lý do, số lần 9router bận, số cảnh, cảnh báo, cờ, tên thật lọt, sự việc chưa được phủ). Cần ghi vào đây: thời gian, số việc, số lần gọi lại, số cảnh, cảnh báo, có lọt tên thật không, có đủ sự kiện chính không.
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

# TASKS — chốt trạng thái trước khi test luồng (2026-10-21)
- [x] Đối chiếu 23 file chưa commit với 4 phiên con: duyệt dàn ý true-crime; chia bài dài thành nhiều phần (script_splitter, api.py, config, .env.example, schemas, toast app.js, 2 file test mới); thanh tiêu đề 1280–1700px (index.html, app.js, tailwind.css); trạng thái Muse chỉ báo "Chưa kết nối" sau 3 lần lỗi (app.js)
- [x] Bộ offline 31 file: **638 pass, 0 fail**, 15 phút (lâu vì 9router đã chạy lại nên vài test vox/chia cảnh gọi LLM thật). Không sinh dự án hay comic_slices mới
- [x] 9router chạy lại: `ag/gemini-3.8-flash-low` và `-high` đều trả 200 (lỗi 503/403 ngày 20/10 đã hết)
- [x] Khởi động lại server 8000 (đang chạy `script_splitter.py` cũ); giữ Fleet Runner; log ở `.cache/server_8000.*.log`. Trang chính và modal Hồ Sơ Kỳ Án mở được, console sạch; 1366px thanh tiêu đề không tràn
- [x] Chép mẫu Nhũ Cô từ worktree cũ sang `.cache/samples/` (nhu_co.txt, run_nhu_co.py, probe_9router.py); `run_nhu_co.py` tự duyệt dàn ý khi vụ dừng ở `review`
- [x] Commit 4 nhóm theo phiên (người dùng duyệt 21/10): `ba3fd73` duyệt dàn ý, `128072e` chia bài dài, `06e2fa5` thanh tiêu đề, `21ac38e` trạng thái Muse. Mã trong 4 commit đúng bản đã chạy 638 test
- [x] 07:37 app Claude mở lại làm tắt server 8000, Fleet Runner, VieNeu và 9router (lượt test thật đầu chết giữa chừng, không có log). Bật lại 9router nền `--tray -H 127.0.0.1 -p 20128` (mặc định của 9router là 0.0.0.0, mở ra LAN), server 8000 tự bật Fleet Runner; test thật chạy tách tiến trình, log ở `.cache/live_runs/`
- [x] Task 11 bước 2–3 chạy thật xong (xem mục Task 11): bản ngắn PASS 10 phút; Nhũ Cô xong 63,6 phút, sạch tên thật, nhưng video dài ~13–14,5 phút thay vì 8
- [x] Sửa độ dài lời kể true-crime cho khớp số phút đã chọn (xong 21/10, xem mục "kể cuốn" bên dưới: Nhũ Cô 8 phút còn ~8,3–8,8 phút)
- [ ] Task 11 bước 4 (Muse ảnh/video, giọng, bản Anh): kế hoạch Nhũ Cô có 0 cảnh video nên chưa thử được clip Muse từ luồng này
- [ ] Dọn (chờ người dùng): worktree `.claude/worktrees/true-crime-adaptation` (39 MB, đã gộp), `.cache/commit_check_nhom_b` (9,5 MB), `output/board_samples` (6,6 MB), `dist/` bản 19/10, các dự án thử cũ trong `projects/`
- Lưu ý: cổng VieNeu 5005 hiện do server VieNeu của douyin-movie-studio giữ; story-studio dùng chung server đó

# TASKS — kể cuốn, không bịa lời, đúng thời lượng (2026-10-21, người dùng duyệt)
- [x] Bước mới G4b `dedupe_events` (sau đặt tên hư cấu, trước dàn ý): gộp sự việc bài kể hai lần vào sự việc đầy đủ nhất, giữ đoạn gốc của bản bị gộp (`extra_chunk_indices`); gộp tối đa một nửa; vụ cũ không có bước này vẫn chạy
- [x] Dàn ý kể cuốn: thứ tự kể không bắt buộc theo thời gian (mở bằng lúc phát hiện rồi quay ngược); `dropped` bỏ tối đa 1/3 sự việc vụn kèm lý do, cấm bỏ sự việc then chốt; người dùng bỏ/đưa lại tuỳ ý trên màn duyệt (mục "Bỏ khỏi video")
- [x] Cuối mỗi nhịp (trừ nhịp cuối) là câu hỏi bỏ ngỏ dẫn sang nhịp sau, khác kiểu câu hỏi nhịp trước (không mở bằng "Liệu"); bản Anh giữ câu hỏi đó (lỗi nhẹ: gọi lại, hết lượt vẫn nhận)
- [x] Bỏ "lời thoại dựng lại" và "nội tâm": lời trích trong ngoặc kép phải có nguyên văn trong bài; không có thì gọi lại, hết lượt thì cảnh báo ở màn xem lại (`find_unsourced_quotes`)
- [x] Độ dài lời kể theo thời lượng (sửa lỗi 8 phút ra 13–14,5 phút): `word_budget` tính số chữ mỗi cảnh từ số giây mỗi cảnh và tốc độ đọc đã đo (Việt 229, Anh 133 chữ/phút; VieNeu đo thêm 218). 8 phút: Việt nhắm 37–46, nhận 22–51; Anh nhắm 21–27, nhận 13–30. Bản tiếng Anh viết lại cảnh đã sửa cũng theo thời lượng của kế hoạch
- [x] Bước lọc trùng chờ 600 s (thật: 177 sự việc thì 240 s không đủ, hỏng 3 lần), mỗi dòng sự việc gửi đi rút còn 220 ký tự
- [x] Chạy thật vụ Nhũ Cô 8 phút qua trình duyệt (server 8000, 9router thật, case_b7c70756): 17 đoạn, lọc trùng gộp 7 (177 → 170), dàn ý 13 nhịp 39 cảnh, bỏ 56 chi tiết vụn (thủ tục, tin đồn, cáo trạng kể lại; mốc then chốt giữ đủ); viết 13 nhịp 37 phút, không cờ, không lời trích bịa, 115/115 sự việc giữ lại đều được kể; lời Việt 2.013 chữ (~8,8 phút), lời Anh 1.098 chữ (~8,3 phút); 12/12 nhịp giữa kết bằng câu hỏi. Sau đó siết giới hạn chữ và đổi kiểu câu hỏi (kiểm lại 3 nhịp bằng 9router thật: hết "Liệu", 45–52 chữ)
- [x] Bấm thử trên trình duyệt: 3 nút mẫu, Phân tích hồ sơ, Đóng/X/Esc, Thử lại; màn duyệt dàn ý: đưa lại/bỏ sự việc, chuyển nhịp, đổi loại nhịp, số cảnh, số phút tư liệu, chèn/xoá nhịp, Bỏ thay đổi, Lưu (lỗi và đúng), Duyệt và viết cảnh; màn xem lại: đổi tên + Lưu tên đã sửa, Thêm tên (trống và đủ), sửa lời kể (cảnh báo lời trích hiện ra), bảng ghim tới cảnh N, nhãn Việt/Anh, Tạo dự án bản Việt, Phân tích vụ khác; Bảng Đạo Diễn: Voice cảnh 2 (VieNeu 14,6 s cho 53 chữ), Lưu dự án, Tạo bản tiếng Anh (cảnh đã sửa viết lại 27 chữ). Console không có lỗi JS. Dự án thử: `proj_crime_f9c7c101` (Việt), `proj_crime_5aec9b3a` (Anh)
- [x] Test: 419 pass ở 10 file true-crime (thêm 17 test); bộ offline 32 file (mọi tests/test_*.py trừ e2e, live, launcher, live_browser_reality): **664 pass, 0 fail**, 6 phút 17 giây
- [x] Hai bản sửa độ dài trùng nhau (phiên này trên nhánh `do-dai-loi-ke`; phiên "Logic nhận thông tin" ở `8e31159`): người dùng chọn giữ bản master và thêm hai phần còn thiếu, `d13ec7b`: số giây mỗi cảnh = min(mức bảng, số phút ÷ số cảnh thật của dàn ý, theo số phút tư liệu nếu ít hơn), cả khi viết lại lời Anh; check_plan cảnh báo khi bản Việt/Anh đọc lâu hơn số phút đã chọn quá 15%. 422 test true-crime + 667 test offline (32 file) qua. Nhánh và worktree `do-dai-loi-ke` đã xoá, 2 commit cũ xuất ra `.cache/patches/`
- [x] Đo thật Nhũ Cô 8 phút trên `d13ec7b` (case_7dcf6158, 90,5 phút chạy, 61 lần gọi LLM, 3 lần bị loại): 41 cảnh, lời Việt 1.740 chữ ≈ 7,6 phút, lời Anh 984 từ ≈ 7,4 phút (229/133 từ mỗi phút); không cờ, không lọt tên thật; 57/172 sự việc bị dàn ý bỏ có chủ ý, còn lại đều được kể. So sánh: gốc 12,9/14,5 phút; nhánh vòng 1 10,3/10,2; nhánh vòng 2 8,4/8,5. Phiên "Logic nhận thông tin" thu giọng thật VieNeu + Edge trên vụ này để đo thời lượng thật
- [x] Kiểm chứng độc lập (phiên "Logic nhận thông tin", 21/10 tối) trên kế hoạch case_7dcf6158: 40 cảnh lời kể + 1 miễn trừ, 12 nhịp; lọc trùng gộp 5 (172 sự việc), dàn ý bỏ 57 chi tiết vụn; 11/11 nhịp giữa kết bằng câu hỏi ở cả bản Việt lẫn Anh, 0 câu mở bằng "Liệu"; không lời trích bịa, không lọt tên thật, không cờ chặn; 115/115 sự việc giữ lại đều được kể. **Thu giọng thật toàn bộ 41 cảnh**: bản Việt VieNeu Mai Anh **7,54 phút**, bản Anh Edge Andrew **7,43 phút**, không cảnh nào hỏng (kế hoạch cũ case_b7c70756 trước khi siết: 8,83 / 8,41 phút; gốc 12,9 / 14,5)
- [x] Lỗi tìm ra khi kiểm chứng: nhãn bằng chứng evd_35 chứa "ngày 28 tháng 2" / "February 28" (lần này không lên bảng ghim, nhưng vụ khác có thể hiện ngày thật trên hình, màn xem lại không sửa được nhãn). Sửa: `check_plan` tự bỏ ngày cụ thể khỏi tên tập và nhãn bằng chứng/quan hệ (`strip_dates`, ghi vào `warnings`; nhãn chỉ có ngày thì giữ và cảnh báo); prompt đọc bài dặn không ghi ngày trong nhãn. Kiểm lại trên kế hoạch thật: nhãn còn "Biên bản đối chất", lời kể không đổi
- [x] Test: 32 file offline 667 pass + 1 test cần Edge-TTS thật (`test_adversarial_produce_long_video_pipeline`) hỏng vì dịch vụ Microsoft trả "No audio", chạy lại riêng thì qua
- [x] Dọn: 2 dự án thử và case_b7c70756 (từ lần bấm thử giao diện) đã chuyển vào Thùng rác

# Dự án mẫu true-crime — GIỮ, KHÔNG DỌN (2026-10-21)
- Vụ `case_7dcf6158` (Nhũ Cô, video 8 phút, phân tích bằng `d13ec7b`) trong `projects/_cases/`, cùng hai dự án dựng từ vụ này:
  `proj_crime_52c3a5e8` "MẪU — Lời Nhắn Từ Đỉnh Vọng Nguyệt (bản Việt, không xoá)" (giọng vieneu-MaiAnh) và
  `proj_crime_8329b12d` "MẪU — Whispers from Wangyue Peak (English, do not delete)" (en-US-AndrewMultilingualNeural).
  Mở ở danh sách dự án hoặc `http://localhost:8000/?project_id=proj_crime_52c3a5e8`. Dọn dữ liệu thử thì bỏ qua 3 mục này
- Có sẵn: 41 cảnh, lời Việt/Anh, prompt ảnh, 16 bảng ghim + 1 thẻ miễn trừ (vẽ trên máy). Chưa chạy Muse theo yêu cầu người
  dùng: 24 cảnh ảnh còn trống, chưa có giọng, chưa có video. Đo giọng thật trên kế hoạch này: Việt 7,54 phút, Anh 7,43 phút
- [x] Worktree cũ `.claude/worktrees/true-crime-adaptation` (đã gộp, code 20/10, có bản sao `.env`) chuyển vào Thùng rác; nhánh
  `worktree-true-crime-adaptation` đã xoá; ghi chú quy trình chép sang `.superpowers/` (git bỏ qua). Git chỉ còn nhánh master

# TASKS — dọn dẹp sau rà soát (2026-10-21, người dùng duyệt C1–C11, T1–T3, T4a; nhánh `don-dep-sau-ra-soat`)
Giữ: T4b (8 dự án thử 4–16/10), "ZZ Thử Muse", 3 mục MẪU. Mỗi mục một commit, chạy test liên quan sau mỗi commit.
- [x] Test mốc: bộ offline (`pytest tests --ignore-glob=*e2e* --ignore-glob=*live* --ignore=tests/test_launcher.py`): **668 pass, 0 fail**, 8 phút 35 giây; không sinh dự án mới
- [x] C1 xoá `services/nhu_co_case_scenes.py`
- [x] C2 xoá màn Render Video giả (không mở được)
- [x] C3 xoá hàm JS chết, bỏ gắn sự kiện bước hai lần
- [x] C4 Python: import thừa `api.py`, re-export `models/__init__`, nhánh trỏ douyin, `generate_ai_video_segment` giả, comment sai
- [x] C5 xoá ảnh `style_*.jpg` và `.srt` mẫu giọng không dùng
- [x] C6 xoá `test_live_browser_reality.py`, `test_launcher.py`
- [x] C7 bỏ `run_all_tests.py`, sửa lệnh test trong README/AGENTS.md
- [x] C8 bỏ CLI `run_studio.py`/`.bat`, 2 hàm chỉ CLI dùng, typer/rich
- [x] C9 xoá endpoint không ai gọi kể cả test (đúng danh sách đã duyệt; `/upload-reference-image`, `/auto-gen`, `muse-cloud/generate-all-*` cũng không còn ai gọi nhưng chưa xoá vì ngoài danh sách)
- [x] C10 xoá `docs/technical_report_openrouter_veo3_and_vox_workflow.md`
- [x] C11 `.bat` Muse: bỏ nhánh trỏ đường dẫn cũ
- [x] T1–T3, T4a chuyển vào Thùng rác: 24 thư mục comic_slices, 2 evidence_boards, `output/`, `public/`, `dist/`, 4 dự án Nhũ Cô cũ (33 mục)
- [x] Cuối đợt: bộ offline (`pytest tests -q --ignore-glob="*e2e*" --ignore-glob="*live*"`) **667 pass, 0 fail**, 7 phút (mốc 668 trừ 1 test của hàm đã xoá); không sinh dự án hay comic_slices mới. Giao diện trên server thử cổng 8010 (`.claude/launch.json`, tắt worker và Fleet Runner tự bật): 4 bước chuyển đúng, 7 cửa sổ chính mở/đóng được, console không lỗi, không có 404/500, bấm Bước 4 chỉ gọi `/seo-pack` một lần; 3 `project.json` (ZZ Thử Muse, 2 MẪU) không bị ghi
- Còn lại, chưa làm vì ngoài danh sách: endpoint `/upload-reference-image`, `/auto-gen`, `muse-cloud/generate-all-images|videos` không còn ai gọi; hàm chỉ test dùng: `grid_slicer.slice_grid_image`, `generate_parallax_layers`, `audio_engine.mix_3layer_audio`; `generate_voiced_scene_audio` không ai dùng; `muse_bridge.py` còn import thừa `re`, `JSONResponse`; `config.DEFAULT_RESOLUTION` không ai dùng

# TASKS — CLAUDE.md và FEATURE_MAP.md (2026-10-21, bước 3, nhánh `tai-lieu-agent`)
- [x] FEATURE_MAP.md: điều kiện ban đầu, cách mở app/server thử, từng màn và cửa sổ (id, hàm, endpoint, chỗ tốn quota), 5 luồng xuyên suốt, chức năng chỉ có API, tiến trình nền, test theo tính năng. Kiểm bằng script: 205 id, 109 hàm, 93 endpoint, 65 đường dẫn đều có thật trong code
- [x] CLAUDE.md: mục đích (để trống cho chủ dự án), nguyên tắc nguyên văn (Dune, tư duy, tra FEATURE_MAP), lệnh, kiến trúc hiện tại, 14 đường cấm (đề xuất, chưa duyệt), quy tắc làm việc (nguyên văn + đề xuất làm dày), bảng định tuyến (cột quy trình để trống). Nguyên văn kiểm khớp từng chữ với tin nhắn của chủ dự án
- [x] AGENTS.md chỉ còn trỏ sang CLAUDE.md (nội dung cũ đã gộp vào CLAUDE.md mục 3 và 6)
- [x] `.claude/launch.json`: server thử cổng 8010 tắt hàng việc phân tích và tự bật Fleet Runner
- [ ] Chủ dự án: viết mục 1 (mục đích), duyệt mục 5 (đường cấm) và phần làm dày ở mục 6, điền cột quy trình mục 7

# TASKS — bộ kiểm tra tự động (2026-10-21, bước 4, người dùng duyệt cả gói; nhánh `kiem-tra-tu-dong` tách từ `tai-lieu-agent`)
- [x] `pytest.ini` + cờ `live` (mặc định bỏ qua), chặn mạng/dịch vụ thật trong test không gắn cờ, báo dự án rác sau khi chạy. Chạy thử có chốt chặn lộ đúng 12 test gọi Edge-TTS/9router/VieNeu (khớp dự đoán lúc rà soát): đã gắn cờ `live`, cùng 3 file e2e/live → 19 test `live`
- [x] `tests/test_architecture.py`: đường cấm kiểm được bằng máy, chỗ vi phạm cũ ghi thành ngoại lệ hẹp
- [x] `tests/test_feature_map.py`: id, hàm, endpoint, file trong FEATURE_MAP.md và CLAUDE.md phải có thật
- [x] Ruff 0.17.1 (ghim trong `requirements-dev.txt`), `ruff.toml`; 193 lỗi cũ ghi vào mốc `tools/ruff_baseline.json` (122 import thừa, 35 try/except pass, 22 gọi chặn trong async…), không sửa code cũ
- [x] `tools/check.py` (nhanh / đầy đủ) + hook trước commit (đã cài ở `.git/hooks/pre-commit`; nhánh chưa có `tools/check.py` thì hook bỏ qua)
- [x] Cập nhật CLAUDE.md, README, FEATURE_MAP theo lệnh mới
- [x] Bằng chứng (22/10/2026): `tools/check.py --full` **ĐẠT**, 3 phút: Ruff 0 lỗi mới, 2 file JS đúng cú pháp, 10 test kiến trúc/FEATURE_MAP, **672 test mặc định đạt, 0 lỗi** (2 phút 47 giây; trước đây 7–9 phút vì gọi dịch vụ thật); không có dự án rác. Thử ngược: test kiến trúc bắt được 4 nút bước gắn sự kiện hai lần trên code trước đợt dọn và bắt vi phạm giả; hook chặn commit có lỗi Ruff mới (HEAD không đổi). Chưa chạy lại 19 test `live` (tốn quota, cần mạng)

# TASKS — sửa lỗi và dọn nốt sau rà soát (2026-10-22, người dùng: "làm nốt", nhánh `sua-loi-sau-ra-soat`)
Không đụng phần nguyên văn của chủ dự án trong CLAUDE.md (mục đích, duyệt đường cấm, quy trình).
- [x] Mốc: 19 test `live` trên master (STORY_STUDIO_LIVE=1): **18 đạt, 1 lỗi** trong 25 phút 40 giây. Lỗi là `test_dossier_through_real_9router`: 9router không trả lời câu ping trong 60 giây. Không để lại dự án rác
- [x] Lỗi mất dự án: project.json hỏng → `ProjectUnreadableError` (API 409), không ghi đè thành dự án rỗng; ghi an toàn qua `services/safe_files.py` (dùng chung với case_store); mọi chỗ ghi qua `project_service.save_project()`. Test `tests/test_project_service_safety.py`: 7 lỗi trên code cũ → 8 đạt
- [x] Fleet Runner: bật tự động chỉ ở `runners/autostart.py`; `run.py` tôn trọng `STORY_STUDIO_DISABLE_FLEET_AUTOSTART`; runner gọi về đúng cổng (`--url`). `tests/test_fleet_autostart.py`: 2 lỗi trên code cũ → 4 đạt
- [x] Test không ghi vào `projects/` thật: đổi `PROJECTS_DIR`/`COMIC_SLICES_DIR` ở mọi module; `tests/test_test_isolation.py`. `test_api` chạy 2 giây thay vì vài chục giây
- [x] Thành công giả: `get_audio_duration()` báo `MediaDurationError` thay vì đoán 3 giây; nhập truyện tranh chép ảnh lỗi thì đánh dấu "Lỗi ảnh" (`tests/test_comic_import_errors.py`), giao diện cảnh báo
- [x] Thông báo chèn chữ chưa lọc: 21 chỗ + thư viện Muse; `escapeHtml()` nhận mọi kiểu; luật máy kiểm (đường cấm 9) bắt đủ 20 chỗ trên code cũ
- [x] Kiểm đường dẫn: `complete_task()` dùng `is_within` (test `proj_a`/`proj_ab` lỗi trên code cũ → đạt); `project_service` dùng `security.is_safe_id`
- [x] Biến môi trường gom về `config.py` (còn 3 file tiến trình riêng có lý do); `.env.example` thêm 8 biến (luật máy kiểm bắt đủ 8 trên file cũ); `DEFAULT_VOICE` có tác dụng (`.env` hiện trùng mặc định nên máy này không đổi giọng)
- [x] Code chết: 6 endpoint (auto-gen, Muse tạo hết ảnh/video, upload-reference-image, grid-slicer/compose-prompt), `grid_slicer.py`, 4 hàm âm thanh, 3 model yêu cầu; bỏ 6 test của phần đã xoá
- [x] Ruff: bỏ import/biến thừa, f-string thừa, chuỗi thoát sai; mốc 193 → 57 (còn `except: pass`, gọi chặn trong async, 3 báo nhầm fixture)
- [x] Cắt truyện tranh (OpenCV) và vẽ thumbnail (PIL) chạy ở luồng phụ
- [x] Giao diện (server thử 8010, dự án ZZ Thử Muse): thông báo có mã HTML hiện dạng chữ, không chạy; thư viện Muse tải đủ 8 ảnh + 7 video; dữ liệu nút "Gắn" đọc đúng đường dẫn; danh sách dự án 12 mục; 15 giây không request lỗi; 3 `project.json` mẫu/thử không bị ghi
- [x] Test `live` không cần 9router (Edge-TTS, VieNeu, dựng video, e2e): **11/11 đạt** trên code mới
- [x] Review độc lập (agent Code Reviewer, chỉ đọc) trên toàn nhánh: không có lỗi nặng; sửa đủ 5 điểm nhỏ: lỗi Muse bị mã hoá hai lần; thumbnail ghi tạm rồi đổi tên (lỗi mới do chuyển sang luồng phụ); ghép video xong mà không đo được thời lượng vẫn thành công; `scenes` sai kiểu không làm sập danh sách dự án; `safe_files` fsync trước khi đổi tên. Thư mục tạm của test chuyển sang `.cache/pytest-tmp` (ổ C gần đầy)
- [x] Kiểm cuối trên nhánh: `tools/check.py --full` **ĐẠT** — Ruff 0 lỗi mới (mốc 57), 12 test kiến trúc/FEATURE_MAP, **691 test mặc định đạt** (2 phút 40 giây)
- [x] Sau khi người dùng bật lại 9router (ping 4,5 s): cả 19 test `live` trên master (a2d1da7) **19/19 đạt**, 20 phút. Test phân tích vụ án thật: 23 lần gọi LLM, 953 s, gọi lại 0, 9router bận 0, lỗi khác 0. Test Nanahoshi 5–7 s mỗi test (lần mốc lúc 9router treo: 300 s). Không để lại dự án rác
- Còn lại có chủ đích (cần chủ dự án quyết hoặc kiểm thật với 9router/Muse): gom 3 client LLM về `case_adaptation_llm` (đường cấm 5); tách hàng việc Muse khỏi `routers/` (đường cấm 13); Muse lỗi rơi sang 9router tính tiền (đường cấm 4); xoá vĩnh viễn ở `delete_project`/`clear_all_gallery` (đường cấm 12); 31 chỗ `except: pass`

# Đối chiếu 4 ý của yêu cầu ban đầu (2026-10-22)
- [x] Ý 1, báo cáo rà soát trước khi sửa: đã gửi (cấu trúc, rác/trùng/chết, chỗ mỗi nơi một kiểu, lệnh test/lint/build, rủi ro khi agent tự làm)
- [x] Ý 2, dọn theo danh sách duyệt: 11 commit C1–C11 (`e7b7a0d`…`f814867`) + 33 thư mục vào Thùng rác; test mốc 668 đạt, sau dọn 667 đạt
- [x] Ý 3, CLAUDE.md (7 mục, 4 đoạn nguyên văn khớp từng chữ, 14 đường cấm, bảng định tuyến cột quy trình để trống) + FEATURE_MAP.md (test đối chiếu tên với code đạt)
- [x] Ý 4, bộ kiểm tra tự động: `pytest.ini` + cờ `live`, test kiến trúc, test FEATURE_MAP, Ruff 0.17.1 ghim, `tools/check.py` + hook trước commit; `check.py --full` trên master đạt (691 test)
- [x] Dòng "story-studio chưa có git" trong `D:\25. OPC\OP_CTOOL\AGENTS.md` (ngoài dự án) sửa thành "có git riêng từ 19/10/2026" theo đồng ý của người dùng; bản cũ sao lưu trong scratchpad phiên
- [x] Mục 1 CLAUDE.md: ghi nguyên văn mục đích của chủ dự án (22/10/2026, kiểm khớp từng chữ) + bảng 1.1 đối chiếu với code (đề xuất của agent, chưa duyệt)
- [x] Mục 1 CLAUDE.md: ghi nguyên văn "Mức tối thiểu là 15 phút" (22/10/2026); bảng 1.1 thêm khoảng cách: true-crime còn lựa chọn 8 phút, truyện chữ chưa báo khi video dưới 15 phút
- [x] Mục 1.2 CLAUDE.md: 7 câu trả lời của chủ dự án về quy trình (remake, dưới 15 phút, Anh + Việt, từng bước trước 1-Click, ảnh chuyển động + video 5/10 giây, tự đăng YouTube, giữ 8 phút), kiểm khớp từng chữ bằng script; bảng 1.1 cập nhật theo (thêm dòng bản Anh cho truyện chữ, dòng video 5/10 giây: nút Muse Video đang cố định 5 giây)
- [x] Mục 1.2 thêm câu 8 (remake cho dài ra = thêm nhận xét ngoài lề, ưu tiên gộp chương), kiểm khớp từng chữ; mục 1.3 ghi sơ đồ quy trình làm video dạng chữ, chủ dự án xác nhận tạm "Tạm thời là đúng ý tôi rồi"
- [x] Chủ dự án duyệt mục 5, 6, cột "Nhận biết" mục 7 (kèm điều kiện phân loại khoá cứng/mềm), gộp nhánh; quy tắc "vi phạm từ 3 lần thì thành khoá cứng" ghi nguyên văn ở mục 2.4; câu 9 mục 1.2 (gói SEO YouTube dựa trên repo/chuẩn có sẵn, không thuần AI). Kiểm khớp từng chữ bằng script
- [ ] Bảng 1.1: chủ dự án mới góp ý dòng kênh YouTube, chưa nói duyệt cả bảng; cột quy trình mục 7 chủ dự án điền sau

# Khoá cứng / khoá mềm (2026-10-22, nhánh `khoa-cung-mem`, theo CLAUDE.md mục 2.4)
- [x] Đếm số lần vi phạm từng quy tắc bằng lịch sử git (reflog `master`, định dạng commit, file gốc đã xoá) và quét code (lệnh xoá, except trả rỗng, chữ chèn vào HTML)
- [x] Bảng 5.1 (14 đường cấm) và 6.1 (12 quy tắc làm việc) ghi khoá cứng/mềm, lệnh kiểm, số lần vi phạm, bằng chứng; mục 7 ghi là khoá mềm
- [x] Khoá cứng mới: đường cấm 2 (except trả rỗng không log), 3 (link media mẫu, hàm chỉ có pass), 9 (chữ chưa lọc trong khuôn HTML), 12 (lệnh xoá file mới) trong `tests/test_architecture.py`; quy tắc 6.1 dòng 1 (commit thẳng master) và 10 (định dạng commit) bằng hook git trong `tools/check.py`; dòng 11 (script ở gốc) trong `tests/test_working_rules.py`; chính quy tắc "từ 3 lần là cứng" trong `tests/test_guardrail_policy.py`
- [x] Thử phá từng khoá rồi hoàn lại: 6/6 bị chặn (điều 4 tăng lên 3 lần mà vẫn mềm; script ở gốc; lệnh xoá mới; chữ chưa lọc trong HTML; except trả None; link BigBuckBunny)

# Gói SEO YouTube (2026-10-22, nhánh `goi-seo-youtube`, câu 9 mục 1.2 CLAUDE.md)
Chủ dự án bỏ qua phần hỏi thiết kế: "cứ làm theo hướng bạn đề xuất đi. không ổn tôi sẽ chỉnh sau". Hướng: luật chính thức YouTube làm khoá cứng; từ khoá từ dữ liệu thật (gợi ý tìm kiếm YouTube khi bấm, YouTube Data API khi có key, dán tay); AI chỉ viết câu trong khuôn từ khoá đã chọn; thumbnail font đủ dấu.
- [x] `services/youtube_seo_rules.py`: luật tiêu đề, mô tả, tags, hashtag, chương, thumbnail (+ test)
- [x] `services/youtube_keywords.py`: gợi ý tìm kiếm, YouTube Data API (`YOUTUBE_API_KEY`), dán tay; dữ liệu quá 30 ngày thì bỏ (+ test bằng mạng giả)
- [x] `services/youtube_seo_pack.py`: chương theo thời gian video thật, AI viết câu qua `ask_validated` của luồng vụ án, lưu vào dự án (+ test LLM giả)
- [x] `routers/youtube_seo.py`: xem, tìm từ khoá, tạo gói, sửa (kiểm lại), tải .txt
- [x] Thumbnail: font Segoe UI Black (đủ 109/109 chữ có dấu; Impact thiếu 80), bỏ emoji và "FULL MOVIE", tự xuống dòng, ≤2 MB; bỏ đường dẫn cứng C:\Windows\Fonts (đường cấm 14)
- [x] Bỏ gói SEO cũ (khuôn giật tít, câu sai sự thật "9-Grid Spec 8K", hashtag mất dấu)
- [x] Giao diện Bước 4 (`youtube_seo.js` riêng), FEATURE_MAP, test kiến trúc quét cả file JS mới
- [x] Kiểm chứng:
  - test mới: 42 (luật, từ khoá với mạng giả, ghép gói với LLM giả, API, thumbnail); `tools/check.py --full` đạt 756 test (trước là 714)
  - gọi thật trong thư mục tạm `.cache/live_seo` (bản sao 2 dự án MẪU, thời lượng cảnh chia theo số chữ từ số đo giọng thật 7,54/7,43 phút): gợi ý tìm kiếm YouTube trả 10 từ khoá mỗi ngôn ngữ (0,2–0,3 s); 9router viết gói Việt 18,6 s, Anh 22,4 s, mỗi gói 1 lần gọi, đạt 18/18 luật ngay lần đầu, có 3 chương và câu miễn trừ vụ án
  - xem ảnh thật: chữ có dấu đủ; phát hiện và sửa 2 lỗi: thumbnail lấy thẻ miễn trừ (ảnh chữ) làm nền; vệt sáng ở góc trái dưới do lớp tối phía dưới xoá lớp tối bên trái (lỗi có từ code cũ)
  - bấm thật giao diện server thử 8010 với `proj_ea5b04db`: Tìm từ khoá (10 gợi ý thật), tích 3 từ khoá, Tạo gói SEO (9router thật, 1 lần gọi, đạt 15/15 luật; video 21 giây nên không có chương), sửa tiêu đề có emoji và viết HOA thì bị chặn kèm 2 lý do, bấm tải khi chưa lưu thì bị nhắc, lưu lại thì tải .txt đúng nội dung; thumbnail có emoji báo lỗi rõ, để trống thì lấy chữ của gói SEO. Console chỉ có 2 lỗi 422 do cố tình làm sai; log server không có 500; danh sách `projects/` không đổi
- [ ] Chưa kiểm chứng: nguồn YouTube Data API (chưa có `YOUTUBE_API_KEY`); chương trên một video thật dài trên 15 phút (chưa có dự án nào đã dựng video dài); YouTube có đọc đúng mốc H:MM:SS sau 60 phút không
- [ ] Để sau (chờ chủ dự án): nguồn YouTube Analytics (từ khoá người xem thật sự gõ để tìm ra kênh, cần đăng nhập Google của kênh); xem lại pháp lý trước khi đưa gợi ý tìm kiếm YouTube vào bản bán

# Bộ việc mẫu chuẩn (2026-10-23, nhánh `bo-viec-mau`)
Chủ dự án giao: kiểm tra 10 skill ở `claude-skills-mau`, tạo bộ 3–5 việc mẫu có đáp án rõ, "Từ nay, mỗi lần sửa skill hoặc agent, phải chạy lại bộ việc mẫu này và báo cáo điểm trước/sau", bảng đối chiếu skill với expert agency-agents, phương án số agent.
- [x] Chọn 5 việc từ lỗi thật đã sửa trong git (T1 Muse/kiểm đường dẫn, T2 giọng đọc/thành công giả, T3 giao diện, T4 pipeline LLM vụ án, T5 thumbnail + FEATURE_MAP); đề bài, test ẩn bổ sung (7), `docs/bo-viec-mau/`
- [x] Công cụ `tools/bo_viec_mau.py` (chuan-bi, cham, so-sanh, tinh-dap-an) + `tests/test_bo_viec_mau.py` (10 test)
- [x] Đáp án: `tinh-dap-an` cả 5 việc tự kiểm ĐẠT (bản gốc 0 điểm, đáp án 9/9 điểm máy), 0 test chập chờn
- [x] CLAUDE.md: nguyên văn quy tắc chủ dự án (mục 6), bảng 6.1 dòng 13 (khoá mềm), lệnh ở mục 3
- [x] Đo điểm gốc với agent thật (`general-purpose`, Opus 5.5, chưa cài skill; giám khảo Sonnet): **50/50**. Lần chạy làm lộ 2 lỗi chấm oan của máy chấm, đã sửa (T1 8 → 10, T3 7,33 → 10, lý do trong README mục 5). Chi phí: người làm bài khoảng 1,2 triệu token, 75 phút; giám khảo khoảng 0,6 triệu token
- [x] `tools/check.py --full`: 766 test đạt, 2 phút 40 giây (sau cả 2 lần sửa máy chấm)
- [ ] Chờ chủ dự án quyết: bộ đang chạm trần (50/50) nên chỉ bắt được tụt điểm, chưa đo được tiến bộ; có thêm việc khó hơn không

# Skill và agent dự án, phương án 3 agent (2026-10-23, nhánh `skill-agent-du-an`)
Chủ dự án giao: "Thiết kế và cài bộ skill cùng 2 agent giám khảo và rà soát vào dự án theo phương án 3 agent, rồi chạy lại bộ việc mẫu và báo điểm trước/sau."
- [x] 9 skill `.claude/skills/` + agent `giam-khao` (Sonnet), `ra-soat`; CLAUDE.md mục 6 (commit `737f87a`)
- [x] Máy chấm chạy lại riêng một lần các test hỏng (test video chập chờn khi máy thiếu bộ nhớ ảo), `tests/test_bo_viec_mau.py` 11 đạt (commit `854e86e`)
- [x] Đo lại bộ việc mẫu, lần `2026-10-23-skill-tu-nap` (mở phiên mới để skill tự nạp; đề giống hệt lần gốc): **48,33/50** so với 50/50. T1, T2, T4, T5 được 10; T3 8,33 do chấm oan (ghi chú trong `docs/bo-viec-mau/lich-su-diem.md`), không tính chấm oan thì 50/50. Cả 5 việc agent tự gọi skill `giao-viec` và agent `giam-khao`; T3 gọi thêm `cham-cheo`. Giám khảo phần E cho cả 5 việc 1 điểm. Thời gian người làm bài: T2 16 phút, T3 14 phút, T4 16 phút, T5 9,5 phút
- [x] Máy thiếu bộ nhớ ảo làm lần chấm T1 đầu hỏng test video; sau khi chủ dự án nới page file, chấm lại T1 9/9 điểm máy, không test nào phải chạy lại
- [x] Sửa chấm oan T3 (chủ dự án duyệt 24/10/2026): `viec.json` thêm `bo_cham` + `ly_do_bo_cham` (test của lần sửa thật không chấm), `tools/bo_viec_mau.py tinh-dap-an` bỏ các test đó, test bổ sung `test_thong_bao_loc_chu_tu_loi_may_chu_va_nguoi_dung` nhận biến lọc lúc gán (kèm test tự kiểm bộ quét); `tests/test_bo_viec_mau.py` kiểm `bo_cham` có lý do và không còn được chấm. Bộ quét mới: bản gốc 18 chỗ chưa lọc, đáp án 0, bài T3 lần gốc 0, bài T3 lần này 0. `tinh-dap-an --viec T3` tự kiểm ĐẠT (3 test ẩn, 686 test cũ, 0 chập chờn). Chấm lại T3: 10/10 → lần đo sau cài skill **50/50**, bằng lần gốc
- [x] Gộp nhánh `skill-agent-du-an` vào `master` (chủ dự án đồng ý 24/10/2026; fast-forward, `tools/check.py --full` trên `master`: 767 test đạt, 3 phút 28 giây)

# Test trọn luồng vụ án thật (2026-10-26, nhánh `test-vu-an-tram-dung`)
Chủ dự án giao: test trọn luồng với vụ án Trạm Dung (Đài Bắc 1993, bài 42.040 ký tự, lưu `.cache/samples/tram_dung.txt`, không vào git), kỳ vọng video từ 20 phút; xong báo video, thuật lại quy trình và lỗi còn gặp.
- [x] Bật app thật cổng 8000 (cấu hình tạm `story-studio-8000` trong `.claude/launch.json`, đã trả lại sau khi test; lần đầu `run.py --no-browser`, sau đổi sang `uvicorn` trực tiếp, xem dòng sự cố 18:55); app, Fleet Runner, VieNeu đều tắt trước đó
- [x] Phân tích vụ `case_71c574da` (20 phút): gửi 18:29, dàn ý xong 19:09 (16 đoạn; lần gọi LLM đầu chờ 9router ~14 phút). Sự cố 18:55: app bị tắt từ bên ngoài (mã -1, đúng lúc phiên Claude bên douyin-movie-studio khởi động lại app của nó bằng `run.py`); bật lại thì vụ tự chạy tiếp từ đoạn 14, không mất dữ liệu
- [x] Dàn ý 25 nhịp, 74 cảnh (+1 miễn trừ), bài đủ tư liệu 20 phút; duyệt 19:10, viết lời Việt + Anh xong 20:04 (96/96 bước, 0 lỗi, 0 cờ)
- [x] Xem lại: tên người, thành phố, đường đã đổi; **lọt tên 2 phim thật và 2 vai diễn** (bộ kiểm không bắt) → thêm 4 tên qua ô "Thêm tên" trên giao diện, app tự thay và ghi 6 chỗ; còn "Đài Loan/Taiwan" (cấp quốc gia, giữ)
- [x] Tạo dự án bản Việt `proj_crime_f2512eac` (75 cảnh: 41 bảng ghim, 32 ảnh, 1 video, 1 miễn trừ; giọng VieNeu Mai Anh, ảnh Muse)
- [x] Sản xuất bản Việt (nút "Sản Xuất Video Dài") 20:07–21:05 (58 phút): giọng 12 phút (75 file, tổng 18,45 phút), ảnh 33 phút (32 Muse ~55 s/ảnh, 1 ảnh dự phòng trả phí 9router ở cảnh 4), dựng + ghép 10 phút. `renders/story_final.mp4`: **18:27**, 1920×1080 25 fps, AAC 48 kHz, 372 MB, âm lượng trung bình −28,8 dB (đỉnh −9,2 dB). Xem 9 khung hình: ảnh Muse đúng phong cách noir, phụ đề karaoke đúng chữ; bảng ghim chiếm 10,3/18,4 phút, thẻ toàn biểu tượng kính lúp, chữ nhãn nhỏ
- [x] Gói SEO: từ khoá gốc "vụ án chưa có lời giải" (10 gợi ý thật), chọn 3; AI viết đạt 18/18 luật, 7 chương theo video thật, có câu miễn trừ; tải .txt được. Thumbnail: nền ảnh Muse, chữ đủ dấu, không vệt sáng
- [x] Bản tiếng Anh `proj_crime_58e75e48` (tạo 13 s, dùng lời Anh viết sẵn, dùng lại 75 ảnh, không gọi Muse): sản xuất 21:13–21:41 (28 phút), giọng Andrew tổng 18,07 phút; `renders/story_final.mp4` **18:04**, 1080p, 372 MB, âm lượng trung bình −30,4 dB. Gói SEO tiếng Anh ("unsolved murder case", 10 gợi ý thật, chọn 3) đạt 18/18 luật; thumbnail tạo lại ra chữ tiếng Anh
- [x] Kiểm: xem 12 khung hình 2 bản + 2 thumbnail; `projects/` chỉ thêm 2 dự án và 1 vụ của lần này; gọi LLM: 96 bước phân tích (97 lượt, 1 lượt chạy lại sau sự cố) + 2 gói SEO; Muse 33 ảnh; ảnh trả phí 1
- [ ] Chưa kiểm chứng: nghe giọng thật hai bản (máy không có công cụ nhận dạng giọng; chỉ đo được thời lượng, âm lượng, phụ đề khớp chữ)
- Lỗi gặp (chưa sửa, chờ chủ dự án quyết):
  - [ ] Độ dài: chọn 20 phút ra 18:27 (Việt) / 18:04 (Anh). `word_budget()` dặn AI viết 75–95% số chữ đúng thời lượng để không vượt; kiểm tra chỉ cảnh báo khi dài hơn, không cảnh báo khi ngắn hơn. Trái với "15 phút là mức tối thiểu" (CLAUDE.md 1)
  - [ ] Lọt thông tin thật: tên phim, tên vai diễn không bị coi là tên cần đổi (bộ kiểm lọt tên không bắt); phải thêm tay ở màn Xem lại
  - [ ] Bảng ghim chiếm 41/75 cảnh, 10,3/18,4 phút; thẻ toàn biểu tượng kính lúp, chữ nhãn nhỏ; có đoạn 6 cảnh bảng ghim liền nhau
  - [ ] Muse: app chờ 240 s rồi chuyển ảnh trả phí 9router, trong khi Fleet Runner còn đang thử lại (150 s + nghỉ 60 s); lần thử lại ra ảnh sau 45 s → vừa tốn tiền vừa tốn lượt Muse (cảnh 4)
  - [ ] Bản tiếng Anh chép nguyên thumbnail và dữ liệu từ khoá SEO tiếng Việt của bản Việt; không bấm tạo lại thì thumbnail bản Anh mang chữ Việt
  - [ ] Âm lượng video nhỏ (trung bình −28,8 / −30,4 dB)
  - [ ] Nhỏ: dòng trạng thái bước 2 ghi "Thu âm Edge-TTS" khi giọng là VieNeu; lần gọi LLM đầu chờ 9router ~14 phút không báo gì trên giao diện
  - [ ] Môi trường: app chạy bằng `run.py` bị tắt khi phiên khác khởi động lại app của nó (nghi tắt theo tên lệnh `run.py`); hàng việc tự chạy tiếp, không mất dữ liệu

# Sửa lỗi và làm video vụ án rùng rợn hơn (2026-10-26, nhánh `sua-video-vu-an-rung-ron`, tách từ `test-vu-an-tram-dung`)
Chủ dự án giao: "Sửa cả 8 lỗi" của lần test Trạm Dung + 6 góp ý (giọng chậm, có cảm xúc; sound effect; ảnh nối tiếp; font Việt đẹp; nghiên cứu phong cách hoạt hình như video mẫu; bớt câu hỏi tu từ). Lần test sau chỉ xuất bản Việt. Duyệt kế hoạch 26/10: thêm lựa chọn "Hoạt hình 2D rùng rợn"; font Be Vietnam Pro + Oswald (+ Patrick Hand cho nhãn bảng ghim); SFX tự tìm nguồn CC0; nối ảnh bằng ảnh cảnh trước làm tham chiếu.
- [x] A9 Fleet Runner chỉ nhận media mới sinh sau khi gửi prompt (đã gặp: nhận video cũ trong chat, task_m_72445b82)
- [x] A4 Thời gian chờ Muse phủ cả vòng thử lại
- [x] A5 Bản ngôn ngữ mới không chép SEO/thumbnail của ngôn ngữ khác
- [x] A6 Âm lượng: amix normalize=0 + loudnorm −16 LUFS
- [x] A7 Nhãn bước thu âm đúng giọng; giao diện báo khi 9router bận
- [x] A1 Số phút chọn là mức tối thiểu; cảnh báo khi ngắn hơn
- [x] A2 Trích cả tên tác phẩm, vai diễn, nghệ danh để đổi
- [x] B6 Bớt câu hỏi tu từ (hook + tối đa ~1/4 số nhịp)
- [x] A3 Bảng ghim ≤ 25% số cảnh; thẻ dùng ảnh cảnh liên quan; chữ to hơn
- [x] B4 Font đóng gói (Be Vietnam Pro, Oswald, Patrick Hand) cho phụ đề, bảng ghim, thumbnail
- [x] B1 Giọng chậm hơn + ngắt nghỉ; mẫu giọng cho chủ dự án chọn
- [x] B2 Hiệu ứng âm thanh CC0 theo `sfx_cue`; nhạc nền theo `bgm_energy`
- [x] B3 Ảnh cảnh sau tham chiếu ảnh cảnh trước; khoá nhân vật dự án vụ án
- [x] B5 Phong cách "Hoạt hình 2D rùng rợn"
- [x] Chạy lại vụ Trạm Dung bản Việt, phong cách "Hoạt hình 2D rùng rợn" (`proj_crime_4a93fd60`, nút "Sản Xuất Video Dài" trên giao diện): `renders/story_final.mp4` **22:53**, 1080p, **−16,0 LUFS**, không có đoạn lặng ≥ 2 s, 0 cảnh báo trong nhật ký. So lần 1 (`proj_crime_f2512eac`): độ dài 18:27 → 22:53; bảng ghim 41/75 → 16/78 cảnh (thẻ có ảnh cảnh, nhãn Patrick Hand); câu hỏi 24 → 6; dấu "…" 0 → 68; âm lượng TB −28,8 dB → −16 LUFS. Tốc độ đọc đo thật 189,5 chữ/phút (VieNeu Mai Anh, 0,87; lần 1 ~230), `VI_WORDS_PER_MINUTE = 200` lệch 5%, giữ nguyên
- [x] Xem 14 khung hình: đúng kiểu hoạt hình 2D, cảnh liền nhau cùng bối cảnh và nhân vật; phụ đề Be Vietnam Pro tô vàng từ khoá. Ảnh: 74 Muse, 4 trả phí 9router (cảnh 2–5, Fleet Runner chưa online → sửa ở commit `55ebf1e`)
- [x] Lỗi mới khi chạy lại: thư viện tiếng động chênh 36 LU (fluorescent_hum −6,4 LUFS đè giọng ở 29 cảnh; footsteps_wet −42,9 LUFS không nghe thấy) và giọng mono bị hạ ~3 dB khi trộn sang stereo. Sửa: đo từng file rồi đưa về `SFX_TARGET_LUFS = −36`, trộn mono. Test mới đỏ trên code cũ, xanh trên code mới; dựng lại (không gọi Muse/9router): 77 cảnh có tiếng động, giọng sau trộn chỉ to hơn giọng gốc 0,11 LU (tối đa 0,18)
- [ ] Chưa kiểm chứng: nghe bằng tai giọng, tiếng động, nhạc nền (máy chỉ đo được độ to); 5 tiếng CC0 "tạm" trong `NGUON.md`; nhân vật thám tử lúc vẽ mặt tròn trắng lúc vẽ mặt người thật; bảng ghim cuối video >30 thẻ, nhãn dây đỏ chồng nhau
- [x] Giám khảo ĐẠT (không điểm chặn, tự đo lại khớp số), `check.py --full` ĐẠT: 794 passed, 0 lỗi, 3 phút 17 giây

# Video cho cảnh cao trào từ ảnh 9-grid (2026-10-27, nhánh `lam-bai`)
Chủ dự án giao: những đoạn cao trào, gay cấn dùng video Muse thay vì ảnh; phong cách giống ảnh 100%, bám nhân vật, vị trí, phong cảnh của cảnh; làm ảnh 9-grid trước rồi từ đó ra video, lời kể dài hơn một video thì làm thêm grid, nhiều video rồi ghép. Đã chốt: nút riêng (làm từng bước), tối đa khoảng 50% số cảnh, chỉ dự án vụ án, không gọi LLM.
- [x] `services/climax_video.py`: chấm điểm, chọn cảnh (`pick_climax_scenes()`), số clip/grid (`clip_count()`, `grid_plan()`), prompt khuôn (`grid_prompt()`, `clip_prompt()`, `STYLE_LOCK_EN`), cắt grid, chỉnh màu từng khung (cv2, ~4 s/clip 5 s), máy kiểm clip (SSIM khung đầu, cắt cảnh, lệch sáng, độ dài), ghép, `run_scene_climax_video()` (thử lại clip 1 lần; lỗi thì giữ ảnh, ghi lý do)
- [x] `routers/climax_video.py`: pick / bật-tắt cảnh / chạy nền / trạng thái; Fleet Runner chưa chạy thì bật và chờ tối đa 60 s như phần tạo ảnh
- [x] Sửa `TaskCreateRequest.duration` mặc định `None`: `parameters.duration_sec = 10` nay ra task 10 giây (test đỏ trên code cũ: 5 ≠ 10)
- [x] `render_scene_video()`: clip ngắn hơn lời kể thì giữ khung cuối (tpad), không lặp; dài hơn thì cắt (test ffmpeg thật đỏ trên code cũ: giây 1,25 quay về khung đỏ)
- [x] Giao diện `backend/static/climax_video.js`: `#btn-climax-video-pick`, `#btn-climax-video-run`, nhãn + nút bật/tắt trên thẻ cảnh; chỉ hiện với dự án vụ án
- [x] Kiểm giao diện (server thử 8010, dự án thử tạo bằng ảnh giả `proj_crime_uithu01`, kiểm xong đã chuyển sang `.cache/climax_try/`, `projects/` trống như trước): chọn đúng 2/5 cảnh; bật cảnh thứ 3 bị chặn kèm lý do; tắt cảnh thì nút đổi "Tạo video cho 1 cảnh"; bấm chạy khi không có Muse → nhãn đỏ "Video lỗi, giữ ảnh" kèm lý do, thông báo tổng kết; chạy trọn quy trình bằng Muse giả trên dự án đó → thẻ cảnh hiện clip 1920×1080. Console chỉ có lỗi 400 cố ý (bật quá giới hạn), log server không lỗi
- [x] Test `tests/test_climax_video.py` (Muse giả, ffmpeg thật) + 3 test trong `tests/test_no_fake_success_and_motion_render.py`
- [x] Chạy thật trên Muse 27/10/2026 21:25–22:13 (chủ dự án cho phép): repo thật tạm chuyển sang nhánh `thu-video-cao-trao`, server thử 8010, bản sao dự án Trạm Dung `proj_crime_thucaotrao` (dự án gốc không đụng), xong đưa repo thật về `master`. 16 lượt Muse (5 ảnh grid, 11 clip)
  - Ảnh 9-grid: **tốt** — cảnh 12 và 28 đều đúng nhân vật, quần áo, bối cảnh của ảnh cảnh, khoảng 2 phút/ảnh
  - Lượt 1 (prompt cũ): cảnh 12 (4 clip) và 28 (3 clip) **ready**, nhưng 7/7 clip zoom sát rồi vẽ lại mặt nhân vật kiểu tả thực/anime sau ~1 giây (đầu tròn trắng thành mặt có mắt mũi); mỗi chỗ nối clip giật về hình gốc; 1 clip mọc thêm bóng người. Máy kiểm cho qua cả 7 (SSIM khung đầu 0,78–0,84 nhưng tụt còn 0,12–0,36 giữa clip). Nguyên nhân zoom: task không nói máy quay nên `enqueue_and_wait_muse_task()` gắn "cinematic slow tracking pan", prompt còn xin "push-in"; runner không gửi negative_prompt của video
  - Lượt 2 (commit `baf25de`, máy quay đứng yên): hết zoom, bố cục giữ tốt hơn (SSIM thấp nhất 0,44–0,64), nhưng 4/4 clip cảnh 12 **vẫn vẽ lại mặt** sau ~1 giây. Cảnh 12 failed vì `MemoryError` (máy còn ~1 GB bộ nhớ ảo trống / 43 GB); cảnh 28 failed vì Fleet Runner treo khi vẽ grid (720 s). Dừng, chưa chạy cảnh 41, 53
- [ ] Chưa đạt yêu cầu "phong cách giống ảnh 100%": Muse video vẽ lại mặt dù prompt khoá; máy kiểm không bắt được trôi phong cách. Chờ chủ dự án quyết hướng (không gộp / thêm luật kiểm "giữ giống ô gốc suốt clip" / clip ngắn hơn / cách khác)

# Video cao trào theo bảng nhân vật (2026-10-28, nhánh `lam-bai`, kế hoạch `docs/superpowers/plans/2026-10-28-video-cao-trao-bang-nhan-vat.md`)
Chủ dự án chốt 28/10: bảng nhân vật cho cả dự án, mỗi cảnh một side chat Muse, tài khoản video tự vẽ ảnh (chỉ video cao trào), không có kiểu tóc mặc định, giữ bước duyệt grid (đêm 28/10 agent duyệt thay), gộp bảng diễn viên thành 1 ảnh, làm Native; dùng thêm 4 tài khoản Muse của videopic-workflow, gọi từ từ.
- [x] Task 1 muse_bridge: route_kind, pin_account, avoid_accounts, thread_url, attachments; trả thread_url, muse_reply
- [x] Task 2 Fleet Runner: mở lại side chat, nhiều ảnh đính kèm, raw_prompt, dừng sớm khi Muse báo lỗi bằng chữ, profile Chrome ngoài (STORY_STUDIO_EXTRA_CHROME_PROFILES)
- [x] Task 3–4 Bảng nhân vật: dịch vụ, API, cửa sổ `#btn-character-sheets`
- [x] Task 5–6 Video cao trào hai pha (grid → duyệt → clip) trong side chat của cảnh; thẻ cảnh có nhân vật và duyệt grid
- [x] `check.py --full` ĐẠT 01:36: 858 test đạt, 0 lỗi, 20 phút 15 giây (sau đó thêm 6 commit sửa từ lần chạy thật, mỗi commit qua hook nhanh + test liên quan)
- [x] Kiểm giao diện server thử 8010 (dự án thử ảnh giả, không gọi Muse): mọi nút đúng, console chỉ 2 lỗi 400 cố ý
- [x] Chạy thật 28/10 01:37–03:13 (repo thật tạm nhánh `thu-video-cao-trao`, bản sao Trạm Dung `proj_crime_thucaotrao`, xong về `master`, cấu hình tài khoản trả về bản cũ): 11 lượt Muse (2 bảng nhân vật, 4 grid, 5 lượt clip)
  - Bảng Hàn Thụy Côn: lần 1 mặt người thật ở các góc nghiêng phải (Muse theo câu "gaunt facial features") → agent sửa thiết kế (đầu tròn, không mũi/tai/râu) + ghi chỗ sai → lần 2 nhất quán 9 góc (còn chấm mũi ở 1 hình, tai nhỏ), agent duyệt
  - Grid cảnh 28: lần 1 sai ô 6–7 (gáy trắng) → ghi chỗ sai → lần 2 đúng cả 9 ô, agent duyệt
  - Grid cảnh 41: ảnh cảnh vẽ Hàn Thụy Côn mặt người thật, mâu thuẫn bảng đầu tròn; vẽ lại còn tệ hơn (gán tóc rối cho cô gái, cậu bé) → để "chờ duyệt grid", chờ chủ dự án quyết
  - Clip cảnh 28: không ra video nào. vid_02 trả lời "dịch vụ tạo video đã không khả dụng"; vid_01 hết phiên đăng nhập; vp_04, vp_01, vp_03 (videopic) chờ 300 s không có video (02:56–03:13). Dừng để khỏi dồn tài khoản
  - Lỗi tìm ra khi chạy thật và đã sửa (mỗi lỗi có test): địa chỉ chat chưa lưu khi kết quả về sớm; tài khoản bị tránh vẫn nhận thay; NO_MEDIA chưa đổi tài khoản; khe Fleet Runner luôn giữ tài khoản active (việc tránh nó nằm chờ 30 phút); lỗi sau khi gửi prompt chưa kèm câu Muse nói
  - Lỗi thao tác của agent: tắt Fleet Runner mà không bật lại → việc grid cảnh 28 chờ 12 phút rồi quá giờ (không tốn lượt Muse)
- [x] Người duyệt độc lập tìm 9 lỗi (3 nặng), sửa ở commit `e70f290`, 13 test mới `tests/test_climax_review_fixes.py` (không gọi Muse): runner coi chính prompt là lời Muse báo lỗi (chữ trơn "lỗi"/"error"); mọi tài khoản bị tránh thì việc treo tới hết giờ, tự thử lại của bridge không biết tránh; giao diện tự lưu bản cũ đè mất trạng thái duyệt grid; chọn lại cảnh xoá grid đã duyệt mà clip lỗi; khoá characters.json; đường dẫn grid ngoài thư mục cảnh; PROFILE_IN_USE/SESSION_EXPIRED/BROWSER_ERROR chưa đổi tài khoản; thiếu `grid_approved` trong trạng thái cần bảng; số phiên bản script
- [x] `check.py --full` ĐẠT (commit `c6fe7e8`): 875 test đạt, 0 lỗi, 4 phút 2 giây
- [x] Bấm thật trên server thử 8010 (dự án ảnh giả `proj_crime_uiduyet`, Muse giả; xong chuyển sang `.cache/climax_try/ui_duyet/`, `projects/` trống như trước): sửa lời kể cảnh 3 chưa lưu rồi bấm "Duyệt grid" → giao diện lưu (PUT) rồi mới duyệt (POST approve 200); server "grid_approved", lời sửa còn; ép giao diện gửi lại trạng thái cũ "grid_review" → server vẫn giữ "grid_approved"; nút chạy đổi "Làm clip cho 1 cảnh đã duyệt grid". Console chỉ có lỗi kết nối từ lúc server chưa bật và 404 dự án thử cũ nhớ trong trình duyệt
- [x] Sửa thêm (commit `b363b9c`): mỗi lần bấm chạy không mang theo danh sách tài khoản cần tránh của lần trước (đêm 28/10 cảnh 28 còn nhớ "tránh vid_02")
- [x] Chạy lại pha clip cảnh 28 sáng 28/10 07:29–07:38 (chủ dự án cho phép; repo thật tạm nhánh `thu-video-cao-trao`, thêm 4 tài khoản videopic, xong về `master`, cấu hình tài khoản trả bản cũ, chỉ tắt tiến trình 8010 của mình): **ready**, 4 lượt Muse (3 clip + 1 làm lại vì khung đầu không giống ô), cả 4 trong một side chat trên `muse_acc_vid_02`, ~2 phút/clip; video ghép 15 s 1920×1080 cho lời kể 11,9 s. Ảnh xem: `.cache/climax_try/xem/clip_28_lan2/`
  - Tốt hơn đêm 27/10: không còn mặt tả thực/anime, nét vẽ 2D, bối cảnh (xe đỏ, cửa sắt, hộp thư, hành lang), máy quay đứng yên giữ đúng
  - Vẫn **sai nhân vật**: 3/3 clip, sau ~1 giây đầu tròn to thành đầu nhỏ có tóc dài phủ cả đỉnh và trước trán (mặt trắng chấm mắt còn giữ); áo xanh xám nhạt dần thành trắng, quần be thành hồng đào ở clip 3. Mỗi chỗ nối clip đầu tròn hiện lại ~1 khung rồi đổi. Muse tự kiểm báo "mặt giữ dạng phẳng" — đúng một phần, không nhắc đổi dáng đầu
  - Clip 3: Muse tự chèn dải ô phía trên + vạch trắng ở ~1,5 s đầu (ô cắt từ grid không có viền); máy kiểm cho qua
  - Máy kiểm (khung đầu, cắt cảnh, độ sáng) cho qua cả 3 clip sai nhân vật: chưa có luật "giữ giống ô gốc suốt clip"
- [ ] Chưa đạt "giống ảnh 100%" ở pha clip; chờ chủ dự án quyết hướng
- [ ] Chờ chủ dự án: đăng nhập lại muse_acc_vid_01 và videopic muse_vid_02; cảnh 41 (vẽ lại ảnh cảnh hay đổi bảng Hàn Thụy Côn); duyệt lại thiết kế Hàn Thụy Côn agent đã sửa; chạy lại pha clip ban ngày

# Video cao trào: giao việc nhiều bước cho Muse + tóc nhân vật nữ (2026-10-28 tối, nhánh `video-cao-trao-giao-viec`)
Thiết kế `docs/superpowers/specs/2026-10-28-video-cao-trao-giao-viec-muse-design.md`, kế hoạch `docs/superpowers/plans/2026-10-28-video-cao-trao-giao-viec-muse.md` (chủ dự án duyệt, làm kiểu Native). Nhánh = `master` + các commit của `thu-video-cao-trao` trừ `3bef9ee` (giữ đội agent).
- [x] Thí nghiệm trước khi code (28/10 chiều, script nháp, `.cache/thu-muse-AB-28/`, `.cache/thu-muse-28-lan2/`): một yêu cầu Muse nhiều bước giữ đầu tròn; đoạn quay lưng bắt đầu từ ảnh góc sau vẽ riêng thì hết đĩa trắng. Chủ dự án loại hướng dựng bằng code
- [x] Task 1 nhánh; Task 2 quy tắc tóc nữ (`FEMALE_HAIR_RULE_EN`, chỉ phong cách đầu tròn); Task 3 bản giao việc `services/climax_brief.py`; Task 4 runner `agent-video` (`runners/muse_agent_turn.py`, `_finish_agent_turn()`); Task 5 bridge + pha clip mới + `redo`; Task 6 thẻ cảnh (báo cáo Muse, cảnh báo, làm lại)
- [x] Bộ test mặc định chạy từng file (máy còn ~2,4 GB bộ nhớ ảo, `check.py --full` chết vì MemoryError): 60 file, 900 đạt, 0 lỗi, 390 s
- [x] Bấm thử 8010 (dự án ảnh giả `proj_crime_uiagent`, không gọi Muse; xong chuyển sang `.cache/climax_try/ui_agent/`, `projects/` như trước): thẻ cảnh hiện báo cáo, cảnh báo vượt ngân sách, "Đã thay ảnh cảnh (bản cũ: scene_003.truoc_sua_toc.jpg)", chữ HTML trong báo cáo không thành thẻ; "Làm lại" hỏi xác nhận rồi về "grid_approved"; console sạch
- [x] Chạy thật cảnh 28 (`proj_crime_thucaotrao`, vid_02, 21:16–21:36): Muse làm xong và tự báo ĐẠT nhưng app **không tải được** video (blob bị Muse tạo lại, "Failed to fetch") và bridge **tự giao lại** → tốn **2 yêu cầu Muse** (số video mỗi lần do Muse tự đếm, xem chat). Đã sửa cả hai, mỗi lỗi một test đỏ→xanh (commit `5e72941`)
- [x] Kết quả thật của lần 2 (chat https://muse.ai/thread/6a8b1802-dc4c-4b6c-959b-9e73cb93efd2) tải bằng script chỉ đọc, cho đi qua pha clip của app: video 12,0 s đạt kiểm, cảnh "ready", ảnh cảnh thay bằng ảnh Muse sửa tóc (giống ảnh cũ 0,922; ảnh bìa video 0,68 bị bỏ), bản cũ `images/scene_028.truoc_sua_toc.jpg`. Xem từng giây (`.cache/live28_do_video/khung_video_cuoi.jpg`): 0–3 s chạy thật tới cửa, 4–7 s đẩy cửa vào, 8–12 s hành lang quay lưng; mặt tròn, tóc dày trên đầu suốt video, không đĩa trắng. Muse tự chia đoạn từ bản giao việc
- [x] Giám khảo độc lập (Opus) chấm CHƯA ĐẠT: ảnh bìa video có thể thay nhầm ảnh cảnh (giống 0,68 > ngưỡng 0,45); quy tắc tóc bị cắt khỏi bản giao việc với thiết kế mặc định. Đã sửa (commit `6fadad9`), mỗi lỗi một test đỏ→xanh; chạy lại kết quả thật cảnh 28 theo luật mới: vẫn thay đúng ảnh Muse sửa, bản cũ còn nguyên
- [x] Bộ test sau sửa, chạy từng file: 60 file, 906 đạt, 0 lỗi, 349 s
- [x] Chạy lại trọn từ nút cảnh 28 sau khi sửa (29/10 07:11–07:17, server thử 8010, vid_02; 8 tài khoản video online gồm 4 tài khoản videopic): **1 yêu cầu Muse**, Muse dùng 3 video + 2 ảnh, runner tải được video cuối ngay, cảnh "ready" sau 368 s. Muse thấy ảnh cảnh đã đúng tóc nên ghi `ANH_CANH_MOI: không` → app giữ nguyên ảnh (bản dự phòng gốc còn nguyên). Xem từng giây (`.cache/live28b/khung.jpg`): 0–4 s chạy tới cửa, 4–8 s vào cửa (góc sau, ảnh khởi đầu riêng), 8–12 s hành lang; mặt tròn, tóc dày trên đầu, không đĩa trắng. `projects/` như trước
- [ ] Cảnh 41 chờ chủ dự án: bảng Hàn Thụy Côn đầu tròn mâu thuẫn ảnh cảnh vẽ mặt người; cô gái và cậu bé chưa có bảng nhân vật
- [x] Tài khoản: dùng chung 4 hồ sơ Muse của videopic-workflow (`muse_acc_vp_01..04`, `STORY_STUDIO_EXTRA_CHROME_PROFILES`); vp_01/02/03 còn đăng nhập. muse_acc_vid_01 hết phiên, chủ dự án bỏ ("Dùng cái nào còn tốt là được")

# Cảnh 41 và video hoàn chỉnh dự án thử Trạm Dung (2026-10-29, nhánh `toc-nu-moi-nhan-vat`)
- [x] Dọn nhánh: xoá 6 nhánh đã gộp và `thu-video-cao-trao` (gắn tag `luu/thu-video-cao-trao` giữ commit cũ mà TASKS.md còn nhắc)
- [x] Bản giao việc: quy tắc tóc áp cho mọi nhân vật nữ trong cảnh phong cách đầu tròn (kể cả người chưa có bảng nhân vật), ảnh cảnh có nữ đầu trọc thì vẽ lại (commit `a04022d`, test `test_hair_rule_covers_every_female_in_round_head_scene`)
- [x] Cảnh 41 chạy thật 29/10 07:45 (vid_02, 1 yêu cầu Muse: 5 video + 2 ảnh): app hết giờ chờ 45 phút (AGENT_TIMEOUT), Muse gửi bản cuối muộn hơn. Lấy video từ chat bằng script chỉ đọc, cho qua pha clip của app: "ready", video 21 s. Hàn Thụy Côn thành đầu tròn tóc rối đúng bảng; đoạn quay lưng sạch. **Chưa đạt:** cô gái vẫn tóc chỉ ở gáy (Muse tự chấm sai là đủ tóc); từ giây 3 cô gái và cậu bé có nét lông mày buồn nhỏ. Muse ghi `ANH_CANH_MOI: có` nhưng không gửi ảnh cảnh đã vẽ lại → ảnh tĩnh cảnh 41 giữ nguyên (Hàn Thụy Côn mặt người trong ảnh tĩnh)
- [x] Nâng chờ Muse mặc định 45 → 75 phút (commit `b4d8142`)
- [x] Video hoàn chỉnh: nút "Sản xuất video dài" trên server thử 8010 (không gọi Muse/ảnh trả phí: đủ ảnh và giọng), 14 phút dựng → `projects/proj_crime_thucaotrao/renders/story_final.mp4`, 22:53,6, 1920×1080 25 fps, −16,0 LUFS (đoạn cảnh 28: −16,3; cảnh 41: −16,1); khung tại cảnh 28 (464,7 s) và 41 (694,9 s) là video Muse có phụ đề. `projects/` như trước
- [ ] Đề xuất: làm bảng nhân vật cho cô gái cảnh 41 (để tóc theo bảng) rồi làm lại cảnh 41; runner nhắc Muse gửi ảnh khi báo `ANH_CANH_MOI: có` mà không kèm ảnh; lấy kết quả Muse gửi muộn sau khi hết giờ
- [x] Làm lại cảnh 41 theo lời kể (29/10, chủ dự án chọn "Vẽ lại theo lời kể"; cô gái và cậu bé không phải nhân vật vụ án, do mô hình vẽ ảnh tự thêm):
  - Vẽ lại ảnh cảnh bằng Muse (tài khoản ảnh img_01, prompt cảnh + câu phong cách đầy đủ, dặn chỉ hai cảnh sát và Hàn Thụy Côn): lần đính kèm bảng nhân vật Muse từ chối 2 lần (không vẽ nhân vật trong ảnh tham chiếu bị áp giải); bỏ đính kèm thì vẽ được, 1 ảnh. Ảnh cũ chép dự phòng ở `.cache/backup/`
  - **Lỗi thao tác của agent:** lệnh "vẽ lại grid" bị máy chủ từ chối (chữ tiếng Việt trong lệnh curl hỏng mã hoá) mà vẫn bấm chạy, nên app làm thẳng video với lưới cũ, bỏ qua bước chủ dự án duyệt lưới mới. Tốn 1 yêu cầu Muse (3 video + 1 ảnh, 10 phút)
  - Kết quả: 0–10 s ba người đầu tròn, không còn người thừa (Muse theo ảnh cảnh, không theo lưới cũ); 10–21 s quay lưng, hai cảnh sát đội mũ phớt, dáng to giống người thật hơn đoạn trước
- [x] Dựng lại video hoàn chỉnh (17 phút): 22:53,6, −16,0 LUFS, khung tại cảnh 41 đúng bản mới

# Vẽ lại ảnh tĩnh cho đồng bộ phong cách (2026-10-29, nhánh `ve-lai-anh-toc-nu`)
- [x] Nguyên nhân: 78 ảnh cảnh dự án thử Trạm Dung vẽ ngày 27/10, trước khi có quy tắc tóc nữ; quy tắc chỉ áp cho ảnh vẽ sau đó. Xem bằng mắt cả 61 ảnh cảnh (`.cache/toc_nu/tam_1..4.jpg`): 10 ảnh nữ đầu trọc (002, 020, 021, 022, 023, 029, 031, 033, 034, 037; lọc theo chữ trong prompt bỏ sót 033, 034) và 4 ảnh lệch sang mặt người (006 ảnh chân dung trong khung, 007, 053, 067)
- [x] Vẽ lại cả 14 ảnh (chủ dự án chọn "Vẽ lại cả 14 ảnh"): server thử 8010, tài khoản ảnh img_01, prompt cảnh + câu phong cách đầu tròn đầy đủ + dòng dặn riêng từng cảnh (`.cache/redraw14/`). **14 yêu cầu Muse ảnh**, 13:41–13:57, mỗi ảnh 50–80 s, không lỗi, không gọi ảnh trả phí. Ảnh cũ và video final cũ chép dự phòng ở `.cache/backup/anh_truoc_ve_lai_29-10/`
- [x] Xem từng ảnh mới (`.cache/redraw14/tam_moi.jpg`): nữ có tóc phủ kín đỉnh đầu, mọi người mặt tròn trắng chấm mắt. Cảnh 023 và 034 nay không có nhân vật chính, cảnh 033 thám tử đội mũ trùm: đúng prompt và lời kể (ảnh cũ vẽ thừa người)
- [x] Dựng lại video hoàn chỉnh (nút "Sản xuất video dài", 17 phút, không thêm việc Muse): 22:53,6, 1920×1080 25 fps, −16,0 LUFS; khung tại 12 cảnh vẽ lại đều là ảnh mới (`.cache/redraw14/khung_final.jpg`). `projects/` như trước

# Giọng đọc nhịp review (2026-10-29, nhánh `giong-doc-nhip-review`)
- [x] Phân tích 2 video mẫu chủ dự án gửi (`.cache/mau_video/`, số liệu `so_lieu.json`): cảnh 4–7 s, 80–93% khung có chuyển động, đọc 240–272 chữ/phút, 8–11% thời lượng gần như im; video Trạm Dung ~18 s mỗi ảnh, 186–190 chữ/phút, 0,2% im. Giọng nữ video mẫu cao 254–285 Hz
- [x] Thử giọng review ngoài app (`.cache/thu_giong_review/`): viết lại cảnh 2–5 kiểu review (2 lượt LLM, không thêm sự thật), đọc VieNeu tốc độ gốc 1,0 ngừng ngắn. Chủ dự án nghe: giọng nam (Thiện Minh) và nữ (Mai Anh) đều ổn, muốn thành lựa chọn. Đo 11 giọng nữ VieNeu + Edge HoaiMy cùng 4 câu: gần mẫu nhất là Trúc Ly (đọc đủ đoạn: 254 Hz, 261 chữ/phút); Mai Anh 205 Hz
- [x] Phát hiện: `VIENEU_SPEED` 0,87 kéo giãn âm thanh bằng atempo sau khi đọc (`vieneu_server.py`), không phải model đọc chậm tự nhiên
- [x] App: 3 giọng `vieneu-review-TrucLy/MaiAnh/ThienMinh` (danh mục `/api/voices`, nhóm "Nhịp review phim" trong `#select-voice`), đọc `REVIEW_SPEED` 1,0, ngừng 0,2 s / "…" 0,6 s; giọng cũ giữ nguyên (commit `76fc84f`, test `tests/test_review_voice_pacing.py`)
- [x] Kiểm chứng: 113 test giọng/vụ án đạt (98 s); `tools/check.py` ĐẠT; server thử 8010: chọn giọng lưu vào dự án thử rồi trả về Hoài My, nghe thử sinh mẫu thật (Trúc Ly 246 Hz, Mai Anh 195, Thiện Minh 130; ~252 chữ/phút), không rơi sang Edge, console không lỗi, `projects/` như trước. Giám khảo: ĐẠT
- [ ] Chủ dự án quyết: số chữ/phút dùng để tính độ dài lời vụ án (`VI_WORDS_PER_MINUTE` 200) chưa theo giọng review (220–260) → video ngắn hơn số phút chọn 10–25%
- [ ] Đề xuất: đường dự phòng CLI VieNeu (khi server lỗi) không ngừng giữa câu; viết lời kiểu review trong pipeline LLM (việc ưu tiên 1 chủ dự án đã nêu)

# Quyết định chủ dự án và dọn dự án thử (2026-10-29, nhánh `ghi-quyet-dinh-va-don-du-an`)
- [x] Ghi nguyên văn 4 quyết định vào CLAUDE.md mục 1.2 (câu 10–13): thời lượng ngắn hơn được, cốt là viết đủ không rút gọn (khoá bằng Python); ngôi kể thứ 3 kiểu phóng sự; nới quy tắc biểu cảm nhân vật đầu tròn; thêm việc khó vào bộ việc mẫu và đo liên tục
- [x] Chủ dự án quyết câu "số chữ/phút theo giọng review" (mục Giọng đọc nhịp review): không bù, xem câu 10 mục 1.2
- [x] Worktree cũ: `.claude/worktrees/` đã trống, `git worktree list` chỉ còn bản chính; app còn 1 worktree 155 MB của một phiên đang giữ (chưa đủ 30 ngày không dùng nên công cụ dọn của app không xoá)
- [x] Chuyển vào Thùng rác Windows (khôi phục được) 11 dự án thử cũ và 2 vụ đi kèm, ~2,3 GB: `proj_270da203`, `proj_58075554`, `proj_899c1fbb`, `proj_8f6aaead`, `proj_b4c7cf2d`, `proj_crime_4a93fd60`, `proj_crime_58e75e48`, `proj_crime_f2512eac`, `proj_f8cc1379`, `proj_fb8e8c1b`, `proj_fcc95d71`, `_cases/case_0db7af5b`, `_cases/case_71c574da`. Kiểm 13/13 có trong Thùng rác. Giữ: 2 dự án MẪU + `case_7dcf6158`, `proj_ea5b04db` (dự án thử giao diện), `proj_crime_thucaotrao` + `case_6110efa8` (Trạm Dung đang làm), `proj_huyen_thoai_rung_suong_mu` (mã dự án mặc định trong `app.js`)

# Bộ việc mẫu: thêm việc khó (2026-10-29/30, nhánh `bo-viec-mau-viec-kho`, CLAUDE.md mục 1.2 câu 13)
- [x] Thêm T6 (Muse: video cuối tải hỏng vì blob bị huỷ + bridge tự giao lại việc nhiều bước; lần sửa thật `5e72941`) và T7 (dựng video nhỏ tiếng, nhạc nền chia đôi giọng; `70fa508`). Đề chỉ tả triệu chứng, phạm vi rộng. Loại ứng viên `6fadad9` (test bám tên tham số, đúng số ký tự). Giới hạn số việc trong `tests/test_bo_viec_mau.py` 3–5 → 3–10 theo câu 13
- [x] Sửa công cụ: bài làm có file giữ chỗ `docs/bo-viec-mau/README.md` (CLAUDE.md từ 23/10 nhắc file này; thiếu thì cổng kiểm hỏng ngay trên đáp án, D = 0). Test `test_bai_lam_khong_co_de_dap_an_nhung_co_file_giu_cho_readme`. Lập đáp án T6, T7: tự kiểm máy chấm ĐẠT (gốc 0, đáp án 9/9)
- [x] Đo lần đầu `2026-10-29-viec-kho` (general-purpose Opus 5.5 + 9 skill dự án; giám khảo Sonnet), điểm thô, CHƯA ghi `lich-su-diem.md`: T6 7,5/10 (không dùng để so sánh, xem dòng dưới) (A 2,5: hỏng test ẩn bổ sung; B 2, C 1, D 1, E 1; ~197 nghìn token, 14 phút); T7 8/10 (A 5; B 0: hỏng 2 test cũ `test_assemble_logs_xfade_failure_and_falls_back_to_concat`, `test_assemble_succeeds_when_final_duration_cannot_be_measured` vì thêm bước đo độ to cần ffmpeg thật, bài làm tự sửa 2 test đó; ~200 nghìn token, 22 phút)
- [x] T6 chấm oan do test bổ sung của agent (trang Muse giả chỉ hiểu các đoạn JS có sẵn; bài làm tải bằng đoạn JS mới, hợp lý). Giám khảo nhánh đồng ý; đã ghi ràng buộc giao diện vào `T6/de-bai.md` (test không đổi nên đáp án giữ nguyên). README sửa chữ cho khớp 7 việc
- [ ] Đo lại T6 với đề mới rồi mới ghi `lich-su-diem.md` (~200 nghìn token, ~15 phút làm bài + chấm)
- [ ] Có từ trước, ngoài phạm vi: `check.py --full` hỏng `test_muse_fleet_runner.py::test_accounts_config_structure` vì cấu hình máy có 14 tài khoản Muse (thêm 4 tài khoản videopic 28/10), test đòi 10

# Làm trọn kế hoạch 7 ý (chủ dự án duyệt 02/11/2026, nhánh `lam-tron-ke-hoach-thang-11`; quyết định: CLAUDE.md mục 1.2 câu 14–22)
Yêu cầu chốt: làm hết, test kỹ từng nút theo FEATURE_MAP như người dùng thật, tách 1–2 tính năng A/B test (đội agent / không đội agent), báo kết quả cuối.
- [x] Ghi nguyên văn câu 14–22 vào CLAUDE.md mục 1.2
- [x] Test cấu hình tài khoản Muse không đòi đúng 10 tài khoản (câu 22)
- [x] 1. Chống rút gọn (câu 10, 14, 21): bảng sự thật cố định, danh sách ý từng đoạn, mỗi phần viết phải dùng đủ ý, code Python chặn khi thiếu ý / ngắn bất thường / trái bảng sự thật; test kiến trúc chặn gọi AI viết cả truyện một lần
- [x] 2. Viết kiểu review (câu 16): bỏ chữ "tóm tắt", quy tắc review; ngôi thứ ba có máy kiểm (câu 11)
- [x] 3. Âm thanh tiết chế: tiếng động chỉ ở khoảnh khắc then chốt, có quãng gần như im 8–11% thời lượng
- [x] 4. Truyện chọn tiếng Việt hoặc tiếng Anh (câu 15) (làm cùng việc 1; A/B test chuyển sang việc 5 và 6 vì không đụng phần viết lời)
- [ ] 5. Khoá bối cảnh (bảng bối cảnh như bảng nhân vật) + nới biểu cảm, cấm mặt người (câu 12, 17)
- [ ] 6. Video Muse theo lời thoại (câu 18, 19): tối thiểu 5 s không cắt; thoại dài chia nhiều video, mỗi video theo đoạn thoại của nó (đổi cảnh, không chỉ đổi góc máy) — A/B test
- [ ] 7. Đo câu 10–13 có được tuân thủ không (câu 21); cái nào máy kiểm được thì làm khoá cứng
- [x] 1–3: commit `2e4c9ef`, `1e3d91e` (test: story_review 10, vụ án kiểm 6, khoá cứng 4, âm thanh 9)
- [ ] 8. Cập nhật bảng 1.1 và 1.3 theo câu 14–22 và code mới
- [ ] 9. Test trọn luồng trên server thử 8010 bằng trình duyệt, từng nút theo FEATURE_MAP, dịch vụ thật
- [ ] 10. Báo cáo cuối

# Bài A/B 02/11/2026 — bản không đội agent (nhánh `lam-bai`, bản sao riêng): ý 5 và ý 6 ở trên
- [x] Việc 1 — khoá bối cảnh: `services/location_sheets.py`, `routers/location_sheets.py`, `backend/static/location_sheets.js`, nút `#btn-location-sheets`. LLM (1 lượt, qua `ask_validated`) tìm nơi lặp lại ≥ 2 cảnh, Python kiểm; chủ dự án sửa tên, mô tả, số cảnh, tự thêm, bỏ; Muse vẽ ảnh chuẩn (cảnh trống), vẽ lại trong cùng side chat, duyệt. Chỉ nơi đã duyệt mới khoá: "Gen lại ảnh AI", bước 3 "Sản xuất video dài", "Muse 2K", "Muse Video" nhận mô tả cố định + ảnh chuẩn (bỏ ảnh chuẩn khi cận cảnh); Fleet Runner dặn Muse vai trò từng ảnh đính kèm
- [x] Việc 1 — nới biểu cảm đầu tròn: `ROUND_HEAD_EXPRESSION_RULE_EN` (lông mày nét, nước mắt, nửa mặt xám khi sợ; cấm mũi, mắt có tròng, mặt người, mặt anime) trong phong cách `horror_cartoon_2d`, bản giao việc video cao trào bỏ "không lông mày"; quy tắc tóc nữ giữ nguyên
- [x] Việc 2 — video Muse theo lời thoại: `services/dialogue_video.py`, `routers/scene_muse_video.py`, `backend/static/scene_muse_video.js`. Lời ≤ 8 s đọc: 1 video; dài hơn: chia đoạn liền nhau theo câu (ít đoạn nhất, tối đa 12), mỗi đoạn một việc Muse trong cùng side chat, prompt chứa đúng lời đoạn đó và luật đổi cảnh; hộp xác nhận báo số video Muse trước khi chạy; ghép: video k chiếm đúng thời gian đoạn k, video cuối giữ trọn; dựng: cảnh kéo thêm tối đa 5 s cho hết video, giọng đệm lặng; lỗi giữa chừng giữ video đã xong, bấm lại làm tiếp
- [x] Test mới: `tests/test_location_sheets.py` 18 đạt, `tests/test_dialogue_video.py` 14 đạt (Muse giả, LLM giả, ffmpeg thật). `tools/check.py` nhanh ĐẠT (Ruff không lỗi mới, 7 file JS, 35 test kiến trúc + bản đồ)
- [x] Giao diện (server thử, cổng 8011 vì 8010 bận): cửa sổ Bối cảnh mở được; "Tìm bối cảnh" báo rõ lỗi thiếu `NINEROUTER_API_KEY`; tự thêm bối cảnh 3 cảnh qua khung "+ Tự thêm"; duyệt ảnh chuẩn (ảnh giả đặt tay, vì không có Muse) → "Đã duyệt — đang khoá"; "Muse Video" cảnh 20 s báo "Cần 4 video Muse" kèm lời từng đoạn, cảnh 3 s báo 1 video; console không lỗi. Không bấm "Vẽ ảnh chuẩn (Muse)" (bị chặn quyền, bản sao không có Muse). Dự án thử chuyển ra `.cache/ab/`, `projects/` như trước (không có)
- [ ] Chưa kiểm chứng: chạy thật với Muse (ảnh chuẩn, ảnh cảnh có khoá, video nhiều đoạn có đổi cảnh đúng lời hay không) và LLM thật tìm bối cảnh trên dự án vụ án thật

# TASKS — một luồng làm truyện cho truyện chữ và vụ án (2026-11-03, nhánh `dong-bo-luong-truyen-va-vu-an`)

Chủ dự án: "đồng bộ thành 1 luồng cho dễ quản lý"; chỉ khác bước nội dung (truyện chữ kể kiểu review, vụ án viết lại).
Gốc lỗi video truyện 03/11: Bước 1 không có phong cách đầu tròn, truyện không có danh sách nhân vật, ảnh cảnh thường
không dùng bảng nhân vật (kể cả vụ án), 1-Click tự tạo ảnh trước khi khoá nhân vật.

## A. Lối vào chung (Bước 1)
- [x] A1. Ô "Loại nội dung": truyện chữ / vụ án có thật; vụ án dùng cùng API phân tích của cửa sổ Hồ Sơ Kỳ Án rồi mở cửa sổ đó để theo dõi, duyệt dàn ý, duyệt bảng tên
- [x] A2. Một danh sách phong cách cho Bước 1, cửa sổ vụ án, cài đặt dự án (có đầu tròn); test chặn lệch danh sách
- [x] A3. 1-Click không tự tạo ảnh (câu 4 mục 1.2): ảnh tạo sau khi khoá nhân vật, bối cảnh

## B. Nhân vật cố định dùng chung
- [x] B1. Truyện chữ có danh sách nhân vật: LLM tìm người + ngoại hình cố định + cảnh có mặt, code kiểm; tự chạy khi tạo dự án truyện, có nút chạy lại; vụ án lấy từ bảng tên như cũ
- [x] B2. Vẽ bảng nhân vật được khi chưa có ảnh cảnh
- [x] B3. Khoá nhân vật ở mọi lần tạo ảnh cảnh (nút ảnh từng cảnh, tạo lại hàng loạt, sản xuất video dài): mô tả cố định + ảnh bảng đã duyệt đính kèm Muse, Muse được dặn vai trò từng ảnh
- [x] B4. Nút Nhân vật, Video cao trào hiện cho mọi dự án có cảnh vẽ

## C. Phần dựng chung
- [x] C1. Cảnh truyện mang phần (vẽ nối tiếp), loại cảnh, tiếng động gợi ý, độ căng nhạc nền như cảnh vụ án
- [x] C2. Sản xuất video dài: tiếng động thưa áp dụng cả truyện

## D. Kiểm chứng
- [x] D1. Test mới + `tools/check.py --full`
- [x] D2. Bấm thật trên server thử 8010: Bước 1 hai loại, tạo truyện ngắn bằng LLM thật, tìm nhân vật, vẽ bảng, tạo ảnh có khoá, xem ảnh
- [x] D3. Cập nhật FEATURE_MAP.md, CLAUDE.md (bảng 1.1, 1.3, 5.1)

### Phát sinh khi bấm thật (03/11/2026)
- [x] Nút "Muse 2K" chỉ gửi mã phong cách ("horror_cartoon_2d") nên Muse vẽ mặt người: thêm `image_service.with_style()` (câu mô tả phong cách như mọi đường khác)
- [x] Thẻ cảnh treo "Đang sinh ảnh AI" sau khi Muse xong: `complete_task()` đặt `status_image` "ready"
- [x] Tìm nhân vật chỉ đọc lời review nên mất chi tiết (bộ ria bạc của bác bảo vệ): lưu truyện gốc `story_source.txt`, gửi kèm
- [x] Thanh nút Bước 2 chật khi truyện chữ hiện đủ nút: cho xuống dòng
- [x] Video truyện chữ im nhạc nền và không có tiếng động: độ căng đọc giá trị mặc định "ambient_low" trước nhịp kể; thêm `scene_sound.scene_energy()`, `has_energy_info()` (dự án không có nhịp kể giữ nhạc nền chung)
- [x] Cả video một kiểu chuyển động "zoom_in": nút Sản xuất video dài gửi chuyển động chung đè từng cảnh; bỏ (có từ ngày đầu repo)
- [x] Nhật ký sản xuất ghi "Nhân vật: Mặc định": nay ghi số nhân vật cố định và số bảng đã duyệt
- [ ] Bảng nhân vật vẽ trên tài khoản Muse video: vid_01, vid_02 hết phiên đăng nhập, không tài khoản video nào nhận việc (chủ dự án đăng nhập lại)

### Bằng chứng
- Test: `tests/test_one_flow.py` (21 bài) + sửa test cũ; `tools/check.py --full`: 989 đạt (trước 2 bản sửa cuối)
- Bấm thật server 8010: Bước 1 hai loại (vụ án: chặn lời gọi cuối để không sinh hồ sơ rác, kiểm dữ liệu gửi đi); truyện thử `proj_787e69c7` (LLM thật: 13 cảnh, 13 ý, 1 vòng; 3 nhân vật); Muse ảnh cảnh 1, 2, 10 đầu tròn, Khang giữ áo hoodie xám, bác Tư có ria bạc (`.cache/thu_dong_bo/`)
- Sản xuất video dài truyện thử 3 lần (lần 2, 3 không tốn Muse): `projects/proj_787e69c7/renders/story_final.mp4` 1080p 73,8 giây, nhạc nền 4 đoạn (có nhạc 0–7 s và 13–52 s, im ở đoạn giới thiệu và đoạn kết), tiếng động 3/13 cảnh, 5 kiểu chuyển động; cảnh 11 Muse từ chối nên rơi sang 9router (1 ảnh trả phí, có ghi cảnh báo)
- Khoá bối cảnh trên truyện: AI tìm 2 bối cảnh, ảnh chuẩn phòng ký túc xá duyệt, "Gen lại ảnh AI" cảnh 5 vẽ đúng phòng đó
- Tốn: LLM khoảng 6 lượt (viết, kiểm, tìm nhân vật 2 lần, tìm bối cảnh); Muse ảnh 17 lượt (15 ảnh cảnh, 1 ảnh chuẩn, 1 lượt Muse từ chối cảnh 11), Muse video 1 lượt hỏng (hết phiên đăng nhập); 9router ảnh trả phí 1

## Đưa repo lên GitHub (05/11/2026)

Chủ dự án giao: chuẩn bị file cần thiết và push lên GitHub để người khác pull về chạy được, có file hướng dẫn. Chủ dự án chọn repo riêng tư, chỉ đẩy nhánh `master`.

- [x] Rà bí mật trước khi đẩy: 216 commit không từng chứa `.env`, `backend/chrome_profiles/`, `backend/config/muse_fleet_accounts.json`; giá trị khoá trong `.env` không xuất hiện ở commit nào; chuỗi giống khoá duy nhất là khoá giả trong `tests/test_case_adaptation_llm.py`
- [x] `README.md` viết lại cho người mới (phần mềm cần có kèm lệnh winget, clone, cài, 9router, Muse, chạy, cập nhật, lỗi thường gặp)
- [x] `tools/cai_dat.bat`: tạo `.venv` bằng Python 3.14, cài thư viện, chép `.env`, báo thiếu ffmpeg/Node.js/9router/uv. Không tải Chromium của Playwright vì Fleet Runner dùng Chrome/Edge có sẵn
- [x] `.gitattributes`: `.bat` luôn xuống dòng CRLF trên máy clone
- [x] `tests/test_feature_map.py` bỏ qua đường dẫn `.cache/` (máy clone không có, test báo lỗi giả)
- [x] Repo riêng tư https://github.com/Nagias/story-studio, nhánh `master`
- [ ] `tests/test_muse_fleet_runner_integration.py::test_fleet_runner_10_accounts_loaded` lỗi trên máy chủ dự án (đọc file tài khoản Muse thật, có tài khoản video mang khả năng tạo ảnh); có từ trước, đạt trên máy clone

### Bằng chứng
- Bản sao sạch trong `.cache/thu-clone/`: `tools/cai_dat.bat` lần đầu mã thoát 0 (49 giây, thư viện đã có trong cache pip), chạy lại 2 giây giữ `.env`; giấu ffmpeg/node/9router/uv khỏi PATH thì báo đủ 4 dòng thiếu, vẫn mã thoát 0
- Bản sao sạch: bộ test mặc định 989 đạt, 3 lỗi (2 test hook git chưa cài, 1 test FEATURE_MAP đòi file `.cache/`); sau khi sửa test và cài hook theo README: 3 test FEATURE_MAP đạt, 14 test hook đạt
- Bản sao sạch chạy `run.py` cổng 8020 (tắt Fleet Runner, hàng việc vụ án, VieNeu): trang chính, mọi file JS/CSS, `/api/health`, `/api/projects` trả 200, console không lỗi
- Repo gốc `tools/check.py --full`: 991 đạt, 1 lỗi (test 10 tài khoản ở trên); `projects/` không đổi
- Clone lại từ GitHub: commit khớp `63f8296`, 288 file, 0 file bí mật, `run.bat` xuống dòng CRLF

## Video vụ án Khang Cúc Hoa (đêm 05–06/11/2026, chủ dự án giao làm một mạch)
Dự án `proj_crime_03b5d8c5`, vụ `_cases/case_4242cd2b`, phong cách đầu tròn `horror_cartoon_2d`, giọng `vi-VN-NamMinhNeural`.
- [x] Phân tích vụ, viết lời kể 72 cảnh (4.330 chữ); kiểm 60 tên thật: 0 lần lọt. Sửa tay cảnh 38 và 68 (app gộp nhầm hai nạn nhân cùng họ)
- [x] Khoá nhân vật: 7 bảng nhân vật duyệt (Chu Khải Phong vẽ 3 lần; Chu Tố Linh còn một ô sau gáy trọc, nhận vì chỉ có 1 cảnh). 4 nhân vật không có mặt trong cảnh nào để nháp
- [x] Khoá bối cảnh: 7 nơi, 7 ảnh chuẩn Muse, xem từng ảnh rồi duyệt
- [x] Sản xuất video dài 02:25:42 → 04:27 (khoảng 2 giờ): `renders/story_final.mp4`
- [x] Kiểm chứng: ffprobe 1172 giây (19 phút 32 giây), 1920x1080, 25 khung/giây, AAC 48 kHz stereo, 320 MB; âm lượng trung bình −18,7 dB, đỉnh −1,6 dB, không có đoạn im lặng trên 1,5 giây; 72/72 file giọng, tổng 19,54 phút; phụ đề 650 câu, 4.340 chữ; xem 24 khung hình cắt đều: đầu tròn, bối cảnh khớp
- [ ] Còn lại: cảnh 2 và 13 do Muse không trả ảnh (NO_MEDIA sau 150 giây) nên app tự chuyển sang 9router (trả phí, 2 ảnh); ảnh cảnh 2 vẽ cô gái không phải đầu tròn. 49 cảnh báo "bằng chứng chưa hiện lên bảng" (không chặn)
- Số lần gọi: Muse 68 ảnh (10 bảng nhân vật, 7 bối cảnh, 51 ảnh cảnh kể cả 2 lần lỗi); 9router ảnh 2; LLM: phân tích vụ 89 bước + 1 lần tìm bối cảnh. `projects/` chỉ thêm `proj_crime_03b5d8c5`
- [x] 06/11 tối, chủ dự án báo một chỗ có 2 phụ đề cùng lúc: nguyên nhân là Edge-TTS trả giọng cảnh 52 bị cụt (6,96 giây, mốc chữ tới 13,3 giây), app vẫn nhận. Sửa `tts_service.generate_speech()`: chữ cuối trễ hơn độ dài tiếng quá 0,5 giây thì thu lại, hết lượt thì báo lỗi; test `tests/test_tts_cut_audio.py` (2 test, đỏ trước khi sửa). Quét mọi dự án: chỉ cảnh 52 bị cụt. Thu lại cảnh 52 (14,6 giây) và dựng lại trên server thử 8010 (server 8000 đã tắt): 1179,9 giây, 0 chỗ phụ đề chồng, 0 file giọng cụt. Bản cũ giữ ở `.cache/vu_an/story_final_ban1.mp4`
- [x] Kiểm chứng: 6 test Edge-TTS thật đạt; `tools/check.py --full`: 993 đạt, 1 lỗi có sẵn từ trước (`test_fleet_runner_10_accounts_loaded` đòi đúng 5+5 tài khoản Muse, câu 22 mục 1.2), lỗi cả khi bỏ phần sửa
- [x] 06/11 chủ dự án bảo "Chạy video Muse": "Video cho cảnh cao trào" trên server 8000. Chọn 25 cảnh (bỏ 9 cảnh phong cảnh, đồ vật, người không tên; thêm 9 cảnh có nhân vật; gán nhân vật cho cảnh 11, 17). Lưới 9 ô: 21:45–22:32, 25 lưới; duyệt 23, trả về 004 (người chồng mặt anime) và 055 (ô cuối mặt người)
- [x] Lượt làm clip 1 (06/11 22:33 → 07/11 12:13): 18 cảnh ra clip, 5 cảnh AGENT_TIMEOUT 75 phút (007, 021, 033, 037, 045). Lưới 055 vẽ lại đạt, duyệt; lưới 004 vẽ lại người chồng vẫn lệch (tóc rối, mặt người) nên bỏ cảnh 004, giữ ảnh tĩnh
- [x] Lượt làm lại (07/11 12:14 → 14:05): 007, 021, 033, 037 xong mỗi cảnh 5–8 phút vì app mở lại đúng chat Muse cũ, Muse đã làm xong ở đó sau mốc 75 phút (tức "treo" lần 1 thật ra là làm lâu); 055 ra clip; 045 hỏng lần 2, lần này treo thật (chat mới, Muse chỉ nói "👍" rồi im 75 phút), không chạy lần 3
- [x] Tài khoản Muse 07/11: chỉ `muse_acc_vid_03` (video) và `muse_acc_img_01` (ảnh) còn sống; 8 tài khoản video khác báo mất phiên. Mọi clip làm trên một tài khoản, từng cảnh một: 9–82 phút mỗi cảnh
- [x] Dựng lại video dài 14:06 → 14:21: `renders/story_final.mp4` 1180,2 giây, 1920x1080, 337 MB; bản trước giữ ở `.cache/vu_an/story_final_ban2.mp4`
- [x] Kiểm chứng: 23 clip, mỗi clip dài hơn lời đọc 0–1 giây, không clip nào trùng file; trích 3 khung mỗi clip: đầu tròn, nhân vật khớp bảng; 23 đoạn dựng khớp clip gốc (lệch dưới 1/255); xem khung hình video cuối ở cảnh 005, 021, 055, 068: đúng hình clip; clip chiếm 388,2 / 1180,1 giây = 32,9%; phụ đề chồng 0; giọng cụt 0 (mọi dự án); `projects/` không thêm dự án
- [ ] Còn dưới mức 50% video Muse: app chỉ chọn tối đa một nửa số cảnh có người, 20 cảnh bảng chữ và lời cảnh báo không làm clip được; cảnh 004, 045 vẫn là ảnh tĩnh
- Số lần gọi Muse cho clip: 25 lưới + 2 lưới vẽ lại; việc làm clip 29 lượt (lượt 1: 18 xong + 5 hỏng; lượt làm lại: 5 xong + 1 hỏng); mỗi lượt Muse tự khai tối đa 6 video + 4 ảnh

### Bản tiếng Anh (10/11/2026)
- [x] `POST /api/projects/proj_crime_03b5d8c5/create-language-version` trên server 8000: dự án `proj_crime_f297bced` "Shadows in the Cornfield", 72 cảnh, 72 ảnh, 23 clip Muse chép từ bản Việt; không cảnh nào phải viết lại (0 lượt LLM, 0 lượt Muse). Giọng `en-US-AndrewMultilingualNeural`
- [x] Kiểm lời Anh (`.cache/vu_an/kiem_ten_en.py`): 41 tên trong danh sách cấm, lọt 0; con số nhận dạng 0; tên dạng Việt 0; 2.899 chữ. Cảnh 38, 68 (đã sửa tay ở bản Việt) đúng ý ở bản Anh
- [x] Dựng: 1256,8 giây (20 phút 57 giây), 1080p; clip chiếm 404,1 giây = 32,2%; thẻ cảnh báo và bảng hồ sơ bằng tiếng Anh
- [x] Lỗi phụ đề nháy hai dòng: kiểu `kinetic_pop` giữ mỗi chữ tối thiểu 0,12 giây nên dòng chữ trước chưa tắt thì dòng chữ sau đã hiện (bản Anh 388 chỗ, bản Việt 7 chỗ; lần kiểm trước chỉ đọc SRT nên không thấy). Sửa `subtitle_engine.generate_karaoke_ass()`: dòng tắt khi chữ sau hoặc cảnh sau bắt đầu; test `tests/test_subtitle_no_overlap.py` (đỏ trước khi sửa). Dựng lại cả hai bản trên server thử (cổng 8011 vì 8010 bị chương trình khác giữ): phụ đề ASS chồng 0 ở cả hai bản, SRT chồng 0, giọng cụt 0; xem khung hình phút 5:36 bản Anh còn một dòng. Bản trước giữ ở `.cache/vu_an/story_final_en_ban1.mp4`
- [x] `tools/check.py --full`: 999 đạt, 1 lỗi có từ trước (`test_fleet_runner_10_accounts_loaded`). `projects/` chỉ thêm `proj_crime_f297bced`
- [ ] Bản Anh: 14/23 cảnh có lời dài hơn clip, app giữ khung cuối của clip cho phần dư (dài nhất 3,2 giây ở cảnh 13, tổng 18,7 giây); muốn hết phải làm clip Muse dài hơn (tốn Muse)


# TASKS — đổi cổng AI từ 9router sang CLI Proxy (2026-11-09, nhánh `doi-sang-cli-proxy`)

- [x] `.env`: `NINEROUTER_BASE_URL=http://127.0.0.1:8317/v1`, key CLI Proxy do chủ dự án dán; model bỏ tiền tố `ag/`: chữ `gemini-3.8-flash-high`, ảnh `gemini-3.1-flash-image`, chia cảnh `gemini-3-flash` (CLI Proxy không có `-low`). Dòng 9router cũ giữ dạng ghi chú; bản sao `.cache/env.backup-truoc-cli-proxy`
- [x] `tests/conftest.py`: chặn cổng 8317 cho test không gắn cờ `live` (kiểm bằng test tạm: bị chặn, đã xoá test tạm)
- [x] `image_service.generate_9router_gemini`: CLI Proxy trả HTTP 400 "not supported on /v1/images/generations" cho model ảnh Gemini → gọi `/chat/completions` qua hàm mới `case_adaptation_llm.call_chat_image` (đường cấm 5: không viết client LLM riêng; tách phần gửi chung `_post_chat`, `call_llm_json` giữ nguyên hành vi), lấy ảnh ở `choices[0].message.images`; 9router vẫn đi `/images/generations` như cũ. Test `tests/test_image_gemini_chat_endpoint.py` (4 test)
- [x] Đo thật qua code app: `call_llm_json` 4,6 s; chia cảnh đoạn `dossier.txt` (1.481 ký tự): `gemini-3-flash` 3,3 s / 6 cảnh, `gemini-3.5-flash-lite` 3,5 s / 6 cảnh, `gemini-3.8-flash-high` 24 s / 6 cảnh, không cảnh nào rơi về chia offline; ảnh Gemini 10,6 s, 1376×768, mở xem đúng nội dung. `projects/` không có thư mục mới
- [ ] Chưa làm (đề xuất): đổi mặc định `config.py`, `.env.example`, README, `tools/cai_dat.bat`, CLAUDE.md mục 3, chữ "9router" trong thông báo lỗi và giao diện

## Video vụ án xưởng sắt Cao Hùng, bản tiếng Anh (08–10/11/2026, chủ dự án giao: 50% video Muse, chèn 8 ảnh thật, dịch hết sang tiếng Anh)
Dự án `proj_crime_59ee682e`, vụ `_cases/case_9ad5c9bf`, ngôn ngữ `en`, phong cách đầu tròn `horror_cartoon_2d`, giọng `en-US-AndrewMultilingualNeural`, nhạc nền `mysterious_dark`.
- [x] Phân tích vụ, viết lời kể tiếng Anh 75 cảnh (2.853 chữ), tên hư cấu
- [x] Khoá nhân vật: bảng nhân vật duyệt sau khi vẽ lại (thám tử, A Li, con gái: tóc lệch; A Qiang đổi thiết kế thành đầu hói). Sửa mô tả con gái thành phụ nữ khoảng 35 tuổi (cảnh 49, 64, 65, 70)
- [x] Khoá bối cảnh: 8 ảnh chuẩn Muse
- [x] Giọng đọc 75/75 cảnh, tổng 1.246,3 giây, 0 file cụt
- [x] Ảnh cảnh: 48 ảnh, tất cả bằng Muse. Cảnh 36 Muse từ chối hai lần (thuốc, dây trói) nên viết lại mô tả nhẹ hơn (người mẹ kéo khoá túi vải)
- [x] Video Muse theo lời thoại: 48/48 cảnh hoạt hình, 840,9 giây
- [x] Chèn 8 ảnh thật vào cảnh 8, 10, 13, 16, 28, 33, 43, 51; chú thích tiếng Anh, tên đổi theo tên hư cấu. Ảnh số 3 (cảnh 16): chú thích dưới đè phụ đề nên dời lên trên và thu ảnh vào trong khung để hiệu ứng phóng to không cắt chữ (dựng lại 2 lần; bản đầu giữ ở `.cache/vu_xuong_sat/story_final_ban1.mp4`)
- [x] Dựng `renders/story_final.mp4`: 03:43 → 04:00 (16 phút)
- [x] Kiểm chứng: ffprobe 1.283,9 giây (21 phút 24 giây), 1920x1080, 25 khung/giây, AAC 48 kHz stereo, 424 MB; 48 clip Muse khác nhau, khung trong video cuối khớp clip gốc; clip Muse chiếm 840,9 / 1.283,8 giây = 65,5%; phụ đề 450 câu, chồng 0; âm lượng trung bình −18,7 dB, đỉnh −1,3 dB; 4 chỗ lặng 1,6–2,9 giây đều ở cuối cảnh có clip dài hơn lời (đúng câu 19 mục 1.2); xem 24 khung cắt đều và khung 8 cảnh ảnh thật; `projects/` chỉ thêm `proj_crime_59ee682e` và `_cases/case_9ad5c9bf`
- [x] Sự cố: tài khoản `muse_acc_img_01` treo trình duyệt 13:50–19:17 ngày 09/11, chặn một trong hai luồng của Fleet Runner nên 25 ảnh hết giờ; app Claude tắt hai lần làm server 8000 tắt theo (19:17 và 00:19), bật lại bằng `run.py --no-browser` và chạy tiếp từ chỗ dở
- Số lần gọi: LLM 94 bước phân tích + 1 lần tìm bối cảnh; Muse ảnh: 13 bảng nhân vật (kể cả vẽ lại), 8 bối cảnh, 48 ảnh cảnh thành công + 29 lượt lỗi (25 hết giờ do tài khoản treo, 4 Muse từ chối/không trả ảnh); Muse video theo lời thoại 155 lượt; 9router ảnh: các lần rơi sang đều báo lỗi 403/502, 0 ảnh trả phí

## Video vụ xưởng sắt bản tiếng Anh: làm lại phần video Muse (10–11/11/2026)
Chủ dự án xem bản trước: clip Muse "không hề là video", chỉ lia/zoom ảnh. Đo lại đúng vậy: 48 clip "Muse Video theo lời thoại" (`services/dialogue_video.py`) sau khi trừ chuyển động máy quay chỉ còn 3,8–6,6 (ảnh tĩnh zoom = 3,8). Làm lại bằng "Video cho cảnh cao trào" như vụ Khang Cúc Hoa.
- [x] Sửa gốc lỗi "lần nào cũng phải nhắc": `pick_climax_scenes()` coi 50% là mức trần số cảnh (Khang Cúc Hoa chỉ 32,9%); nay chọn cảnh có nhân vật tới khi lời kể đạt ít nhất 50% thời lượng, bỏ mức trần khi bật thêm cảnh (commit `6a2b4c4`, câu 24 mục 1.2)
- [x] Gán nhân vật cảnh 20 (A Cường, Tạ Khải Viễn); bỏ nhân vật khỏi 8 cảnh ảnh thật để không bị chọn. Chọn 38 cảnh, lời kể 636,6 / 1.246,3 giây = 51,1%
- [x] Lưới 9 ô: 38 lưới 23:34 → 01:20; duyệt 36; cảnh 19 vẽ lại 2 lần (A Cường sai áo, mặt màu da, thừa người; lần 2 Muse không trả ảnh), cảnh 20 vẽ lại 1 lần (thám tử bị vẽ hói)
- [x] Clip: 01:22 → 07:14, 38/38 xong (cảnh 57 quá 75 phút lần đầu, làm lại được); xem tận mắt: thám tử bước vào rồi ngồi xổm (cảnh 5), xếp đồ rồi chạy xe máy (cảnh 42), cô gái đi rồi người cắt cỏ thấy thi thể (cảnh 50)
- [x] Sửa lỗi phụ đề chữ nhảy chạy trước hình (lệch tới ~38 giây cuối video): ASS cộng dồn theo độ dài giọng, đoạn hình dài hơn vì clip Muse dài hơn lời; nay dùng độ dài đoạn hình như .srt (`video_service.subtitle_scene_timing()`, commit `6368a06`, test `tests/test_kinetic_subtitle_timing.py` đỏ trước khi sửa)
- [x] Dựng lại `renders/story_final.mp4` 07:37 → 07:49; bản trước giữ ở `.cache/vu_xuong_sat/story_final_ban3_clip_cu.mp4`, `story_final_ban4_phude_lech.mp4`; 48 clip cũ ở `.cache/vu_xuong_sat/clip_loi_thoai_cu/`
- [x] Kiểm chứng: 1.283,9 giây, 1920x1080, 25 khung/giây, AAC 48 kHz; 38/38 cảnh trong video cuối khớp clip Muse (không phải ảnh tĩnh), 38 clip khác nhau; video Muse 665,6 / 1.283,8 giây = 51,8%; giọng khớp hình (tương quan 0,83–0,88 ở cảnh 5, 42, 72); phụ đề in trên hình khớp câu đang đọc ở 10 điểm từ giây 59 tới 1276; âm lượng −18,7 dB, đỉnh −1,3 dB; 0 file giọng cụt; `tools/check.py --full`: 1.000 đạt, 1 lỗi có sẵn (`test_fleet_runner_10_accounts_loaded`, câu 22)
- [ ] 10 cảnh hoạt hình không có người (2, 6, 14, 41, 46, 53, 54, 70, 73, 75) vẫn dùng clip cũ chỉ lia máy quay; không tính vào 51,8%
- [x] Quét video vụ Khang Cúc Hoa (`proj_crime_03b5d8c5`, bản dựng 10/11 22:50): KHÔNG lệch. Độ dài đoạn hình trùng cách tính phụ đề (lệch tối đa 0,09 giây); xem 6 điểm từ giây 196 tới 1176, chữ trên hình khớp câu đang đọc. Lỗi lệch chỉ xảy ra khi đoạn hình được kéo dài hơn giọng (clip theo lời thoại dài hơn lời, câu 19 mục 1.2)
- Số lần gọi Muse: 38 lưới + 4 lần vẽ lại (1 lần không trả ảnh); 39 việc làm clip (38 + 1 làm lại cảnh 57), mỗi việc Muse tự khai tối đa 6 video + 4 ảnh. Thử nghiệm trước đó: 2 video ép cử động (cảnh 5, 20). `projects/` có thêm `proj_crime_f297bced` (bản Anh vụ Khang Cúc Hoa, tạo 21:42 ngày 10/11, không do phiên này tạo)

# TASKS — sửa một lượt các lỗi còn lại của hai video Khang Cúc Hoa và Vương Nghĩa Tường (11/11/2026, nhánh `sua-loi-hai-video`)
Chủ dự án: "tổng hợp ... rồi giải quyết 1 lần. Đừng làm kiểu lắt nhắt sửa trong lúc làm video". Nhánh tách từ `video-muse-du-50-phan-tram` (chưa gộp `master`), lấy thêm commit ghi chép `d88778b` của nhánh `video-vu-xuong-sat`.
- [x] 1. Fleet Runner: mỗi việc có trần thời gian (`task_ceiling_sec()`), trình duyệt treo thì bỏ việc với lỗi TASK_HUNG, đóng trình duyệt (đóng cũng có trần), luồng nhận việc khác. Gốc: vụ xưởng sắt, một lệnh đọc trang của `muse_acc_img_01` đứng im 13:50–19:17 ngày 09/11, 25 ảnh hết giờ
- [x] 2. Video Muse đòi cử động thật, máy quay đứng yên: `services/muse_motion.py`; video theo lời thoại thêm luật; việc video không ghi máy quay thì đặt máy quay đứng yên (bỏ mặc định "lia máy chậm")
- [x] 2b. GỐC lỗi "không phải video" ở cả hai vụ: bản giao việc "Video cho cảnh cao trào" (`climax_brief.py`, từ 28/10) viết "nhân vật cử động ít hoặc chạy tại chỗ vẫn đạt" và "bị loại thì giảm cử động". Đo thật: 34/38 clip cao trào vụ xưởng sắt và 13/23 clip Khang Cúc Hoa gần như đứng hình; xem tận mắt 6 clip điểm 0 (cảnh 7, 20, 37, 42, 59 xưởng sắt; 21 Khang Cúc Hoa): chỉ đổi nét mặt hoặc đứng im. Nay bản giao việc đòi hành động bằng cơ thể, chỉ đổi nét mặt hay chỉ lia/zoom là không đạt, làm lại không được bớt cử động
- [x] 3. Đo cử động tự động (`services/clip_motion.py`: bù máy quay, đo phần ảnh đổi thật giữa hai khung cách 1 giây, bách phân vị 90). Hiệu chỉnh trên 125 clip thật: 10/10 clip chỉ lia/zoom ra 0; clip người cử động rõ ra 1,6–10,6; cử động rất nhỏ (người ôm đầu lắc nhẹ, Khang Cúc Hoa cảnh 21) cũng ra 0, nên chỉ cảnh báo "nên xem lại", không loại clip. Thẻ cảnh cao trào có cảnh báo khi clip gần như đứng hình; mỗi lần dựng (cả hai nút dựng) ghi tỉ lệ video Muse, số giây thiếu so với 50%, danh sách cảnh nghi đứng hình vào nhật ký dựng và `metadata.video_share` (`services/video_share.py`)
- [x] 4. "Chọn cảnh cao trào" báo phần trăm đạt được, dưới 50% thì báo vàng (`coverage()`; bản Anh Khang Cúc Hoa chỉ đạt 49,2% vì cảnh có nhân vật không đủ)
- [x] 5. Clip ngắn hơn lời: kéo chậm tối đa 1,25 lần (`clip_stretch()`), còn thiếu mới giữ khung cuối
- [x] 6. Ảnh cảnh Muse "không trả ảnh" (Khang Cúc Hoa cảnh 2, 13): KHÔNG phải Muse lỗi. Nhật ký runner: 3 lượt trên 2 tài khoản Muse đều viết "Đã tạo xong" nhưng runner không thấy ảnh trên trang, nên app rơi sang ảnh trả phí không theo bảng nhân vật. Không tái hiện được nếu không chạy Muse; không đoán mò sửa đoạn tìm ảnh (dễ nhận nhầm ảnh cũ). Thêm: lần sau NO_MEDIA thì runner lưu ảnh chụp trang + danh sách mọi ảnh/video trên trang vào `.cache/muse_no_media/` (giữ 30 lần) để sửa tận gốc
- [x] 7. Test `test_fleet_runner_10_accounts_loaded` thay bằng test kiểm mỗi tài khoản có khả năng đúng loại, số lượng tuỳ máy (câu 22 mục 1.2; commit `efc2832` sửa test khác, test này vẫn lỗi tới nay)
- [x] 8. Kiểm chứng (dưới)
- Không cần làm: video Khang Cúc Hoa (bản Việt dựng 10/11 22:50 và bản Anh) KHÔNG lệch phụ đề chữ nhảy: so 650/650 câu bản Việt, 430/434 câu bản Anh, lệch tối đa 0,01 giây (ghi chú cũ "nhiều khả năng lệch" sai; phiên vụ xưởng sắt cũng kết luận vậy, commit `6579423`)

### Bằng chứng
- Test mới đỏ trước khi sửa: `tests/test_muse_runner_hang.py` (4 đỏ → 6 đạt), `tests/test_muse_real_motion_prompt.py` (3 đỏ → 3 đạt), `tests/test_short_clip_stretch.py` (3 đỏ → 3 đạt); `tests/test_clip_motion_and_share.py` 9 đạt (clip tự tạo: ảnh tĩnh zoom/lia ra dưới ngưỡng, người đi + giơ tay ra trên ngưỡng). Sửa `tests/test_climax_brief.py` theo luật mới ("chạy tại chỗ" → "không phải ảnh chuyển động")
- `tools/check.py --full`: 1.024 đạt, 0 lỗi (4 phút 27 giây); mốc Ruff 54 → 53
- Dựng lại bản Anh Khang Cúc Hoa (`proj_crime_f297bced`) trên server thử cổng 8011 (8010 do chương trình khác giữ), 14:04 → 14:13, 0 lượt Muse, 0 lượt LLM: 1.256,8 giây, 1920x1080, 25 khung/giây, AAC 48 kHz stereo, 347 MB; nhật ký dựng tự báo "Video Muse: 404,1 / 1256,9 giây = 32,1%", "DƯỚI 50%: thiếu khoảng 224,4 giây", 13 cảnh nghi đứng hình. 12/14 cảnh có clip ngắn hơn lời chạy hình tới hết cảnh; cảnh 39, 40 đứng ngay trong clip gốc Muse (nằm trong danh sách nghi đứng hình). Cuối cảnh 13: bản cũ hai khung cách 0,8 giây khác nhau 0,01 (đứng hình), bản mới khoảng 6,0. Phụ đề chữ nhảy lệch tối đa 0,01 giây, SRT chồng 0. Bản trước giữ ở `.cache/vu_an/story_final_en_ban2.mp4`, project.json trước khi dựng ở `.cache/vu_an/project_en_truoc_dung_lai_11-11.json`
- Báo cáo tỉ lệ tính trên dữ liệu thật (không dựng lại): xưởng sắt 65,5% là clip nhưng 44/48 cảnh nghi đứng hình; Khang Cúc Hoa bản Việt 32,9%, thiếu 201,8 giây, 13 cảnh nghi đứng hình
- Giao diện (server thử 8011, dự án thử `proj_ea5b04db`, giả lập máy chủ trong trình duyệt nên không ghi dữ liệu): bấm `#btn-climax-video-pick` hiện "Đã chọn 2 cảnh có nhân vật, nhưng chỉ đạt 49,2%, dưới mức 50% video Muse..."; console không lỗi; `project.json` dự án thử không đổi
- `projects/` không thêm thư mục; file điểm cử động `*.motion.json` nằm cạnh các clip đã đo

### Còn lại (cần chủ dự án quyết, tốn Muse)
- [ ] Hai video hiện có vẫn phần lớn là clip gần như đứng hình (xưởng sắt 44/48 cảnh, Khang Cúc Hoa 13/23) và Khang Cúc Hoa chỉ 32–33% video Muse: muốn sửa phải làm lại clip bằng bản giao việc mới (mỗi cảnh 1 việc Muse, tối đa 6 video + 4 ảnh, 9–82 phút/cảnh khi chỉ còn 1 tài khoản video)
- [ ] Bản giao việc mới (đòi cử động) chưa chạy thật với Muse: chưa biết Muse có giữ đầu tròn khi cử động nhiều không (thử 10/11 cảnh 20 thì giữ được)
- [ ] Khang Cúc Hoa cảnh 2, 13 vẫn là ảnh 9router không đầu tròn; cảnh 004, 045 vẫn là ảnh tĩnh
- Không sửa: hai nạn nhân cùng họ bị gộp (bài gốc chỉ gọi "cô gái họ Trương", hiếm, đã sửa tay, muốn tái hiện phải chạy LLM); 49 cảnh báo "bằng chứng chưa hiện lên bảng" (chỉ là thông báo); Muse từ chối cảnh có thuốc/dây trói (viết lại mô tả tay); chèn ảnh thật vẫn làm bằng script ngoài app (`.cache/vu_xuong_sat/ve_chu_anh.py`)

# TASKS — khoá cứng "khoảng 50% video là video Muse" và làm lại hai video (11–12/11/2026, nhánh `khoa-cung-50-video-muse`)
Plan chủ dự án duyệt: `C:\Users\pc\.claude\plans\gi-l-p-plan-c-c-effervescent-boole.md`. Chủ dự án chọn 11/11: chặn dưới 45% (mục tiêu 50%), áp dụng mọi dự án, cảnh phong cảnh không người được làm video và được tính, thử 2 cảnh trước rồi làm hết.

## Phần 1–2: khoá cứng (code) và kiểm chứng không tốn Muse
- [x] `services/video_share.py`: một nơi tính tỉ lệ; chỉ tính clip máy đo thấy có cử động hoặc chủ dự án đã duyệt ("Đã xem, có cử động", gắn với đúng file clip). `require_gate()` trước `assemble_full_video()` ở cả hai đường dựng; kiểm ngay khi bấm (409 `VIDEO_SHARE_LOW`) và chốt cuối trước giai đoạn 4. Bản nháp `draft` ra `renders/story_nhap_duoi_45.mp4`, không ghi đè thành phẩm, không đổi video cuối, không vẽ thumbnail
- [x] `services/render_inputs.py` (chuyển từ `routers/api.py`); router mới `routers/video_share.py` (`GET video-share`, `PUT motion-review`)
- [x] Giao diện: bị chặn thì hộp xác nhận hỏi dựng bản nháp; thẻ cảnh có clip nghi đứng hình hiện "Clip gần như đứng hình: chưa tính" + nút "Đã xem, có cử động" / "Bỏ duyệt" (theo số đo máy chủ, áp cho mọi clip, kể cả clip cũ); nút chọn cảnh báo đỏ dưới 45%, vàng dưới 50%
- [x] Cảnh vẽ không có nhân vật: video phong cảnh (`landscape_brief()`, không lưới 9 ô), chọn thêm khi cảnh có người không đủ 50%. Cảnh ảnh thật (`metadata.real_photo`) không bao giờ làm video (gắn cho 8 ảnh thật vụ xưởng sắt: cảnh 8, 10, 13, 16, 28, 33, 43, 51)
- [x] Khoá cứng: `tests/test_architecture.py::test_every_final_render_passes_the_video_share_gate` (thử gỡ chốt: test lỗi, trả lại: đạt), đường cấm 17 và dòng 17 bảng 5.1 trong CLAUDE.md
- [x] Test: `tests/test_video_share_gate.py` 16 (đỏ trên code cũ: lỗi nạp vì chưa có chốt), sửa `test_climax_video.py`, `test_clip_motion_and_share.py`, `test_climax_brief.py`; `tools/check.py --full` 1.039 đạt, 0 lỗi (2 lần)
- [x] Bấm thật server thử 8011, bản Anh Khang Cúc Hoa: 13 thẻ có nhãn + nút duyệt; "Sản xuất video dài" bị chặn, hộp xác nhận báo 14,2% (178,1 / 1.256,9 giây), thiếu 387,5 giây để đạt 45%, liệt kê 13 cảnh; chọn không: về Bước 2, không file nào được ghi; duyệt cảnh 21: 178,1 → 194,1 giây (đúng 16,08 giây của cảnh), bỏ duyệt: về 178,1; chọn bản nháp: ra `story_nhap_duoi_45.mp4` 1.256,8 giây 1920x1080, `story_final.mp4` giữ nguyên (14:17), video cuối của dự án không đổi, nhật ký ghi "BẢN NHÁP". File nháp thử chuyển ra `.cache/thu_khoa_cung/ban_nhap_kch_en/`. Dòng "Rạp Chiếu Phim Thành Phẩm" ở bản nháp đã sửa thành câu bản nháp

## Phần 3: thử thật 2 cảnh vụ xưởng sắt với Muse (server 8000, tài khoản `muse_acc_vid_03`)
- [x] Cảnh 2 (phong cảnh): 7 phút, điểm cử động 7,13; xem 6 khung: khói tràn vào, cửa đóng mở, giấy trên sàn đổi chỗ
- [x] Cảnh 7 lần 1: Muse bỏ clip AI méo đầu rồi TỰ DỰNG 3 clip từ ảnh tĩnh bằng công cụ trên máy (máy quay, đèn nhấp nháy), vẫn tự chấm ĐẠT; máy đo 0,0 và gắn cảnh báo. Chỉnh bản giao việc một lần: cấm tự dựng clip giả (`AI_CLIPS_ONLY`), mỗi clip một hành động 3–6 giây với khung đầu và khung cuối từ storyboard
- [x] Cảnh 7 lần 2: 9 phút, 5 video AI, điểm 14,37; xem 8 khung: cúi người, với tay tới điện thoại, chỉ vào cốc, đứng dậy chỉ ra cửa; đầu tròn trắng giữ nguyên
- Clip cũ giữ ở `.cache/thu_khoa_cung/`

## Phần 4: làm lại clip (đang chạy)
- [x] Gốc lỗi "Muse vẽ xong mà runner không thấy ảnh" (Khang Cúc Hoa cảnh 2, 13): bằng chứng `.cache/muse_no_media/` cho thấy runner có thấy ảnh 2048x1152 nhưng loại vì vân tay 8x8 giống ảnh chuẩn bối cảnh đính kèm. Đo 77 ảnh cảnh thật: ảnh đính kèm hiện lại khác gốc ≤ 0,3, ảnh cảnh mới ≥ 3,1 (ảnh xám 64x36). Nay chỉ loại khi giống cả vân tay lẫn từng điểm ảnh (< 1,5). Test đỏ trước khi sửa
- [x] Muse báo hết lượt dùng mà runner chờ đủ 75 phút rồi lượt chạy ghi lỗi hàng loạt: runner nhận câu hết lượt (`muse_quota_message()`, mã QUOTA_EXCEEDED) và bỏ việc ngay; lượt chạy video cao trào dừng khi không còn tài khoản video (`STOP_RUN_WORDS`), cảnh chưa tới giữ nguyên. Test đỏ trước khi sửa
- [x] Cảnh ảnh thật bị chọn nhầm làm video phong cảnh: thêm `metadata.real_photo` (xem Phần 1–2)
- [ ] **DỪNG ở điểm dừng của plan (12/11 03:22)**: tài khoản video duy nhất `muse_acc_vid_03` hết lượt dùng Muse ("You've reached your usage limit. Upgrade now or invite friends to get more Muse tokens."); 6 tài khoản video khác cần đăng nhập lại (`muse_acc_vid_04`, `vid_05`, `vp_01`–`vp_04`)
- [~] Vụ xưởng sắt: 14 cảnh làm lại xong (2, 3, 4, 7, 9, 11, 12, 14, 15, 19, 20, 21, 22, 24; điểm cử động 3,84–29,58); tỉ lệ video Muse có cử động 8,2% → 23,9%. Còn 30 cảnh: 15 cảnh lỗi do hết lượt (26, 29, 30, 32, 35, 36, 37, 38, 39, 41, 42, 46, 47, 53, 54), 15 cảnh chưa tới lượt (55, 57, 59, 60, 62–67, 69, 70, 72, 73, 75); lưới 9 ô đã duyệt giữ nguyên, chạy lại được ngay
- Xem tận mắt 14 clip: cử động thật ở cả 14; đầu tròn trắng đúng ở cảnh 2, 7, 11, 12, 14, 15, 21, 24; lệch nhẹ: nạn nhân (bảng duyệt là đầu tròn màu da, có tai) ở cảnh 9, 19 vẽ mặt chi tiết hơn bảng (nét mũi, nếp nhăn), người phụ nữ cảnh 20, 22 nét mặt gần mặt người, khung cuối cảnh 4 mặt ngả màu da
- [x] Khang Cúc Hoa: vẽ lại ảnh cảnh 2, 13 bằng Muse sau khi khởi động lại runner (2 ảnh, không rơi sang trả phí: bản sửa phép so ảnh có tác dụng trên Muse thật); chép sang bản Anh. Ảnh 9router và ảnh cũ giữ ở `.cache/thu_khoa_cung/anh_kch_*`
- [ ] Khang Cúc Hoa bản Việt: 12 cảnh có người mới (2, 4, 23, 24, 27, 28, 48, 52, 58, 60, 62, 69: vẽ lưới 9 ô, duyệt), 13 cảnh làm lại (7, 14, 17, 20, 21, 25, 30, 33, 37, 39, 40, 46, 68), cảnh 45: chưa làm (cần tài khoản video)
- [ ] Khang Cúc Hoa bản Anh: chép clip mới từ bản Việt: chưa làm
- [ ] Phần 5 (dựng lại 3 video): chưa làm. Chốt mới sẽ chặn dựng thành phẩm cả 3 video cho tới khi đủ 45% (đúng thiết kế)
- Làm tiếp khi có tài khoản video: trên giao diện mở dự án, bấm "Tạo video" (`#btn-climax-video-run`): cảnh lỗi do hết lượt và cảnh chưa tới lượt đã nằm sẵn trong hàng chờ; Khang Cúc Hoa bấm "Chọn cảnh cao trào" trước
- Số lần gọi: Muse video (việc nhiều bước) 17 lượt thành công (cảnh 2, 7 hai lần, 14 cảnh làm lại) + 1 lượt hết lượt dùng; Muse ảnh 2 thành công + 6 lượt NO_MEDIA do lỗi phép so cũ; ảnh trả phí 2 (cảnh 2, 13 Khang Cúc Hoa, rơi sang trước khi sửa runner); 0 lượt LLM

## Chạy tiếp ngày 12/11 (14:05–14:50, nhánh `tiep-lam-video-muse`), chủ dự án: "cứ tạo bằng tài khoản đã đăng nhập"
- Kiểm ngầm (`.cache/kiem_dang_nhap_muse.py`, không đăng nhập gì): còn phiên `muse_acc_vp_03`, `muse_acc_vp_04` (profile dùng chung với `D:\29. Workflow VideoPic`); cần đăng nhập lại `vid_04`, `vid_05`, `vp_01`, `vp_02`
- [x] Sửa: một tài khoản hết lượt thì tài khoản khác làm tiếp, chỉ dừng lượt chạy khi hết sạch tài khoản video
- [x] Sửa: tài khoản có profile dùng chung đang bị app khác mở thì tạm không nhận việc (trước đó app VideoPic mở profile `vp_04`, runner vẫn nhận việc, 29 cảnh bị ghi lỗi PROFILE_IN_USE trong 10 phút, không tốn Muse)
- [x] Sửa: Muse báo hết lượt dùng thì khoá tài khoản 6 tiếng thay vì 15 phút
- [ ] DỪNG lần 2: không còn tài khoản video tạo được video. `vid_03`: giới hạn theo TUẦN, Muse báo "Your full weekly usage will reset at 11:34 PM on Tuesday, November 17". `vp_03`: Muse không tạo video, chỉ viết prompt ra file `.md` rồi tự báo "KHÔNG ĐẠT, vì không có clip AI nào" (4 việc, mỗi việc khoảng 3 phút; luật cấm clip giả làm Muse báo thật thay vì dựng clip từ ảnh tĩnh). `vp_04`: app VideoPic đang mở
- Lượt này: 0 clip mới. Tỉ lệ video Muse có cử động: xưởng sắt 23,9%, Khang Cúc Hoa bản Việt 14,0%, bản Anh 14,2% (cả ba bị chốt chặn dựng thành phẩm, đúng thiết kế)
- Khang Cúc Hoa: lưới cảnh 24 đạt (chờ duyệt, chưa gửi được vì dự án đang chạy); lưới cảnh 4 cần vẽ lại (người chồng mắt kiểu anime, ô 9 thừa một ông Tống Đức Minh). Cảnh 2: Muse không vẽ lưới mà hỏi lại vì prompt lệch ánh sáng (cảnh ghi buổi sáng, thiết kế nhân vật Tống Lan Phương, Chu Tố Linh ghi "cold blue-green night lighting")
- Cảnh 45 Khang Cúc Hoa: AGENT_TIMEOUT lần 3 (Muse chỉ trả "👍"); nên bỏ cảnh này khỏi danh sách

## Chạy tiếp tối 12/11 (từ 21:41), chủ dự án: "tiếp tục xử lý đi... video final render ở trong folder chưa sửa đâu, làm nốt đi"
- Đầu phiên: server 8000 đã tắt (lượt chạy chiều bị ngắt). Tỉ lệ video Muse có cử động: xưởng sắt 38,2%, Khang Cúc Hoa bản Việt 22,4%, bản Anh 14,2%. Ba file `renders/story_final.mp4` vẫn là bản cũ (10/11, 11/11)
- Tài khoản video: chỉ `vp_02` làm được; `vid_03`, `vid_05`, `vp_04` hết lượt tuần tới 23:34 thứ Ba 17/11; `vid_04`, `vp_01` mất đăng nhập (kiểm ngầm 21:45); `vp_03` chỉ viết prompt
- Duyệt lưới cảnh 46 xưởng sắt, cảnh 28 Khang Cúc Hoa (khớp bảng nhân vật); bỏ cảnh 4 Khang Cúc Hoa (lưới vẽ người chồng kiểu anime). 21:47 chạy lại: 20 cảnh xưởng sắt, 18 cảnh Khang Cúc Hoa
- [x] Sửa (commit `0e50fce`): tài khoản hết lượt tuần bị khoá tới đúng giờ Muse ghi là hồi lượt (trước đó khoá 6 tiếng, hết 6 tiếng app mở lại, 21:49 cảnh 29 hỏng ngay vì `vid_05` vẫn hết lượt). Có tác dụng từ lần khởi động lại server sau
- Script `.cache/vu_an/chep_clip_en.py`: chép clip Muse và ảnh vẽ của bản Việt sang bản Anh; không chép ảnh bảng hồ sơ, thẻ miễn trừ (có chữ tiếng Việt)
- [x] Sửa (commit `95bdb32`): thời gian việc Muse nằm hàng chờ không còn tính vào giờ chạy. Bằng chứng: lưới cảnh 27 Khang Cúc Hoa xếp hàng 22:15:24, tài khoản nhận lúc 22:26:27, app bỏ cuộc 22:27:24 ("Caller timed out after 720s"); cảnh 2 cũng vậy. Nay: giờ chạy tính từ lúc runner nhận việc, hàng chờ tối đa 4 tiếng, hết sạch tài khoản đúng loại quá 5 phút thì báo "Không có tài khoản Muse video nào đang online" để lượt chạy dừng. Test mới trong `tests/test_muse_fleet_routing.py` báo lỗi trước khi sửa, đạt sau khi sửa
- 22:35 khởi động lại server 8000 (ngay sau khi cảnh 28 Khang Cúc Hoa xong, không bỏ phí việc Muse nào). Khoá tay trong `backend/config/muse_fleet_accounts.json` tới 23:36 17/11: `vid_05`, `vp_04` (hết lượt tuần), `vp_03` (Muse chỉ viết prompt, 12/15 việc NO_FINAL); bản trước khi khoá ở `.cache/muse_fleet_accounts_truoc_khoa_12-11.json`
- Lượt 21:47–22:35: xong cảnh 46 (17,85), 47 (17,57), 53 (12,26) xưởng sắt; cảnh 28 (26,2) Khang Cúc Hoa. Lưới cảnh 23 Khang Cúc Hoa: nghi phạm có tai, mắt tròng, mũi, miệng hồng chi tiết, lệch bảng nhân vật: từ chối kèm góp ý, vẽ lại
- 22:36 chạy lại: 17 cảnh xưởng sắt, 17 cảnh Khang Cúc Hoa, chỉ trên `vp_02`
- 23:56 vụ xưởng sắt đạt 50,3%: khởi động lại server (cảnh 33 Khang Cúc Hoa mới chạy 1 phút) để dừng lượt xưởng sắt, chỉ chạy Khang Cúc Hoa (14 cảnh); duyệt lưới 27, bỏ cảnh 2 Khang Cúc Hoa (lần 3 hỏng ở bước lưới: Muse vẽ hai bản lưới rồi hỏi "chọn bản nào" thay vì giao một ảnh; bằng chứng `.cache/muse_no_media/20261112_225029_task_m_90120f6f.png`)
- [x] DỰNG LẠI vụ xưởng sắt 23:57–00:25 (server 8000, 0 lượt Muse, 0 LLM): 1.283,9 giây (21 phút 24 giây), 1920x1080, 25 khung/giây, AAC 48 kHz stereo, 392 MB. Nhật ký dựng: "Video Muse có cử động: 645,6 / 1284,0 giây = 50,3%"; 11 cảnh cuối (62–75) còn clip cũ gần như đứng hình, không được tính. Âm lượng −16,0 LUFS, LRA 3,7 LU. Phụ đề: 450 câu, 1 chỗ chồng 0,01 giây, chữ nhảy lệch đầu câu tối đa 0,005 giây (`.cache/kiem_phu_de.py`). Bản trước giữ ở `.cache/vu_xuong_sat/story_final_ban5_truoc_12-11.mp4`. `projects/` không đổi
- Xem tận mắt 48 clip (`.cache/to_xem_clip.py`, 3 khung mỗi clip) và 12 khung video cuối: đúng phong cách ở đa số; lệch: nạn nhân Trịnh Đức Toàn (bảng: đầu tròn màu da nét đơn giản) bị vẽ mặt ông lão nhăn chi tiết ở cảnh 3, 9, 19, 35, 39, 49; nhân chứng áo vàng cảnh 50 mặt gần kiểu truyện tranh; cảnh 54 người đi xe gần như đứng im (cử động là mưa, nước, sương)
- Lượt Khang Cúc Hoa 23:56–02:33 (chỉ `vp_02`): xong cảnh 3, 6, 8, 23, 24, 27, 28, 30, 33, 37, 39, 40, 46, 68 (điểm cử động 3,9–37,0); mọi clip cũ nghi đứng hình đã được thay. Duyệt lưới 23 (vẽ lại đạt), 27, 48, 52, 58, 60, 62, 69. Bỏ cảnh 2, 4, 45 (hỏng nhiều lần ở bước lưới hoặc clip), bật thay cảnh 3, 6, 8
- [ ] DỪNG lần 3 (02:09): `vp_02` chạm hạn mức tạo video. Muse ghi "Tổng số đã tạo: 0 video / 0 ảnh mới — lần gọi clip A bị chặn ở cổng hạn mức", đoán mở lại sau khoảng 24 giờ. 6 cảnh lưới đã duyệt (48, 52, 58, 60, 62, 69, tổng khoảng 100 giây) hỏng vì vậy, lưới giữ nguyên, chạy lại được ngay khi có tài khoản video
- [x] Sửa (commit `da5d931`): việc nhiều bước kết thúc không có video mà Muse viết là bị hạn mức hoặc "0 video" thì runner báo QUOTA_EXCEEDED, backend khoá tài khoản (trước đó ghi NO_FINAL, tài khoản nhận tiếp cảnh để hỏng; `vp_03` hỏng 12 việc như vậy). Có tác dụng từ lần khởi động lại Fleet Runner sau
- Tỉ lệ cuối: xưởng sắt 50,3% (đã dựng thành phẩm); Khang Cúc Hoa bản Việt 42,6% (503 / 1.180 giây), bản Anh 41,4% (521 / 1.257 giây): cả hai dưới 45%, chốt chặn không cho dựng thành phẩm (đúng thiết kế); `renders/story_final.mp4` hai bản này vẫn là bản cũ 10/11 và 11/11
- [x] Chép sang bản Anh (`.cache/vu_an/chep_clip_en.py --ghi`, 02:35): 20 clip và ảnh vẽ lại cảnh 17; 30 cảnh dùng video, mọi clip mở được, ảnh bảng hồ sơ tiếng Anh giữ nguyên. project.json trước khi chép: `.cache/thu_khoa_cung/project_kch_en_truoc_chep_13-11.json`
- Xem tận mắt 26 clip Khang Cúc Hoa: bối cảnh, quần áo, dáng người khớp; nét mặt lệch khi khóc/sợ (mắt có tròng, mũi, nếp nhăn kiểu truyện tranh) ở cảnh 17, 20, 21, 30, 55 (Chu Khải Phong), 33, 39 (Đỗ Thành Cương), ông lão cảnh 5, 7, 57. Lưới 9 ô duyệt trước đều đúng; lệch phát sinh khi Muse làm chuyển động
- Kiểm tra đầy đủ lần 1 (13/11, 765 giây): 1 test lỗi `tests/test_muse_agent_bridge.py::test_enqueue_keeps_agent_video_mode` do luật hàng chờ mới (test cũ dựa vào việc nằm chờ hết giờ sau 1 giây); sửa test theo luật mới (commit riêng)
- Số lần gọi đêm 12–13/11 (đếm theo file clip và lưới có giờ sửa sau 21:40): Muse video (việc nhiều bước) 23 thành công (xưởng sắt 9, Khang Cúc Hoa 14), 8 hỏng không ra video (1 `vid_05` hết lượt tuần, 1 `vp_03` chỉ viết prompt, 6 `vp_02` chạm hạn mức), 1 bị ngắt khi khởi động lại server (cảnh 33, chạy được 1 phút, làm lại sau đó đạt); Muse ảnh lưới 9 ô 9 thành công (23 hai lần, 27, 48, 52, 58, 60, 62, 69), 3 hỏng (cảnh 2 hai lần, cảnh 27 một lần hết giờ hàng chờ trước khi sửa); 0 lượt LLM; 0 ảnh trả phí
- Kiểm tra đầy đủ lần 2 (13/11, sau khi sửa test): ĐẠT, 1.050 test đạt, 0 lỗi, 316 giây; Ruff không có lỗi mới (53 lỗi cũ trong mốc); test kiến trúc 40 đạt

## Làm nốt Khang Cúc Hoa 13/11 (từ 11:40), chủ dự án: "bào nhanh luôn chỉ 2 tài khoản đó thôi, nhớ đổi nhau luân phiên... tài khoản đang chạy cảnh nào thì phải chạy cho hết"
- Chủ dự án đăng nhập lại `vid_04`, `vp_01` (kiểm ngầm 11:50: cả hai còn đăng nhập). Khoá tay thêm `vp_02` tới 23:36 17/11 để chỉ dùng hai tài khoản này; bản trước ở `.cache/muse_fleet_accounts_truoc_13-11.json`
- [x] Sửa (commit `17572f1`): cửa sổ Chrome có giao diện theo cỡ màn hình. Màn hình máy 1280x720 (vùng dùng 1280x672) mà khung trang khoá 1280x800 nên trang Muse bị cắt phần dưới. Đo thật sau khi sửa: trang 1280x529, vừa màn hình. Chạy ngầm giữ 1280x800
- [x] Sửa (commit `9b20956`): video cao trào chia cảnh cho các tài khoản video, mỗi tài khoản một người làm, cảnh ghim vào đúng tài khoản được giao; tài khoản hết lượt thì nghỉ, cảnh của nó không chuyển sang tài khoản khác
- [x] Sửa (commit `cf367d2`, đường cấm 3, lần vi phạm thứ 6): tỉ lệ video Muse chỉ tính phần clip thật sự chạy. Cảnh 048: lời kể 18,1 giây, Muse trả 9 giây (Muse tự ghi "KHÔNG ĐẠT... hết ngân sách 6 video"), khi dựng clip chỉ kéo chậm tới 11,25 giây rồi đứng khung cuối; cách đếm cũ tính đủ 18,1 giây. Đếm lại: xưởng sắt 50,3% thành 50,1%
- [x] Sửa (commit `e14582d`): slot ưu tiên ảnh của Fleet Runner sang giúp làm video khi không có việc ảnh. Trước đó chỉ một slot làm video nên `vp_01` đứng chờ 30 phút (11:58–12:31) trong khi `vid_04` làm liền 5 cảnh. Sau khi sửa (13:37): hai tài khoản chạy song song thật (cảnh 036 trên `vid_04`, 041 trên `vp_01` cùng lúc)
- [x] Sửa (commit `13bdecd`): cảnh đã bắt đầu trên tài khoản nào thì chỉ tài khoản đó làm tiếp. Gặp 13:23: server tắt theo phiên làm việc lúc cảnh 052 đang chạy trên `vp_01`; chạy lại thì `vid_04` nhận mất, đã dừng sau vài giây và giao lại `vp_01`. Từ đây server 8000 bật thành tiến trình riêng
- Kết quả 6 cảnh lưới đã duyệt: 048 (`vid_04`, 9,0 giây, cử động 13,0), 058 (`vid_04`, 17,0 giây, 34,1), 060 (`vid_04`, 17,0, 23,4), 062 (`vid_04`, 17,0, 26,5), 069 (`vid_04`, 18,0, 26,7), 052 (`vp_01`, 15,0, 36,0). Thêm 2 cảnh để bản Anh đủ 50%: 036 (`vid_04`, 17,0, 34,8), 041 (`vp_01`, 17,0, 20,0). Xem tận mắt 6 khung mỗi clip: đầu tròn, quần áo đúng, cử động thật; lỗi nhỏ: chữ "HANDPRINT" trên giấy dán tường cảnh 058, mái tóc khung cuối cảnh 058 hơi khác, nếp nhăn ở khung 5 cảnh 062
- Phát hiện chưa sửa: cảnh 036 bị app xếp là "phong cảnh không người" vì chưa gắn nhân vật, trong khi lời kể và ảnh có Thẩm Hạo Nhiên và hai trinh sát; Muse vẽ theo ảnh cảnh nên đúng, nhưng loại cảnh này không được đính bảng nhân vật
- Tỉ lệ sau khi chép sang bản Anh (`chep_clip_en.py --ghi`, 8 clip): bản Việt 52,9% (636 / 1.180 giây), bản Anh 52,1%
- Số lần gọi 13/11: Muse video (việc nhiều bước) 8 thành công (`vid_04` 6, `vp_01` 2), 2 bị ngắt (cảnh 052 trên `vp_01` khi server tắt theo phiên, cảnh 052 trên `vid_04` dừng tay sau vài giây); 0 lưới 9 ô; 0 LLM; 0 ảnh trả phí
- [x] DỰNG LẠI Khang Cúc Hoa bản Việt 13:49–14:10 (server 8000, 0 lượt Muse, 0 LLM): 1.180,3 giây (19 phút 40 giây), 1920x1080, 25 khung/giây, AAC 48 kHz stereo, 359 MB. Nhật ký dựng: "Video Muse có cử động: 624,5 / 1180,2 giây = 52,9%"; báo 3 cảnh clip ngắn hơn lời kể (30, 48, 68). Âm lượng −16,1 LUFS, LRA 2,6 LU. Phụ đề 650 câu, chữ nhảy lệch đầu câu trung bình 0,002 giây (tối đa 0,01); 5 chỗ chồng 0,001 giây (làm tròn)
- [x] DỰNG LẠI Khang Cúc Hoa bản Anh 14:11–14:34: 1.256,9 giây (20 phút 57 giây), cùng thông số, 370 MB. Nhật ký dựng: "654,7 / 1256,9 giây = 52,1%"; 3 cảnh clip ngắn hơn lời kể (27, 48, 68). −16,1 LUFS, LRA 3,3 LU. Phụ đề 434 câu, lệch trung bình 0,002 giây; 2 chỗ chồng 0,001 giây
- Bản cũ của hai video ở `.cache/thanh_pham_cu_13-11/`. Xem tận mắt 24 khung bản Việt và 12 khung bản Anh: các cảnh mới đúng phong cách, bảng hồ sơ bản Anh chữ tiếng Anh; còn lệch mặt đã biết ở ông lão và người con khóc (khung 0:49 bản Việt, 0:52 bản Anh, cảnh 5 và 7)
- Sửa script đo `.cache/kiem_phu_de.py`: trước lấy nhầm chữ cuối của câu trước nên báo lệch 0,33 giây; nay lấy chữ có giờ gần đầu câu nhất
- Kiểm tra đầy đủ (13/11, 1.275 giây, chạy cùng lúc với dựng video): ĐẠT, 1.062 test đạt, 0 lỗi; Ruff không có lỗi mới; test kiến trúc 40 đạt

## Sửa một lần cho xong hai video 13–14/11, chủ dự án: "Ngoài lỗi xếp nhầm cảnh đó còn lỗi nào không để sửa 1 lần cho xong luôn 2 video đi"
- Rà soát: hai trợ lý xem từng tờ khung hình (`.cache/to_ra_soat.py`, 4 khung mỗi clip, `.cache/ra_soat_13-11/`) so với bảng nhân vật đã duyệt; tôi xem lại tận mắt 14 cảnh bị chấm nặng, đúng cả 14. Khang Cúc Hoa: 6 nặng (004 ảnh: người chồng mặt anime; 017, 020, 021: mặt Chu Khải Phong kiểu truyện tranh; 034 gần như đứng im; 056 ảnh: bàn tay vẽ như thật), 8 cảnh xếp nhầm phong cảnh, 25 nhẹ, 16/51 đạt hoàn toàn. Xưởng sắt: 8 nặng (003, 009, 019, 035, 039: mặt Trịnh Đức Toàn nhăn chi tiết; 020: em gái A Cường mặt anime; 007 viền trắng; 066 đứng im), 5 xếp nhầm phong cảnh, 21/48 đạt hoàn toàn
- [x] Sửa (commit `6a9449c`): cảnh có người không tên không còn bị coi là phong cảnh; ba loại cảnh (nhân vật trong bảng: lưới 9 ô; người không tên: `crowd_brief()` giữ đúng người trong ảnh; không người: `landscape_brief()`), xếp lại mỗi lần chạy; nhãn trên thẻ cảnh
- [x] Sửa (commit `ee02d60`): gốc lỗi mặt ông già là chữ tả mặt thật trong thiết kế đã duyệt ("deep sun-etched wrinkles", "weathered features", "sunken cheeks", "sharp resolute eyes"). Lúc ghép prompt ảnh cảnh, lưới 9 ô, bản giao việc video (phong cách đầu tròn) thì bỏ các vế tả mặt (`character_sheets.without_face_details`); thiết kế đã lưu không đổi. Luật đầu tròn thêm: người già lúc khóc vẫn là quả bóng tròn phẳng
- [x] Sửa (commit `3085bc4`): Muse tự ghép đoạn để lại dải trắng ở mép hình ở 8 clip (3–30 điểm ảnh). App đo và cắt viền khi nhận clip (`services/clip_border.py`); đã cắt 5 clip Khang Cúc Hoa (024, 027, 040, 047, 068) và 2 clip xưởng sắt (007, 022), đo lại không còn viền (còn 025: 2 điểm ảnh). Bản cũ ở `.cache/anh_canh_cu_13-11/`
- [x] Sửa (commit `2799d76`): runner nhận một ảnh cũ của đoạn chat dùng lại làm ảnh mới (ảnh cảnh 004 vẽ lại lần đầu ra hai phụ nữ ở ruộng ngô, sau 15 giây); nay chỉ nhận media nằm sau tin nhắn prompt vừa gửi. Ảnh sai đã trả về ảnh cũ ngay, giữ ở `.cache/anh_canh_cu_13-11/kch_scene_004_muse_sai.jpg`
- Làm lại: Khang Cúc Hoa 017, 020, 021, 034 (clip, đạt; viên cảnh sát không tên cảnh 020 vẫn mặt màu be theo lưới cũ), 004 và 056 (ảnh, vẽ lại trên tài khoản ảnh `img_01` qua "Gen lại ảnh AI", không rơi sang ảnh trả phí). Xưởng sắt: 003 (7 giây, đúng nét), 009, 019, 039, 062, 064, 065, 066, 067, 069, 070, 072, 073, 075 đạt; 035 vẫn mặt nhăn (ảnh cảnh và bảng nhân vật của ông Toàn đã vẽ như vậy: muốn sửa phải vẽ lại bảng nhân vật, chờ chủ dự án quyết); 063 hỏng 2 lần (Muse trả 4 giây, rồi `vp_01` bị chặn tạo video, giữ clip cũ); 020 vẽ lại lưới 3 lần (lần đầu ông Toàn hai lần ở cảnh 073 cũng từ chối, vẽ lại đạt)
- [x] DỰNG LẠI Khang Cúc Hoa bản Việt 14/11 19:24–19:37: 1.180,3 giây, 1920x1080, 25 khung/giây, AAC 48 kHz stereo, 361 MB, 52,9% video Muse, −16,1 LUFS, LRA 2,6, phụ đề lệch trung bình 0,002 giây; xem tận mắt 6 cảnh đã sửa trong thành phẩm (`.cache/ra_soat_13-11/final_kch_vi.jpg`)
- [x] DỰNG LẠI Khang Cúc Hoa bản Anh 19:37–19:51: 1.256,9 giây, cùng thông số, 371 MB, 52,1%, −16,1 LUFS, LRA 3,3, phụ đề lệch 0,002 giây; 6 cảnh đã sửa có trong thành phẩm (`final_kch_en.jpg`). Bản trước ở `.cache/thanh_pham_cu_14-11/`
- [x] DỰNG LẠI vụ xưởng sắt 14/11 20:51–21:02: 1.283,9 giây (21 phút 24 giây), 1920x1080, 25 khung/giây, AAC 48 kHz stereo, 358 MB. Nhật ký dựng: "799,4 / 1284,0 giây = 62,3%" (lần trước 50,3%); còn cảnh 63 clip gần như đứng hình (không tính), 4 cảnh clip ngắn hơn lời kể (3, 19, 35, 39). −16,0 LUFS, LRA 3,7; phụ đề 450 câu, lệch trung bình 0,003 giây, 1 chỗ chồng 0,001 giây. Bản trước ở `.cache/thanh_pham_cu_14-11/`
- Số lần gọi 13–14/11 (đợt sửa này): Muse video (việc nhiều bước) 22 thành công, 5 hỏng (009 và 063 clip dưới 5 giây, 063 hai lần hết 75 phút trên `vp_01`); Muse lưới 9 ô 6 (070 hai lần, 073 hai lần, 020 ba lần, trong đó 1 hỏng NO_MEDIA); Muse ảnh cảnh 3 trên `img_01` (004 hai lần, lần đầu nhận nhầm ảnh cũ; 056 một lần); 0 LLM; 0 ảnh trả phí
- Kiểm tra đầy đủ (14/11, 643 giây): ĐẠT, 1.078 test đạt, 0 lỗi
- Còn lại, chờ chủ dự án: (1) Trịnh Đức Toàn (xưởng sắt): bảng nhân vật đã duyệt vẽ đầu màu da, có tai, nếp nhăn; Muse bám theo nên cảnh 009, 035 (và ảnh cảnh 035) mặt nhăn chi tiết; sửa tận gốc phải vẽ lại bảng nhân vật rồi vẽ lại các cảnh có ông. (2) Cảnh 063 xưởng sắt còn clip đứng hình (không tính vào tỉ lệ). (3) Lỗi nhẹ còn lại theo bảng rà soát (vd chữ "HANDPRINT" cảnh 058, viên cảnh sát mặt màu be cảnh 020 Khang Cúc Hoa)
- Chủ dự án 15/11/2026 chọn "Giữ như hiện tại" cho bảng nhân vật Trịnh Đức Toàn: không vẽ lại bảng, cảnh 009 và 035 vụ xưởng sắt giữ như đã dựng

# TASKS — giao diện gọn 5 bước kiểu ElevenLabs (15/11/2026, nhánh `giao-dien-gon`)
Chủ dự án duyệt bản xem thử 15/11: "Duyệt, viết kế hoạch". Thiết kế: `docs/superpowers/specs/2026-11-15-giao-dien-gon-design.md`; kế hoạch: `docs/superpowers/plans/2026-11-15-giao-dien-gon.md`; bản xem thử: `docs/superpowers/specs/2026-11-15-giao-dien-gon-ban-xem-thu.html`.
- [x] Viết thiết kế, cho người đọc độc lập soát (6 câu hỏi, 4 chỗ lệch code), sửa theo
- [x] Đổi so với bản xem thử sau khi đọc code: phong cách hình chọn ở trang Ý tưởng (AI viết mô tả ảnh theo phong cách ngay lúc viết kịch bản); nguồn tạo ảnh ở trang Hình mẫu (cài đặt của từng dự án, không phải của cả app); thẻ Dàn ý và Tên hư cấu chỉ hiện khi đang theo dõi vụ chưa tạo dự án (như cửa sổ hiện nay); giọng từng cảnh ở trang Kịch bản
- [x] Kiểm: mọi id và tên hàm trong hai tài liệu có trong code; `tools/check.py` ĐẠT (40 test kiến trúc, 26 giây)
- [x] Làm 12 task của kế hoạch (mỗi task: người làm riêng, người soát riêng, controller bấm thử trên server 8010)
- [x] Task 1: Khoá cứng giữ id và test bố cục
- [x] Task 2: Khung mới (thanh bên, thanh trên, 8 trang, ngăn kéo)
- [x] Task 3: Trang Kịch bản và giọng (phần chung cho mọi thể loại)
- [x] Task 4: Trang Hình mẫu
- [x] Task 5: Trang Cảnh và trang Dựng và xuất bản
- [x] Task 6: Trang Dự án, Thư viện Muse, Tài khoản (phần Muse)
- [x] Task 7: Khuôn thể loại và trang Ý tưởng
- [x] Task 8: Hồ Sơ Kỳ Án vào trang Kịch bản
- [x] Task 9: Gỡ các cửa sổ và nút trùng còn lại
- [x] Task 10: Dọn màu trang trí sang hệ đen trắng xám (đỏ ban đầu: 296 chỗ lớp màu trang trí, index.html 106, app.js 128, climax_video.js 23, true_crime.js 14, youtube_seo.js 11, character_sheets.js 7, location_sheets.js 7; nay 0, test `tests/test_ui_palette.py`)
- [x] Task 11: Trang Tài khoản và kết nối — trạng thái kết nối
- [x] Task 12: Kiểm chứng cuối và tài liệu
- Soát cả nhánh (model mạnh nhất): "sẵn sàng sau khi sửa", 5 lỗi đáng kể + 6 điểm nhỏ, sửa một lượt (commit `043b4e7`, `0864a3e`), soát lại: 11/11 đã sửa
- Lỗi chỉ lộ ra khi bấm thật (người soát đọc mã chấm đạt): trang Kịch bản không hiện cảnh nào vì đọc `window.AppState`; sửa lời ở Kịch bản mà trang Cảnh vẫn lời cũ; dòng phong cách cũ sau khi đổi dự án; nút chính chưa thành viên thuốc đen
### Bằng chứng (15/11/2026)
- `tools/check.py --full`: ĐẠT, 1.128 test đạt, 19 bỏ qua (cờ live), Ruff không lỗi mới, 12 file JS đúng cú pháp (lần chạy của người sửa cuối; lần trước ở 4d3dd60: 1.118 đạt, 257,9 giây)
- `tools/build_release.py`: gói 167 file, 23,8 MB, không báo thiếu file `/static/...`; gói thử đã chuyển vào Thùng rác
- Bấm thử server 8010 (`proj_ea5b04db`, mở xem `proj_crime_52c3a5e8`, vụ `case_7dcf6158` qua localStorage, mọi lệnh ghi vào mục MẪU bị chặn): 8 trang, sửa lời, nghe giọng, thêm/xoá cảnh, Hình mẫu đổi dự án, ngăn xem thử, Tuỳ chỉnh dựng, dựng bị chặn 45% (giả lập) → hỏi bản nháp, gắn ảnh từ Thư viện (giả lập), vụ án đang theo dõi → thẻ Dàn ý/Tên hư cấu, Ctrl+S, trang Tài khoản khớp cấu hình thật
- "Gọi thử" bấm 1 lần: báo "Không kết nối được 9router tại 127.0.0.1:8317" sau 2,1 giây (cổng 8317 và 20128 đang tắt trên máy) → 0 lượt AI bị tính
- Tràn ngang: 0/8 trang ở 1024x768 (thanh bên mở và thu gọn), 1280x720, 1920x1080 (vùng giữa rộng 1.036 px, canh giữa); ảnh chụp ở `.cache/giao_dien_gon/`
- `projects/` không thêm thư mục; `proj_ea5b04db` giống hệt bản sao trước khi thử (cảnh và cài đặt)
- [ ] Còn chờ chủ dự án: `projects/proj_crime_52c3a5e8/renders/thumbnail.jpg` do máy chủ tự vẽ khi controller mở trang Dựng của dự án MẪU (file mới, không ghi đè gì); giữ hay chuyển vào Thùng rác
- [ ] Còn chờ chủ dự án: gộp nhánh `giao-dien-gon` vào `master`
- Số lần gọi dịch vụ: LLM 0 lượt tính tiền (1 lần gọi thử bị từ chối vì cổng AI tắt), Muse 0, ảnh trả phí 0

# TASKS — sửa thao tác sau khi chủ dự án xem thử giao diện gọn (15/11/2026, nhánh `giao-dien-gon`)
Chủ dự án xem giao diện mới, góp ý 9 điểm (chọn cảnh cao trào không thấy gì, prompt video giống prompt ảnh, video 5/10 giây, không xem lớn được ảnh/video, làm lại một cảnh lấy prompt ở đâu, không huỷ được bản tiếng Anh, nhân vật phải AI tự tìm và vẽ, tạo một lần ăn ngay, nút dự án thừa và lưới dự án có ảnh). Quyết định 15/11: lưới 9 khung tự chạy tiếp không chờ duyệt; chọn cảnh cao trào bằng Gemini, "không cần tiết kiệm token". Kế hoạch: `C:\Users\pc\.claude\plans\wobbly-brewing-aurora.md`.
- [x] A1 Bỏ nút dự án ở thanh bên; trang Dự án thành lưới thẻ có ảnh bìa (`cover_url`, chỉ đọc, không gọi đường tự tạo thumbnail)
- [x] A2 Bấm ảnh/video trên thẻ cảnh để xem lớn (`media_viewer.js`); bảng nhân vật, ảnh bối cảnh cũng vậy
- [x] A3 Thẻ cảnh hiện prompt thật gửi Muse (ảnh 2K; video theo lời thoại: số video và số giây; bản giao việc cao trào, lý do khi sẽ bị chặn); gỡ ô prompt video không được gửi đi; bỏ chữ "(10s)" ghi cứng
- [x] A4 Gemini chọn cảnh cao trào theo nhóm 14 cảnh có kiểm, lý do trên thẻ; dải tổng kết "Làm video: N/M cảnh · X% thời lượng", bộ lọc Tất cả/Làm video/Ảnh, công tắc Làm video trên mọi thẻ
- [x] A5 Nút Huỷ khi tạo bản tiếng Anh (dừng sau bước AI đang chạy, dọn dự án dở, không đụng bản Việt)
- [x] A6 "AI tìm và vẽ tất cả" nhân vật và bối cảnh, "Duyệt tất cả", tiến độ và Dừng; báo trước số lượt Muse
- [x] B "Tạo hình cho cả dự án": cảnh thường ra ảnh, cảnh cao trào ra lưới → tự duyệt → clip; báo trước số ảnh, số video, số lượt Muse, cảnh thiếu điều kiện gom theo nguyên nhân; ảnh đi đúng việc "Muse 2K" của thẻ (không rơi sang ảnh trả phí)
- Mỗi việc: người làm riêng, người soát riêng (A3, A4, A6, B có lỗi quan trọng, đã sửa và bấm thử lại), controller bấm thử trên 8010
- Lỗi chỉ lộ khi bấm thử (người làm báo đạt): nút Huỷ bản tiếng Anh không hiện trong lúc chạy (sửa `efdfd29`); ô xác nhận "Tạo hình cho cả dự án" cao 1.380 px, nút Chạy nằm ngoài màn hình 720 px, và 7 giây chờ không báo gì (sửa `dfb85c5`)
### Bằng chứng (15/11/2026)
- Gemini chọn cảnh cao trào chạy thật 1 lần trên `proj_ea5b04db`: 1 lượt AI, dưới 1 phút, 5 cảnh có điểm và lý do tiếng Việt, chọn 3 cảnh (67,7% thời lượng); đã tắt lại 3 cảnh qua công tắc của app, project.json giống bản sao
- Bấm thử 8010 (`proj_ea5b04db`, `proj_crime_thucaotrao`): lưới 11 dự án; xem lớn ảnh/video, Esc/nền/× đóng; prompt đầy đủ và kế hoạch video trên thẻ; 2 khối video cho cảnh cao trào, lý do chặn đúng; dải tổng kết 40/78 cảnh 51%, lọc 40/38; Huỷ bản tiếng Anh (máy chủ giả lập): hiện Huỷ, "Đang huỷ…", trả nút; vẽ tất cả nhân vật: xác nhận "16 lượt" đúng 16 bảng nháp, tiến độ, Dừng (máy chủ giả lập); kế hoạch "Tạo hình cho cả dự án": 11 video, khoảng 22 lượt Muse, 27 cảnh thiếu bảng nhân vật duyệt; ô xác nhận vừa 1280x720 và 1024x640
- Không file dự án nào bị ghi thêm trong các lần bấm thử (so `find projects -newer`)
- [x] Chạy thật "Tạo hình cho cả dự án" với Muse trên `proj_ea5b04db` (chủ dự án: "Chạy thử Muse"; server 8000 khởi động lại có phép), bấm nút thật lúc 15:19, xong 16:40 (81 phút). Trước khi chạy: sao `project.json` và 2 ảnh cũ (cảnh 1, 5) vào `.cache/muse_live_1115/`, bật Làm video cho cảnh 3, 4. Kế hoạch: 2 ảnh, 2 video cao trào, 0 lưới, 4 lượt Muse
  - 2 ảnh cảnh thường: ra trong 2 phút, 2048x1152 (2K 16:9), mở xem: cùng một người đàn ông áo khoác xanh rêu trên vách núi, đúng kiểu khung prompt (cảnh 1 góc cao kiểu drone, cảnh 5 lùi xa). Prompt Muse nhận (`recent_completed` của cầu nối Muse) trùng phần "Scene Details" của khối "Prompt đầy đủ gửi Muse" trên thẻ, 2K, 16:9, cinematic_realistic. Ảnh không kể chuyện chiếc ô đỏ vì mô tả cảnh của dự án thử là câu chung chung và dự án không có bảng nhân vật, không phải lỗi đường gửi
  - [ ] 2 video cao trào: thất bại, app ghi đúng lý do trên cảnh (không báo xong giả). Cảnh 3: Muse báo hết hạn mức video sau 66 phút. Cảnh 4: quá 4.500 giây chưa xong, Muse làm bản nháp lời kể thay video. Nguyên nhân: 6/7 tài khoản video hết hạn mức tuần (Muse ghi mở lại 23:34 thứ Ba 17/11/2026), tài khoản thứ 7 chỉ ghi "đang nghỉ". Chưa kiểm được phần video của nút này cho tới khi có tài khoản video
  - Sửa sau lượt chạy: kế hoạch đếm tài khoản Muse video dùng được (`routers/one_pass_visuals.usable_video_accounts`); bằng 0 thì mọi cảnh cao trào vào "thiếu điều kiện" với lý do hết tài khoản video và nút "Mở trang Tài khoản và kết nối", lượt chạy chỉ làm ảnh, không ngồi chờ 75 phút mỗi cảnh. Hôm nay sửa này chưa tự chặn được vì tài khoản thứ 7 không mang dấu khoá. Test `test_no_usable_video_account_moves_climax_to_missing_and_run_makes_images_only`; bấm thử 8010 với kế hoạch giả: ô xác nhận hiện lý do và nút dẫn đúng trang Tài khoản, console sạch, `projects/` không đổi
  - Dòng ghi chú ô xác nhận không còn nói "vẽ lưới 9 khung" khi kế hoạch có 0 lượt lưới (`one_pass.js?v=1.1.1`)
- [ ] Chưa chạy thật "vẽ tất cả" nhân vật/bối cảnh với Muse
- Số lần gọi dịch vụ: LLM 1 lượt (Gemini chọn cảnh); Muse 4 lượt (2 ảnh xong, 2 việc video thất bại), 81 phút; ảnh trả phí 0

## Tài khoản Muse nhận cả ảnh lẫn video (17/11/2026, nhánh `muse-tai-khoan-ca-hai`)
Chủ dự án: giữ 4 tài khoản (`muse_acc_vid_01`, `vid_03`, `vid_05`, `vp_04`), xoá profile khác (vào Thùng rác, cấu hình cũ ở `.cache/muse_accounts_1117/`); "Mấy tài khoản anh để lại generate được cả video và img nên dùng cả đi".
- [x] Loại tài khoản `both`: `muse_bridge.account_kinds()`, `serves()`; `FleetAccount.serves()`; giao diện xếp tài khoản vào cả nhóm ảnh và nhóm video; khoá hết lượt khoá cả tài khoản. 4 tài khoản đổi sang `both`
- [x] Hai test Fleet Runner dùng tài khoản giả, không đọc danh sách thật; test đếm tài khoản video của "Tạo hình cho cả dự án" trước luôn đạt vì gọi nhầm bản giả, nay gọi hàm thật
- [x] `check.py --full` đạt 1200 test
- [x] Chạy thật trên `proj_ea5b04db`, cùng một tài khoản `muse_acc_vid_01`: video cảnh 3 (23:21–23:32, người chạy xuống dốc, độ cử động 27,1), ảnh cảnh 2 (44 giây, 2048x1152), ảnh cảnh 4 (32 giây), video cảnh 4 (23:40–23:47, khói và ánh sáng chuyển, người gần như đứng yên, độ cử động 3,0). Muse báo đã tạo 6 video để chọn 1 clip cho cảnh 3. Ảnh cũ cảnh 2, 4 ở `.cache/muse_live_1117/images/`
- Số lần gọi dịch vụ: Muse 4 việc (2 ảnh, 2 việc video cao trào), khoảng 33 phút; ảnh trả phí 0

## Sửa luật tận gốc (18/11/2026, nhánh `sua-luat-goc`)
Kế hoạch chủ dự án đã duyệt: rà luật chồng chéo sau hai video Khang Cúc Hoa và Vương Nghĩa Tường; mỗi khái niệm một nơi định nghĩa; repo có sẵn chỉ dùng `pysubs2`, `filelock`; code cũ vào `legacy/`. Mốc trước khi sửa: `check.py --full` đạt 1200 test (5 phút 49 giây).
- [x] GĐ1: `services/video_rules.py` là nơi duy nhất của mục tiêu 50%, chặn 45%, độ dài clip nhận (từ 3 giây, như Fleet Runner), ngưỡng cử động, kéo chậm và số giây đếm. `video_share.clip_counts()` / `climax_done()` là định nghĩa duy nhất "clip được tính": clip đứng hình không còn là "xong", "Tạo hình cho cả dự án" báo lỗi rõ và lượt sau tự làm lại. Video theo lời thoại lưu phần chạy thật (không đếm khung đứng yên chèn thêm) và đo cử động khi tạo. Test `tests/test_video_rules.py`, `test_still_clip_is_not_done_and_next_run_redoes_it`
- [x] GĐ2: cầu nối khoá tài khoản theo MÃ LỖI của Fleet Runner (`account_block_for`), không dò chữ trong cả câu: lỗi trình duyệt quá giờ ("Timeout 90000ms exceeded") và câu Muse kể nối sau "| Muse nói:" không còn khoá tài khoản; báo cáo "6 video, 0 video đạt" không còn bị đọc thành hết hạn mức 6 giờ. Tài khoản nghỉ thì cảnh của nó (kể cả cảnh vừa hỏng) làm lại cả cảnh trên tài khoản khác, chat mới. Server chờ việc nhiều bước lâu hơn runner (`AGENT_TASK_EXTRA_SEC` 900 > 600 + 90). Việc từ nút trên thẻ nằm hàng quá hạn thì bỏ. Test `tests/test_account_errors.py` dùng câu lỗi thật trong log; sửa 3 test cũ giữ luật dò chữ
- [x] GĐ3: `services/prompt_rules.py` là nơi duy nhất của luật đầu tròn (gộp 4 bản), tóc nữ, máy quay, cử động, góc máy theo cử động (chốt 1: cử động mạnh quay góc trung/xa), không xoay người, không chữ. Video thoại bỏ "đổi góc máy" (cãi "máy quay đứng yên"), gửi kèm bảng nhân vật đã duyệt. Lưới 9 khung bỏ "chỉ cử động nhẹ", "không cắt cảnh". Bản giao việc cao trào: phần tả nhân vật chỉ còn ngoại hình (không chép phong cách cho từng người, bỏ cắt 1.500 ký tự làm cụt luật tóc), cảnh dài chia việc Muse ≤ 15 giây (chốt 2), phần đã xong lưu lại làm tiếp. Gửi danh sách cấm của phong cách; bỏ "cinematic lighting 8k" và mã phong cách trần; gỡ nhân vật chính chung khỏi prompt (Python và app.js). Một phong cách mặc định: `config.DEFAULT_STYLE` = đầu tròn (sửa cả dòng DEFAULT_STYLE trong `.env` của máy, trước là manga), app.js `DEFAULT_STYLE_PRESET`. Bỏ `muse_motion.py`. Test hành vi `tests/test_prompt_rules.py` dựng prompt cuối từng đường, chặn cặp luật cãi nhau. Bộ test đầy đủ: 1213 đạt, 4 lỗi do test giữ luật cũ, đã sửa
- [x] GĐ4: lưới đã duyệt có dấu (`climax_video.grid_key`: nhân vật, thiết kế, số ô); đổi một thứ thì lượt sau tự vẽ lại lưới thay vì gửi lưới cũ hay báo lỗi lặp. Đổi thiết kế huỷ cả bảng "review"/"drawing" và xoá góp ý cũ; duyệt thì xoá góp ý cũ (bảng, ảnh chuẩn, lưới). "drawing" sót lại sau khi server tắt không còn kẹt (`drawing_now`). Lựa chọn nhân vật chọn tay không bị lần tìm nhân vật ghi đè (`manual_scene_ids`). "Tạo ảnh còn thiếu" chỉ vẽ cảnh chưa có ảnh. Test `tests/test_state_invalidation.py`. Chưa làm: giữ `media_view_mode` khi giao diện tự lưu bản cũ (cần xem cách nút đổi ảnh/video trên thẻ dùng trường này)
- [x] GĐ5: bản Anh vụ án bỏ "viết gọn hơn bản Việt, giữ ý chính" và qua bước kiểm đủ ý (coverage_guard) như bản Việt (thêm 1 lượt LLM mỗi nhịp, tối đa 3 vòng). Lời trích bịa cho người thật thành lỗi nặng (trước: hết 3 lượt vẫn nhận). Đoạn mở đầu được thêm câu hỏi cho mỗi sự việc chỉ gợi (hai luật câu hỏi hết đụng). Bỏ yêu cầu `video_prompt` 5 giây (không ai dùng). Dàn ý bỏ trần số cảnh trong prompt. Truyện chữ: bước kiểm phần đầu có ghi chú cho phép mở bằng khoảnh khắc căng nhất; gỡ ô nhịp cảnh không có tác dụng. Không đổi: `MAX_VIDEO_RATIO` chỉ là gợi ý cảnh video cho LLM, không chặn mục tiêu 50%; tốc độ đọc 200 và 252 chữ/phút là của hai giọng khác nhau, gộp là việc riêng
- [ ] GĐ6: dựng video
- [ ] GĐ7: `legacy/`, `pysubs2`, `filelock`
- [ ] GĐ8: tài liệu và khoá cứng
- [ ] Kiểm chứng offline và chạy thật 6 cảnh xưởng sắt
