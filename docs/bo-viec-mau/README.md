# Bộ việc mẫu chuẩn

Bộ này đo chất lượng agent và skill bằng 7 việc thật của dự án (5 việc thường, 2 việc khó), cho ra điểm số so được trước/sau mỗi lần thay đổi.

**[Nguyên văn chủ dự án]** (23/10/2026)

> Từ nay, mỗi lần sửa skill hoặc agent, phải chạy lại bộ việc mẫu này và báo cáo điểm trước/sau.

Cách hiểu "sửa skill hoặc agent" — **[Đề xuất của agent — chưa duyệt]**:
- thêm, bớt hay sửa file skill hoặc file agent mà dự án dùng;
- đổi agent nào làm loại việc nào (bảng định tuyến, CLAUDE.md mục 7).

## 1. Các việc mẫu

Mỗi việc là một lần sửa lỗi có thật trong lịch sử git, có test kèm theo. Người làm bài nhận mã nguồn ngay trước lần sửa. Đáp án là lần sửa thật đó.

| Mã | Việc | Loại việc | Lần sửa thật (mã gốc) | Test ẩn | Test cũ phải giữ |
|---|---|---|---|---|---|
| T1 | Ảnh Muse của `proj_ab` bị gắn link sang `proj_a` | Sửa lỗi bảo mật, kiểm đầu vào (Muse) | `c639f93` (gốc `d33d9df`) | 3 | 687 |
| T2 | `get_audio_duration()` đoán 3 giây khi không đo được | Giọng đọc, xử lý lỗi, "thành công giả" | `1f059f7` + `44521ea` (gốc `ff8114d`) | 2 | 686 |
| T3 | Lọc chữ từ máy chủ trong thông báo và thư viện ảnh Muse | Sửa giao diện JS, chống chèn HTML | `d33d9df` (gốc `ccf87db`) | 3 | 685 |
| T4 | Ngày tháng thật lọt vào tên tập và nhãn bằng chứng | Pipeline LLM true-crime, kiểm lọt thông tin thật | `8224dfb` (gốc: `c786fd9` bỏ riêng lần sửa này) | 2 | 755 |
| T5 | Thumbnail lấy nhầm thẻ chữ làm nền, vệt sáng góc trái dưới | Ảnh (Pillow), duy trì `FEATURE_MAP.md` | `c786fd9`, phần thumbnail (gốc `5629971`) | 2 | 756 |
| T6 (khó) | Muse làm xong video cao trào mà app báo lỗi tải, rồi tự giao lại nên Muse làm lần hai | Muse / Fleet Runner, lỗi ở 2 file | `5e72941` (gốc `487cc60`) | xem `T6/dap-an.json` | xem `T6/dap-an.json` |
| T7 (khó) | Video thành phẩm nhỏ tiếng, có nhạc nền thì giọng càng nhỏ | Dựng video (ffmpeg), đo độ to thật | `70fa508` (gốc `fae2d62`) | xem `T7/dap-an.json` | xem `T7/dap-an.json` |

Vì sao chọn 5 việc đầu (T1–T5):
- **Đại diện loại việc hay gặp.** Trong 106 commit (23/10/2026), pipeline LLM true-crime chiếm nhiều nhất (khoảng 28 commit), nên có T4. Các việc còn lại đại diện giao diện (T3), Muse (T1), giọng đọc (T2), ảnh và tài liệu (T5).
- **Đều là lỗi thật đã sửa và có test.** Cỡ mỗi lần sửa từ 15 đến 70 dòng, nên mỗi lần đo không mất cả ngày.

Việc khó (T6, T7, thêm 29/10/2026 theo CLAUDE.md mục 1.2 câu 13: "cứ thêm việc khó và đo liên tục để tối ưu"): đề chỉ tả triệu chứng chủ dự án thấy khi chạy thật, không chỉ file hay hàm sai; người làm bài phải tự tìm nguyên nhân, tái hiện bằng test rồi mới sửa. Phạm vi được sửa rộng (cả `backend/` hay `backend/services/`) để không lộ chỗ sai. Ứng viên bị loại: `6fadad9` (video cao trào) vì test của lần sửa thật bám vào tên tham số và đúng số ký tự, bài làm đúng cách khác sẽ bị chấm oan.

Đề bài từng việc: `T1/de-bai.md` … `T7/de-bai.md`, ghép sau `loi-dan-chung.md`. Tham số máy đọc: `viec.json`.

Về cột "Test ẩn":
- Gồm test của lần sửa thật cộng test bổ sung (`T*/test_an_*.py`). Test bổ sung được viết cho những yêu cầu trong đề mà lần sửa thật không có test.
- Mọi test ẩn đều đã chạy thử: hỏng ở bản gốc, đạt ở đáp án (mục 4). Riêng vài test bổ sung chỉ chặn tụt chất lượng (ví dụ `T7/test_an_t7_dinh_am_va_giong.py`: đỉnh âm, đủ hình tiếng, đúng độ dài) đạt cả ở bản gốc nên vào danh sách test cũ phải giữ (p2p), không phải test ẩn.

## 2. Thang điểm: 10 điểm mỗi việc (7 việc: 70 điểm cả bộ)

| Phần | Điểm | Cách chấm |
|---|---|---|
| A. Đúng yêu cầu | 5 | 5 × tỉ lệ test ẩn đạt |
| B. Không làm hỏng chỗ khác | 2 | Cả bộ test mặc định: không test cũ nào hỏng thì 2, hỏng 1 thì 1, hỏng từ 2 thì 0 |
| C. Đúng phạm vi | 1 | Chỉ sửa file đề bài cho phép, sửa đủ file bắt buộc |
| D. Cổng kiểm của dự án | 1 | `tools/check.py` chạy trong bài làm đạt, và không nâng ngoại lệ khoá cứng hay mốc Ruff |
| E. Báo cáo trung thực | 1 | Giám khảo độc lập chấm theo `giam-khao.md`: 0, 0,5 hoặc 1 |

B, C, D chỉ tính khi A > 0: bài không làm được gì thì không ăn điểm phụ. Khi chấm, mã của bài làm được ghép với thư mục `tests/` của đáp án. Vì vậy người làm bài không lách được bằng cách sửa hay xoá test.

## 3. Chạy một lần đo

Mọi lệnh chạy ở gốc dự án, bằng `.venv\Scripts\python.exe`.

1. **Chuẩn bị**: `.venv\Scripts\python.exe tools\bo_viec_mau.py chuan-bi --lan 2026-10-23-goc --mo-ta "general-purpose (Opus), chưa cài skill"`.
   - Mỗi việc có một thư mục làm bài trong `.cache\bo-viec-mau\<lần>\<việc>\`. Đó là mã nguồn trước lần sửa, có git riêng không kèm lịch sử, `.env` rỗng, `.venv` nối về dự án.
   - Đề bài đầy đủ nằm ở `<việc>-de-bai.md`.
2. **Giao việc**: với từng việc, mở agent cần đo (công cụ Agent, `subagent_type` của agent đó; skill cần đo phải đang được cài) và đưa nguyên nội dung `<việc>-de-bai.md`.
   - Làm lần lượt từng việc: chạy song song thì máy chậm, test hay chập chờn.
3. **Lưu báo cáo**: chép nguyên văn câu trả lời cuối của agent vào `<việc>-bao-cao.md`.
4. **Máy chấm**: `.venv\Scripts\python.exe tools\bo_viec_mau.py cham --lan <lần>`.
   - Mỗi việc mất khoảng 5–10 phút, vì chạy cả bộ test.
   - Kết quả chi tiết ở `<việc>-may-cham.json`: test nào hỏng, file nào ngoài phạm vi, nhật ký cổng kiểm.
5. **Giám khảo**: mỗi việc mở một agent khác model với người làm bài. Đưa cho nó `docs/bo-viec-mau/giam-khao.md` và `<việc>-ho-so-giam-khao.md`, rồi lưu JSON nó trả về vào `<việc>-giam-khao.json`.
6. **Gộp điểm, ghi lịch sử**: `tools\bo_viec_mau.py cham --lan <lần> --ghi-lich-su` thêm một dòng vào `lich-su-diem.md`.
7. **Báo cáo trước/sau**: `tools\bo_viec_mau.py so-sanh <lần trước> <lần sau>` in bảng điểm từng việc. Báo cáo gửi chủ dự án gồm:
   - đã sửa skill/agent gì;
   - bảng trước/sau;
   - việc nào tụt điểm, vì sao (đọc `<việc>-may-cham.json` và lý do của giám khảo).

## 4. Đáp án và tự kiểm máy chấm

`T*/dap-an.json` gồm các danh sách sau:

| Danh sách | Nghĩa |
|---|---|
| `f2p` | test ẩn: hỏng ở bản gốc, đạt ở đáp án |
| `p2p` | test cũ phải giữ: đạt ở cả hai |
| `khong_on_dinh` | test chập chờn, không chấm |
| `hong_ca_hai_hoac_bo_qua` | test hỏng sẵn hoặc bị bỏ qua trên máy này, không chấm. Ví dụ T1, T3: vài test đã hỏng sẵn trong lịch sử thật, được sửa ở commit sau |

Lập bằng `tools\bo_viec_mau.py tinh-dap-an` (khoảng 25 phút mỗi việc):
- Lệnh chạy cả bộ test trên bản gốc 1 lần và trên đáp án 2 lần (để loại test chập chờn).
- Sau đó lệnh tự kiểm máy chấm: bản gốc phải được 0 điểm, đáp án phải được đủ 9 điểm máy (A–D). Không đúng thì báo CHƯA ĐẠT.

Chạy lại lệnh này khi thêm hay sửa việc mẫu, đổi test bổ sung, hoặc nâng Python và thư viện.

## 5. Giới hạn cần biết

- **Bộ việc từng chạm trần (đến 29/10/2026).** Lần đo điểm gốc 23/10/2026 (`lich-su-diem.md`), agent `general-purpose` (Opus 5.5) chưa cài skill được 50/50. Vì vậy bộ hiện chỉ bắt được khi một thay đổi làm tụt điểm; chưa đo được thay đổi có làm tốt hơn hay không. Nguyên nhân: đề ghi rất rõ kết quả mong đợi, đúng yêu cầu "có đáp án rõ ràng", nên đề cũng dễ. Muốn đo được tiến bộ thì cần thêm việc khó hơn: đã thêm T6, T7 (mục 1); điểm của chúng ở `lich-su-diem.md`.
- **Chi phí một lần đo** (số đo lần điểm gốc):
  - người làm bài: khoảng 1,2 triệu token, 11–18 phút mỗi việc, tổng khoảng 75 phút;
  - giám khảo: khoảng 0,6 triệu token, dưới 1 phút mỗi việc;
  - máy chấm: khoảng 2,5–3 phút mỗi việc.
- **Số việc còn ít (7 việc; 23/10/2026 chủ dự án chọn 3–5, 29/10/2026 cho thêm việc khó).** Chênh từ 1 điểm trở xuống ở một việc có thể chỉ là dao động giữa hai lần chạy. Muốn chắc thì đo mỗi bên 2 lần. Chuyên gia "Multi-Agent Systems Architect" khuyên từ 20 ca trở lên; chủ dự án chọn 3–5 việc để mỗi lần đo không quá lâu.
- **Người làm bài vẫn đọc được đáp án nếu cố tình.** Thư mục dự án thật và lịch sử git của nó (có đáp án) vẫn mở. Lời dặn chung cấm đọc ra ngoài thư mục làm bài, nhưng máy không chặn được, giám khảo cũng không thấy được. Đã gặp ở lần đo điểm gốc: agent làm T3 tự khai đã lỡ đọc `CLAUDE.md` của dự án thật.
- **Bài làm đúng theo cách khác có thể bị chấm oan.** Test ẩn viết theo lần sửa thật, nên bài làm đúng theo cách khác hẳn có thể mất điểm ở A hoặc B. Điểm tụt thì đọc test nào hỏng trước khi kết luận. Lần đo điểm gốc đã gặp và sửa 2 lần chấm oan:
  - T1: bản chấm thiếu file test mới mà bài làm đã ghi vào `FEATURE_MAP.md`;
  - T3: test ẩn chưa nhận `encodeURIComponent` là cách lọc.

  Lần đo `2026-10-23-skill-tu-nap` gặp thêm 1 lần ở T3: bộ quét thông báo của lần sửa thật (`test_architecture.py::test_toasts_escape_untrusted_text`) chỉ nhìn dòng `showToast()`, nên không nhận biến đã lọc ngay lúc gán (`const errText = escapeHtml(...)`). Test này được ghi vào `bo_cham` trong `viec.json` (không chấm), thay bằng test bổ sung `test_thong_bao_loc_chu_tu_loi_may_chu_va_nguoi_dung` nhận cả cách lọc lúc gán. Test của lần sửa thật mà chấm oan thì làm như vậy: không sửa được lịch sử git, nên bỏ chấm có ghi lý do và thay bằng test bổ sung.
- **Thiếu hai loại việc:**
  - "tính năng mới lớn": mỗi lần đo sẽ mất hàng giờ;
  - việc chỉ kiểm được bằng mắt hay tai: giao diện thật, giọng thật.
- **Chỉ chạy trên máy Windows này.** Cần font Segoe UI hoặc Arial Bold, ffmpeg, Node.js và `.venv` của dự án.
- **Phần E do AI chấm, có thể lệch.** Luôn đọc lý do trong `<việc>-giam-khao.json`.

## 6. Dọn dẹp

Công cụ không xoá gì. Mỗi lần đo để lại thư mục `.cache\bo-viec-mau\<lần>\` (git bỏ qua). Ghi điểm xong có thể chuyển thư mục cũ vào Thùng rác.
