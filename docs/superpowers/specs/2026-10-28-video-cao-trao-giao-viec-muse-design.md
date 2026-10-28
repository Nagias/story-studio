# Video cao trào: giao việc nhiều bước cho Muse + tóc nhân vật nữ — thiết kế

Ngày 28/10/2026. Trạng thái: **chờ chủ dự án duyệt**. Sau khi duyệt mới viết kế hoạch code (`docs/superpowers/plans/`).

## 1. Vì sao

**[Nguyên văn chủ dự án]** (28/10/2026)

> Vậy phương án dùng code là không khả thi, giờ tập trung làm như nào cho video tốt hơn là được. không cần phải hoàn hảo 100% đâu. miễn là phong cách được đồng bộ từ đầu đến cuối, đừng từ mặt tròn chuyển sang mặt người là được. với cả tóc của nhân vật nữ trông trọc quá. nữ thì nên có tóc trên đầu chứ không chỉ 1 chỏm nhỏ ở sau đầu.

> Nếu dựng video bằng code thì cũng là dựng trên Muse luôn, Muse hoàn toàn có thể dựng được như thế. Chính bạn còn chưa nắm được khả năng của Muse, bảo sao video ra bị sai hoàn toàn hết cả.

Bằng chứng (đo thật 27–28/10/2026, ảnh và video trong `.cache/`):

| Cách gọi Muse | Kết quả |
|---|---|
| App hiện tại (nhánh `thu-video-cao-trao`): mỗi clip một prompt, lấy ngay video đầu tiên, khung đầu là ô cắt từ lưới 9 ô | 14/14 clip vẽ lại đầu sau 0,5–1,5 giây (đầu tròn → đầu nhỏ tóc dài, mặt anime). Đo diện tích đầu: 1,0 → 0,55 → mất dáng tròn |
| Thí nghiệm 1 (`.cache/thu-muse-AB-28/`): một yêu cầu, Muse tự tạo, tự trích khung kiểm, tạo lại; khung đầu là ảnh nét, khung cuối là ô storyboard, nối bằng snapshot | Giữ đầu tròn ở góc trước/nghiêng 0–8 giây. Hỏng khi nhân vật xoay ra sau trong clip: đĩa trắng mờ sau tóc. 5 video + 1 ảnh, 21 phút |
| Thí nghiệm 1, cách lai (nền video sinh + nhân vật ghép bằng code) | Đầu đúng tuyệt đối nhưng như hình dán, chân méo. Chủ dự án loại hướng code |
| Thí nghiệm 2 (`.cache/thu-muse-28-lan2/`): như thí nghiệm 1, thêm (a) vẽ lại ảnh cảnh cho tóc nữ phủ đỉnh đầu theo bảng nhân vật, (b) đoạn quay lưng bắt đầu từ ảnh góc sau vẽ riêng, không clip nào xoay người | **Đạt** suốt 12 giây: mặt tròn, tóc trên đầu, quần áo giữ; quay lưng không còn đĩa trắng. Đánh đổi: ngoài phố cô chạy tại chỗ. 4 video + 2 ảnh, ~10 phút |

Muse tự khai (hỏi thẳng trong chat, 28/10/2026): mỗi tài khoản có máy ảo Linux (Python, ffmpeg, PIL); một yêu cầu được tối đa 6 video và 4 ảnh và làm nhiều bước rồi mới gửi bản cuối; công cụ video nhận chuỗi chữ + ảnh (ảnh 1 khung đầu, ảnh 2 khung cuối), có `resume_from_snapshot_id`; không chọn được thời lượng (~10 giây), không có seed hay ô negative prompt.

## 2. Mục tiêu, không làm, chống mục tiêu

**Mục tiêu**
1. Nút video cao trào ra video mà phong cách đồng bộ từ đầu tới cuối: nhân vật đầu tròn không bao giờ thành mặt người/anime.
2. Nhân vật nữ (dự án phong cách đầu tròn) có tóc mọc trên đỉnh đầu, ở mọi ảnh của dự án: ảnh cảnh, bảng nhân vật, video.
3. Cách giao việc cho Muse giống hai thí nghiệm: một yêu cầu nhiều bước mỗi cảnh, Muse tự kiểm và tự làm lại.

**Không làm**
- Dựng chuyển động bằng code (chủ dự án loại).
- Tự vẽ lại ảnh cảnh của dự án cũ (tốn lượt; chủ dự án tự bấm vẽ lại nếu muốn).
- Đổi luồng 1-Click hay luồng truyện chữ.
- Tự đăng YouTube, nâng độ phân giải video (Muse trả 1248×704; để việc riêng).

**Chống mục tiêu** (có chạy cũng là hỏng)
- Video có đoạn nhân vật đổi sang mặt người, dù chỉ vài khung.
- Ảnh tĩnh của dự án còn đầu trọc trong khi video cao trào có tóc (lệch phong cách giữa các cảnh).
- App cầm nhầm bản nháp Muse gửi giữa chừng làm kết quả.
- Một lần bấm tiêu quá 6 video + 4 ảnh mỗi cảnh mà không ai biết.

## 3. Thiết kế

### 3.1 Quy tắc tóc nhân vật nữ

Một quy tắc, hai chỗ đọc, cùng một hằng số (không chép hai lần):
- Hằng số mới `FEMALE_HAIR_RULE_EN` trong `services/image_service.py`, cạnh `STYLE_PRESETS`. Nội dung đề xuất: *"Female characters always have thick, full hair covering most of the top of the head: a generous mass of hair on the crown that frames the white face, then falls to the length given in the design; never a bald round head with only a little hair at the nape."*
- Phong cách `horror_cartoon_2d` (preset có nhân vật đầu tròn) ghép thêm câu này vào `prompt_suffix` → mọi ảnh cảnh vẽ sau đó đều có (prompt ảnh cảnh đã lấy `prompt_suffix` qua `case_adaptation_prompts` và `image_service`).
- Bảng nhân vật và bản giao việc video: câu này được ghép **lúc dựng prompt** (`character_sheets.sheet_prompt()` và `climax_brief.scene_brief()`) cho người `gender == "female"` khi dự án dùng `horror_cartoon_2d`, không ghi cứng vào `design_en` đã lưu. Nhờ vậy thiết kế cũ (kể cả đã duyệt) cũng nhận quy tắc mà không phải sửa dữ liệu. Chỗ nào thiết kế đã lưu nói khác về vị trí tóc (ví dụ "chỉ phủ nửa sau đầu"), prompt ghi rõ quy tắc tóc thắng.
- Kiểu tóc (dài, xoăn, buộc…) vẫn lấy từ `appearance_en` của từng người. Quy tắc chỉ nói tóc phải có trên đỉnh đầu.

### 3.2 Pha clip mới: một yêu cầu Muse cho mỗi cảnh

Pha 1 giữ nguyên: lưới 9 ô làm trong chat riêng của cảnh → chủ dự án duyệt lưới. Pha 2 (làm clip) thay hẳn: bỏ vòng lặp từng clip (`_make_clip`, `clip_prompt`, chỉnh màu từng khung, `check_clip` theo SSIM khung đầu), thay bằng:

1. **Bản giao việc** dựng bằng khuôn trong code, không gọi LLM: `services/climax_brief.py` (file mới), hàm `scene_brief(project, scene, cast, done_token)` trả chuỗi tiếng Việt theo cấu trúc của thí nghiệm 2:
   - đính kèm theo thứ tự: ảnh cảnh đã duyệt, bảng diễn viên của cảnh (`cast_board`), lưới đã duyệt;
   - lời kể và số giây của cảnh; khoá nhân vật lấy từ thiết kế đã duyệt của từng người (`design_en` rút gọn); quy tắc tóc nữ;
   - **Muse tự chia đoạn**: code không biết lúc nào nhân vật quay lưng, nên bản giao việc yêu cầu Muse tự lập danh sách clip từ lời kể và lưới đã duyệt (ô nào góc trước/nghiêng, ô nào góc sau), ghi danh sách đó vào báo cáo, rồi làm theo luật bên dưới. Thí nghiệm 2 do agent viết sẵn từng clip; cách Muse tự chia **chưa thử**, lần chạy thật cảnh 28 và 41 (mục 4) là để kiểm điều này trước khi coi là xong;
   - đánh đổi được chấp nhận: nhân vật cử động ít hoặc chạy tại chỗ thì vẫn đạt; đổi sang mặt người thì không bao giờ đạt;
   - luật cứng: không clip nào để nhân vật xoay từ trước ra sau; đoạn quay lưng phải bắt đầu từ ảnh góc sau vẽ riêng; máy quay đứng yên hoặc lia rất chậm; ảnh cảnh khác bảng nhân vật (ví dụ tóc) thì vẽ lại ảnh cảnh trước;
   - tự kiểm: trích khung mỗi giây và khung cuối; tiêu chí loại như thí nghiệm 2; làm lại trong ngân sách;
   - ngân sách: tối đa 6 video và 4 ảnh;
   - độ dài mục tiêu: bằng lời kể, tối đa 24 giây (6 video mà còn chừa lượt làm lại); lời kể dài hơn thì phần thừa giữ khung cuối khi dựng (đã có `tpad`);
   - giao: đúng một file video cuối, báo cáo ngắn, dòng cuối là `done_token`.
2. **Fleet Runner** thêm kiểu việc `agent_brief` (cùng đường `muse_bridge` như việc ảnh/video):
   - mở chat riêng của cảnh (đã có `thread_url`, `pin_account`), đính kèm nhiều ảnh (đã có), gửi nguyên văn (đã có `raw_prompt`);
   - chờ tới khi chữ trong chat kết thúc bằng `done_token` và đứng yên 90 giây, tối đa `MUSE_AGENT_WAIT_MIN` phút (biến mới trong `config.py` và `.env.example`, mặc định 45);
   - xong thì tải video trong **tin nhắn cuối của Muse** (tin có `done_token`), cùng chữ báo cáo (`muse_reply`). Bản giao việc dặn tin cuối chỉ có một video. Tin cuối có nhiều video → lấy video cuối cùng và ghi cảnh báo. Không có video nào → `NO_FINAL`. Video phải đứng yên qua 2 lần quét như hiện tại (`CANDIDATE_STABLE_CHECKS`) mới tải;
   - đếm số video và ảnh Muse hiện ra sau prompt, trả về trong kết quả (`media_count`). Vượt 6 video hoặc 4 ảnh thì thẻ cảnh hiện cảnh báo (không chặn được Muse, chỉ để chủ dự án biết);
   - giờ chờ của việc này dùng `MUSE_AGENT_WAIT_MIN` ở cả runner lẫn bridge (bên gọi chờ và bước dọn việc treo), không dùng `VIDEO_TASK_TIMEOUT_SEC` 20 phút;
   - Muse báo lỗi bằng chữ (đã có `muse_reply_error`), hết giờ hay không có video → thất bại có mã rõ (`NO_FINAL`, `AGENT_TIMEOUT`), không thử lại tự động (mỗi lần thử tốn tới 6 video);
   - nút "Cho phép" giữa chừng: runner hiện đang tự bấm; giữ như vậy.
   - `done_token` riêng cho mỗi việc (`XONG-<task_id>`) để không khớp nhầm chữ của việc khác trong cùng chat.
3. **App nhận kết quả** (`climax_video.py`): kiểm file bằng ffprobe (video hợp lệ, có hình, dài ≥ 5 giây và ≤ 2 × mục tiêu + 1), không kiểm SSIM khung đầu nữa (Muse được phép vẽ lại ảnh cảnh để sửa tóc). Lưu báo cáo của Muse vào trạng thái cảnh, gắn video làm clip của cảnh, hiện báo cáo trên thẻ cảnh. Không đạt kiểm file → cảnh "Video lỗi, giữ ảnh" kèm lý do, như hiện tại.
4. **Giao diện**: nút và trạng thái giữ như nhánh `thu-video-cao-trao` (chọn cảnh, duyệt lưới, chạy); thẻ cảnh thêm ô "Báo cáo của Muse" và nút "Làm lại cảnh này" (tốn thêm tối đa 6 video + 4 ảnh; hỏi xác nhận trước khi bấm).
6. **Ảnh cảnh đã sửa tóc**: bản giao việc dặn: nếu phải vẽ lại ảnh cảnh, tin cuối gửi kèm đúng một ảnh đó (cùng khung với ảnh cảnh), ghi rõ trong báo cáo dòng `ANH_CANH_MOI: có`. Runner tải cả ảnh trong tin cuối. App: có ảnh mới thì chép ảnh cũ sang `images/<scene_id>.truoc_sua_toc.jpg` (không ghi đè nếu đã có bản dự phòng), lưu ảnh mới làm ảnh cảnh (`image_path` giữ nguyên tên file để mọi chỗ đang trỏ vẫn đúng), ghi qua `project_service.save_project()`. Ảnh mới hỏng (không mở được, không phải 16:9) thì giữ ảnh cũ và ghi lý do.
5. **Làm lại, hết giờ**: thất bại hay hết giờ thì đánh dấu chat của cảnh là bẩn (`thread_dirty`), vì Muse có thể vẫn đang làm và gửi kết quả muộn. "Làm lại" mở chat mới trên cùng tài khoản nếu tài khoản đó còn dùng được, gửi lại lưới đã duyệt (file có sẵn trên máy) làm ảnh đính kèm thứ ba; không vẽ lại lưới.

### 3.3 Nhánh code

Nhánh mới từ `master`, lấy lần lượt các commit của `thu-video-cao-trao` **trừ** `3bef9ee` (commit gỡ skill/agent làm bản "không đội" cho thử A/B). Gộp nguyên nhánh sẽ xoá đội agent của dự án.

## 4. Kiểm chứng

- Test offline (Muse giả): bản giao việc có đủ các phần và luật (`tests/test_climax_brief.py`); runner nhận đúng `done_token` ở cuối, bỏ qua token nằm trong chính prompt và bản nháp giữa chừng, lấy video cuối cùng, hết giờ báo `AGENT_TIMEOUT`; quy tắc tóc có trong `prompt_suffix` và thiết kế mặc định của nhân vật nữ, không có ở nhân vật nam; luồng pha 2 với Muse giả trả một video → cảnh "ready", có báo cáo.
- `tools/check.py --full` đạt.
- Giao diện: server thử 8010, dự án thử ảnh giả, Muse giả; bấm đúng các phần tử ghi trong `FEATURE_MAP.md`.
- Chạy thật: cảnh 28 và cảnh 41 của bản sao Trạm Dung (`proj_crime_thucaotrao`; cảnh 41 nhiều nhân vật, hôm 28/10 vẽ lỗi nhất). Tối đa 2 × (6 video + 4 ảnh). Xem từng giây bằng mắt; chủ dự án xem video.

## 5. Chi phí ước tính

- Mỗi cảnh cao trào: một yêu cầu Muse, thí nghiệm dùng 4–5 video + 1–2 ảnh, 10–21 phút. Tối đa 50% số cảnh là video (đã chốt) → dự án 78 cảnh có thể tới ~39 yêu cầu; nên chạy từ từ trên nhiều tài khoản video.
- Code: khoảng 1 ngày làm của agent (bản giao việc, kiểu việc mới ở runner, pha 2, giao diện nhỏ, test).

## 6. Phần agent tự quyết (chủ dự án xem lại)

- Câu chữ của `FEMALE_HAIR_RULE_EN` (mục 3.1).
- Mục tiêu tối đa 24 giây mỗi cảnh; phần lời kể dư giữ khung cuối.
- Bỏ kiểm SSIM khung đầu và chỉnh màu từng khung ở pha clip.
- Không tự thử lại khi một yêu cầu thất bại; chủ dự án bấm "Làm lại".
- Chờ tối đa 45 phút mỗi yêu cầu.
- Nhánh mới lấy từng commit, bỏ `3bef9ee`.
- Quy tắc tóc ghép lúc dựng prompt, thắng thiết kế đã lưu (mục 3.1).
- Muse tự chia đoạn; chạy thật cảnh 28 và 41 để kiểm (mục 3.2).
- Chọn video trong tin cuối, đếm media chỉ để cảnh báo, chat bẩn khi lỗi, làm lại ở chat mới (mục 3.2).

## 7. Cần chủ dự án quyết

1. ~~Quy tắc tóc có đúng ý không?~~ Đã trả lời — **[Nguyên văn chủ dự án]** (28/10/2026): "Ý tôi là khi làm tóc cho nữa thì nên là phủ nhiều trên đầu thay vì chỉ có chút tóc ở phần gáy thôi, như vậy nhìn sẽ rất xấu." Câu quy tắc ở mục 3.1 đã sửa theo ý này.
2. ~~Áp cho phong cách nào?~~ **[Nguyên văn chủ dự án]** (28/10/2026): "Câu 2: chỉ áp cho phong cách đầu tròn."
3. ~~Thay ảnh tĩnh bằng ảnh Muse đã sửa tóc?~~ **[Nguyên văn chủ dự án]** (28/10/2026): "Câu 3: có, tải ảnh Muse đã sửa tóc về thay ảnh tĩnh, giữ ảnh cũ làm bản dự phòng." Cách làm: mục 3.2 bước 6.

Chủ dự án duyệt bản thiết kế ngày 28/10/2026 ("Viết kế hoạch code").
