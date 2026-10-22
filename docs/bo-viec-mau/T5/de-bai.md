# Việc: thumbnail lấy nhầm thẻ chữ làm nền, có vệt sáng ở góc trái dưới

Xem ảnh thumbnail thật (Bước 4, `generate_youtube_thumbnail()` trong `backend/services/thumbnail_service.py`) thấy hai lỗi:

- Nền thumbnail lấy ảnh của cảnh đầu tiên. Nhưng cảnh đầu của video vụ án thường là thẻ miễn trừ trách nhiệm (ảnh chữ do app vẽ); bảng ghim cũng là ảnh chữ. Thumbnail thành chữ chồng lên chữ.
- Góc trái phía dưới có một vệt sáng: lớp làm tối bên trái bị mất ở dải phía dưới.

Kết quả mong đợi:

1. Người dùng không chọn cảnh thì nền là ảnh của cảnh đầu tiên không phải ảnh chữ.
   - Ảnh chữ là cảnh có `metadata["visual_kind"]` bằng `"disclaimer"` (thẻ miễn trừ) hoặc `"board"` (bảng ghim).
   - Không có ảnh nào dùng được thì dùng nền chuyển màu như cũ.
   - Người dùng tự chọn cảnh (`scene_index`) thì vẫn dùng đúng cảnh đó.
2. Không còn vệt sáng: lớp tối bên trái và lớp tối phía dưới chồng lên nhau; càng xuống dưới càng tối, không dải nào sáng lên.
3. Cập nhật dòng Thumbnail trong `FEATURE_MAP.md` cho đúng cách chọn ảnh nền mới.
4. Tự mở xem ảnh thumbnail tạo ra trước khi báo xong.

Phạm vi được sửa: `backend/services/thumbnail_service.py`, thư mục `tests/`, `FEATURE_MAP.md` (bắt buộc); cập nhật `CLAUDE.md`, `TASKS.md` khi quy tắc dự án yêu cầu; `tools/ruff_baseline.json` chỉ được hạ mốc. Không sửa file khác.
