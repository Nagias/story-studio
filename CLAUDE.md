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
| Ảnh tĩnh có chuyển động nhẹ; cần thì xuất video riêng 5 hoặc 10 giây (câu 5 mục 1.2) | Ảnh: chuyển động nhẹ khi dựng (`build_zoompan_filter()`). Video: Fleet Runner nhận 5 hoặc 10 giây (`clamp_video_duration()`), nhưng nút "Muse Video" luôn gửi 5 giây (`generateSceneWithMuse()`); clip ngắn hơn lời thoại thì giữ khung cuối khi dựng (`render_scene_video()`, từ 27/10/2026). Dự án vụ án: nút riêng làm video cho cảnh cao trào (`#btn-climax-video-run`): bảng nhân vật đủ góc được duyệt (`#btn-character-sheets`), mỗi cảnh một side chat Muse trên tài khoản video vẽ ảnh 9-grid, duyệt grid, rồi giao Muse một việc nhiều bước (Muse tự chia đoạn, tự kiểm, làm lại; tối đa 6 video + 4 ảnh), ảnh cảnh được thay bằng ảnh Muse sửa (giữ bản cũ). Nhân vật nữ phong cách đầu tròn có tóc dày trên đỉnh đầu (`FEMALE_HAIR_RULE_EN`) | Nút "Muse Video" chưa chọn được 10 giây; chưa báo khi lời thoại dài hơn clip |
| Đầu vào là nội dung, quy trình ngầm, bấm là ra video | Luồng A và C trong `FEATURE_MAP.md`; nút Sản xuất video dài (`#btn-produce-long-video`) tự thu giọng, tạo ảnh còn thiếu, dựng và ghép | Đã có khung; độ dài và cách giữ nguyên văn như hai dòng trên |
| Nhiều kênh YouTube; kênh theo loại nội dung, tính sau; tự đăng lên YouTube (câu 6 mục 1.2). Đã có kênh; cần tiêu đề, mô tả, thumbnail tải về được, chuẩn SEO YouTube dựa trên repo/nguồn có sẵn, không thuần AI (câu 9 mục 1.2) | Mỗi dự án độc lập. Gói SEO ở Bước 4 (`backend/static/youtube_seo.js`, `routers/youtube_seo.py`): từ khoá từ gợi ý tìm kiếm YouTube, YouTube Data API (`YOUTUBE_API_KEY`) hoặc dán tay; AI chỉ viết câu trong khuôn từ khoá đã chọn; luật chính thức YouTube là khoá cứng (`youtube_seo_rules.py`); tải .txt; thumbnail font đủ dấu. Không có phần đăng YouTube | Chưa có khái niệm "kênh" trong code (để sau); không cần làm phần đăng YouTube; nguồn YouTube Analytics (từ khoá người xem thật sự gõ để tìm ra kênh) chưa làm |

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
| 9 | (Góp ý khi duyệt bảng 1.1, dòng kênh YouTube) | Tôi đã có kênh, cứ làm luôn cả mô tả, tiêu đề, thumbnail để tôi tải về đi. Cái này phải xem có repo nào hỗ trợ không để chuẩn SEO Youtube, chứ không được thuần AI suy nghĩ. AI sẽ không chính xác. |
| 10 | (29/10/2026) Giọng nhịp review đọc nhanh hơn nên video ngắn hơn số phút đã chọn: có cần bù số chữ không? | Trúc Ly ổn rồi đó. còn thời gian ngắn hơn cũng được, không vấn đề gì cả. Mục đích anh yêu cầu thời gian lúc đầu là muốn em viết được nội dung đầy đủ chứ không được rút gọn, vì nội dung anh gửi rất dài. Cái cần tuân thủ là các lệnh python để AI không tìm đường tắt, không rút gọn và thêm các quy luật để viết review hay hơn, cảm xúc hơn, có thể tìm kiếm các mã nguồn mở liên quan. |
| 11 | (29/10/2026) Vụ án kể ở ngôi thứ ba kiểu phóng sự, hay ngôi "tôi" như hai video mẫu? | Tôi duyệt ngôi kể thứ 3 kiểu phóng sự. |
| 12 | (29/10/2026) Nhân vật đầu tròn có được biểu cảm như video mẫu (lông mày, nước mắt, nửa mặt tô xám khi sợ) không, khi quy tắc hiện tại cấm lông mày? | Có nới quy tắc ra. |
| 13 | (29/10/2026) Bộ việc mẫu chạm trần 50/50 nên chỉ bắt được tụt điểm: có thêm việc khó hơn không? | Mục 8 thì có đo được khi agent giỏi lên, cứ thêm việc khó và đo liên tục để tối ưu. |
| 14 | (30/10/2026, ý 1 khi cô đọng bảng 1.1) Có cần nút chọn 40–50 phút cho truyện không? | Các nút lựa chọn 40 - 50 phút theo dạng fix số phút cố định cho truyện anh thấy không cần thiết. Mục đích của anh khi nói số phút này là để LLM không bị tìm đường tắt để làm cho xong công việc, không bị nghĩ vội. Mà phải tách nhánh công việc, làm các đầu việc từ từ để bổ 1 truyện sao cho đủ ý, đủ thông tin, không bị cắt gọt nhiều. Cái này em phải làm hard guardrail cho anh bằng script chứ không chỉ viết claude.md là xong. |
| 15 | (30/10/2026, ý 2) Truyện làm bản Việt, bản Anh hay cả hai? | Truyện sẽ có 2 option là tiếng anh hoặc tiếng việt để user lựa chọn. Không nhất thiết 1 truyện bắt buộc phải ra cả 2 bản việt và anh. |
| 16 | (30/10/2026, ý 3) Truyện chữ có cần lựa chọn bê nguyên văn không? | Kể như review là đúng rồi, không bê nguyên văn, rất khó để chia vai |
| 17 | (30/10/2026, ý 4) Hình ảnh: ưu tiên gì? | về mặt hình ảnh thì anh đồng ý, cái quan trọng nhất là khóa bối cảnh và khóa nhân vật. còn lại về biểu cảm thì cần linh hoạt hơn |
| 18 | (30/10/2026, ý 5) Video Muse dài bao nhiêu? | Muse Video 5 giây hay 10s hay dài hơn thì phải do đoạn hội thoại đó nữa, không thể cứ cố định 5 - 10 giây trong khi hội thoại chỉ có 3 giây hoặc dài tơi 15 giây được. Vì thế phải xem lại cho anh cách render được video có độ dài ngang với thoại, 1 video không đủ thì 2 video, chỉ cần thay đổi góc máy, cảnh quay dạng chuyển cảnh chẳng hạn. |
| 19 | (02/11/2026, nói thêm ý 5) Thoại ngắn hơn video Muse thì cắt? Thoại dài thì chia video thế nào? | Nếu minimum video muse là 5 giây thì cứ để 5s, dài hơn thoại tý không sao. không cần cắt. còn 15 giây như em nói là đúng ý anh rồi. Tuy nhiên thay vì chỉ thay đổi góc máy khác nhau thì ý anh là rộng hơn, giả sử thoại đó là nói nhiều cảnh, thì các video cũng phải thay đổi cảnh, chứ không chỉ thay đổi mỗi góc máy. ví dụ thoại trong rừng thì không thể chỉ thay đổi góc máy. ý chung của anh là thoại dài thì chia thành nhiều video cho phù hợp với thoại là được. |
| 20 | (30/10/2026, ý 6) SEO YouTube? | SEO Youtube chưa cần. |
| 21 | (30/10/2026, ý 7) Câu 10–13 chỉ ghi trong CLAUDE.md có đủ mạnh không? | Việc ghi vào claude.md ở các câu 10-13 em phải đo lường thêm cho anh khi thực hiện là liệu nó có đủ mạnh để áp dụng không, không thì phải tạo hard guardrail mới được |
| 22 | (02/11/2026) Test đòi đúng 10 tài khoản Muse trong khi máy có 14: sửa cấu hình hay sửa test? | Cái kiểm chứng thứ 2 mà muse phải có 10 tải khoản là sai, anh không login 10 tải khoản đâu nhé. Đừng có fix cái đó, có bao nhiêu dùng bấy nhiêu. Số 10 có lẽ là số lượng mà em tự thêm chứ không phải anh bảo. |

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
  11. Chủ dự án tự đăng YouTube; tiêu đề, mô tả, tags theo từ khoá tìm kiếm thật và luật YouTube, thumbnail, tải .txt — có (22/10/2026).
- Để sau: kênh theo loại nội dung (câu 6 mục 1.2).

## 2. Nguyên tắc

### 2.1 Thiết kế kiểu Dune — [Nguyên văn chủ dự án]

> Nguyên tắc thiết kế kiểu Dune — đường đúng phải cần ÍT quyết định hơn đường tắt; phụ thuộc/mẫu bị cấm phải làm test hoặc CI báo lỗi tự động chứ không chỉ ghi nhắc; mỗi loại dữ liệu chỉ có MỘT nơi được ghi; việc mới thì thêm file/thành phần riêng thay vì sửa chen vào file dùng chung; ngoại lệ phải hẹp, ghi rõ lý do và được duyệt như thay đổi kiến trúc.

### 2.2 Tư duy — [Nguyên văn chủ dự án]

> Nguyên tắc tư duy: mục đích project và các quyết định trong CLAUDE.md giữ NGUYÊN VĂN lời của tôi — bạn được đề xuất và làm dày, nhưng không tự viết lại ý và không tự chốt các quyết định mang tính tư duy (viết ra chính là lúc tư duy, phần đó là của tôi).

### 2.3 Tra bản đồ trước — [Nguyên văn chủ dự án]

> mọi việc làm/tái hiện lỗi/kiểm chứng đều phải tra FEATURE_MAP.md trước, cấm đoán đường.

### 2.4 Khoá cứng và khoá mềm — [Nguyên văn chủ dự án] (22/10/2026, khi duyệt mục 5, 6, 7)

> 14  điều cấm khi viết code đang là Quy tắc cứng có luôn file script chạy gì đó hay là quy tắc mềm chỉ ghi trên Claude.md. Tôi đề xuất là cứ lỗi nào lặp đi lặp lại ít nhất 3 lần thì đưa thành quy tắc cứng - hard guardrail.

> vẫn câu hỏi giống B là bạn đang để ở hard guardrail hay chỉ đơn thuần là 1 file markdown. Nếu bị vi phạm lỗi từ 3 lần trở lên, nếu đang là 1 file cấm dạng mềm như markdown thì chuyern thành khóa cứng luôn để không bao giờ vi phạm lại lỗi.

> Tương tự với mục B và C. Tôi duyệt cho bạn nhưng cần phân loại rõ ràng giữa khóa cứng và khóa mềm. Trong đó khóa cứng là hard guardrail, tôi không rõ làm bằng gì nhưng là câu lệnh rõ ràng, không phải chỉ 1 file markdown. Còn khóa mềm đơn thuần là file markdown, tđôi lúc AI còn không thèm quét qua nên hay làm sai

(B là mục 5, C là mục 6, D là mục 7 khi agent trình bày trong chat.)

## 3. Lệnh

| Việc | Lệnh |
|---|---|
| Chạy app | `run.bat` (hoặc `.venv\Scripts\python.exe run.py`), mở `http://localhost:8000`. Tự bật Fleet Runner |
| Python | luôn `.venv\Scripts\python.exe` (Python 3.14), không dùng `python` hệ thống; in tiếng Việt thì thêm `-X utf8` |
| Cài thư viện | `.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt` (phiên bản đã ghim); Playwright thêm `.venv\Scripts\python.exe -m playwright install chromium` |
| Kiểm tra nhanh (hook tự chạy mỗi lần commit) | `.venv\Scripts\python.exe tools\check.py`: Ruff so với mốc, cú pháp JS, test kiến trúc, test FEATURE_MAP, test khoá cứng mục 5.1 và 6.1 (khoảng 15 giây) |
| Kiểm tra đầy đủ (trước khi gộp `master`) | `.venv\Scripts\python.exe tools\check.py --full`: thêm cả bộ test mặc định |
| Cài hook git (một lần mỗi bản sao repo, và sau khi `tools/check.py` đổi cách cài hook) | `.venv\Scripts\python.exe tools\check.py --install-hook`: hook pre-commit chặn commit thẳng lên `master`/`main` rồi chạy bản nhanh; hook commit-msg chặn dòng đầu commit sai dạng `<vùng>: <mô tả>`. Không bỏ qua hook bằng `--no-verify` |
| Test một file | `.venv\Scripts\python.exe -m pytest tests\test_xxx.py -q` |
| Bộ test mặc định (offline) | `.venv\Scripts\python.exe -m pytest -q` (`pytest.ini` bỏ qua test cờ `live`; test không gắn cờ mà gọi mạng, 9router, VieNeu hay server 8000 thì bị chặn và báo lỗi; còn dự án rác trong `projects/` thì báo lỗi) |
| Test gọi dịch vụ thật | chỉ khi được yêu cầu: `.venv\Scripts\python.exe -m pytest -m live -q` (Edge-TTS, 9router, VieNeu); riêng `tests/test_case_adaptation_live.py` cần thêm `STORY_STUDIO_LIVE=1` |
| Sửa bớt lỗi Ruff cũ | sửa xong chạy `.venv\Scripts\python.exe tools\check.py --shrink-ruff-baseline` để hạ mốc `tools/ruff_baseline.json`. Không có lệnh nâng mốc |
| Kiểm giao diện | server thử cổng 8010 theo `.claude/launch.json` (tắt hàng việc phân tích và tự bật Fleet Runner), mở bằng trình duyệt trong app, dùng dự án thử `?project_id=proj_ea5b04db`. Không khởi động lại server 8000 đang dùng chung |
| Build CSS | thêm class Tailwind mới: `cd tools\tailwind`, `npm install --cache .npm-cache`, `npm run build` → `backend/static/tailwind.css` |
| Đóng gói bán | `.venv\Scripts\python.exe tools\build_release.py` → `dist/` (lấy theo danh sách cho phép, tự chặn bí mật) |
| Đo agent/skill bằng bộ việc mẫu | `.venv\Scripts\python.exe tools\bo_viec_mau.py chuan-bi --lan <tên> --mo-ta "<agent/skill đang đo>"`, giao đề cho agent, rồi `cham --lan <tên>` và `so-sanh <lần trước> <lần sau>`; đủ các bước trong `docs/bo-viec-mau/README.md` |
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

## 5. Đường cấm — [Đề xuất của agent — chủ dự án duyệt 22/10/2026, kèm phân loại khoá cứng/mềm theo mục 2.4]

Lập từ đợt rà soát 21/10/2026. Cột cuối liệt kê chỗ còn vi phạm để agent **không chép theo**; sửa chúng là việc riêng.

Dòng nào là khoá cứng, dòng nào là khoá mềm: bảng 5.1 ngay dưới bảng này.

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
| 14 | Đường dẫn tuyệt đối của máy này, hay trỏ sang dự án khác | đường dẫn từ `config.py` | hỏng trên máy khách; `tools/build_release.py` chặn | — (font thumbnail lấy qua `config.WINDOWS_FONTS_DIR` từ 22/10/2026); vài chuỗi hợp lệ có ghi lý do trong `tests/test_architecture.py` |
| 15 | Viết lời kể (truyện chữ, vụ án) bằng LLM mà không qua bước kiểm đủ ý, hoặc dặn LLM "tóm tắt" | `services/coverage_guard.py` (LLM trích nguyên văn bằng chứng từng ý, code đối chiếu, viết lại khi thiếu) như `story_review.review_part`, `case_adaptation_steps._run_write_vi` | LLM làm tắt, bỏ ý, kể lặp hay kể trái điều đã kể (CLAUDE.md mục 1.2 câu 10, 14, 21) | — |

Code mới nên theo mẫu của mảng true-crime (mục 4), không theo mảng cũ.

### 5.1 Khoá cứng hay khoá mềm (theo mục 2.4)

- **Khoá cứng**: có lệnh chạy tự động mỗi lần commit (`tools/check.py`, hook git), vi phạm là bị chặn, không lưu được. Chỗ vi phạm có từ trước được ghi thành ngoại lệ đếm đúng số lần: không cho thêm chỗ mới, chỉ cho giảm.
- **Khoá mềm**: chỉ ghi trong file này, dựa vào agent đọc và người duyệt.
- Quy tắc của mục 2.4: dòng nào ghi từ 3 lần vi phạm trở lên thì không được để "mềm". Máy kiểm chính bảng này: `tests/test_guardrail_policy.py` (đọc cột "Khoá" và "Số lần vi phạm"; dòng "cứng" phải trỏ tới lệnh kiểm có thật). Gặp thêm vi phạm thì tăng số ở đây.

| # | Khoá | Máy kiểm | Số lần vi phạm đã ghi nhận | Bằng chứng; phần còn mềm |
|---|---|---|---|---|
| 1 | cứng | `tests/test_architecture.py::test_only_project_service_writes_project_json` | 13 | 13 chỗ ghi project.json ngoài `project_service`, gom về một nơi (commit `c116f07`) |
| 2 | cứng | `tests/test_architecture.py::test_except_does_not_silently_return_empty`, `tools/ruff_baseline.json` (luật S110) | 49 | 1 sự cố (dự án bị ghi đè thành rỗng) + 31 chỗ `except: pass` + 17 chỗ `except` trả rỗng không ghi log (còn 16, chưa rà từng chỗ, có chỗ hợp lệ) |
| 3 | cứng một phần | `tests/test_architecture.py::test_no_sample_media_links`, `tests/test_architecture.py::test_no_functions_that_only_pass` | 4 | `get_audio_duration()` đoán 3 giây; nhập truyện tranh gán ảnh không có; màn Render giả kèm video mẫu (commit `34421c9`); chuỗi tạo ảnh báo xong khi lỗi (test `tests/test_no_fake_success_and_motion_render.py`). Còn mềm: các kiểu "thành công giả" khác máy không nhận ra được |
| 4 | mềm | — | 1 | Muse lỗi tự rơi sang 9router (có ghi lý do, test `tests/test_no_fake_success_and_motion_render.py`) |
| 5 | cứng | `tests/test_architecture.py::test_no_new_llm_clients` | 3 | 3 client cũ trong `script_splitter.py` (2) và `storyboard_engine.py` (1) |
| 6 | cứng | `tests/test_architecture.py::test_env_read_only_in_config`, `tests/test_architecture.py::test_every_env_var_is_documented_in_env_example` | 1 | `DEFAULT_VOICE` trong `.env` không có tác dụng |
| 7 | cứng | `tests/test_architecture.py::test_no_string_prefix_path_checks` | 1 | `complete_task()` khớp nhầm `proj_a` với `proj_ab` |
| 8 | cứng một phần | `tools/ruff_baseline.json` (luật ASYNC220, ASYNC221, ASYNC230) | 22 | 20 chỗ `open()`/`subprocess` trong hàm async + 2 việc nặng OpenCV, PIL (đã chuyển luồng phụ). Còn mềm: gọi ffmpeg, OpenCV qua thư viện khác |
| 9 | cứng | `tests/test_architecture.py::test_toasts_escape_untrusted_text`, `tests/test_architecture.py::test_html_templates_escape_interpolations` | 30 | 21 thông báo + 9 chỗ ở thư viện ảnh Muse chưa lọc (commit `d33d9df`); 148 chỗ `${...}` cũ trong khuôn HTML ghi thành ngoại lệ (chưa rà từng chỗ); file JS mới tự bị kiểm, ngoại lệ 0 |
| 10 | cứng | `tests/test_architecture.py::test_click_handlers_bound_once` | 1 | nút tải SEO chạy hai lần |
| 11 | cứng | `tests/conftest.py`, `tests/test_test_isolation.py::test_no_loaded_module_points_at_real_projects_dir` | 3 | test để lại dự án rác và thư mục cắt truyện tranh nhiều lần trước 22/10/2026 |
| 12 | cứng | `tests/test_architecture.py::test_no_new_permanent_deletes` | 3 | `delete_project()`, `delete_gallery_item()`, `clear_all_gallery()` vẫn xoá vĩnh viễn (ghi ngoại lệ; sửa là việc riêng) |
| 13 | cứng | `tests/test_architecture.py::test_services_do_not_import_routers` | 1 | `image_service.py` import `routers.muse_bridge` |
| 14 | cứng | `tests/test_architecture.py::test_no_machine_specific_paths` | 1 | font thumbnail `C:\Windows\Fonts` (đã sửa 22/10/2026) |
| 15 | cứng | `tests/test_architecture.py::test_narration_writers_check_coverage`, `tests/test_architecture.py::test_one_click_story_goes_through_story_review`, `tests/test_architecture.py::test_story_prompts_never_ask_to_summarize`, `tests/test_architecture.py::test_case_assemble_requires_verified_parts` | 2 | vụ Trạm Dung kể việc phát hiện thi thể hai lần như hai lần khác nhau (29/10/2026); truyện chữ dặn LLM "review và tóm tắt", AI lỗi thì chép nguyên văn truyện. Chủ dự án yêu cầu khoá bằng script (mục 1.2 câu 14). Còn mềm: chất lượng câu chữ (hay, cuốn) máy không chấm được |

## 6. Quy tắc làm việc của agent

**[Nguyên văn chủ dự án]**

> làm trên branch, không push thẳng main, làm xong phải tự kiểm chứng bằng bằng chứng

**Làm dày — [Đề xuất của agent — chủ dự án duyệt 22/10/2026, kèm phân loại khoá cứng/mềm theo mục 2.4]**
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

**[Nguyên văn chủ dự án]** (23/10/2026, khi giao bộ việc mẫu `docs/bo-viec-mau/README.md`)

> Từ nay, mỗi lần sửa skill hoặc agent, phải chạy lại bộ việc mẫu này và báo cáo điểm trước/sau.

**Skill và agent của dự án** (phương án 3 agent, chủ dự án duyệt 23/10/2026; dựng từ bộ skill mẫu ghép với expert agency-agents). Agent tự nạp skill hay tự gọi agent khi việc khớp dòng `description` — đó là khoá mềm.
- Người làm (phiên chính) dùng 9 skill trong `.claude/skills/`: giao-viec, kiem-chung, cham-cheo, ban-giao, duy-tri-feature-map, tao-feature-map, lam-vuon, loop-toi-chuan, sua-thanh-luat.
- Giám khảo `.claude/agents/giam-khao.md` (model Sonnet, chỉ đọc và chạy lệnh kiểm): gọi trước khi báo "xong" một thay đổi có đụng code, tối đa 3 vòng.
- Rà soát `.claude/agents/ra-soat.md` (chỉ đọc): gọi khi chủ dự án yêu cầu rà soát, hoặc một loại lỗi lặp từ 3 lần.
- Sửa các file này là "sửa skill hoặc agent": chạy lại bộ việc mẫu (`docs/bo-viec-mau/README.md`).

### 6.1 Khoá cứng hay khoá mềm (theo mục 2.4)

Cùng cách đọc và cùng máy kiểm với bảng 5.1. Hook git chỉ có tác dụng khi đã cài: `.venv\Scripts\python.exe tools\check.py --install-hook` (test `tests/test_git_guards.py` báo nếu chưa cài hoặc bản cũ).

| # | Khoá | Máy kiểm | Số lần vi phạm đã ghi nhận | Quy tắc; bằng chứng; phần còn mềm |
|---|---|---|---|---|
| 1 | cứng | `tools/check.py::hook_script` (hook pre-commit), `tests/test_git_guards.py::test_pre_commit_hook_blocks_commit_on_master` | 25 | Không commit thẳng lên `master`: 25 commit thẳng trong lịch sử, 3 sau khi có quy tắc (`b4fd74e`, `6d0666e`, và `603dba6` là commit rỗng lọt khi agent thử khoá bản đầu, vì master còn `tools/check.py` cũ; nay phần chặn viết thẳng trong hook). Gộp nhánh vào `master` vẫn được |
| 2 | mềm | — | 0 | Chỉ gộp vào `master` khi chủ dự án đồng ý: máy không biết chủ dự án đã đồng ý chưa |
| 3 | mềm | — | 0 | Không push khi chưa được bảo (repo chưa có remote) |
| 4 | mềm | — | 0 | Trước khi sửa: tra `FEATURE_MAP.md`, nói trước file sẽ sửa, việc dài ghi checklist `TASKS.md` |
| 5 | cứng một phần | `tools/check.py::check_pytest` (hook pre-commit chạy bản nhanh) | 1 | Có bằng chứng mới báo xong; lần ghi nhận: báo số ước tính thay số đo thật (21/10/2026). Còn mềm: chạy `--full` trước khi gộp, bấm thật giao diện, nghe/xem file thật, báo "chưa kiểm chứng" |
| 6 | cứng một phần | `tests/conftest.py` | 3 | Không để lại dự án rác: phần test là cứng. Còn mềm: chạy thử bằng server thử hay script thì tự so `projects/` trước và sau |
| 7 | mềm | — | 0 | Không đụng 3 mục MẪU; dọn thì vào Thùng rác và phải hỏi trước |
| 8 | cứng một phần | `.gitignore`, `tools/build_release.py` | 1 | Bí mật: `git add` thường không lấy được `.env`, `backend/chrome_profiles/`, `backend/config/muse_fleet_accounts.json`; gói bán tự chặn chuỗi giống key (gói zip cũ từng lộ key, trước khi có git). Còn mềm: không in `.env` ra chat, không dùng `git add -f` |
| 9 | cứng một phần | `tests/conftest.py`, `.claude/launch.json` | 0 | Quota: test không gọi được dịch vụ thật nếu không gắn cờ `live`; server thử tắt sẵn hàng việc phân tích. Còn mềm: ghi số lần gọi, không chạy lặp vô ích |
| 10 | cứng | `tools/check.py::commit_message_problem` (hook commit-msg) | 4 | Dòng đầu commit dạng `<vùng>: <mô tả>`: 4 commit sai (`ffa1c3b`, `afaadab`, `a3de4c7`, `c116f07`). Còn mềm: viết tiếng Việt, mỗi thay đổi một commit |
| 11 | cứng một phần | `tests/test_working_rules.py::test_no_new_scripts_in_project_root` | 3 | Không thêm script ở gốc dự án: đã phải xoá 3 script (run_studio.py, run_studio.bat, run_all_tests.py; xem `git log --diff-filter=D`). Còn mềm: không sửa file ngoài thư mục dự án khi chưa hỏi |
| 12 | mềm | — | 0 | Thư viện tuỳ chọn: chỉ là ghi chú, không phải điều cấm |
| 13 | mềm | — | 0 | Sửa skill hoặc agent thì chạy lại bộ việc mẫu và báo điểm trước/sau (`docs/bo-viec-mau/README.md`): máy chưa biết lúc nào skill hay agent của dự án bị sửa |

## 7. Bảng định tuyến: loại việc → quy trình

Cột "Quy trình" để trống, chủ dự án điền ở giai đoạn sau. Cột "Nhận biết" là **[Đề xuất của agent — chủ dự án duyệt 22/10/2026, kèm phân loại khoá cứng/mềm theo mục 2.4]**.

Khoá: cả mục 7 là **khoá mềm**. Xếp một việc vào loại nào là phán đoán, máy không kiểm được; chưa ghi nhận lần xếp sai nào. Khi cột "Quy trình" có bước cụ thể, bước nào máy kiểm được (ví dụ "chạy `tools/check.py --full`") thì làm thành khoá cứng như bảng 6.1.

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
