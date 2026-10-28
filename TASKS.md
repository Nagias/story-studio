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
- [ ] Chưa chạy lại trọn từ nút sau khi sửa tải video (để khỏi tốn thêm yêu cầu Muse): đường tải mới chỉ kiểm bằng test và bằng script dò cùng cách đọc địa chỉ
- [ ] Cảnh 41 chờ chủ dự án: bảng Hàn Thụy Côn đầu tròn mâu thuẫn ảnh cảnh vẽ mặt người; cô gái và cậu bé chưa có bảng nhân vật
- [ ] muse_acc_vid_01 hết phiên đăng nhập (runner tự tạm ngừng)
