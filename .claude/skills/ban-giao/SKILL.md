---
name: ban-giao
description: Dùng khi kết thúc một phiên làm việc dài trong Story Studio, khi phiên sắp bị ngắt, hoặc trước khi dừng một chuỗi việc chưa xong. Ghi trạng thái vào TASKS.md để một agent mới đọc vào là làm tiếp được ngay.
---

# Bàn giao đóng ca

Nguồn: skill ban-giao của bộ mẫu; file trạng thái của dự án là `TASKS.md`.

1. **Cập nhật `TASKS.md`** ở mục của việc đang làm:
   - việc nào xong (tick, kèm bằng chứng bằng số);
   - việc nào dở: đang ở bước nào, nhánh nào, commit nào, bước tiếp theo là gì;
   - việc nào kẹt và kẹt vì sao.
   Quyết định mới của chủ dự án thì ghi nguyên văn vào `CLAUDE.md` đúng mục (mục 2.2: không tự viết lại ý). Lỗi mới thì theo skill sua-thanh-luat.
2. **Kiểm cuối:** không còn việc "đã hứa mà chưa ghi". Mọi cam kết phải nằm trong `TASKS.md` hoặc `CLAUDE.md`, không chỉ nằm trong cuộc trò chuyện. Nhánh nào chưa gộp thì ghi tên nhánh.
3. **Báo cáo bàn giao tối đa 10 dòng**, 4 mục: ĐÃ XONG (bằng chứng) — ĐANG DỞ và bước tiếp — KẸT, CẦN CHỦ DỰ ÁN QUYẾT (mỗi mục kèm 2 phương án) — RỦI RO hoặc lỗi mới phát hiện.
