# Giao diện gọn kiểu ElevenLabs: 5 bước, mỗi tính năng một chỗ — thiết kế

Ngày 15/11/2026. Trạng thái: **chủ dự án đã duyệt bản xem thử** (15/11/2026, "Duyệt, viết kế hoạch"). Kế hoạch code: `docs/superpowers/plans/2026-11-15-giao-dien-gon.md`.

Bản xem thử bấm được: `docs/superpowers/specs/2026-11-15-giao-dien-gon-ban-xem-thu.html` (mở bằng trình duyệt). Sơ đồ luồng hiện tại và kỳ vọng làm hôm trước: `docs/superpowers/specs/2026-11-14-luong-hien-tai-va-ky-vong.html`.

## 1. Vì sao

**[Nguyên văn chủ dự án]** (15/11/2026)

> Mục đích của tôi là Luồng hoạt động cần phải lean hơn, những tính năng nào bị double hoặc xuất hiện nhiều lần, nhiều nơi thì gom về 1 nơi duy nhất theo trình tự các bước đã chốt. Đã xuất hiện ở 1 nơi rồi thì không có xuất hiện ở nơi khác. Phân loại tính năng vào các bước phù hợp để từ ý tưởng, làm lại ý tưởng (với 01 số thể loại nhất định thì có, còn lại thì không), rồi chốt được mẫu nhân vật và cảnh, hướng graphic cho video rồi generate video bằng muse và ghép các cảnh với nhau. Rồi khu vực quản lý tài khoản gồm tài khaorn gemini cho API, tài khoản Muse như nào... Tôi muốn UI UX phải lean hết cỡ, hiện tại rất là rối.

> Luồng 1 UI nhập liệu phải thiết kế tính năng sao cho có thể lựa chọn nhiều chủ đề hơn không chỉ dừng lại ở truyện và kỳ án. Cái này là mục tiêu dài hạn để mở rộng, không phải là thiết kế luôn bây giờ.

> UI hồ sơ kỳ án thì đây là chỉ dành cho kỳ án. Vì thế để tránh loạn các luồng với nhau.

Yêu cầu giao diện (chủ dự án dán, 15/11/2026): làm lại toàn bộ lớp giao diện, giữ 100% tính năng, logic, API và dữ liệu; luồng thẳng trong một không gian làm việc; mặc định chỉ hiện phần chính, phần phụ cất vào thanh công cụ khi di chuột, ô nổi hoặc ngăn kéo; phong cách ElevenLabs sáng, chỉ đen trắng xám:
- màu: vùng làm việc `#FFFFFF`, thanh bên `#F9FAFB`/`#F4F4F5`, đường kẻ `1px solid #E4E4E7`, không đổ bóng nặng;
- nút chính viên thuốc đen `#09090B`, chữ trắng, `border-radius: 9999px`, `padding: 8px 16px`, chữ 13px nặng 500; nút phụ trong suốt hoặc viền `#E4E4E7`, rê chuột nền `#F4F4F5`;
- chữ `Be Vietnam Pro` toàn app; mục điều hướng 13–14px nặng 500 màu `#52525B`, đang chọn chữ `#09090B` nền `#F4F4F5` bo 6px; nhãn nhóm 11–12px màu `#A1A1AA`; tiêu đề trang 20–24px nặng 600, giãn chữ `-0.02em`; chữ thân 14–15px, dòng 1.6, màu `#18181B`;
- khung: thanh bên trái 240px thu gọn được, biểu tượng 16px nét 1.5px, cụm tiện ích ghim đáy; thanh trên 52px có nút thu thanh bên, đường dẫn trang, ô tìm kiếm viên thuốc ở giữa, trạng thái bên phải; vùng giữa tối đa 1100px canh giữa; thẻ bo 12px viền `#E4E4E7`;
- khoá cả trang cao 100vh, chỉ vùng giữa cuộn.

Hiện trạng đo trên code (15/11/2026): 32 nhóm tính năng; 13 nhóm có ở từ 2 nơi trở lên, tổng 43 chỗ; 9 cửa sổ nổi; 91 nút có id; chọn phong cách hình ở 6 nơi; ô dán nội dung ở 4 nơi; tạo ảnh cảnh có 5 đường. Bảng đầy đủ: trang "Gom tính năng trùng" trong bản xem thử.

## 2. Mục tiêu, không làm, chống mục tiêu

**Mục tiêu**
1. Năm trang theo đúng thứ tự làm video: **Ý tưởng → Kịch bản và giọng → Hình mẫu → Cảnh → Dựng và xuất bản**. Thêm ba trang ngoài luồng: **Dự án**, **Thư viện Muse**, **Tài khoản và kết nối** (ghim đáy thanh bên).
2. Mỗi tính năng hiện ở đúng một trang (bảng mục 4). Không còn cửa sổ nổi nào cho tính năng thuộc luồng chính.
3. Hồ Sơ Kỳ Án không còn là cửa sổ riêng: ô dán bài nằm ở trang Ý tưởng, dàn ý và tên hư cấu là thẻ trong trang Kịch bản, chỉ hiện khi dự án là vụ án.
4. Bước 1 chọn thể loại bằng thẻ; mỗi thể loại là một "khuôn" khai báo ở một chỗ (có viết lại không, bước sau có thêm gì). Thêm thể loại mới về sau là thêm một khuôn.
5. Phong cách hình chọn khi bắt đầu video, ở trang Ý tưởng (lý do: mục 4.4). Trang Hình mẫu chỉ hiện phong cách của dự án và cất ô đổi phong cách của dự án đã có vào một ô nổi kèm cảnh báo.
6. Trang Tài khoản và kết nối gom tài khoản Muse, nguồn tạo ảnh và trạng thái kết nối AI (cổng, đã có khoá chưa, gọi thử được không), giọng đọc, khoá YouTube.
7. Giao diện đúng hệ màu, chữ, khung ở mục 1.

**Không làm (lần này)**
- Không đổi cách chạy của pipeline: chia cảnh, viết lời, vẽ bảng nhân vật, lưới 9 ô, làm clip Muse, chốt 45%, dựng, SEO giữ nguyên hành vi. Phần "Video Muse nhanh hơn" (cảnh thử, duyệt lưới xong tự làm clip, nút dừng) là **đợt 6, một thiết kế riêng** cần chủ dự án duyệt riêng và cần chạy thật với Muse.
- Không làm thể loại mới (tin tức, kiến thức, video ngắn): chỉ chừa chỗ trong khuôn.
- Không cho nhập khoá truy cập trên giao diện: khoá vẫn ở `.env`, trang Tài khoản chỉ báo có hay chưa.
- Không làm chế độ tối, không làm bản điện thoại riêng (chỉ cần không vỡ ở màn hẹp).
- Không thêm thư viện giao diện mới (không React, không bộ biểu tượng mới).

**Chống mục tiêu** (làm xong mà dính một điều này là hỏng)
- Một nút, một ô hay một tính năng đang dùng được biến mất mà không nằm trong danh sách gỡ đã duyệt (mục 4.2).
- Bấm một nút ở chỗ mới mà nó không làm gì, hoặc làm hai lần (đường cấm 10).
- Một thao tác tốn tiền (LLM, Muse, ảnh trả phí) chạy mà người dùng không bấm.
- Giao diện mới mà vẫn có hai chỗ cho cùng một việc.
- Chữ từ máy chủ chèn vào trang mà không lọc (đường cấm 9).

## 3. Cách làm đã chọn

| Cách | Được | Mất |
|---|---|---|
| **A. Giữ phần xử lý và mọi id, dựng lại khung HTML/CSS quanh chúng, dời từng khối sang trang mới** (đã chọn) | Mọi hàm JS tìm phần tử theo id vẫn chạy; test hiện có vẫn kiểm được; làm từng đợt, đợt nào xong app vẫn dùng được | Một số khối bên trong vẫn mang class Tailwind cũ cho tới khi được dọn ở đợt sau |
| B. Viết lại toàn bộ giao diện từ số không (khoảng 12.000 dòng JS/HTML) | Mã sạch | Giao diện chưa có test tự động: rất dễ làm rơi tính năng mà không ai biết; app không dùng được trong lúc làm |
| C. Chỉ đổi màu, chữ, giữ bố cục 4 bước | Nhanh | Không giải quyết "rối" và trùng lặp, trái mục đích chính |

Chủ dự án duyệt cách A cùng bản xem thử (trang "Thứ tự làm").

## 4. Gom tính năng

### 4.1 Mỗi trang chứa gì

**Ý tưởng** (thay Bước 1 `#step-view-1`)
- Hàng thẻ thể loại: Truyện chữ, Vụ án có thật, Truyện tranh; ba thẻ "Sau này" chỉ để minh hoạ, không bấm được.
- Ô dán duy nhất `#step1-script-textarea`. Thể loại Truyện tranh thay ô dán bằng khu thả ảnh (`#step1-comic-dropzone`, `#step1-comic-mode`, `#step1-comic-order`, `#btn-step1-process-comic`).
- Phong cách hình `#step1-style-select`, hiện dạng thẻ (mục 4.4).
- Truyện chữ: ngôn ngữ lời review `#step1-language-select` (ô này hiện chỉ với truyện chữ, như hiện nay). Vụ án: số phút `#step1-case-duration`, cùng chỗ báo lỗi gửi bài `#tc-input-error` và ước thời gian `#tc-time-estimate` (dời từ cửa sổ Hồ Sơ Kỳ Án, để lỗi gửi bài vụ án vẫn hiện cho người dùng).
- "Tuỳ chọn" (ngăn kéo): `#step1-pacing-select`.
- Hai ô nguồn ảnh lúc tạo dự án `#step1-engine-select` (truyện) và `#tc-vision-engine` (vụ án) vào khối ẩn, giữ mặc định Muse; nguồn ảnh chọn ở trang Hình mẫu (mục 4.5).
- Nút chính `#btn-step1-process-script`.
- Ô `#step1-content-kind` giữ nguyên trong HTML (ẩn), thẻ thể loại đặt giá trị cho nó; `applyStep1ContentKind()` chạy như cũ.

**Kịch bản và giọng** (trang mới)
- Thẻ "Dàn ý" và "Tên hư cấu": các khối của cửa sổ Hồ Sơ Kỳ Án `#tc-progress`, `#tc-outline-review`, `#tc-review` (bảng tên, cảnh báo, bảng ghim, sửa lời từng cảnh), `#btn-tc-create-vi`. Hai thẻ chỉ hiện **khi đang theo dõi một vụ chưa tạo dự án** (`TrueCrimeState.caseId`), đúng như cửa sổ hiện nay: bấm `#btn-tc-create-vi` xong, `tcDetach()` xoá vụ đang theo dõi thì hai thẻ ẩn, lời kể sửa tiếp ở thẻ "Lời kể theo cảnh" (không có hai chỗ sửa lời).
- Thẻ "Lời kể theo cảnh": danh sách lời kể từng cảnh, sửa bằng `updateSceneText()`; giọng từng cảnh (nghe `playSceneVoice()`, tua `seekSceneAudio()`, thu lại `regenerateSceneVoice()`) nằm trên từng dòng; thêm, nhân bản, đổi chỗ, xoá cảnh (`#btn-add-scene`, `moveScene()`, `duplicateScene()`, `deleteScene()`) hiện khi di chuột lên cảnh.
- Thẻ "Giọng đọc": `#select-voice`, `#btn-preview-voice-sample`, thu giọng còn thiếu, `#btn-regen-all-voices`. Khi đang theo dõi vụ chưa tạo dự án, thẻ này hiện `#tc-voice-vi` và `#tc-voice-en` (hai ô chỉ được đọc lúc bấm `#btn-tc-create-vi`, `true_crime.js` dòng ~1466) thay cho `#select-voice`.

**Hình mẫu** (trang mới)
- Phong cách: một dòng ghi phong cách của dự án; nút "Đổi" mở ô nổi chứa `#select-project-style` kèm cảnh báo (mục 4.4).
- Nhân vật: nội dung cửa sổ `#modal-character-sheets` đặt thẳng vào trang (không còn nút mở cửa sổ).
- Bối cảnh: nội dung cửa sổ `#modal-location-sheets` đặt thẳng vào trang.
- Nguồn tạo ảnh của dự án `#select-image-provider` (mục 4.5).

**Cảnh** (phần hình của Bước 2 `#step-view-2`)
- Thanh tỉ lệ video Muse và các nút `#btn-climax-video-pick`, `#btn-climax-video-run`.
- `#btn-auto-gen-all` (đổi nhãn "Tạo ảnh còn thiếu"), `#btn-regen-all-images` cất vào nút phụ.
- Danh sách thẻ cảnh `#scene-list-container` (`renderSceneList()`), thẻ hiện ảnh/video, nhãn trạng thái và các nút hình (lời kể chỉ đọc, giọng từng cảnh đã sang trang Kịch bản); các nút ít dùng (prompt, chuyển động, tải ảnh riêng, chọn từ thư viện) cất vào thanh công cụ khi di chuột hoặc phần mở rộng của thẻ.
- Xem thử có tiếng (Live Studio Player) cất vào ngăn kéo bên phải.

**Dựng và xuất bản** (Bước 3 `#step-view-3` + Bước 4 `#step-view-4` + phần dựng của Bước 2)
- Nút chính `#btn-produce-from-board`; "Tuỳ chỉnh dựng" (ngăn kéo): `#select-bgm`, `#bgm-upload-input`, `#toggle-audio-ducking`, `#toggle-hardsub`, `#select-transition`, `#select-subtitle-style`.
- Tiến độ dựng: thanh 5 giai đoạn và nhật ký của Bước 3 thu gọn ngay dưới nút dựng (nhật ký cất trong phần mở rộng).
- Thành phẩm: `#cinema-video-player`, các nút tải, `#btn-cinema-open-folder`.
- Đăng YouTube: gói SEO và thumbnail của Bước 4 (giữ nguyên `backend/static/youtube_seo.js`).
- Bản tiếng Anh: `#btn-create-en-version` (cùng điều kiện hiện như cũ, `refreshLanguageVersionButton()`).

**Dự án**: nội dung cửa sổ `#modal-project-manager` thành một trang. Ô chọn dự án đầu thanh bên mở trang này.

**Thư viện Muse**: phần gallery của cửa sổ `#modal-muse-cloud` (gồm `#btn-clear-all-gallery`).

**Tài khoản và kết nối**: phần tài khoản của cửa sổ `#modal-muse-cloud` (`#muse-fleet-pool-grid`, `#btn-muse-refresh-accounts`, hai nút chép lệnh) và khối trạng thái kết nối mới (mục 5.3).

### 4.2 Gỡ khỏi giao diện (chủ dự án duyệt cùng bản xem thử)

| Gỡ | Vì sao | Còn lại ở đâu |
|---|---|---|
| Cửa sổ 9-Grid Spec `#modal-master-storyboard`, nút `#btn-open-master-storyboard-modal` | Lối tạo dự án thứ ba, ngoài luồng đã chốt | API `POST /api/storyboard/deconstruct`, `POST /api/storyboard/import` giữ nguyên |
| Cửa sổ Kịch bản AI `#modal-script-importer`, nút `#btn-open-script-modal`, nút "Nhập kịch bản truyện" của danh sách cảnh rỗng (gọi `openScriptModal()`, dòng ~1264 `app.js`; đổi thành nút về trang Ý tưởng) | Chủ dự án chốt không bê nguyên văn (câu 16 mục 1.2 CLAUDE.md) | API `POST /api/projects/{project_id}/split-script` giữ nguyên |
| Cửa sổ cắt truyện tranh `#modal-comic-slicer`, nút `#btn-open-comic-modal` | Trùng với thể loại Truyện tranh ở trang Ý tưởng | Trang Ý tưởng, API giữ nguyên |
| Nhân vật chính kiểu cũ: `#step1-char-preset-select`, `#step1-char-name`, `#step1-char-anchor`, ảnh tham chiếu (`#step1-char-ref-*`), thẻ `#character-consistency-card`, cửa sổ `#modal-character-editor` | Có bảng nhân vật thì app đã tự bỏ `character_anchor` (`scene_locks.py`) | Bảng nhân vật ở trang Hình mẫu |
| Ô phong cách của Hồ Sơ Kỳ Án `#tc-visual-style` trên giao diện; ô `#split-style-select`, `#edit-char-style`, `#master-sb-style-dna` đi cùng cửa sổ bị gỡ | Phong cách chọn một chỗ | `#step1-style-select` ở trang Ý tưởng. Giữ `#tc-visual-style` dạng ô ẩn còn đủ lựa chọn, vì `tcStartFromStep1()`, `tcAnalyze()` và lúc tạo dự án vụ án đọc và ghi vào nó (`.options`) |
| Ô dán của Hồ Sơ Kỳ Án `#tc-case-text`, ô số phút `#tc-duration-select` và nút mẫu `#btn-tc-sample-1..3` trên giao diện | Trùng ô dán và ô số phút của trang Ý tưởng | Giữ `#tc-case-text` và `#tc-duration-select` dạng ẩn vì `tcStartFromStep1()` chép bài, số phút vào đó rồi gửi (đường đang chạy); nút mẫu gỡ hẳn |
| `#btn-step1-open-true-crime`, `#btn-open-true-crime-modal` | Không còn cửa sổ để mở | Trang Kịch bản |
| `#btn-produce-long-video` trên thanh trên cùng | Trùng `#btn-produce-from-board` | Trang Dựng và xuất bản |
| `#btn-save-project` | App đã tự lưu sau 1,5 giây (`ProjectSync`) | Chữ "Đã lưu" ở thanh trên; `Ctrl+S` vẫn chạy |
| Màn Bước 3 riêng, `#btn-producer-goto-cinema` | Gộp vào trang Dựng | Thanh tiến độ trong trang Dựng |
| Một trong hai nút tải thumbnail (`#btn-download-thumbnail-direct`, `#btn-cinema-download-thumbnail`) | Trùng | Giữ một nút (người làm chọn, ghi lý do) |
| Bốn nút bước `#step-nav-1..4` | Thay bằng thanh bên | Thanh bên |

Ô "vào khối ẩn" là ô vẫn nằm trong HTML (trong `#ws-hidden-inputs`, có thuộc tính `hidden`), giữ id và lựa chọn, vì code đang đọc ghi nó.

Gỡ khỏi giao diện là xoá phần HTML và phần gắn sự kiện của nó; **không xoá API, không xoá service**. Hàm JS chỉ phục vụ phần đã gỡ thì xoá cùng (để không còn mã chết), trừ khi phần khác còn gọi.

### 4.3 Khuôn thể loại

Một nơi duy nhất khai báo thể loại: file mới `backend/static/genres.js`, mỗi thể loại một mục gồm: mã (`story`, `case`, `comic`), tên hiện, câu mô tả, có viết lại không (câu hiện cho người dùng), trang Kịch bản có thẻ Dàn ý/Tên hư cấu không, có bỏ qua trang Hình mẫu không (truyện tranh: hình đã có sẵn), hành động khi bấm nút chính (gọi đúng hàm đang có: truyện chữ `handleStep1ProcessScript()`, vụ án qua `tcStartFromStep1()`, truyện tranh `handleStep1ProcessComic()`). Thể loại "Sau này" khai báo với cờ chưa bật.

Thể loại của **dự án đang mở** suy ra từ dữ liệu có sẵn, không thêm trường mới: có `metadata.case_id` là vụ án; dự án mà cảnh mang `metadata.source == "comic_slicer"` (do `POST /api/projects/{project_id}/comic/import-scenes` gắn) là truyện tranh; còn lại là truyện chữ.

### 4.4 Vì sao phong cách chọn ở trang Ý tưởng

Bản xem thử ngày 15/11/2026 đặt ô phong cách ở trang Hình mẫu, với lý do "phong cách không ảnh hưởng tới chữ". Đọc lại code thì lý do đó **sai**: lúc viết kịch bản, AI viết luôn mô tả ảnh (`image_prompt`) của từng cảnh theo phong cách đã chọn (truyện chữ: `story_review.write_prompt()` ghi "phong cách {style_preset}"; vụ án: `case_adaptation_prompts.prompts_prompt()` đưa cả đoạn mô tả phong cách `_style_detail()`). Chọn phong cách sau khi đã có kịch bản thì mô tả ảnh vẫn theo phong cách cũ.

Vì vậy: chọn phong cách ở trang Ý tưởng, trước khi tạo kịch bản. Trang Hình mẫu chỉ hiện phong cách của dự án. Ô `#select-project-style` (đổi phong cách của dự án đã có, app chỉ đổi phần đuôi phong cách gắn vào mô tả ảnh lúc vẽ) cất trong ô nổi, kèm câu cảnh báo: "Mô tả ảnh của các cảnh đã viết theo phong cách cũ; đổi ở đây chỉ đổi phần phong cách gắn thêm khi vẽ, và các bảng nhân vật, ảnh chuẩn bối cảnh đã duyệt sẽ phải vẽ lại." Viết lại mô tả ảnh theo phong cách mới là tính năng chưa có, không làm lần này.

### 4.5 Nguồn tạo ảnh ở trang Hình mẫu

Nguồn tạo ảnh (Muse, Gemini qua 9router, …) hiện có ở 3 ô: `#step1-engine-select` (lúc tạo dự án truyện), `#tc-vision-engine` (lúc tạo dự án vụ án) và `#select-image-provider` (cài đặt **của từng dự án**, `app.js` dòng ~1933 lưu vào dự án đang mở). Bản xem thử đặt ô này ở trang Tài khoản, nhưng trang đó là cài đặt chung cho cả app, đặt ở đó sẽ đổi nghĩa ô (người dùng tưởng đổi cho mọi dự án).

Quyết định của người làm (agent, 15/11/2026, chủ dự án xem lại khi đọc kế hoạch): `#select-image-provider` nằm ở trang Hình mẫu, cạnh dòng phong cách, vì ảnh cảnh chỉ được tạo sau bước Hình mẫu. Hai ô lúc tạo dự án vào khối ẩn, giữ mặc định Muse (miễn phí). Trang Tài khoản chỉ ghi "Nguồn ảnh mặc định khi tạo dự án: Muse" và nhắc Gemini là dịch vụ tính tiền.

## 5. Khung giao diện và quy tắc kỹ thuật

### 5.1 Khung
- `backend/static/index.html` dựng lại: thanh bên, thanh trên, vùng giữa, ngăn kéo phải. Bốn khối `#step-view-1..4` và các cửa sổ được dời vào đúng trang theo mục 4.1.
- File mới `backend/static/workspace.css`: biến màu, chữ, khoảng cách và các lớp thành phần (`ws-btn`, `ws-btn-primary`, `ws-card`, `ws-nav`, …). CSS viết tay, không cần build Tailwind. Nạp sau `tailwind.css` để thắng các lớp cũ khi trùng.
- File mới `backend/static/workspace.js`: điều hướng trang (`showPage(name)`), thu/mở thanh bên, mở/đóng ngăn kéo, đường dẫn trang ở thanh trên, nhớ trang đang mở theo dự án (localStorage, có try/catch). Khi vào trang Hình mẫu thì bắt đầu nạp và hỏi lại hai danh sách nhân vật, bối cảnh; rời trang thì dừng hỏi (hiện phần nạp và vòng hỏi nằm trong hàm `open()` riêng của `character_sheets.js`, `location_sheets.js`, còn `close()` ẩn cửa sổ và được gọi khi đổi dự án và khi bấm `Esc`: kế hoạch tách thành hàm bắt đầu/dừng, không ẩn gì); vào trang Dựng thì gọi `loadCinemaYouTubePackage()` như `switchStep(4)` đang làm.
- `switchStep(n)` giữ tên, chuyển thành gọi `showPage()` tương ứng (1→Ý tưởng, 2→Cảnh, 3 và 4→Dựng) để mọi chỗ đang gọi `switchStep()` vẫn đúng.
- Các hàm mở cửa sổ đang có (`openTrueCrimeModal()`, `openMuseModal()`, `openProjectModal()`, mở bảng nhân vật/bối cảnh) giữ tên, chuyển thành chuyển trang. `closeAllModals()` và phím `Esc` chỉ còn đóng ngăn kéo và các hộp nhỏ còn lại.
- Chữ: `Be Vietnam Pro` từ Google Fonts (thay `Inter`, cùng cách nạp như hiện tại).
- Biểu tượng thanh bên và thanh trên: bộ SVG nét viết thẳng trong `index.html` (như bản xem thử). Biểu tượng FontAwesome bên trong các khối dời sang giữ nguyên ở lần này.
- Ô tìm kiếm ở thanh trên: lần này chỉ tìm cảnh theo số và lời kể, nhảy tới cảnh đó ở trang Cảnh (dữ liệu `AppState.currentProject.scenes`, không gọi máy chủ). Tìm dự án, lệnh: để sau.

### 5.2 Hồ Sơ Kỳ Án vào luồng chung
- `true_crime.js` giữ nguyên logic. `TrueCrimeState.modalOpen` đổi nghĩa thành "trang Kịch bản đang mở với dự án hoặc vụ đang theo dõi"; việc hỏi tiến độ (`tcStartPolling()`/`tcStopPolling()`) bật tắt theo trang như trước đây theo cửa sổ.
- App luôn có một dự án đang mở (dự án mở gần nhất hoặc `DEFAULT_PROJECT`), kể cả lúc một vụ mới đang phân tích. Quy tắc khi đang theo dõi một vụ chưa tạo dự án: trang Kịch bản chỉ hiện hai thẻ Dàn ý, Tên hư cấu và thẻ Giọng đọc (của vụ), kèm dòng "Đang làm vụ mới. Dự án đang mở là «tên»: xem ở Hình mẫu, Cảnh, Dựng"; các trang Hình mẫu, Cảnh, Dựng vẫn là của dự án đang mở, kèm dải mỏng trên cùng "Vụ mới đang phân tích NN%: xem ở Kịch bản". Tạo xong dự án vụ án thì app mở dự án mới (như hiện nay) và dải biến mất.
- Chọn giọng: xem thẻ Giọng đọc ở mục 4.1 (không lúc nào hai ô giọng cùng hiện).
- `#tc-vision-engine` vào khối ẩn (mục 4.5).

### 5.3 Trạng thái kết nối (phần mới duy nhất ở máy chủ)
- Router mới `backend/routers/connections.py`, một đường `GET /api/connections/status` trả về: cổng AI viết lời (`NINEROUTER_BASE_URL`), đã có khoá chưa (chỉ `true/false`, **không bao giờ trả khoá**), các model đang đặt, có `YOUTUBE_API_KEY` chưa (true/false), nguồn tạo ảnh mặc định. Đọc qua `config.py` (đường cấm 6).
- Nút "Gọi thử" gọi `POST /api/connections/llm-ping`: một lần gọi LLM rất ngắn qua `services/case_adaptation_llm.py` (đường cấm 5), trả thời gian và lỗi nếu có. Tốn 1 lượt LLM mỗi lần bấm, ghi rõ trên nút.
- Trạng thái Muse lấy từ `GET /api/muse-bridge/accounts` và `GET /api/muse-bridge/status` đang có. Edge-TTS, VieNeu: người làm chọn cách báo không tốn gọi mạng (ví dụ VieNeu xem cổng 5005 có mở không); không gọi Edge-TTS thật chỉ để báo trạng thái.
- Khoá, mở khoá tài khoản Muse trên giao diện: **không làm lần này** (thuộc đợt 6 cùng phần tài khoản). Trang chỉ hiện tài khoản, loại, trạng thái, khoá tới khi nào (`blocked_until`, `block_reason`) nếu dữ liệu có.

### 5.4 Khoá cứng mới
- Test mới `tests/test_ui_ids_preserved.py`: lấy danh sách id của `index.html` bản `master` lúc bắt đầu (lưu thành file `tests/data/ui_ids_truoc_giao_dien_gon.txt`), bắt buộc mọi id đó còn trong `index.html` mới, trừ danh sách gỡ đã duyệt (ghi ngay trong test, mỗi id kèm lý do và trỏ về mục 4.2 tài liệu này). Thêm id mới thì tự do; mất id không có trong danh sách là test đỏ.
- Test mới trong cùng file: mọi id mà `app.js`, `true_crime.js`, các file JS khác gọi bằng `getElementById('…')`/`tcEl('…')`/`el('…')` với chuỗi cố định phải có trong `index.html` hoặc nằm trong danh sách id dựng bằng JS (ghi trong test).
- Hai khoá cứng cũ về phong cách (`tests/test_one_flow.py::test_style_lists_are_the_same_everywhere`, `tests/test_case_project_builder.py::test_cartoon_style_is_offered_and_explained_to_the_prompt_writer`) **giữ nguyên**: ba ô phong cách vẫn có trong HTML với cùng danh sách (một ô ẩn). Test bố cục mới (kế hoạch, Task 1) kiểm `#tc-visual-style` nằm trong vùng ẩn và chỉ `#step1-style-select` hiện ở luồng tạo video.
- `tools/build_release.py`: thêm `workspace.css`, `workspace.js`, `genres.js` vào danh sách file bắt buộc và danh sách file giao diện được quét.
- `FEATURE_MAP.md` sửa cùng nhánh: mọi id, hàm đổi chỗ hay bị gỡ (test `tests/test_feature_map.py` bắt tên không còn trong code).

## 6. Đợt làm

| Đợt | Việc | Xong khi |
|---|---|---|
| 1 | Khung: `workspace.css`, `workspace.js`, thanh bên, thanh trên, vùng giữa; bốn bước cũ hiện trong khung mới (Ý tưởng = Bước 1, Cảnh = Bước 2, Dựng = Bước 3 + 4); test giữ id | App chạy đủ như cũ trong khung mới |
| 2 | Chia 5 trang: tạo trang Kịch bản và Hình mẫu, dời khối từ Bước 2 sang Kịch bản/Hình mẫu/Dựng; cửa sổ nhân vật, bối cảnh, dự án, Muse thành trang | Mỗi khối ở đúng trang mục 4.1 |
| 3 | Hồ Sơ Kỳ Án vào luồng chung; khuôn thể loại `genres.js`, thẻ thể loại ở trang Ý tưởng | Cửa sổ `#modal-true-crime` không còn; vụ án đi trọn từ Ý tưởng tới tạo dự án trong trang |
| 4 | Gỡ chỗ trùng theo mục 4.2; sửa hai test phong cách; dọn class cũ của các khối sang lớp `ws-*` | Không còn tính năng nào ở hai chỗ |
| 5 | Trang Tài khoản và kết nối, router `connections.py` | Trang báo đúng trạng thái trên máy thật |
| 6 | Video Muse nhanh hơn | **Thiết kế riêng, không thuộc kế hoạch này** |

## 7. Kiểm chứng

- Mỗi đợt: `tools/check.py --full` đạt; test giữ id đạt.
- Mỗi đợt: server thử cổng 8010 (`.claude/launch.json`), dự án thử `proj_ea5b04db` và dự án vụ án mẫu `proj_crime_52c3a5e8` (**chỉ mở xem, không bấm nút ghi**): bấm qua mọi trang, mọi nút không tốn tiền ghi trong `FEATURE_MAP.md`; console không lỗi; log server không lỗi; so danh sách `projects/` trước và sau.
- Nút tốn tiền (LLM, Muse, ảnh trả phí) không bấm thật khi kiểm; kiểm bằng cách xem nút có gắn đúng hàm cũ (đọc code) và bằng giả lập trả lời máy chủ trong trình duyệt như lần kiểm 11/11/2026.
- Cuối đợt 4: chạy một lượt trọn luồng truyện chữ trên `proj_ea5b04db` với các bước không tốn tiền (mở từng trang, sửa lời, đổi giọng, xem thử, mở trang Dựng, xem thành phẩm cũ).
- Chụp màn hình từng trang ở 1280x720 và 1920x1080 để chủ dự án xem.

## 8. Phần để người làm tự quyết

- Tên lớp CSS cụ thể, cách chia `workspace.css`.
- Thứ tự dời các khối trong một đợt, miễn mỗi commit app vẫn chạy.
- Hình biểu tượng SVG cụ thể.
- Giữ nút tải thumbnail nào (mục 4.2).
- Cách báo trạng thái Edge-TTS, VieNeu không tốn gọi mạng (mục 5.3).
- Thanh công cụ khi di chuột trên thẻ cảnh chứa những nút nào, miễn mọi nút hiện có trên thẻ vẫn tới được trong tối đa hai lần bấm.
