---
name: loop-toi-chuan
description: Dùng khi một đầu ra trong Story Studio chưa đạt tiêu chí chất lượng, khi chủ dự án đòi chất lượng cao cho một sản phẩm cụ thể, hoặc khi viết/sửa prompt LLM (chia cảnh, phân tích vụ án, viết lời, bản tiếng Anh, gói SEO). Vòng làm - chấm theo thang - sửa phần dưới chuẩn, tối đa 3 vòng.
---

# Lặp tới chuẩn

Nguồn: skill loop-toi-chuan của bộ mẫu; phần prompt LLM lấy ý từ expert Prompt Engineer.

## Vòng lặp chung
1. Chốt thang chấm trước khi lặp (từ yêu cầu, CLAUDE.md, hoặc đề xuất cho chủ dự án duyệt). Chưa có thang thì chưa lặp.
2. Vòng 1: làm bản đầu, chấm từng tiêu chí, ghi điểm và lý do.
3. Vòng sau: chỉ sửa tiêu chí dưới ngưỡng (mặc định 8/10), rồi chấm lại toàn bộ.
4. Dừng khi mọi tiêu chí đạt ngưỡng (nộp kèm bảng điểm từng vòng), hoặc sau 3 vòng (báo tiêu chí chưa đạt, nguyên nhân nghi ngờ, 2 phương án). Cấm nộp bản dưới chuẩn mà không nói.

## Khi sửa prompt LLM
1. Viết rõ trước: định dạng đầu ra (JSON gì, trường nào) và tiêu chí đạt (ví dụ "không lọt tên thật", "đủ số cảnh của dàn ý"). Không dùng chữ mơ hồ kiểu "ngắn gọn" mà không nói ngắn là bao nhiêu.
2. Mỗi thay đổi prompt có ít nhất 3 ca thử: bình thường, biên, hỏng (LLM trả sai định dạng, bỏ sót). Ca thử chạy offline bằng LLM giả (`tests/case_adaptation_fakes.py`).
3. Sửa một chỗ mỗi lần rồi chạy lại toàn bộ ca thử; sửa nhiều chỗ một lúc thì không biết chỗ nào có tác dụng.
4. 9router hay lười, hay tóm tắt: việc lớn chia thành nhiều bước nhỏ có kiểm, chạy lần lượt (mẫu `services/case_adaptation_steps.py`). Gọi LLM qua `services/case_adaptation_llm.py`, không viết client mới (đường cấm 5).
5. Thử với 9router thật chỉ khi cần: ghi số lần gọi, thời gian, model; không chạy lặp vô ích (quota).
