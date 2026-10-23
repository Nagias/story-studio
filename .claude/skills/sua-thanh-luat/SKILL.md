---
name: sua-thanh-luat
description: Dùng mỗi khi phát hiện một lỗi trong Story Studio - do chủ dự án báo, do kiểm chứng phát hiện, do giám khảo chỉ ra, hay do agent tự vi phạm quy tắc. Sửa lỗi trước mắt, tìm nguyên nhân gốc, ghi số lần vi phạm, lặp từ 3 lần thì đề xuất khoá cứng.
---

# Sửa lỗi thành luật

Nguồn: skill sua-thanh-luat của bộ mẫu, chỉnh theo quy tắc khoá cứng/khoá mềm của chủ dự án (CLAUDE.md mục 2.4, 5.1, 6.1).

1. **Cầm máu:** sửa lỗi trước mắt nếu đang gây hại; ghi chính xác hiện tượng (lệnh, đầu vào, kết quả sai).
2. **Nguyên nhân gốc:** điều gì trong code, quy trình, bản đồ hay luật đã để lỗi xảy ra được. "Sơ suất" không phải nguyên nhân gốc. Hỏi "vì sao" tới khi gặp điều kiện có thể chặn bằng luật.
3. **Sổ lỗi là bảng 5.1 (đường cấm) và 6.1 (quy tắc làm việc) trong CLAUDE.md:**
   - lỗi thuộc một dòng đã có: tăng cột "Số lần vi phạm đã ghi nhận", thêm bằng chứng (commit, file);
   - lỗi kiểu mới: đề xuất dòng mới, chờ chủ dự án duyệt (mục 2.2: luật là quyết định của chủ dự án).
4. **Chọn tầng luật theo mục 2.4:**
   - dòng "mềm" có số lần vi phạm từ 3 trở lên thì bắt buộc làm khoá cứng: test trong `tests/` hoặc bước trong `tools/check.py`/hook git, kèm ngoại lệ đếm đúng số chỗ cũ (chỉ cho giảm); `tests/test_guardrail_policy.py` sẽ báo lỗi nếu để mềm;
   - dưới 3 lần: thêm bước kiểm vào skill liên quan hoặc ghi rõ trong CLAUDE.md.
5. **Thử phá khoá mới đúng 1 lần:** cố ý tạo vi phạm, chứng minh khoá chặn, rồi hoàn lại. Không cần thử phá lặp lại.
6. **Rà chỗ tương tự** đã có trong code xem có dính cùng lỗi không; báo danh sách cho chủ dự án, không tự sửa ngoài phạm vi.
