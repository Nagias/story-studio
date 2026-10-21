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
