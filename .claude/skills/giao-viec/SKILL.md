---
name: giao-viec
description: Dùng mỗi khi chủ dự án giao một việc mới trong Story Studio (sửa lỗi, tính năng, giao diện, pipeline LLM, Muse, giọng đọc, dựng video, tài liệu). Bao trọn vòng đời việc - chốt phạm vi, đọc luật, lập kế hoạch, làm từng bước có kiểm chứng, tự soát phạm vi, mời giám khảo, báo cáo.
---

# Giao việc

Nguồn: skill giao-viec của bộ mẫu, ghép kỷ luật phạm vi của expert Minimal Change Engineer và cách lập kế hoạch việc lớn của Master Plan Architect.

## 1. Chốt phạm vi trước khi làm
- Đọc yêu cầu theo đúng chữ. Nhắc lại phạm vi bằng một câu ở đầu tin nhắn đầu tiên (làm gì, ở đâu, thế nào là xong).
- Chủ dự án dặn (23/10/2026): "Lần sau tôi yêu cầu gì thì chỉ làm đến hết là được, không được làm sai". Việc ngoài phạm vi chỉ ghi thành đề xuất ở cuối báo cáo, không tự làm.
- Yêu cầu có hai cách hiểu mà hai cách dẫn tới kết quả khác hẳn: chọn cách hẹp, nói rõ đã chọn cách nào. Chỉ hỏi lại khi không thể đi tiếp.

## 2. Đọc luật và bản đồ
- `CLAUDE.md` (mục 5 đường cấm, mục 6 quy tắc làm việc) và `FEATURE_MAP.md` trước mọi việc. Cấm đoán đường: tính năng nằm đâu, bấm gì, cần dữ liệu gì phải tra bản đồ.
- Mỗi việc một nhánh mới từ `master`, tên tiếng Việt không dấu. Không commit lên `master`; chỉ gộp khi chủ dự án đồng ý.

## 3. Lập kế hoạch
- Chia thành bước nhỏ; mỗi bước ghi tiêu chí "đạt" và cách kiểm chứng (skill kiem-chung).
- Việc dài: ghi checklist vào `TASKS.md`, tick khi xong.
- Việc lớn (đổi kiến trúc mục 4, xin ngoại lệ đường cấm, đổi schema dữ liệu, nhiều phần, hoặc có bước không đảo ngược được): trình chủ dự án duyệt kế hoạch trước, gồm
  - danh sách file sẽ đổi, mỗi file ghi [MỚI] / [SỬA] / [XOÁ] kèm lý do một dòng;
  - ít nhất 3 rủi ro (giả định dễ sai, chỗ khác có thể hỏng theo, việc cố ý không làm lần này);
  - cách kiểm chứng và cách quay lại nếu hỏng.
- Mức tự chủ (làm luôn, không hỏi): mọi việc trong phạm vi được giao, chạy test, commit trên nhánh. Phải hỏi trước: gộp vào `master`, xoá dữ liệu (chỉ chuyển vào Thùng rác), sửa file ngoài thư mục dự án, gọi dịch vụ tốn quota ngoài mức việc cần, việc không đảo ngược được.

## 4. Làm từng bước
- Diff nhỏ nhất giải được việc: mỗi dòng đổi phải trả lời được "việc này cần đúng dòng này". Không tiện tay dọn, đổi tên, làm "cho linh hoạt sau này" hay thêm lớp trừu tượng; ba dòng giống nhau tốt hơn một hàm dùng chung làm sớm.
- Không cắt validation, xử lý lỗi hay bảo mật để code ngắn hơn (đường cấm 2, 3 của dự án).
- Xong bước nào kiểm chứng bước đó (skill kiem-chung), ghi bằng chứng.
- Bước không đạt sau 2 lần sửa: ghi nguyên nhân, làm tiếp các bước không phụ thuộc; không im lặng bỏ qua.
- Gặp lỗi mới (của mình hay có sẵn): skill sua-thanh-luat. Đụng tính năng hay giao diện: skill duy-tri-feature-map.

## 5. Tự soát phạm vi trước khi báo
- Xem lại toàn bộ diff (`git diff master...HEAD` và phần chưa commit): dòng nào việc không đòi thì bỏ.
- Liệt kê những gì đã thấy mà cố ý không làm (đưa vào mục đề xuất).

## 6. Giám khảo trước khi báo "xong"
- Thay đổi có đụng code: dùng skill cham-cheo (gọi agent `giam-khao`). Chưa đạt thì sửa, tối đa 3 vòng.
- Chỉ đổi tài liệu hoặc trả lời câu hỏi: không cần giám khảo.

## 7. Báo cáo (tiếng Việt đời thường, kết luận trước)
1. ĐÃ XONG: làm gì, để được gì; bằng chứng bằng số (lệnh đã chạy, bao nhiêu đạt/lỗi, thời gian).
2. KẾT QUẢ GIÁM KHẢO: đạt hay chưa, điểm yếu còn lại.
3. CHƯA KIỂM CHỨNG: phần nào, vì sao.
4. CẦN CHỦ DỰ ÁN QUYẾT: kèm phương án đề xuất; việc ngoài phạm vi đã thấy, ghi là đề xuất.
