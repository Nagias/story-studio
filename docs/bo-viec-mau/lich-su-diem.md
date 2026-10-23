# Lịch sử điểm bộ việc mẫu

Mỗi dòng là một lần đo, ghi bằng `.venv\Scripts\python.exe tools\bo_viec_mau.py cham --lan <lần> --ghi-lich-su`. Cột T1–T5 là điểm trên 10 của từng việc. Cách đo và thang điểm: `README.md`.

| Ngày | Lần chạy | Agent/skill đang đo | T1 | T2 | T3 | T4 | T5 | Tổng |
|---|---|---|---|---|---|---|---|---|
| 23/10/2026 | 2026-10-23-goc | general-purpose (Opus 5.5), chưa cài skill của thư mục mẫu | 10 | 10 | 10 | 10 | 10 | 50 / 50 |
| 24/10/2026 | 2026-10-23-skill-tu-nap | general-purpose (Opus 5.5) + 9 skill dự án tự nạp + agent giam-khao (Sonnet) | 10 | 10 | 8.33 | 10 | 10 | 48.33 / 50 |

Ghi chú lần `2026-10-23-skill-tu-nap`: T3 mất 1 test ẩn (`test_toasts_escape_untrusted_text`) là chấm oan. Hai `showToast()` dùng `errText` đã lọc bằng `escapeHtml()` ngay lúc gán (code gốc đã vậy); bài làm giữ nguyên, còn đáp án lọc thêm lần nữa (lọc hai lần, `&` hiện thành `&amp;`). Test ẩn chỉ nhìn tại dòng `showToast()` nên báo hỏng. Không tính chấm oan thì T3 được 10, tổng 50/50. Máy chấm chưa sửa (chờ chủ dự án).
