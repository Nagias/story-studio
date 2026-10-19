# Thiết kế: chuyển thể vụ án thật thành truyện bằng LLM, song ngữ Việt/Anh

- Ngày: 19/10/2026
- Trạng thái: bản nháp, chờ người dùng duyệt
- Thay cho: luồng `backend/services/case_fictionalizer.py` + `backend/routers/true_crime.py` hiện tại

## 1. Mục đích và lý do

Story Studio làm video YouTube kể chuyện cho thị trường Việt Nam và Mỹ. Một loại đầu vào là bài viết về một vụ án có thật, thường bằng tiếng Việt, dài tới khoảng 60 KB chữ (ví dụ: vụ bộ xương ở núi Nhũ Cô, Đài Loan, file mẫu ở `_archive_2026-10-19/case_input_text.txt`).

Mục tiêu là làm ra thứ giống **một vụ án có thật được chuyển thể thành truyện hoặc phim**:
- giữ nguyên diễn biến, cách gây án, quá trình điều tra và bối cảnh chung (vùng núi, nông thôn, thành thị…);
- chỉ thay tên người và địa danh riêng bằng tên hư cấu, cùng phong cách văn hoá của vụ án gốc.

Một vụ án cho ra một câu chuyện duy nhất, dùng cho nhiều thị trường. Các bản chỉ khác nhau ở lời kể (transcript) và giọng đọc. Bản tiếng Anh bắt buộc có lồng tiếng.

**Vì sao phải làm lại.** Audit ngày 19/10/2026 cho thấy luồng hiện tại gần như chạy theo khuôn:
- ẩn danh bằng regex, chỉ bắt được họ Việt;
- "ma trận 70/30" và "sổ phục bút" là dữ liệu cố định (dao gấp, bật lửa, hợp đồng bảo hiểm) dùng cho mọi vụ;
- lần gọi LLM có timeout 2,5 giây và chỉ đọc 1.200 ký tự đầu, nên gần như luôn rơi về kịch bản offline;
- có một ca đặc biệt Nhũ Cô với 72 cảnh viết sẵn, kích hoạt bởi các từ như "máy bay" hay "nha khoa";
- không có bản tiếng Anh.

Nay 9router đã chạy được với `ag/gemini-3.8-flash-high`: một request nhỏ trả lời trong khoảng 5 giây, ngữ cảnh khoảng 1 triệu token, output tối đa 65.536 token. Cả vụ án dài nhất vẫn gửi được trong một lần gọi.

## 2. Mục tiêu

- **G1.** Dán một vụ án vào, LLM đọc toàn bộ và tạo ra một **kế hoạch chuyển thể**, gồm: bảng tên thật → tên hư cấu (dạng Việt và dạng Anh), dàn ý, danh sách cảnh có lời kể tiếng Việt và tiếng Anh, prompt ảnh/video tiếng Anh, danh sách bằng chứng cho bảng ghim.
- **G2.** Không lọt tên thật hay địa danh thật vào bất kỳ đầu ra nào: tên dự án, lời kể cả hai thứ tiếng, prompt, nhãn bảng ghim.
- **G3.** Từ kế hoạch, tạo dự án Story Studio bản Việt. Khi bản Việt đã có hình, tạo bản Anh dùng lại toàn bộ ảnh và video, chỉ thay lời kể, giọng, phụ đề, và bảng ghim theo ngôn ngữ.
- **G4.** Hỏng ở đâu thì báo rõ ở đó, không lặng lẽ thay bằng khuôn mẫu.
- **G5.** Mọi việc AI đều đi qua 9router.

## 3. Không làm trong đợt này

- Đổi engine giọng tiếng Anh. Tạm thời giữ Edge-TTS en-US; engine sẽ quyết định riêng (xem mục 10).
- Luồng truyện chữ, truyện tranh, storyboard.
- Sửa Muse fleet runner.
- SEO pack và thumbnail tiếng Anh (hiện là chữ tiếng Việt cố định trong code). Đây là việc tiếp theo.
- Ngôn ngữ thứ ba trở đi. Thiết kế không chặn việc thêm sau, nhưng đợt này chỉ làm `vi` và `en`.
- Tự đồng bộ bản Anh khi bản Việt bị sửa sau khi đã tạo bản Anh.

## 4. Những điều được coi là thất bại, dù chạy được

- Lọt tên thật của người hay địa danh riêng ở bất cứ đâu.
- Bịa thêm tình tiết làm sai diễn biến thật: nghi phạm giả, động cơ giả, bằng chứng giả. Công thức "70% thật + 30% đánh lạc hướng" bị bỏ hẳn.
- Lặng lẽ rơi về kịch bản mẫu hay dữ liệu khuôn.
- Ảnh hoặc video máu me rõ ràng, có thể vi phạm chính sách của YouTube hoặc Muse.
- Bản Anh là bản dịch cứng từng chữ.

## 5. Ràng buộc

- **LLM:** 9router, API kiểu OpenAI, `POST {NINEROUTER_BASE_URL}/chat/completions`, model lấy từ `NINEROUTER_LLM_MODEL` (hiện là `ag/gemini-3.8-flash-high`).
  - **Luôn gửi `"stream": false`.** Thiếu cờ này, 9router vẫn trả 200 nhưng body không phải JSON.
  - Lỗi "No active credentials for provider" (HTTP 404) nghĩa là chưa kết nối Gemini trong 9router. Phải hiện đúng thông báo đó cho người dùng.
- Không thêm thư viện mới; `httpx` và `pydantic` đã có.
- Windows 11, `.venv\Scripts\python.exe` (Python 3.14). Không in và không chép `.env`.
- Route nào nhận id hoặc đường dẫn thì dùng các helper trong `backend/security.py` (`require_safe_id`, `validate_path_ids`, kiểm path containment).
- **Test offline phải mock LLM.** Không gọi 9router hay Muse thật trong bộ test thường, để bộ test chạy nhanh và cho kết quả ổn định.
- **Được test thật thoải mái** bằng 9router và Muse (người dùng cho phép ngày 19/10/2026). Test thật được đánh dấu riêng để không chạy chung với bộ test offline.
- Repo có git từ 19/10/2026, commit message bằng tiếng Việt. Có thể có phiên khác cùng làm trong folder: không đổi nhánh, chỉ commit file của mình.
- Dữ liệu người dùng (văn bản vụ án, kế hoạch, dự án) không nằm trong danh sách đóng gói của `tools/build_release.py`, và không được phục vụ qua `/static`.

## 6. Người dùng đã quyết

- Một vụ án dùng cho nhiều thị trường. Các bản chỉ khác lời kể và giọng đọc. Bắt buộc có lồng tiếng Anh.
- **Giữ nguyên** cách gây án, diễn biến, quá trình điều tra, và bối cảnh chung không có tên riêng (vùng núi, nông thôn, thành thị…). Điều này thay cho ý ban đầu "đổi nhẹ cách gây án".
- **Chỉ thay** tên người và địa danh riêng, bằng tên hư cấu theo phong cách văn hoá gốc của vụ án. Ví dụ vụ ở Đài Loan thì dùng địa danh và tên kiểu Trung Hoa. Không chuyển bối cảnh theo thị trường.
- Nhân vật người Hoa có hai dạng tên: Hán-Việt trong bản Việt (ví dụ "Lưu Vinh Phú"), pinyin trong bản Anh (ví dụ "Liu Rongfu"). Vụ ở Việt Nam dùng tên giả kiểu Việt; vụ ở Mỹ dùng tên kiểu Mỹ.
- Bản Anh viết lại cho tự nhiên với người nghe Mỹ, nhưng bám đúng từng cảnh để dùng chung hình. Độ dài mỗi cảnh chạy theo độ dài giọng đọc của từng bản.
- Giọng Việt là VieNeu (một phiên khác đang cài lên ổ D). Giọng Anh hiện là Edge-TTS.
- Ảnh và video tạo bằng Muse.
- Phong cách: như vụ án được chuyển thể thành truyện hoặc phim.
- **Mức kịch tính hoá: "như phim".** Được thêm không khí, cảm xúc, nội tâm và thoại dựng lại, nhưng chỉ dựa trên những sự kiện có trong bài. Được có nhân vật phụ không tên (người qua đường, hàng xóm). Không được thêm sự kiện, nhân vật có vai trò trong vụ án, hay bằng chứng mới.
- **Địa danh lớn: giữ quốc gia.** Giữ tên nước ("Đài Loan", "Việt Nam", "Mỹ") và tên chung của cơ quan ("cảnh sát", "toà án", "viện kiểm sát"). Đổi mọi địa danh từ thành phố, huyện trở xuống, và cả tên đơn vị cụ thể (ví dụ "đội trọng án Đào Viên").
- **Ngày giờ: năm thành thời kỳ.** Bỏ ngày và tháng cụ thể. Năm đổi thành cách nói chung ("giữa thập niên 2010"). Giữ mùa và các mốc tương đối ("ba ngày sau"). Giữ giờ trong ngày, vì giờ có thể là bằng chứng (ví dụ cuộc gọi lúc 02:21).
- **Chia nhỏ việc cho LLM, chạy tuần tự.** Model của 9router hay lười và tóm gọn, nên phân tích phải được chia thành nhiều việc nhỏ chạy lần lượt cho tới khi xong việc lớn. Dùng scheduler nào cũng được, miễn là tuần tự (xem 7.1a).
- **Được test thoải mái bằng LLM 9router và Muse.**
- **Phần cố định: chỉ có câu miễn trừ** ở cảnh đầu video, bằng cả tiếng Việt và tiếng Anh: "Câu chuyện dựa trên một vụ án có thật; tên người và địa danh đã được thay đổi." Không có lời chào của kênh, không có lời kêu gọi đăng ký.

## 7. Thiết kế

### 7.1 Luồng tổng

```
Dán vụ án + chọn thời lượng/giọng/phong cách
└─ [Phân tích] → tạo hàng việc cho vụ án (lưu trên đĩa); worker chạy từng việc nhỏ, lần lượt
   ├─ G1. Chia bài thành các đoạn khoảng 3.000 ký tự, cắt theo ranh giới đoạn văn ......... code
   ├─ G2. Đọc từng đoạn: nhân vật, địa danh, sự việc, bằng chứng có trong đoạn ............ 1 lần gọi mỗi đoạn
   ├─ G3. Gộp các cách gọi khác nhau của cùng một người hay một nơi ....................... 1 lần gọi
   ├─ G4. Đặt tên hư cấu, xác định văn hoá, đặt tên tập, tả ngoại hình → hồ sơ chuyển thể .. 1 lần gọi
   ├─ G5. Dàn ý: chia thành các nhịp, mỗi nhịp 2–6 cảnh ................................. 1 lần gọi
   ├─ G6. Lần lượt từng nhịp: viết lời Việt → viết lời Anh → viết prompt hình ............. 3 lần gọi mỗi nhịp
   └─ G7. Ráp kế hoạch, kiểm tra bằng code (lọt tên, ngày tháng, đủ nội dung) ............. code
└─ Màn xem lại: bảng tên thật → tên Việt → tên Anh (sửa được), cảnh báo, dàn ý, danh sách cảnh
└─ [Tạo dự án bản Việt] → Bước 2 như hiện có: Muse tạo hình, VieNeu đọc, dựng video
└─ [Tạo bản tiếng Anh] → chép hình/video, thay lời kể + giọng Anh + bảng ghim nhãn Anh → dựng bản Anh
```

### 7.1a Vì sao chia nhỏ, và cách chạy tuần tự

**Lý do.** Người dùng đã quan sát thấy model của 9router hay "lười suy nghĩ và tóm gọn vấn đề" khi phải làm một việc lớn trong một lần gọi. Vì vậy:
- mỗi lần gọi chỉ làm một việc hẹp, với kích thước đầu ra cố định (ví dụ "đúng 4 cảnh cho nhịp này");
- đầu ra được code kiểm ngay: số lượng, độ dài tối thiểu, có kể đủ các sự việc được giao hay không;
- đầu ra mỏng hoặc thiếu thì gọi lại, kèm lý do bị loại;
- một việc được thử tối đa 3 lần. Vẫn hỏng thì dừng hàng việc và báo rõ việc nào hỏng, vì sao. Người dùng bấm "Thử lại" để chạy tiếp từ đúng việc đó.

**Hàng việc.**
- `projects/_cases/<case_id>/pipeline.json` liệt kê các việc theo thứ tự, mỗi việc có trạng thái `pending`, `running`, `done` hoặc `failed`. Kết quả từng việc lưu ở `projects/_cases/<case_id>/steps/<step_id>.json`.
- Danh sách việc lớn dần trong lúc chạy: việc G5 xong mới sinh ra các việc G6 (3 việc mỗi nhịp) và việc G7.

**Worker.**
- Chạy ngay trong tiến trình server, khởi động cùng app. Không cần cron bên ngoài.
- Mỗi lúc chỉ chạy **một** việc, cho mọi vụ án. Vụ cũ hơn được làm trước.
- Server khởi động lại thì các việc đang `running` trở về `pending` và chạy tiếp. Việc đã `done` không làm lại.

**Thời gian.** Mỗi lần gọi mất khoảng 5–20 giây. Một vụ dài như Nhũ Cô làm video 8 phút tốn khoảng 10–15 phút phân tích; làm video 30 phút có thể tới 30 phút. Giao diện hiện việc đang làm và số việc đã xong trên tổng số.

### 7.2 G2–G4: Hồ sơ chuyển thể

**Đầu vào:** toàn bộ văn bản vụ án, chia thành đoạn ở G1. Văn bản dài quá giới hạn an toàn (mặc định 200.000 ký tự) thì báo lỗi rõ, không cắt ngầm.

**G2, đọc từng đoạn.**
- Đầu vào: đúng một đoạn, kèm danh sách tên đã gặp ở các đoạn trước để LLM gọi thống nhất.
- Đầu ra: các tên xuất hiện trong đoạn (kèm loại và vai đoán được), các sự việc (tóm tắt, mốc thời gian, những tên liên quan), bằng chứng (nhãn vi/en, mô tả, tên liên quan), quan hệ (nguồn, đích, loại, nhãn vi/en).
- Prompt dặn: mỗi sự việc riêng biệt là một mục, không gộp nhiều sự việc làm một.
- Kiểm tra: đoạn dài từ 150 từ trở lên phải có ít nhất 1 sự việc mỗi 250 từ. Mỗi tóm tắt sự việc phải dài ít nhất 12 từ.

**G3, gộp tên.**
- Đầu vào: mọi tên khác nhau gom từ G2, mỗi tên kèm loại, vai và một câu ngữ cảnh.
- Đầu ra: các nhóm, mỗi nhóm là một entity (ví dụ "Nguyễn Văn Hùng", "ông Hùng", "Hùng" là một người).
- Kiểm tra: mỗi tên đầu vào nằm trong đúng một nhóm.

**G4, đặt tên hư cấu.**
- Đầu vào: các nhóm của G3, cộng một đoạn trích đầu bài để LLM nhận ra văn hoá và thời đại.
- Code ghép kết quả với sự việc, bằng chứng, quan hệ từ G2, để ra **hồ sơ chuyển thể**. Các tên được ánh xạ sang id entity bằng cách so dạng bỏ dấu.
- Kiểm tra: entity nào cũng có `alias_vi` và `alias_en`; không có alias trùng nhau; không alias nào trùng một tên thật.

**Hồ sơ chuyển thể** là JSON, kiểm bằng pydantic, gồm:
- `source_language`
- `culture`: ví dụ `chinese_taiwan`, `vietnamese`, `american`. Dùng để chọn kiểu tên hư cấu.
- `title_vi`, `title_en`: tên tập hư cấu, không chứa tên thật. Thay cho cách cũ lấy dòng đầu của bài.
- `logline_vi`, `logline_en`
- `entities[]`, mỗi mục gồm:
  - `id`
  - `kind`: `person`, `place`, `organization` hoặc `identifier` (biển số, số điện thoại…)
  - `real_names[]`: mọi cách viết xuất hiện trong bài, kể cả biến thể và cách gọi tắt
  - `role`: nạn nhân, nghi phạm, hung thủ, nhân chứng, điều tra viên, người nhà, khác
  - `alias_vi`, `alias_en`
  - `gender`, `age_range`
  - `appearance_en`: mô tả ngoại hình cố định, để ảnh giữa các cảnh nhất quán. Bài không nói thì LLM tự đặt cho hợp với vai và thời đại.
  - `notes`

  Với `place` và `organization`: lấy mọi tên riêng từ cấp thành phố, huyện trở xuống (núi, sông, xã, đường, trường, công ty, bệnh viện, đơn vị công an hay toà án có tên cụ thể). **Không** lấy tên quốc gia và tên chung của cơ quan; những tên này giữ nguyên (xem mục 6). Bối cảnh chung như "vùng núi" hay "thị trấn ven biển" cũng giữ nguyên trong lời kể. Với `identifier`, thay bằng giá trị giả hoặc bỏ hẳn.
- `timeline[]`: `order`, `time_label` (xem 7.6), `summary`, `entity_ids`
- `evidence[]`: `id`, `kind` (hung khí, giám định, giấy tờ, địa điểm, mốc thời gian, người), `label_vi`, `label_en`, `description_vi`, `description_en`, `entity_ids`, `reveal_timeline_order`
- `relations[]`: `source_id`, `target_id`, `relation_type` (theo các giá trị `RelationEdge.relation_type` đang có), `label_vi`, `label_en`, `reveal_timeline_order`
- `setting_notes_en`: thời đại, khí hậu, kiến trúc, trang phục. Dùng cho prompt hình.

### 7.3 G5: Dàn ý

- Đầu vào: dòng thời gian đầy đủ (danh sách sự việc có id), danh sách id bằng chứng, `solved`, và số cảnh mục tiêu.
- Đầu ra: `supported_minutes` và danh sách nhịp. Mỗi nhịp có `id`, `kind`, `event_ids`, `scene_count` (từ 2 đến 6), `summary_vi`.
- Kiểm tra:
  - mọi sự việc nằm trong ít nhất một nhịp;
  - `scene_count` của mỗi nhịp từ 2 đến 6;
  - tổng số cảnh không vượt mục tiêu quá 20%;
  - nếu `supported_minutes` ≥ thời lượng đã chọn mà tổng số cảnh vẫn dưới mục tiêu tối thiểu, thì coi là lười và gọi lại.
- Số cảnh mục tiêu lấy theo bảng thời lượng đang hiện trong modal. Trung bình khoảng 15 giây mỗi cảnh:

  | Thời lượng | Số cảnh |
  |---|---|
  | 8 phút | 35–40 |
  | 15 phút | 50–60 |
  | 20 phút | 70–80 |
  | 30 phút | 100–120 |

- **Số cảnh co theo lượng tư liệu.** G5 ước lượng bài đủ chất liệu cho tối đa bao nhiêu phút mà không phải bịa. Người dùng chọn dài hơn mức đó thì làm ít cảnh hơn, kèm cảnh báo trên màn xem lại ("bài chỉ đủ khoảng N phút"). Không kéo dài cho đủ số cảnh.
- Các nhịp đi theo cấu trúc phim: mở đầu gây tò mò (không tiết lộ kết), bối cảnh, phát hiện, điều tra, bước ngoặt, phá án, kết và dư âm. Vụ chưa phá được thì nhịp "phá án" đổi thành "những câu hỏi còn bỏ ngỏ".
- **Cảnh miễn trừ** luôn là cảnh số 1. Lời kể vi/en là chuỗi cố định trong code, không do LLM viết. Hình là ảnh nền tối có chữ (builder chọn cách vẽ, ví dụ dùng PIL như bảng ghim). Cảnh này được tính vào số cảnh, và không thuộc diện kiểm "không bịa tình tiết".

### 7.4 G6: Viết cảnh (3 lần gọi cho mỗi nhịp, chạy tuần tự)

Các nhịp được viết lần lượt theo thứ tự trong dàn ý, để nhịp sau đọc được những cảnh cuối của nhịp trước.

1. **Lời Việt.**
   - Đầu vào: hồ sơ (dùng tên `alias_vi`); tóm tắt nhịp; các sự việc của nhịp, mỗi sự việc kèm toàn văn những đoạn gốc chứa nó (để bám đúng sự thật; prompt dặn chỉ được dùng tên hư cấu); 2 cảnh cuối của nhịp trước.
   - Đầu ra: đúng `scene_count` cảnh. Mỗi cảnh có `narration_vi`, `visual_kind`, `board_reveal`, `covers_event_ids`.
   - Kiểm tra: đúng số cảnh; mỗi lời dài 25–80 từ; các cảnh gộp lại kể đủ mọi sự việc của nhịp; id trong `board_reveal` đều có thật.
2. **Lời Anh.**
   - Đầu vào: hồ sơ (dùng tên `alias_en`), các cảnh lời Việt của nhịp, và cùng những đoạn gốc ở trên.
   - Đầu ra: `narration_en` cho từng cảnh. Viết lại tự nhiên, không dịch sát từng chữ.
   - Kiểm tra: đúng số cảnh; mỗi lời dài 20–70 từ.
3. **Prompt hình.**
   - Đầu vào: `appearance_en` của các nhân vật, `setting_notes_en`, phong cách hình đã chọn, lời Việt và lời Anh của các cảnh.
   - Đầu ra: `image_prompt`, `video_prompt`, `camera_motion`, `narrative_beat`, `sfx_cue`, `bgm_energy` cho từng cảnh.
   - Kiểm tra: đúng số cảnh; `image_prompt` dài ít nhất 20 từ; cảnh `video` phải có `video_prompt`.

**G7** ráp mọi nhịp thành danh sách cảnh: chèn cảnh miễn trừ làm cảnh 1, đánh số lại, rồi kiểm tra theo 7.5.

**Mỗi cảnh gồm:**
- `order` (đánh số toàn cục) và `part_id` (id của nhịp).
- `narration_vi`, `narration_en`: lời kể ngôi thứ ba, giọng người kể chuyện điện ảnh, dùng tên hư cấu. Kịch tính hoá theo mức "như phim" ở mục 6: được dựng thoại (đặt trong lời kể, ví dụ: anh ta nói: "…") và nội tâm, nhưng chỉ dựa trên sự kiện có trong bài. Ngày giờ theo mục 7.6. Độ dài tham khảo cho cảnh khoảng 15 giây: tiếng Việt 35–45 từ, tiếng Anh 30–40 từ. LLM được co giãn theo nhịp truyện.
- `visual_kind`, một trong ba loại:
  - `board`: cảnh nói về bằng chứng hoặc quan hệ. Dùng ảnh bảng ghim vẽ bằng engine PIL hiện có. `board_reveal[]` là id các evidence/relation hiện ra ở cảnh này.
  - `video`: khoảnh khắc hành động. Tối đa khoảng 15% số cảnh. Lời kể nên ngắn (dưới khoảng 8 giây), vì clip Muse dài 5 giây và sẽ bị lặp nếu giọng dài hơn.
  - `image`: tất cả cảnh còn lại.
- `image_prompt`: tiếng Anh, đọc riêng vẫn hiểu. Gồm khung hình, chủ thể (mô tả bằng `appearance_en`, **không ghi tên**), hành động, bối cảnh lấy từ `setting_notes_en`, ánh sáng, phong cách đã chọn. Bạo lực chỉ được gợi ý qua bóng, hậu cảnh hay đồ vật, không tả máu me.
- `video_prompt`: tiếng Anh, tả chuyển động của máy quay và chủ thể trong 5 giây. Bắt buộc với cảnh `video`.
- `camera_motion`: chỉ dùng các giá trị renderer trong `backend/services/video_service.py` hỗ trợ.
- `narrative_beat`, `sound_design` (`sfx_cue`, `bgm_energy`): giữ các field đang có.

### 7.5 G7: Kiểm tra (bằng code, không dùng LLM)

- **Schema và chất lượng từng việc:** kiểm ngay sau mỗi việc nhỏ, theo 7.1a–7.4. Một việc được thử tối đa 3 lần; lần 2 và lần 3 gửi kèm lý do lần trước bị loại.
- **Lọt tên thật:**
  - Danh sách chuỗi cấm gồm `entities[].real_names`, cộng với các tên mà regex hiện có (`AnonymizerShield.extract_pii_candidates`) bắt được trên văn bản gốc.
  - So khớp theo ranh giới từ, không phân biệt hoa thường, bỏ dấu.
  - Quét ở: tên tập, lời kể vi/en, prompt, nhãn evidence/relation.
  - Tìm thấy tên đã có alias thì tự thay và ghi vào danh sách cảnh báo trên màn xem lại. Tên chưa có alias thì đánh dấu cảnh đó để người dùng sửa.
  - Tên quốc gia và tên chung của cơ quan được giữ (mục 6), nên không bị coi là lọt tên.
  - Builder tự xử lý báo nhầm với tên ngắn hoặc tên chung (ví dụ tên chỉ có một chữ).
- **Ngày tháng:** quét lời kể vi/en để tìm ngày-tháng cụ thể và năm viết bằng số (ví dụ "7 tháng 10", "10/7", "2014", "October 7"). Gặp thì đánh dấu như lọt tên. Giờ trong ngày ("02:21", "2 giờ sáng") được giữ.
- **Cảnh bị đánh dấu chặn việc tạo dự án:** còn cảnh bị đánh dấu thì nút "Tạo dự án" bị khoá, route trả 409. Người dùng gỡ bằng một trong hai cách: sửa lời kể của cảnh đó ngay trên màn xem lại, hoặc thêm tên vào bảng tên. Xong thì chạy lại kiểm tra.
- **Đủ nội dung:**
  - mỗi cảnh có đủ hai thứ tiếng, không bỏ trống;
  - số cảnh không vượt mục tiêu quá 20%; ít hơn mục tiêu thì được, kèm cảnh báo (xem 7.3);
  - mọi id trong `board_reveal` đều tồn tại;
  - mỗi evidence xuất hiện ít nhất một lần.
- **Không có đường lui offline.** 9router lỗi (mạng, 401, 404 chưa kết nối Gemini, timeout) thì hàng việc dừng ở việc đó, kèm thông báo cụ thể và nút "Thử lại". Lỗi 401 và 404 không tự thử lại, vì gọi lại cũng sẽ hỏng y như vậy.

### 7.6 Ngày tháng và chi tiết nhận dạng khác

Người dùng đã quyết (mục 6):
- bỏ ngày và tháng cụ thể;
- năm đổi thành thời kỳ ("giữa thập niên 2010");
- giữ mùa, các mốc tương đối ("một chiều cuối thu", "ba ngày sau", "mười năm sau") và giờ trong ngày.

Mình tự quyết thêm: tuổi giữ ở dạng xấp xỉ ("khoảng năm mươi tuổi"). Khoảng cách thời gian giữa các sự kiện giữ đúng như trong bài.

### 7.7 Dữ liệu và lưu trữ

- Kế hoạch mới tên là `CaseAdaptationPlan` (pydantic). Field: `case_id`, `created_at`, `model`, `target_minutes`, `languages`, `source_language`, `culture`, các tên tập, `entities`, `timeline`, `evidence`, `relations`, `parts`, `scenes`, `warnings`.
- Lưu ở `projects/_cases/<case_id>/plan.json`, kèm `source.txt` (văn bản gốc, có tên thật, chỉ nằm trên máy người dùng). `list_projects` chỉ liệt kê thư mục có `project.json`, nên `_cases` không hiện trong danh sách dự án.
- Dự án tạo từ kế hoạch ghi vào `metadata`: `case_id`, `language` (`vi` hoặc `en`), `sibling_project_ids`.
- Mỗi Scene của dự án:
  - `text` = lời kể của ngôn ngữ dự án;
  - `metadata.narration = {"vi": …, "en": …}`;
  - `metadata.narration_source`: lời của ngôn ngữ dự án tại lúc tạo, dùng để phát hiện cảnh bị sửa về sau (xem 7.8);
  - `metadata.visual_kind`, `metadata.board_reveal`;
  - `image_prompt` và `video_prompt`. Hiện `video_prompt` đang bị bỏ khi tạo cảnh, phải giữ lại;
  - `shot_type` giữ giá trị cũ để tương thích: `B_ROLL_BOARD` cho cảnh `board`, `A_ROLL_NOIR` cho cảnh `image` và `video`.
- Ảnh bảng ghim vẽ thẳng vào `projects/<pid>/images/`, không ghi vào `backend/static/evidence_boards/` (thư mục đó đang công khai).
- Bảng ghim tích luỹ theo cảnh như engine hiện có (`get_cumulative_board_state`), nhưng lấy dữ liệu từ `evidence` và `relations` của kế hoạch, với nhãn theo ngôn ngữ của dự án.

### 7.8 API

| Route | Việc |
|---|---|
| `POST /api/true-crime/analyze` | body `{raw_report, target_minutes, languages, visual_style}` → `{case_id}`. Lưu văn bản gốc, tạo hàng việc; worker tự nhận và chạy. |
| `GET /api/true-crime/cases/{case_id}/progress` | `{status: running/done/failed, step_label, steps_done, steps_total, error}`. `step_label` là câu tiếng Việt, ví dụ "Đang đọc đoạn 3/20" hoặc "Đang viết lời Anh, nhịp 4/12". |
| `POST /api/true-crime/cases/{case_id}/resume` | Đưa việc bị hỏng về `pending` và cho hàng việc chạy tiếp. |
| `GET /api/true-crime/cases/{case_id}` | Trả về kế hoạch. Phân tích chưa xong thì trả 409. |
| `GET /api/true-crime/jobs/{job_id}` | Chỉ dùng cho job tạo bản ngôn ngữ khác (ngắn, chạy trong bộ nhớ). |
| `PUT /api/true-crime/cases/{case_id}/entities` | Người dùng sửa tên hư cấu, hoặc thêm tên mới (thường là tên mà regex bắt được). Áp tên mới cho toàn bộ cảnh và nhãn, rồi chạy lại kiểm tra. |
| `PUT /api/true-crime/cases/{case_id}/scenes/{order}` | Sửa `narration_vi` và/hoặc `narration_en` của một cảnh, rồi chạy lại kiểm tra cho cảnh đó. |
| `POST /api/true-crime/cases/{case_id}/create-project` | body `{language, voice, visual_style, image_provider}` → dự án; bảng ghim vẽ bằng nhãn của ngôn ngữ đó. Trả **409** khi còn cảnh bị đánh dấu (7.5). |
| `POST /api/projects/{pid}/create-language-version` | body `{language, voice}` → `{job_id}`. Các bước: (1) chép ảnh, clip Muse và ảnh tải lên; (2) lấy `text` từ `metadata.narration[lang]`; (3) vẽ lại các cảnh bảng ghim theo ngôn ngữ mới; (4) xoá audio, segment và video cuối; (5) đặt giọng mới; (6) lưu thành dự án mới, liên kết hai chiều qua `sibling_project_ids`. **Cảnh mới thêm, hoặc có lời Việt đã sửa sau khi tạo dự án** (so với bản gốc lưu ở `metadata.narration_source`), thì LLM viết lại lời Anh cho riêng các cảnh đó: dùng bảng tên `alias_en` và mức kịch tính hoá như G6, rồi chạy kiểm tra của G7 cho các cảnh đó. Kết quả liệt kê những cảnh đã được viết lại. |

- Phân tích chạy qua hàng việc lưu trên đĩa (7.1a), nên tắt server giữa chừng vẫn chạy tiếp được.
- Riêng job tạo bản ngôn ngữ khác thì ngắn (chỉ viết lại vài cảnh), nên lưu trong bộ nhớ theo kiểu `active_renders`. Tắt server lúc đang chạy job này thì người dùng bấm lại.
- Khi giao diện đã chuyển sang luồng mới, bỏ `/api/true-crime/fictionalize` và `/api/true-crime/create-project` cũ. `/render-board-scene` chuyển sang đọc kế hoạch mới.

### 7.9 Giao diện (modal Hồ Sơ Kỳ Án)

- **Giữ:** ô dán hồ sơ, nút hồ sơ mẫu (chỉ để nạp văn bản mẫu vào ô), chọn thời lượng, phong cách hình, engine hình.
- **Bỏ:**
  - thanh trượt 70/30, tab "Ma trận" và tab "Phục bút";
  - danh sách cảnh viết cứng trong ô chọn cảnh của bảng ghim;
  - `buildDeterministicTrueCrimePlan` cùng các kế hoạch mẫu viết cứng trong JS;
  - ca Nhũ Cô 72 cảnh: `services/nhu_co_case_scenes.py` không còn được gọi. File để nguyên, chỉ chuyển vào Thùng rác khi người dùng đồng ý.
- **Thêm:**
  - chọn giọng cho từng ngôn ngữ (Việt mặc định VieNeu, Anh mặc định en-US);
  - tiến độ phân tích (đang ở bước nào, phần i/n);
  - màn xem lại, gồm:
    - bảng tên thật → tên Việt → tên Anh: sửa được, thêm được tên mới;
    - cảnh báo: lọt tên, ngày tháng, bài không đủ tư liệu cho thời lượng đã chọn;
    - dàn ý;
    - danh sách cảnh: lời Việt và lời Anh đặt song song, sửa trực tiếp được, kèm loại hình; cảnh bị đánh dấu được làm nổi bật;
  - nút "Tạo dự án bản Việt", bị khoá khi còn cảnh bị đánh dấu.
- Canvas bảng ghim trong modal vẽ từ `evidence`/`relations` của kế hoạch. Sửa luôn lỗi `normalizeBoardData` làm biến dạng kế hoạch rồi gửi ngược lên server.
- Sửa lỗi mỗi nút đang gắn hai trình xử lý click (`onclick` trong HTML và `addEventListener` trong JS), khiến bấm một lần tạo ra hai dự án.
- Ở Bước 2 và Bước 4: dự án có `metadata.narration.en` thì hiện nút "Tạo bản tiếng Anh". Tạo xong thì mở dự án mới.
- Phân tích lỗi thì hiện toast lỗi kèm thông báo cụ thể, không dựng kế hoạch giả.

### 7.10 Prompt LLM

- **Prompt hệ thống:** vai biên kịch chuyển thể vụ án có thật thành truyện hoặc phim. Các quy tắc:
  - giữ nguyên sự thật; không bịa thêm nhân vật, động cơ hay bằng chứng;
  - chỉ đổi tên người và địa danh riêng, theo đúng bảng tên hư cấu;
  - lời kể ngôi thứ ba, giọng người kể chuyện điện ảnh;
  - bản Anh tự nhiên với khán giả Mỹ nhưng cùng nội dung từng cảnh;
  - tôn trọng nạn nhân, không giật gân hoá;
  - trả JSON đúng schema.
- Đặt toàn bộ prompt trong một module riêng, ví dụ `backend/services/case_adaptation_prompts.py`, để dễ chỉnh.

### 7.11 Kiểm thử

- **Offline** (mock hàm gọi LLM), cần có:
  - tên hư cấu được áp đúng;
  - kiểm lọt tên bắt được tên thật (có dấu, không dấu, khác hoa thường) trong lời kể, prompt và nhãn bảng ghim;
  - LLM lỗi thì hàng việc ở trạng thái `failed`, không có đường lui; "Thử lại" chạy tiếp từ đúng việc hỏng;
  - đầu ra mỏng (ít sự việc, lời quá ngắn, thiếu cảnh) bị loại và gọi lại kèm lý do; hỏng 3 lần thì dừng;
  - server khởi động lại giữa chừng thì hàng việc chạy tiếp, việc đã xong không gọi lại LLM;
  - mỗi lúc chỉ có một lần gọi LLM, kể cả khi có hai vụ án cùng phân tích;
  - dự án bản Việt có `text` tiếng Việt và có `metadata.narration`;
  - tạo bản Anh thì media được chép, `text` và giọng được đổi, bảng ghim có nhãn tiếng Anh;
  - tạo bản Anh: cảnh mới thêm hoặc đã sửa thì được gọi LLM viết lại (mock), các cảnh khác giữ nguyên;
  - ngày-tháng cụ thể và năm viết bằng số bị đánh dấu; giờ trong ngày và tên quốc gia không bị đánh dấu;
  - còn cảnh bị đánh dấu thì create-project trả 409; sửa cảnh hoặc thêm tên xong thì tạo được;
  - cảnh 1 luôn là cảnh miễn trừ, có đủ hai thứ tiếng;
  - bài ngắn thì số cảnh co lại và có cảnh báo;
  - route kiểm id.
- Viết lại `tests/test_true_crime_e2e.py`, `tests/test_case_fictionalizer.py`, `tests/test_true_crime_router.py` theo luồng mới.
- Không được tệ hơn baseline: 128 test offline đang đạt.
- **Chạy thật** (người dùng đã cho phép test thoải mái bằng 9router và Muse): vụ Nhũ Cô, 8 phút, gọi 9router thật; sau đó tạo vài ảnh và một video bằng Muse để kiểm cả chuỗi. File mẫu `_archive_2026-10-19/case_input_text.txt` hiện nằm trong Thùng rác của Windows. Khôi phục file rồi đặt vào một thư mục đã có trong `.gitignore` và không nằm trong danh sách đóng gói (bài gốc có tác giả, không đưa lên git). Tiêu chí:
  - không lọt tên thật;
  - đủ các sự kiện chính;
  - bản Anh đọc tự nhiên (người dùng tự đánh giá);
  - ghi lại thời gian phân tích.

### 7.12 Để builder tự quyết

- Các ngưỡng kiểm tra cụ thể (độ dài lời, số sự việc mỗi đoạn, kích thước đoạn), timeout của từng lần gọi, và câu chữ trong prompt. Các con số trong 7.1a–7.4 là mặc định khởi đầu, chỉnh lại sau khi chạy thật.
- Tên file, tên module, chi tiết các model pydantic.
- Thay hẳn `FictionalCasePlan` hay giữ để tương thích.
- Cách bố trí thẻ trên bảng ghim (có thể giữ `assign_fixed_anchor_layout`).
- Chi tiết bố cục màn xem lại.

## 8. Mặc định mình tự chọn (người dùng có thể đổi)

- Bỏ công thức 70/30 và sổ phục bút. Bảng ghim giữ lại như một kiểu hình B-roll, nhưng dùng bằng chứng thật trong vụ án.
- Hàng việc lưu trên đĩa, worker tuần tự chạy ngay trong server; không dùng cron bên ngoài. Đoạn khoảng 3.000 ký tự, nhịp 2–6 cảnh, mỗi việc thử tối đa 3 lần.
- Kế hoạch lưu ở `projects/_cases/`. Bảng ghim không ghi vào `/static` nữa.
- Khoảng 15 giây mỗi cảnh, theo bảng thời lượng có sẵn. Cảnh video tối đa khoảng 15%.
- Mỗi lần viết cảnh đều gửi kèm toàn bộ văn bản gốc, để lời kể bám đúng sự thật.
- Không có đường lui offline. Hàm `generate_offline_script` vừa được khôi phục không còn là đường lui tự động.
- Bản Anh tạo sau khi bản Việt đã có hình, bằng cách chép dự án, để Muse không phải vẽ hai lần.
- Tạm dùng Edge-TTS cho tiếng Anh.
- Số cảnh co theo lượng tư liệu; bài thiếu thì cảnh báo, không bịa cho đủ. Vụ chưa phá được thì kết bằng "những câu hỏi còn bỏ ngỏ".
- Còn cảnh bị đánh dấu thì khoá việc tạo dự án. Màn xem lại cho sửa trực tiếp lời Việt và lời Anh, và cho thêm tên mới.
- Khi tạo bản Anh, LLM viết lại lời Anh cho các cảnh mới thêm hoặc đã bị sửa ở bản Việt.
- Cảnh miễn trừ là ảnh nền tối có chữ, lời kể là chuỗi cố định trong code.

## 9. Lịch sử thay đổi gần đây cần biết

- Phiên "Kiểm toán bảo mật và tổ chức folder" đã sửa `case_fictionalizer.py` để các test cũ chạy qua: khôi phục `YouTubeReviewerScriptGenerator.generate_offline_script`, và nhánh truyện dài chỉ chạy khi `duration_minutes > 1`.
- Phiên "Sửa 3 lỗi chung" đã đổi các chỗ sau:
  - clip Muse lưu ở `videos/{scene}_muse.mp4`;
  - thêm `Scene.motion_video_path` và `status_video`;
  - thêm `Project.settings`;
  - giao diện tự lưu lên server;
  - gỡ các chỗ báo thành công giả.

  Luồng mới phải dựa trên các thay đổi này.

## 10. Rủi ro và lưu ý

- **Edge-TTS** dùng endpoint "Đọc to" của Microsoft Edge, không phải dịch vụ chính thức. Không có cam kết, quyền dùng thương mại không rõ, có thể bị chặn. Cần chọn engine tiếng Anh trước khi bán tool.
- **Nhận ra vụ án:** dù đã đổi tên, một câu chuyện giữ đúng diễn biến vẫn có thể nhận ra là vụ nào. Bài viết gốc có tác giả, nên bản chuyển thể có thể bị coi là tác phẩm phái sinh. Việc rà soát pháp lý vẫn đang để ngỏ.
- **Thời gian và quota Muse:** 30 phút tương đương 100–120 cảnh, khoảng 85–100 ảnh. Mỗi ảnh mất khoảng 45 giây, nên một luồng ảnh cần khoảng 1–1,5 giờ.
- **Thời gian phân tích dài hơn và tốn nhiều lần gọi hơn,** vì chia nhỏ việc: khoảng 10–30 phút mỗi vụ, vài chục tới hơn một trăm lần gọi 9router. Đổi lại, lời kể đủ chi tiết và không bị tóm gọn.
- **Giới hạn của kiểm lọt tên:** chỉ bắt được những tên đã biết. LLM có thể bỏ sót một biến thể, nên màn xem lại là lớp kiểm tra cuối, do người dùng duyệt.
