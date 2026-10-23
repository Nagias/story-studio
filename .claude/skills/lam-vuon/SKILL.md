---
name: lam-vuon
description: Dùng khi chủ dự án yêu cầu rà soát chất lượng Story Studio, hoặc khi cùng một mẫu xấu hay một loại lỗi xuất hiện từ 3 lần trở lên. Gọi agent ra-soat (chỉ đọc) quét chỗ lệch giữa các phiên AI, code chết, tài liệu lệch code; cầm máu trước, dọn sau, không tự dọn.
---

# Làm vườn: rà soát nợ và chỗ lệch

Nguồn: skill lam-vuon của bộ mẫu, thay phần quét bằng cách làm của expert Codebase Archaeologist (nằm trong agent `ra-soat`).

1. **Chốt phạm vi rà soát** theo lời chủ dự án (cả dự án, một vùng, hay một loại lỗi đang lặp).
2. **Gọi agent `ra-soat`** (công cụ Agent, `subagent_type: ra-soat`), đưa phạm vi và lý do rà. Không gọi được thì dùng `general-purpose` và đưa nguyên nội dung `.claude/agents/ra-soat.md` làm lời dặn.
3. **Kiểm lại phát hiện "Nghiêm trọng"** trước khi báo: tự mở file, tái hiện nếu được. Phát hiện chưa chắc thì ghi "chưa chắc", không tô màu.
4. **Đề xuất tối đa 3 mục ưu tiên** kèm lý do. Không tự dọn khi chưa được duyệt; dọn được duyệt thì làm như một việc mới (skill giao-viec).
5. **Cầm máu bằng luật:** loại lỗi đã lặp từ 3 lần thì đề xuất khoá cứng theo CLAUDE.md mục 2.4 (skill sua-thanh-luat).
