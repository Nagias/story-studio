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
- [ ] Khởi động lại server cổng 8000 (code cũ: nếu VieNeu chậm quá 8 s sẽ gọi CLI không có biến cache → có thể tải lại về ổ C)

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

- [x] Task 1: Schema, lưu trữ, hàng việc, fixture test, baseline
- [ ] Task 2: Client LLM qua 9router
- [ ] Task 3: Kiểm lọt tên, ngày tháng, áp tên hư cấu
- [ ] Task 4: Bộ chạy một việc, cùng các việc G1–G4 (từ bài gốc tới hồ sơ)
- [ ] Task 5: Các việc G5–G7 (dàn ý, viết cảnh theo nhịp, ráp kế hoạch)
- [ ] Task 6: Worker chạy hàng việc tuần tự
- [ ] Task 7: Bảng ghim theo ngôn ngữ, tạo dự án, tạo bản ngôn ngữ khác
- [ ] Task 8: API, bỏ luồng cũ
- [ ] Task 9: Giao diện modal Hồ Sơ Kỳ Án
- [ ] Task 10: Nút "Tạo bản tiếng Anh"
- [ ] Task 11: Hồi quy toàn bộ và chạy thật cả chuỗi

## Baseline trước khi sửa (Task 1, bước 1)
- Bộ offline 18 file (lệnh trong kế hoạch, Task 1): **158 pass / 1 fail**, 332 s. Worktree không có `backend/config/muse_fleet_accounts.json` và `backend/chrome_profiles/`.
- Fail sẵn: `tests/test_gate_gout_regressions.py::test_sec_04_block_arbitrary_file_overwrite_in_muse_complete` (test chờ 200, nhưng `/api/muse-bridge/tasks/create` giờ trả 400 khi `output_path` nằm ngoài projects/muse_outputs). Test cũ lệch với code đã siết, không thuộc nhiệm vụ này.
- Lần chạy sinh ra (đều bị `.gitignore` bỏ qua): `projects/proj_crime_e9e94024`, `projects/proj_crime_fa8cad63`, `backend/static/comic_slices/` (3 thư mục), `backend/static/evidence_boards/` (2 thư mục `case_*`), `backend/config/muse_fleet_accounts.json`, `backend/muse_fleet_runner.log` (rỗng). Trước khi chạy thì chưa có `projects/`, `comic_slices/`, `backend/static/comic_slices/`.
- [ ] Dọn các thư mục trên (chuyển vào Thùng rác): lệnh xoá bị chặn nên chưa dọn
