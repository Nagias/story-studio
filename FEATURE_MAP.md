# FEATURE_MAP — bản đồ tính năng Story Studio

Tra file này **trước** khi làm, tái hiện lỗi hay kiểm chứng bất kỳ tính năng nào (quy tắc trong `CLAUDE.md`). Không đoán đường: nếu tính năng cần tìm không có ở đây, tìm trong code rồi bổ sung vào file này trong cùng nhánh.

Quy ước ghi:
- Dấu `#` đứng trước id phần tử trong `backend/static/index.html`; tên hàm JS/Python viết kèm `()` (tìm bằng grep, không ghi số dòng vì số dòng đổi liên tục).
- Endpoint viết dạng "phương thức + đường dẫn", đúng như trong `backend/routers/` (hoặc `backend/main.py`).
- Mọi id, hàm, endpoint, đường dẫn file trong dấu backtick đều phải có thật trong code: sửa code mà đổi tên thì sửa luôn file này.
- "Tốn" ghi rõ thao tác có gọi dịch vụ thật hay không: **LLM** (9router), **Ảnh trả phí** (9router Gemini Image), **Muse** (tài khoản Muse thật), **Edge-TTS** (mạng Microsoft), **VieNeu** (model giọng chạy trên máy, nặng RAM/CPU), **ffmpeg** (chậm, tốn CPU).
- Cập nhật lần cuối: 21/10/2026, nhánh `tai-lieu-agent` (sau đợt dọn dẹp).

---

## 0. Điều kiện ban đầu

| Cần có | Để làm gì | Kiểm tra | Thiếu thì sao |
|---|---|---|---|
| `.venv` Python 3.14 + `backend/requirements-dev.txt` | chạy app và test | `.venv\Scripts\python.exe -m pytest tests --collect-only -q` | không chạy được |
| ffmpeg/ffprobe trong PATH | dựng video, đo thời lượng âm thanh | `ffmpeg -version` | không dựng được video; thời lượng âm thanh bị coi là 3 giây (lỗi đã biết) |
| 9router ở `127.0.0.1:20128` + `NINEROUTER_API_KEY` trong `.env` | LLM chia cảnh, phân tích vụ án, ảnh Gemini | gọi thử 1 lần nhỏ (`.cache/samples/probe_9router.py`) | chia cảnh rơi về bộ chia offline (prompt ảnh chung chung); phân tích vụ án báo "9router chưa sẵn sàng" |
| Mạng Internet | Edge-TTS, FontAwesome (CDN), Google Fonts | mở app, xem icon | không có giọng Edge; icon mất |
| `uv` + model VieNeu (cache trong `.cache/`) | giọng `vieneu-*` | server VieNeu ở `127.0.0.1:5005` (hiện dùng chung với douyin-movie-studio) | tự rơi về Edge-TTS, có ghi lý do |
| Tài khoản Muse đã đăng nhập: `backend/chrome_profiles/` + `backend/config/muse_fleet_accounts.json` | ảnh 2K, video 5s bằng Muse | cửa sổ Muse Fleet (`#btn-muse-cloud-status`) | việc Muse nằm chờ trong hàng; ảnh tự rơi sang 9router (tốn ảnh trả phí) |
| Chrome hoặc Edge | Fleet Runner điều khiển Muse | — | Fleet Runner không chạy |

Dữ liệu mẫu có sẵn (không xoá, không sửa khi thử):
- `projects/proj_crime_52c3a5e8` "MẪU — … (bản Việt)" và `projects/proj_crime_8329b12d` "MẪU — … (English)", dựng từ vụ `projects/_cases/case_7dcf6158` (Nhũ Cô, 41 cảnh, chưa có ảnh Muse, chưa có giọng).
- `projects/proj_ea5b04db` "ZZ Thử Muse — Chiếc ô đỏ trong hẻm": 5 cảnh có ảnh/video Muse thật. **Đây là dự án dùng để thử** (bấm, sửa, dựng).
- Bài vụ án thật dài: `.cache/samples/nhu_co.txt` (61 KB) và script chạy thật `.cache/samples/run_nhu_co.py` (không nằm trong git).
- Nút mẫu trong giao diện: truyện chữ (`data-sample`), truyện tranh (`#btn-step1-sample-grid`, `#btn-step1-sample-strip`), vụ án (`#btn-tc-sample-1..3`), 9-Grid (`#btn-msb-sample-detective`, `#btn-msb-sample-scifi`).

## 1. Mở app, server thử, phím tắt, đường dẫn trực tiếp

| Việc | Cách |
|---|---|
| Chạy app thật | `run.bat` → `run.py`: kiểm tra cổng (`existing_server()`), tự bật Fleet Runner (`start_fleet_runner_daemon()` → `backend/runners/autostart.py`, nơi duy nhất bật runner; tắt bằng `STORY_STUDIO_DISABLE_FLEET_AUTOSTART=1`), mở `http://localhost:8000` |
| Server thử để kiểm chứng (không đụng server 8000) | `.claude/launch.json` cấu hình `story-studio-8010`: cổng 8010, tắt hàng việc phân tích (`STORY_STUDIO_DISABLE_CASE_WORKER=1`) và tự bật Fleet Runner (`STORY_STUDIO_DISABLE_FLEET_AUTOSTART=1`). Mở bằng `preview_start` của trình duyệt trong app. Lưu ý: server thử vẫn đọc ghi `projects/` thật |
| Mở thẳng một dự án | `?project_id=<id>` (`initApp()`) |
| Mở thẳng cửa sổ Muse | `#muse`, `?mode=muse` hoặc `?view=muse` |
| Mở thẳng Hồ Sơ Kỳ Án | `#true-crime`, `?mode=true-crime` hoặc `?view=true-crime` (`initTrueCrimeStudio()`) |
| Phím tắt (`handleGlobalKeydown()`) | `Space` phát/dừng cảnh đang chọn; `Ctrl+S` lưu dự án; `Esc` đóng mọi cửa sổ (đang gõ trong ô nhập thì chỉ thoát ô); `Enter` trong `#step1-char-ref-url` nạp URL ảnh tham chiếu |
| Tự lưu | mọi sửa đổi gọi `saveStateToLocal()` (tên gây hiểu nhầm: thực chất hẹn `PUT /api/projects/{project_id}` sau 1,5 giây qua `ProjectSync`) |

## 2. Màn hình và tính năng

### 2.1 Thanh trên cùng

| Tính năng | Thao tác | Code giao diện | API → code server | Tốn |
|---|---|---|---|---|
| Quản lý dự án (mở danh sách, tạo, chuyển) | `#btn-project-dropdown` → cửa sổ `#modal-project-manager`; tạo: `#new-project-name-input` + `#btn-create-project`; chọn: dòng trong danh sách | `openProjectModal()`, `handleCreateNewProject()`, `switchProject()` | `GET /api/projects`, `POST /api/projects`, `GET /api/projects/{project_id}` → `project_service.py`. Dự án có `projects/<proj_id>/project.json` hỏng vẫn hiện trong danh sách với tên "⚠ Không đọc được: …"; mở nó thì API trả 409 kèm lý do, file được giữ nguyên | — |
| Chuyển bước 1–4 | `#step-nav-1` … `#step-nav-4` | `switchStep()` | Bước 4: `GET /api/projects/{project_id}/youtube-seo` | — |
| Hồ Sơ Kỳ Án | `#btn-open-true-crime-modal` | `openTrueCrimeModal()` | xem 2.6.7 | — |
| Trạng thái + cửa sổ Muse | `#btn-muse-cloud-status` (chữ trạng thái `#header-muse-status-text`, hỏi 5 s/lần) | `openMuseModal()` | `GET /api/muse-bridge/status` | — |
| Cắt truyện tranh | `#btn-open-comic-modal` | `openComicModal()` | xem 2.6.2 | — |
| 9-Grid Spec | `#btn-open-master-storyboard-modal` | `initMasterStoryboardSpec()` | xem 2.6.5 | — |
| Kịch bản AI | `#btn-open-script-modal` | `openScriptModal()` | xem 2.6.3 | — |
| Lưu | `#btn-save-project` hoặc `Ctrl+S` | `handleSaveProject()` | `PUT /api/projects/{project_id}` → `update_project_detail()` | — |
| Tạo bản tiếng Anh (chỉ hiện với dự án true-crime bản Việt: `metadata.case_id` và `language == 'vi'`) | `#btn-create-en-version` | `tcCreateEnglishVersion()`, `refreshLanguageVersionButton()` | `POST /api/projects/{project_id}/create-language-version`, theo dõi `GET /api/true-crime/jobs/{job_id}`; tải lại trang thì hỏi `GET /api/projects/{project_id}/language-version-job` → `language_versions.py`, `case_jobs.py` | **LLM** |
| Sản xuất video dài | `#btn-produce-long-video` | `startProduceLongVideo()` | xem 2.4 | xem 2.4 |

### 2.2 Bước 1 — Nhập liệu (`#step-view-1`)

| Tính năng | Thao tác | Code giao diện | API → code server | Tốn |
|---|---|---|---|---|
| Truyện chữ → dự án mới có cảnh và ảnh ("1-Click") | dán vào `#step1-script-textarea` (hoặc nút `data-sample`), chọn `#step1-engine-select`, `#step1-pacing-select`, `#step1-style-select`, nhân vật `#step1-char-preset-select` / `#step1-char-name` / `#step1-char-anchor`, ảnh tham chiếu (`#step1-char-ref-file-input`, `#step1-char-ref-url` + `#btn-step1-char-ref-apply-url`, gỡ: `#btn-step1-char-ref-remove`) rồi bấm `#btn-step1-process-script` | `handleStep1ProcessScript()` → sang Bước 2 | `POST /api/projects/create-from-script` → `create_project_from_script()`: chia cảnh bằng `analyze_vox_script_async()` (lỗi thì `split_text_into_scenes()` offline, báo lý do), rồi tạo ảnh từng cảnh bằng `generate_image()` (`generate_initial_images`) | **LLM**, **Muse** (ảnh), Muse lỗi thì **Ảnh trả phí** |
| Truyện tranh → dự án mới | thả ảnh vào `#step1-comic-dropzone` / `#step1-comic-file-input`, chọn `#step1-comic-mode`, `#step1-comic-order` (hoặc ảnh mẫu `#btn-step1-sample-grid`, `#btn-step1-sample-strip`), bấm `#btn-step1-process-comic` | `handleStep1ProcessComic()`, `loadComicSample()` | `POST /api/projects`, `POST /api/projects/{project_id}/comic/slice`, `POST /api/projects/{project_id}/comic/import-scenes` → `comic_slicer.py` (OpenCV) | — |
| Mở Hồ Sơ Kỳ Án | `#btn-step1-open-true-crime` | `openTrueCrimeModal()` | — | — |

### 2.3 Bước 2 — Bảng Đạo Diễn (`#step-view-2`)

Danh sách cảnh `#scene-list-container` do `renderSceneList()` vẽ. Mỗi thẻ cảnh có nút gắn thẳng hàm (onclick), không có id riêng:

| Nút trên thẻ cảnh (tooltip) | Hàm | API → code server | Tốn |
|---|---|---|---|
| "Gen lại ảnh AI" | `regenerateSceneImage()` | `POST /api/projects/{project_id}/scenes/{scene_id}/gen-image` → `generate_scene_image()` → `image_service.generate_image()` theo nguồn ảnh của dự án | tuỳ nguồn: **Muse** / **Ảnh trả phí** |
| "Muse 2K" / "Muse Video" (tạo ảnh 2K / video 5s) | `generateSceneWithMuse()` (mode `image` / `video`) | `POST /api/muse-bridge/tasks/create` (tự bật Fleet Runner nếu chưa chạy), hỏi tiến độ `GET /api/muse-bridge/tasks/{task_id}`; Fleet Runner nộp kết quả qua `POST /api/muse-bridge/tasks/{task_id}/complete` → `complete_task()` gắn ảnh/video vào cảnh | **Muse** |
| "Chọn video/ảnh từ Gallery Muse" | `openMuseModalForScene()` → trong gallery: `attachMediaToScene()` | `PUT /api/projects/{project_id}` | — |
| "Tải ảnh riêng từ máy" / "Tải video MP4 riêng từ máy" | `uploadCustomSceneImage()`, `uploadCustomSceneVideo()` | `POST /api/projects/{project_id}/scenes/{scene_id}/upload-media` | — |
| "Voice" / "Tạo lại file âm thanh Edge-TTS" | `regenerateSceneVoice()` | `POST /api/projects/{project_id}/scenes/{scene_id}/gen-voice` → `tts_service.generate_speech()` | **Edge-TTS** hoặc **VieNeu** |
| "Nghe thử voice đọc", tua | `playSceneVoice()`, `seekSceneAudio()` | file qua `GET /api/projects/{project_id}/media/{folder}/{filename}` | — |
| Sửa lời kể, prompt ảnh, prompt video, chuyển động | `updateSceneText()`, `updateSceneVisualPrompt()`, `updateSceneVideoPrompt()`, `updateSceneKenBurns()`, `switchScenePromptTab()` | tự lưu `PUT /api/projects/{project_id}` | — |
| Xem ảnh / video, "Bỏ qua" lỗi ảnh | `setMediaViewMode()`, `resetSceneImageStatus()` | tự lưu | — |
| Di chuyển, nhân bản, xoá cảnh | `moveScene()`, `duplicateScene()`, `deleteScene()` | tự lưu | — |

Các khối khác trong Bước 2:

| Tính năng | Thao tác | Code giao diện | API → code server | Tốn |
|---|---|---|---|---|
| Thêm cảnh | `#btn-add-scene` | `handleAddScene()` | tự lưu | — |
| Auto-Gen ảnh + giọng còn thiếu | `#btn-auto-gen-all` | `handleAutoGenAll()` (lặp từng cảnh qua `regenerateSceneImage()`, `regenerateSceneVoice()`) | như hai dòng trên | **Muse**/**Ảnh trả phí**, **Edge-TTS**/**VieNeu** |
| Live Studio Player | `#btn-preview-play-toggle`, `#preview-timeline-container`, `#btn-prev-scene`, `#btn-next-scene`, `#btn-play-all-story`, `#btn-toggle-fullscreen` | `togglePreviewPlayback()`, `seekStudioPlayback()`, `prevScene()`, `nextScene()`, `togglePlayAllStory()`, `togglePlayerFullscreen()` | — | — |
| Khoá nhân vật | `#character-consistency-card` → `#btn-edit-character` | `openCharacterModal()` | xem 2.6.4 | — |
| Giọng đọc + nghe thử | `#select-voice`, `#btn-preview-voice-sample` | `togglePlayVoiceSample()` | `GET /api/voices/{voice_id}/sample` (chưa có file mẫu thì sinh mới vào `backend/static/voice_samples/`) | **Edge-TTS**/**VieNeu** khi chưa có mẫu |
| Nhạc nền + tải nhạc lên | `#select-bgm`, `#bgm-upload-input` | `loadBgmOptions()`, `handleBgmUpload()` | `GET /api/bgm-tracks`, `POST /api/bgm-tracks/upload` (lưu `backend/assets/bgm/custom_*.mp3`) | — |
| Ducking, phụ đề cứng, chuyển cảnh, kiểu phụ đề | `#toggle-audio-ducking`, `#toggle-hardsub`, `#select-transition`, `#select-subtitle-style` | tự lưu | — | — |
| Kết xuất video → Bước 3 | `#btn-produce-from-board` | `startProduceLongVideo()` | xem 2.4 | xem 2.4 |
| Nâng cao: nguồn ảnh, phong cách, vẽ lại / thu lại toàn bộ | `#btn-toggle-asset-accordion` → `#select-image-provider` (`meta_muse_cloud`, `9router_gemini`, `pollinations`, `api` = DALL-E, `mock_cinematic` = ảnh giả offline), `#select-project-style`, `#btn-regen-all-images`, `#btn-regen-all-voices` | `handleRegenAllImages()`, `handleRegenAllVoices()` (có hỏi xác nhận) | gen-image / gen-voice từng cảnh | **mỗi cảnh một lượt** ảnh/giọng |

### 2.4 Bước 3 — Tiến trình sản xuất (`#step-view-3`)

| Tính năng | Thao tác | Code giao diện | API → code server | Tốn |
|---|---|---|---|---|
| Sản xuất video dài (5 giai đoạn) | `#btn-produce-long-video` hoặc `#btn-produce-from-board`; theo dõi trong `#step-view-3`; xong bấm `#btn-producer-goto-cinema` | `startProduceLongVideo()`: lưu dự án trước (`flushProjectSave()`), theo dõi bằng WebSocket `/ws/render/{render_id}`, rớt thì hỏi `GET /api/render-status/{render_id}` | `POST /api/projects/{project_id}/produce-long-video` → `execute_produce_long_video()`: (1) chia cảnh bằng LLM **chỉ khi gửi kèm `text`** (giao diện không gửi), (2) thu giọng cảnh còn thiếu, (3) tạo ảnh cảnh còn thiếu bằng `generate_image()`; dự án vụ án thì vẽ lại bảng ghim, thẻ có ảnh minh hoạ lấy từ ảnh các cảnh (`redraw_board_images()`), (4) dựng từng cảnh `render_scene_video()` (dự án vụ án: trộn tiếng động thật theo `sfx_cue` vào giọng cảnh bằng `mix_scene_sfx()`, thư viện CC0 `backend/assets/sfx_cc0/`), (5) ghép `assemble_full_video()` (dự án vụ án: nhạc nền đổi theo `bgm_energy` từng đoạn, `build_energy_bgm()`; chọn "không nhạc" thì thôi) ra `projects/<id>/renders/story_final.mp4` | **Edge-TTS**/**VieNeu**, **Muse**/**Ảnh trả phí** cho cảnh thiếu ảnh, **ffmpeg** |

### 2.5 Bước 4 — Rạp chiếu và đóng gói YouTube (`#step-view-4`)

| Tính năng | Thao tác | Code giao diện | API → code server | Tốn |
|---|---|---|---|---|
| Xem video thành phẩm | `#cinema-video-player` | `loadCinemaYouTubePackage()` | `GET /api/projects/{project_id}/media/{folder}/{filename}` (`renders/story_final.mp4`) | — |
| Tải video / phụ đề | `#btn-cinema-download-video`, `#btn-cinema-download-ass`, `#btn-cinema-download-srt` | link trực tiếp | `GET /api/projects/{project_id}/download`, `GET /api/projects/{project_id}/download-ass`, `GET /api/projects/{project_id}/download-srt` | — |
| Mở thư mục trên Windows | `#btn-cinema-open-folder` | `API.openFolder` | `POST /api/open-folder` → `open_folder()` (mở Explorer) | — |
| Gói SEO YouTube, bước 1: tìm từ khoá thật | từ khoá gốc `#yt-seo-seed`; nguồn `#yt-seo-src-suggest` (gợi ý ô tìm kiếm YouTube), `#yt-seo-src-api` (video đứng đầu tìm kiếm, chỉ bật khi có `YOUTUBE_API_KEY`); dán tay `#yt-seo-manual`; bấm `#btn-yt-seo-research`; xem `#yt-seo-candidates`, lỗi nguồn `#yt-seo-research-errors`, bằng chứng `#yt-seo-top-videos` | `ytSeoLoad()` trong `backend/static/youtube_seo.js` (`loadCinemaYouTubePackage()` gọi khi mở Bước 4) | `GET /api/projects/{project_id}/youtube-seo`, `POST /api/projects/{project_id}/youtube-seo/research` → `youtube_keywords.research()`, lưu bằng `youtube_seo_pack.save_research()`; dữ liệu quá 30 ngày tự bỏ | gọi mạng: gợi ý tìm kiếm (không cần key, đường không chính thức), YouTube Data API (khoảng 100 lần tìm mỗi ngày) |
| Gói SEO YouTube, bước 2–3: AI viết trong khuôn, sửa, kiểm luật, tải | tích từ khoá trong `#yt-seo-candidates` (thứ tự ở `#yt-seo-selected`, đầu tiên là từ khoá chính); `#btn-yt-seo-generate`; chọn tiêu đề `#yt-seo-title-options`; sửa `#input-seo-title`, `#textarea-seo-desc`, `#input-seo-tags`, `#yt-seo-hashtags`; kết quả luật `#yt-seo-checks`; `#btn-yt-seo-save`; tải `#btn-yt-seo-download`; sao chép `#btn-copy-seo-title`, `#btn-copy-seo-desc`, `#btn-copy-seo-tags` | `backend/static/youtube_seo.js`, `copyToClipboard()` | `POST /api/projects/{project_id}/youtube-seo/generate` → `youtube_seo_pack.generate_pack()` (chương theo thời gian `renders/story_final.mp4`; chưa dựng video thì 409); `PUT /api/projects/{project_id}/youtube-seo/pack` → `update_pack()` (không đạt luật thì 422 kèm từng luật); `GET /api/projects/{project_id}/youtube-seo/download` → `download_text()`. Luật: `youtube_seo_rules.py` | **LLM** khi Tạo gói SEO (1 lần, thêm lần thử lại khi AI viết sai luật) |
| Thumbnail | chữ: `#input-thumb-headline`, `#input-thumb-subtext` (để trống thì lấy chữ thumbnail của gói SEO, chưa có thì tên dự án); `#btn-generate-custom-thumbnail`; tải: `#btn-download-thumbnail-direct`, `#btn-cinema-download-thumbnail` | `handleGenerateCustomThumbnail()` | `POST /api/projects/{project_id}/thumbnail/generate`, `GET /api/projects/{project_id}/thumbnail` → `thumbnail_service.generate_youtube_thumbnail()` (font Oswald đóng gói trong `backend/assets/fonts/`, thiếu thì font Windows; font đủ chữ có dấu; ký tự font không vẽ được thì 422 kèm ký tự đó; nền là ảnh cảnh đầu tiên không phải ảnh chữ như thẻ miễn trừ, bảng ghim; file tối đa 2 MB) | — |

### 2.6 Cửa sổ (modal)

`Esc` đóng mọi cửa sổ (`closeAllModals()`); Hồ Sơ Kỳ Án đóng thì phân tích vẫn chạy nền.

#### 2.6.1 Quản lý dự án — xem 2.1.

#### 2.6.2 Cắt truyện tranh (`#modal-comic-slicer`)
- Mở: `#btn-open-comic-modal`. Đóng: `#btn-close-comic-modal`, `#btn-cancel-comic-modal`.
- Thao tác: ảnh vào `#comic-dropzone` / `#comic-file-input` (hoặc `#btn-sample-manga-grid`, `#btn-sample-webtoon-strip`), chọn `#comic-layout-mode`, `#comic-reading-order`, `#comic-min-area`, bấm `#btn-start-slice`; xem kết quả `#tab-btn-panels` / `#tab-btn-annotated`; chọn ảnh khác `#btn-reset-comic`; tuỳ chọn xoá cảnh cũ `#comic-clear-existing-cb`; nhập vào dự án `#btn-import-comic-to-storyboard`.
- Code: `handleStartSlice()`, `handleImportComicToStoryboard()`.
- API: `POST /api/projects/{project_id}/comic/slice` (chưa có dự án: `POST /api/comic/slice`), ảnh cắt phục vụ qua `GET /api/comic/media/{session_id}/{filename}`, nhập: `POST /api/projects/{project_id}/comic/import-scenes` → `comic_slicer.py`. Ảnh cắt tạm nằm ở `backend/static/comic_slices/<phiên>/`.
- Khung không chép được ảnh (không có file, nằm ngoài thư mục cho phép, chép lỗi) vẫn thành cảnh nhưng bị đánh dấu "Lỗi ảnh" (`status_image="error"`, lý do trong `metadata.image_error`); API trả `failed_panels`, giao diện cảnh báo số khung lỗi.

#### 2.6.3 Kịch bản AI (`#modal-script-importer`)
- Mở: `#btn-open-script-modal`. Đóng: `#btn-close-script-modal`, `#btn-cancel-script-modal`.
- Thao tác: dán `#import-script-textarea` (hoặc nút `data-sample`), chọn `#split-mode-select`, `#split-style-select`, bấm `#btn-submit-script-split`.
- Code: `handleSubmitScriptSplit()`.
- API: `POST /api/projects/{project_id}/split-script` (chưa có dự án: `POST /api/split-script`) → `split_text_into_scenes()` **chia offline theo luật, không gọi LLM**; cảnh mới được **nối thêm** vào dự án đang mở.

#### 2.6.4 Khoá nhân vật (`#modal-character-editor`)
- Mở: `#btn-edit-character`. Đóng: `#btn-close-character-modal`, `#btn-cancel-char-modal`.
- Thao tác: `#edit-char-name`, `#edit-char-prompt`, `#edit-char-style`, `#edit-char-negative`, lưu `#btn-save-character`.
- Code: `openCharacterModal()`, `handleSaveCharacter()` → tự lưu `PUT /api/projects/{project_id}`.

#### 2.6.5 9-Grid Spec / Master Storyboard (`#modal-master-storyboard`)
- Mở: `#btn-open-master-storyboard-modal`. Đóng: `#btn-close-master-sb-modal`, `#btn-cancel-master-sb-modal`.
- Thao tác: mẫu `#btn-msb-sample-detective`, `#btn-msb-sample-scifi`; kịch bản `#master-sb-script-text`; `#master-sb-style-dna`, `#master-sb-grid-mode`; phân rã `#btn-run-master-sb-deconstruct` (xem trước ở `#master-sb-preview-cards`); nạp `#btn-apply-master-sb-to-project`.
- Code: `initMasterStoryboardSpec()` (gắn sự kiện riêng, gọi `fetch` trực tiếp).
- API: `POST /api/storyboard/deconstruct` → `storyboard_engine.deconstruct_script_async()` (lỗi thì `deconstruct_script_offline()`); `POST /api/storyboard/import` → luôn tạo **dự án mới** (giao diện cố ý không gửi `project_id`, vì gửi thì server ghi đè toàn bộ dự án đó).
- Tốn: **LLM** khi phân rã.

#### 2.6.6 Muse Fleet (`#modal-muse-cloud`)
- Mở: `#btn-muse-cloud-status` hoặc `#muse`. Đóng: `#btn-close-muse-modal`, `#btn-close-muse-modal-footer`.
- Thao tác: làm mới danh sách tài khoản `#btn-muse-refresh-accounts`; bấm vào ô tài khoản trong `#muse-fleet-pool-grid` để chọn tài khoản đang dùng; chép lệnh `#btn-copy-start-fleet-cmd` / `#btn-copy-setup-accounts-cmd`; gallery: xoá một mục, **`#btn-clear-all-gallery` xoá vĩnh viễn toàn bộ `backend/static/muse_outputs/`**; gắn ảnh/video vào cảnh (`attachMediaToScene()`).
- Code: `openMuseModal()`, `loadMuseAccountsUI()`, `handleMuseFleetAccountClick()`.
- API: `GET /api/muse-bridge/accounts`, `POST /api/muse-bridge/accounts/switch`, `GET /api/muse-bridge/status`, `DELETE /api/muse-bridge/gallery/{task_id}`, `DELETE /api/muse-bridge/gallery/clear-all` → `routers/muse_bridge.py`.
- Đăng nhập tài khoản: `setup_muse_accounts.bat` (mở trình duyệt có giao diện cho từng tài khoản, lưu vào `backend/chrome_profiles/`). Chạy Fleet Runner tay: `start_muse_fleet.bat`. Fleet Runner (`backend/runners/muse_fleet_runner.py`) nhận việc qua `GET /api/muse-bridge/tasks/poll`, báo `POST /api/muse-bridge/tasks/{task_id}/progress`, `/complete`, `/fail`, đăng ký `POST /api/muse-bridge/workers/register`, `POST /api/muse-bridge/workers/heartbeat`; một máy chỉ một runner (`runners/single_instance.py`, khoá `backend/runners/.fleet_runner.lock`).

#### 2.6.7 Hồ Sơ Kỳ Án / True Crime (`#modal-true-crime`, code `backend/static/true_crime.js`)
Mở: `#btn-open-true-crime-modal`, `#btn-step1-open-true-crime` hoặc `#true-crime`. Đóng: `#btn-close-true-crime-modal`, `#btn-cancel-true-crime-modal` (phân tích vẫn chạy nền; mở lại thì theo dõi tiếp vụ lưu trong localStorage `story_studio_true_crime_case_id`).

| Màn trong cửa sổ | Thao tác | Code giao diện | API → code server | Tốn |
|---|---|---|---|---|
| Nhập bài | dán `#tc-case-text` (hoặc `#btn-tc-sample-1..3`), chọn `#tc-duration-select` (8/15/20/30 phút), `#tc-visual-style`, `#tc-voice-vi`, `#tc-voice-en` (danh sách từ `GET /api/voices`), `#tc-vision-engine`; bấm `#btn-tc-analyze` | `tcAnalyze()`, `tcLoadSample()` | `POST /api/true-crime/analyze` → `case_store.py` tạo vụ trong `projects/_cases/<case_id>/`, `case_worker.py` chạy hàng việc nền | **LLM**: vụ thật 60–90 phút, 60–70 lần gọi |
| Tiến độ | `#tc-progress` (thanh `#tc-progress-bar`, lỗi `#tc-progress-error`); `#btn-tc-resume` "Thử lại"; `#btn-tc-new-case` "Phân tích vụ khác" | `tcRenderProgress()`, `tcResume()`, `tcNewCase()` | hỏi `GET /api/true-crime/cases/{case_id}/progress` mỗi 2 s; `POST /api/true-crime/cases/{case_id}/resume` | **LLM** khi thử lại |
| Duyệt dàn ý (vụ dừng ở trạng thái `review`) | `#tc-outline-review`: sửa trong `#tc-outline-parts` (chuyển/bỏ sự việc, đổi loại nhịp, số cảnh, số phút tư liệu ở `#tc-outline-intro`), `#btn-tc-outline-revert`, `#btn-tc-outline-save`, `#btn-tc-outline-approve` | `tcSaveOutline()`, `tcApproveOutline()`, `tcRevertOutline()` | `GET /api/true-crime/cases/{case_id}/outline`, `PUT /api/true-crime/cases/{case_id}/outline` (sai thì 400 kèm lý do bằng lời thường), `POST /api/true-crime/cases/{case_id}/outline/approve` → `case_adaptation_steps.py` | **LLM** sau khi duyệt (viết cảnh) |
| Xem lại kế hoạch | `#tc-review`: cảnh báo `#tc-warnings` (bấm để tới cảnh), bảng tên `#tc-entity-table` + `#btn-tc-save-entities`, thêm tên `#tc-add-kind`, `#tc-add-real`, `#tc-add-alias-vi`, `#tc-add-alias-en`, `#btn-tc-add-entity`; bảng ghim `#tc-evidence-canvas` (lọc `#tc-scene-scrubber`, ngôn ngữ `#tc-board-lang`); sửa lời từng cảnh trong `#tc-scene-review` | `tcRenderReview()`, `tcSaveEntities()`, `tcAddEntity()`, `tcSaveScene()`, `EvidenceBoardRenderer` | `GET /api/true-crime/cases/{case_id}`, `PUT /api/true-crime/cases/{case_id}/entities`, `PUT /api/true-crime/cases/{case_id}/scenes/{order}` → `case_plan_edits.py`, `case_adaptation_checks.py` | — |
| Tạo dự án bản Việt | `#btn-tc-create-vi` (chỉ bật khi xong và không còn cảnh bị đánh dấu, gợi ý ở `#tc-create-hint`) | `tcCreateVietnameseProject()` → mở dự án ở Bước 2 | `POST /api/true-crime/cases/{case_id}/create-project` → `case_project_builder.py` (vẽ bảng ghim, thẻ miễn trừ bằng `investigation_board_engine.py`) | — |
| Tạo bản tiếng Anh | `#btn-create-en-version` trên thanh trên cùng | xem 2.1 | xem 2.1 | **LLM** |

## 3. Luồng xuyên suốt

### A. Truyện chữ → video YouTube
1. Bước 1: dán truyện vào `#step1-script-textarea` → `#btn-step1-process-script`. Server tạo `projects/<proj_id>/project.json`, chia cảnh (**LLM**), tạo ảnh (**Muse**, lỗi thì **Ảnh trả phí**). Tự sang Bước 2.
2. Bước 2: kiểm từng thẻ cảnh; thiếu ảnh/giọng thì `#btn-auto-gen-all` hoặc nút trên thẻ; chọn giọng `#select-voice`, nhạc `#select-bgm`.
3. `#btn-produce-from-board` → Bước 3 theo dõi 5 giai đoạn.
4. Bước 4: xem `#cinema-video-player`, tải `#btn-cinema-download-video`, làm SEO/thumbnail.
- Kiểm chứng: file `projects/<proj_id>/renders/story_final.mp4` tồn tại, mở xem khung hình và nghe tiếng; phụ đề `.srt`/`.ass` khớp lời.

### B. Truyện tranh → video
1. Bước 1: ảnh vào `#step1-comic-dropzone` (hoặc `#btn-step1-sample-grid`) → `#btn-step1-process-comic` (tạo dự án, cắt khung, nhập cảnh).
2. Tiếp như luồng A từ bước 2 (lời kể từng cảnh phải tự viết hoặc sửa trên thẻ cảnh).

### C. Vụ án thật → video bản Việt → bản tiếng Anh
1. `#btn-open-true-crime-modal` → dán bài `#tc-case-text`, chọn thời lượng → `#btn-tc-analyze` (**LLM**, chạy nền; đóng cửa sổ được).
2. Vụ dừng ở `review` → duyệt dàn ý `#btn-tc-outline-approve` (**LLM** viết cảnh).
3. Xem lại: tên hư cấu, cảnh báo, lời từng cảnh, bảng ghim → `#btn-tc-create-vi` → dự án `proj_crime_*` mở ở Bước 2.
4. Làm tiếp như luồng A (ảnh Muse, giọng, dựng video).
5. Bản tiếng Anh: trên dự án bản Việt bấm `#btn-create-en-version` (**LLM**), ra dự án mới bản Anh.
- Dữ liệu: vụ ở `projects/_cases/<case_id>/` (file `projects/_cases/<case_id>/source.txt` chứa **tên thật**, không đưa ra ngoài); dự án ở `projects/proj_crime_*`.
- Kiểm chứng: kế hoạch không cờ chặn, không lọt tên thật (xem `case_adaptation_checks.py`), thời lượng giọng thật gần số phút đã chọn (lần đo 21/10: 8 phút → Việt 7,54, Anh 7,43 phút).

### D. Ảnh/video Muse cho từng cảnh
1. Cần tài khoản đã đăng nhập (`setup_muse_accounts.bat`) và Fleet Runner đang chạy (tự bật bởi `run.py` hoặc lần tạo việc đầu tiên).
2. Trên thẻ cảnh bấm "Muse 2K" hoặc "Muse Video" → việc vào hàng `POST /api/muse-bridge/tasks/create`.
3. Fleet Runner lấy việc, mở Muse, tải kết quả, nộp `complete` → ảnh/video tự gắn vào cảnh; bản sao vào gallery `backend/static/muse_outputs/`.
- Kiểm chứng: thẻ cảnh hiện ảnh/video mới, file nằm trong `projects/<proj_id>/images|videos/`; log `backend/muse_fleet_runner.log`. Trạng thái "Chưa kết nối" trên đầu trang không có nghĩa runner đứng.

### E. Đóng gói bản bán
- `.venv\Scripts\python.exe tools\build_release.py` → `dist/story-studio-<ngày>.zip`, chỉ lấy file trong danh sách cho phép (`REQUIRED_FILES`, `WHITELIST_GLOBS`), tự chặn `.env`, hồ sơ trình duyệt, chuỗi giống key, đường dẫn máy này, và kiểm mọi đường `/static/...` mà giao diện gọi đều có trong gói.

## 4. Chức năng chỉ có API (giao diện không gọi)

Dùng được qua `/docs` (Swagger) hoặc test; sửa tới thì nhớ không có nút để bấm thử.
- `GET /api/styles`, `GET /api/characters/presets`, `GET /api/characters/presets/{char_id}`, `GET /api/bgm/{filename}`
- `GET /api/vox/pacing-presets`, `POST /api/vox/analyze-script` (**LLM**), `POST /api/projects/{project_id}/vox-script`, `POST /api/novel/ingest-chapter` (**LLM**)
- `POST /api/projects/create-1click-pipeline` (bí danh của create-from-script)
- Cảnh lẻ: `POST /api/projects/{project_id}/scenes`, `PUT /api/projects/{project_id}/scenes/{scene_id}`, `DELETE /api/projects/{project_id}/scenes/{scene_id}`, `POST /api/projects/{project_id}/scenes/reorder`, `POST /api/gen-image`
- `DELETE /api/projects/{project_id}` (**xoá vĩnh viễn** bằng `shutil.rmtree`, giao diện không có nút xoá dự án)
- `POST /api/projects/{project_id}/render` (đường dựng cũ, chỉ test dùng; đường thật là produce-long-video)
- `POST /api/true-crime/render-board-scene/{scene_id}`, `GET /api/muse-bridge/reference-file` (runner tải ảnh tham chiếu), `GET /api/muse-bridge/download/{task_id}`, `POST /api/muse-bridge/accounts/add`
- `GET /api/health` (giao diện hỏi 8 s/lần; `run.py` dùng để biết Story Studio đã chạy chưa)

## 5. Tiến trình nền, cổng, nơi chứa dữ liệu

| Thứ | Ở đâu | Ghi chú |
|---|---|---|
| Web server | `127.0.0.1:8000` (`STORY_STUDIO_PORT`) | `run.py` không bật server thứ hai nếu cổng đã có Story Studio |
| Hàng việc phân tích vụ án | chạy trong server, khoá `projects/_cases/.worker.lock` | bật server là chạy tiếp vụ dở (**LLM**), trừ khi `STORY_STUDIO_DISABLE_CASE_WORKER=1` |
| Fleet Runner | tiến trình Python riêng, khoá `backend/runners/.fleet_runner.lock`, log `backend/muse_fleet_runner.log` | gọi về cổng server qua `--url` (`runner_url()` theo `STORY_STUDIO_PORT`); chạy tay bằng `start_muse_fleet.bat` thì mặc định cổng 8000 |
| 9router | `127.0.0.1:20128` | chương trình ngoài |
| Server VieNeu | `127.0.0.1:5005` | tự bật qua `uv`, không tự tắt |
| Dự án | `projects/<proj_id>/project.json` + `images/`, `videos/`, `audio/`, `renders/` | ghi duy nhất qua `project_service.save_project()` (file tạm rồi đổi tên, `services/safe_files.py`) |
| Vụ án | `projects/_cases/<case_id>/` | ghi qua `case_store.py` (ghi an toàn) |
| Đầu ra phục vụ tĩnh | `backend/static/muse_outputs/`, `comic_slices/`, `evidence_boards/`, `reference_images/` | git bỏ qua |

## 6. Test tự động theo tính năng

| Tính năng | File test |
|---|---|
| Dự án, đồng bộ, lưu, file hỏng | `tests/test_api.py`, `tests/test_project_sync.py`, `tests/test_project_service_safety.py`, `tests/test_default_voice.py` |
| Chia cảnh (LLM, offline, bài dài) | `tests/test_script_splitter_long_text.py`, `tests/test_scene_analysis_fallback_reason.py`, `tests/test_vox_narrative.py` |
| Ảnh, nhân vật | `tests/test_image.py`, `tests/test_character_consistency.py` |
| Giọng | `tests/test_tts.py` (6 test gắn cờ `live`: Edge-TTS thật, một test bật VieNeu), `tests/test_ui_scan_fixes.py` |
| Dựng video | `tests/test_video.py`, `tests/test_no_fake_success_and_motion_render.py`, `tests/test_youtube_studio_v2_improvements.py`, `tests/test_adversarial_qa.py` |
| Truyện tranh | `tests/test_comic.py` (test gọi produce-long-video thật gắn cờ `live`: **LLM**, **Ảnh trả phí**), `tests/test_comic_import_errors.py` |
| 9-Grid / Master Storyboard | `tests/test_youtube_storyboard_spec.py` |
| Muse | `tests/test_muse_fleet_routing.py`, `tests/test_muse_fleet_runner.py`, `tests/test_muse_fleet_runner_media.py`, `tests/test_muse_fleet_runner_integration.py` |
| True crime | `tests/test_case_*.py`, `tests/test_true_crime_router.py`, `tests/test_true_crime_e2e.py` (offline dù tên có e2e), `tests/test_investigation_board.py` |
| Chạy một server, bật Fleet Runner, mở thư mục, bảo mật | `tests/test_run_single_server.py`, `tests/test_fleet_autostart.py`, `tests/test_open_folder.py`, `tests/test_gate_gout_regressions.py` |
| Test không chạm dữ liệu thật | `tests/test_test_isolation.py` |
| Đường cấm, tài liệu khớp code | `tests/test_architecture.py`, `tests/test_feature_map.py` (chạy cả trong hook trước commit) |
| Gọi dịch vụ thật (cờ `live`, chỉ chạy khi được yêu cầu: `pytest -m live`) | 19 test: `tests/test_e2e_pipeline.py`, `tests/test_nanahoshi_1click_e2e.py`, `tests/test_case_adaptation_live.py` (cần thêm `STORY_STUDIO_LIVE=1`) và 12 test lẻ trong `tests/test_tts.py`, `tests/test_video.py`, `tests/test_api.py`, `tests/test_comic.py`, `tests/test_adversarial_qa.py` |

Test không gắn cờ `live` mà gọi mạng, 9router, VieNeu hay server 8000 thì bị `tests/conftest.py` chặn và báo lỗi.
Giao diện chưa có test tự động: kiểm bằng server thử 8010 + trình duyệt (mục 1).
