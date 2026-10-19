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
- **Test offline phải mock LLM.** Không gọi 9router hay Muse thật trong bộ test thường. Test gọi thật chỉ chạy khi người dùng yêu cầu.
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
- **Phần cố định: chỉ có câu miễn trừ** ở cảnh đầu video, bằng cả tiếng Việt và tiếng Anh: "Câu chuyện dựa trên một vụ án có thật; tên người và địa danh đã được thay đổi." Không có lời chào của kênh, không có lời kêu gọi đăng ký.

## 7. Thiết kế

### 7.1 Luồng tổng

```
Dán vụ án + chọn thời lượng/giọng/phong cách
└─ [Phân tích] — chạy nền, giao diện xem tiến độ
   ├─ B1. Đọc toàn bộ vụ án → hồ sơ chuyển thể (nhân vật, địa danh, mốc thời gian, bằng chứng)
   ├─ B2. Dàn ý theo thời lượng (các phần như một bộ phim)
   ├─ B3. Viết cảnh theo từng phần: lời kể vi + en, loại hình, prompt ảnh/video
   └─ B4. Kiểm tra bằng code: đúng schema, không lọt tên thật, đủ hai thứ tiếng
└─ Màn xem lại: bảng tên thật → tên Việt → tên Anh (sửa được), cảnh báo, dàn ý, danh sách cảnh
└─ [Tạo dự án bản Việt] → Bước 2 như hiện có: Muse tạo hình, VieNeu đọc, dựng video
└─ [Tạo bản tiếng Anh] → chép hình/video, thay lời kể + giọng Anh + bảng ghim nhãn Anh → dựng bản Anh
```

### 7.2 B1: Hồ sơ chuyển thể (một lần gọi LLM)

**Đầu vào:** toàn bộ văn bản vụ án, không cắt. Văn bản dài quá giới hạn an toàn (mặc định 200.000 ký tự) thì báo lỗi rõ, không cắt ngầm.

**Đầu ra:** JSON, kiểm bằng pydantic, gồm:
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

### 7.3 B2: Dàn ý

- Số cảnh mục tiêu lấy theo bảng thời lượng đang hiện trong modal. Trung bình khoảng 15 giây mỗi cảnh:

  | Thời lượng | Số cảnh |
  |---|---|
  | 8 phút | 35–40 |
  | 15 phút | 50–60 |
  | 20 phút | 70–80 |
  | 30 phút | 100–120 |

- **Số cảnh co theo lượng tư liệu.** B2 ước lượng bài đủ chất liệu cho tối đa bao nhiêu phút mà không phải bịa. Người dùng chọn dài hơn mức đó thì làm ít cảnh hơn, kèm cảnh báo trên màn xem lại ("bài chỉ đủ khoảng N phút"). Không kéo dài cho đủ số cảnh.
- LLM chia câu chuyện thành các phần theo cấu trúc phim: mở đầu gây tò mò (không tiết lộ kết), bối cảnh, phát hiện, điều tra, bước ngoặt, phá án, kết và dư âm. Mỗi phần gồm tóm tắt, các mốc `timeline` mà phần đó kể, và số cảnh. Vụ chưa phá được thì phần "phá án" đổi thành "những câu hỏi còn bỏ ngỏ".
- Code kiểm tra mọi mốc `timeline` đều nằm trong ít nhất một phần. Thiếu thì gọi lại.
- **Cảnh miễn trừ** luôn là cảnh số 1. Lời kể vi/en là chuỗi cố định trong code, không do LLM viết. Hình là ảnh nền tối có chữ (builder chọn cách vẽ, ví dụ dùng PIL như bảng ghim). Cảnh này được tính vào số cảnh, và không thuộc diện kiểm "không bịa tình tiết".

### 7.4 B3: Viết cảnh (mỗi phần một lần gọi; được chạy song song)

**Đầu vào mỗi lần gọi:**
- hồ sơ B1 (đã có tên hư cấu) và dàn ý B2;
- phần đang viết, kèm 2 cảnh cuối của phần trước để nối mạch;
- toàn bộ văn bản gốc, để LLM bám đúng sự thật. Prompt dặn rõ chỉ được dùng tên hư cấu.

**Mỗi cảnh gồm:**
- `order` (đánh số toàn cục) và `part_id`.
- `narration_vi`, `narration_en`: lời kể ngôi thứ ba, giọng người kể chuyện điện ảnh, dùng tên hư cấu. Kịch tính hoá theo mức "như phim" ở mục 6: được dựng thoại (đặt trong lời kể, ví dụ: anh ta nói: "…") và nội tâm, nhưng chỉ dựa trên sự kiện có trong bài. Ngày giờ theo mục 7.6. Độ dài tham khảo cho cảnh khoảng 15 giây: tiếng Việt 35–45 từ, tiếng Anh 30–40 từ. LLM được co giãn theo nhịp truyện.
- `visual_kind`, một trong ba loại:
  - `board`: cảnh nói về bằng chứng hoặc quan hệ. Dùng ảnh bảng ghim vẽ bằng engine PIL hiện có. `board_reveal[]` là id các evidence/relation hiện ra ở cảnh này.
  - `video`: khoảnh khắc hành động. Tối đa khoảng 15% số cảnh. Lời kể nên ngắn (dưới khoảng 8 giây), vì clip Muse dài 5 giây và sẽ bị lặp nếu giọng dài hơn.
  - `image`: tất cả cảnh còn lại.
- `image_prompt`: tiếng Anh, đọc riêng vẫn hiểu. Gồm khung hình, chủ thể (mô tả bằng `appearance_en`, **không ghi tên**), hành động, bối cảnh lấy từ `setting_notes_en`, ánh sáng, phong cách đã chọn. Bạo lực chỉ được gợi ý qua bóng, hậu cảnh hay đồ vật, không tả máu me.
- `video_prompt`: tiếng Anh, tả chuyển động của máy quay và chủ thể trong 5 giây. Bắt buộc với cảnh `video`.
- `camera_motion`: chỉ dùng các giá trị renderer trong `backend/services/video_service.py` hỗ trợ.
- `narrative_beat`, `sound_design` (`sfx_cue`, `bgm_energy`): giữ các field đang có.

### 7.5 B4: Kiểm tra (bằng code, không dùng LLM)

- **Schema:** kiểm JSON bằng pydantic. Phần nào lỗi thì gọi lại phần đó, tối đa 2 lần; vẫn lỗi thì báo lỗi.
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
- **Không có đường lui offline.** 9router lỗi (mạng, 401, 404 chưa kết nối Gemini, timeout) thì job thất bại, kèm thông báo cụ thể và nút thử lại.

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
| `POST /api/true-crime/analyze` | body `{raw_report, target_minutes, languages, visual_style}` → `{job_id}`. Chạy nền. |
| `GET /api/true-crime/jobs/{job_id}` | `{status: queued/running/done/failed, step, part_done, part_total, error, case_id}` |
| `GET /api/true-crime/cases/{case_id}` | Trả về kế hoạch. |
| `PUT /api/true-crime/cases/{case_id}/entities` | Người dùng sửa tên hư cấu, hoặc thêm tên mới (thường là tên mà regex bắt được). Áp tên mới cho toàn bộ cảnh và nhãn, rồi chạy lại kiểm tra. |
| `PUT /api/true-crime/cases/{case_id}/scenes/{order}` | Sửa `narration_vi` và/hoặc `narration_en` của một cảnh, rồi chạy lại kiểm tra cho cảnh đó. |
| `POST /api/true-crime/cases/{case_id}/create-project` | body `{language, voice, visual_style, image_provider}` → dự án; bảng ghim vẽ bằng nhãn của ngôn ngữ đó. Trả **409** khi còn cảnh bị đánh dấu (7.5). |
| `POST /api/projects/{pid}/create-language-version` | body `{language, voice}` → `{job_id}`. Các bước: (1) chép ảnh, clip Muse và ảnh tải lên; (2) lấy `text` từ `metadata.narration[lang]`; (3) vẽ lại các cảnh bảng ghim theo ngôn ngữ mới; (4) xoá audio, segment và video cuối; (5) đặt giọng mới; (6) lưu thành dự án mới, liên kết hai chiều qua `sibling_project_ids`. **Cảnh mới thêm, hoặc có lời Việt đã sửa sau khi tạo dự án** (so với bản gốc lưu ở `metadata.narration_source`), thì LLM viết lại lời Anh cho riêng các cảnh đó: dùng bảng tên `alias_en` và mức kịch tính hoá như B3, rồi chạy kiểm tra B4 cho các cảnh đó. Kết quả liệt kê những cảnh đã được viết lại. |

- Job lưu trong bộ nhớ, theo kiểu `active_renders` đang dùng. Kế hoạch ghi ra đĩa khi job xong. Tắt server giữa chừng thì chỉ mất job đang chạy; người dùng chạy lại.
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
  - LLM lỗi thì job ở trạng thái `failed`, không có đường lui;
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
- **Chạy thật** (chỉ khi người dùng yêu cầu): vụ Nhũ Cô, 8 phút, gọi 9router thật. File mẫu `_archive_2026-10-19/case_input_text.txt` hiện nằm trong Thùng rác của Windows. Trước khi chạy, xin người dùng cho khôi phục, rồi đặt vào một thư mục đã có trong `.gitignore` và không nằm trong danh sách đóng gói (bài gốc có tác giả, không đưa lên git). Tiêu chí:
  - không lọt tên thật;
  - đủ các sự kiện chính;
  - bản Anh đọc tự nhiên (người dùng tự đánh giá);
  - ghi lại thời gian phân tích.

### 7.12 Để builder tự quyết

- Gộp hay tách các lần gọi LLM, số phần, mức chạy song song, timeout và retry cụ thể. Mức nên nhắm: phân tích xong trong vài phút.
- Tên file, tên module, chi tiết các model pydantic.
- Thay hẳn `FictionalCasePlan` hay giữ để tương thích.
- Cách bố trí thẻ trên bảng ghim (có thể giữ `assign_fixed_anchor_layout`).
- Chi tiết bố cục màn xem lại.

## 8. Mặc định mình tự chọn (người dùng có thể đổi)

- Bỏ công thức 70/30 và sổ phục bút. Bảng ghim giữ lại như một kiểu hình B-roll, nhưng dùng bằng chứng thật trong vụ án.
- Phân tích chạy dưới dạng job nền có tiến độ, không gói trong một request dài.
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
- **Giới hạn của kiểm lọt tên:** chỉ bắt được những tên đã biết. LLM có thể bỏ sót một biến thể, nên màn xem lại là lớp kiểm tra cuối, do người dùng duyệt.
