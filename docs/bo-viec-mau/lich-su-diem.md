# Lịch sử điểm bộ việc mẫu

Mỗi dòng là một lần đo, ghi bằng `.venv\Scripts\python.exe tools\bo_viec_mau.py cham --lan <lần> --ghi-lich-su`. Cột T1–T7 là điểm (T6, T7 là việc khó, thêm 29/10/2026; lần đo trước đó ghi —) trên 10 của từng việc. Cách đo và thang điểm: `README.md`.

| Ngày | Lần chạy | Agent/skill đang đo | T1 | T2 | T3 | T4 | T5 | T6 | T7 | Tổng |
|---|---|---|---|---|---|---|---|---|---|---|
| 23/10/2026 | 2026-10-23-goc | general-purpose (Opus 5.5), chưa cài skill của thư mục mẫu | 10 | 10 | 10 | 10 | 10 | — | — | 50 / 50 |
| 24/10/2026 | 2026-10-23-skill-tu-nap | general-purpose (Opus 5.5) + 9 skill dự án tự nạp + agent giam-khao (Sonnet) | 10 | 10 | 10 | 10 | 10 | — | — | 50 / 50 |

Ghi chú lần `2026-10-23-skill-tu-nap`: lần chấm đầu T3 được 8,33 (tổng 48,33) vì chấm oan. Hai `showToast()` dùng `errText` đã lọc bằng `escapeHtml()` ngay lúc gán (code gốc đã vậy); bài làm giữ nguyên, còn đáp án lọc thêm lần nữa (`&` hiện thành `&amp;`), và test `test_toasts_escape_untrusted_text` chỉ nhìn dòng `showToast()`. Chủ dự án duyệt sửa (24/10/2026): test đó vào `bo_cham`, thay bằng test bổ sung nhận cả cách lọc lúc gán; lập lại đáp án T3 tự kiểm ĐẠT; chấm lại T3 được 10. Bài T3 của lần gốc cũng qua bộ quét mới (0 chỗ chưa lọc), nên điểm lần gốc giữ nguyên.
