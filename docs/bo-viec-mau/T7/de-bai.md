# Việc: video thành phẩm nhỏ tiếng, có nhạc nền thì giọng càng nhỏ

Việc khó: đề chỉ tả điều chủ dự án thấy, không chỉ chỗ sai. Bạn tự tìm nguyên nhân trong code, tái hiện bằng test (đo độ to thật bằng ffmpeg) rồi mới sửa.

Chạy thật ngày 26/10/2026, dự án vụ án Trạm Dung, nút "Sản Xuất Video Dài". Chủ dự án thấy:

1. Video thành phẩm `renders/story_final.mp4` nghe nhỏ hơn hẳn các kênh YouTube khác. Đo bằng ffmpeg: trung bình khoảng −29 đến −30 dB.
2. Bật nhạc nền (có hoặc không "ducking", tức tự hạ nhạc khi có giọng) thì giọng đọc còn nhỏ thêm so với khi tắt nhạc nền, dù file giọng từng cảnh không đổi.

Kết quả mong đợi:

- Video thành phẩm có độ to tích hợp quanh −16 LUFS (mức các kênh YouTube hay dùng; đo bằng bộ lọc `ebur128` của ffmpeg), đỉnh không vượt −1 dBTP. Đúng cả khi có và không có nhạc nền, cả khi giọng đầu vào rất nhỏ.
- Trộn nhạc nền không được làm giọng nhỏ đi.
- Không in phụ đề vào hình thì không cần mã hoá lại hình.
- Video vẫn đủ hình, đủ tiếng, đúng độ dài như trước.

Phạm vi được sửa: thư mục `backend/services/`, thư mục `tests/`; cập nhật `CLAUDE.md`, `FEATURE_MAP.md`, `TASKS.md` khi quy tắc dự án yêu cầu; `tools/ruff_baseline.json` chỉ được hạ mốc. Không sửa file khác.
