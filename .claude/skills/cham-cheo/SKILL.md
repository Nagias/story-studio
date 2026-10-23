---
name: cham-cheo
description: Dùng trước khi báo "xong" một thay đổi có đụng code trong Story Studio, hoặc trước khi đề nghị gộp nhánh vào master. Gọi agent giam-khao (khác model, chỉ đọc) chấm độc lập để tránh tự chấm thiên vị; chưa đạt thì sửa, tối đa 3 vòng.
---

# Chấm chéo độc lập

Nguồn: skill cham-cheo và loop-toi-chuan của bộ mẫu; danh sách kiểm lấy ý từ expert Code Reviewer, nằm trong agent `giam-khao`.

1. **Gom hồ sơ cho giám khảo** (giám khảo không thấy cuộc trò chuyện, chỉ thấy những gì được đưa):
   - yêu cầu gốc của chủ dự án, nguyên văn;
   - thư mục repo, tên nhánh, lệnh xem diff (`git diff master...HEAD` và phần chưa commit);
   - bằng chứng đã có: lệnh đã chạy và kết quả bằng số;
   - phần tự nhận là chưa kiểm chứng.
2. **Gọi agent `giam-khao`** (công cụ Agent, `subagent_type: giam-khao`). Không gọi được thì dùng agent `general-purpose` model khác (`sonnet`) và đưa nguyên nội dung file `.claude/agents/giam-khao.md` làm lời dặn.
3. **Đọc kết luận:**
   - ĐẠT: ghi tóm tắt vào báo cáo, mục "Kết quả giám khảo".
   - CHƯA ĐẠT: sửa đúng các điểm "chặn", kiểm chứng lại (skill kiem-chung), gọi giám khảo vòng mới với hồ sơ mới. Tối đa 3 vòng.
   - Sau 3 vòng vẫn chưa đạt: dừng, báo chủ dự án điểm còn lại, nguyên nhân nghi ngờ, 2 phương án.
4. **Người làm không tự sửa kết luận của giám khảo.** Không đồng ý một điểm: ghi bất đồng kèm bằng chứng phản biện để chủ dự án phán.
