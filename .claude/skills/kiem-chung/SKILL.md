---
name: kiem-chung
description: BẮT BUỘC dùng trước khi nói bất kỳ việc gì trong Story Studio là "đã xong", "đã sửa", "đã chạy được"; cũng dùng khi tái hiện hay xác nhận một lỗi. Cổng kiểm chứng chung - mọi việc tạo ra thay đổi đều phải qua đây trước khi báo cáo.
---

# Kiểm chứng bằng bằng chứng

Nguồn: skill kiem-chung của bộ mẫu, chỉnh theo CLAUDE.md mục 6 ("Bằng chứng tối thiểu").

1. **Tiêu chí "đạt"** lấy từ yêu cầu của chủ dự án và CLAUDE.md. Chưa có tiêu chí thì đề xuất và nói rõ là đề xuất; cấm tự đặt tiêu chí rồi tự khen đạt.
2. **Tra `FEATURE_MAP.md`** trước khi tái hiện hay kiểm một tính năng: phần tử nào, API nào, điều kiện ban đầu nào. Cấm đoán đường.
3. **Chạy thật theo loại thay đổi:**

   | Thay đổi | Bằng chứng tối thiểu |
   |---|---|
   | Mọi thay đổi code | test liên quan + `.venv\Scripts\python.exe tools\check.py --full`, ghi số đạt/lỗi và thời gian |
   | Giao diện | server thử cổng 8010 (`.claude/launch.json`), bấm đúng phần tử ghi trong FEATURE_MAP, xem console và log server; không khởi động lại server 8000 |
   | Giọng, ảnh, video | mở hoặc nghe file thật, không chỉ nhìn mã thoát hay dung lượng |
   | Pipeline LLM | test với LLM giả (`tests/case_adaptation_fakes.py`); gọi 9router thật chỉ khi cần và ghi số lần gọi, thời gian |
   | Chạy thử ngoài bộ test | so danh sách `projects/` trước và sau, không để dự án rác |

4. **Thử ngược khi sửa lỗi:** test mới phải hỏng trên code cũ và đạt trên code mới; nếu không thì test chưa bắt được lỗi.
5. **Đối chiếu từng tiêu chí với bằng chứng:** đạt mục nào (bằng chứng đâu), chưa đạt mục nào, mục nào không kiểm được bằng công cụ (và vì sao).
6. **Kết luận chỉ có hai dạng:** ĐẠT (kèm bằng chứng) hoặc CHƯA ĐẠT (kèm mục chưa đạt và việc cần làm). Không có "chắc là đạt". Phần không kiểm được thì ghi "chưa kiểm chứng".
7. Ghi kết quả vào `TASKS.md` khi việc có checklist ở đó.
