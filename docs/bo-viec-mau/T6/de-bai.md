# Việc: Muse làm xong video cao trào mà app báo lỗi, rồi Muse phải làm lại lần nữa

Việc khó: đề chỉ tả điều chủ dự án thấy khi chạy thật, không chỉ chỗ sai. Bạn tự tìm nguyên nhân trong code, tái hiện bằng test rồi mới sửa.

Chạy thật ngày 28/10/2026, nút làm video cho cảnh cao trào của dự án vụ án (cảnh 28). Ở chế độ này app giao cho Muse một việc nhiều bước (mã chế độ `agent-video`): Muse tự tạo nhiều clip, tự kiểm, tự làm lại rồi gửi một video cuối. Chủ dự án thấy:

1. Muse làm xong trọn việc, tự báo ĐẠT, video cuối hiện trong chat và xem được. Nhưng thẻ cảnh trong app báo lỗi `NO_FINAL: Không tải được video cuối của Muse`. Nhật ký Fleet Runner có dòng tải media lỗi "Failed to fetch".
2. Ngay sau đó, cùng việc ấy được giao cho một tài khoản video khác. Muse làm lại từ đầu lần thứ hai. Mỗi lần Muse làm tốn tới 6 video, nên chủ dự án mất gấp đôi lượt Muse mà vẫn chưa có kết quả.
3. Chủ dự án mở trang Muse quan sát thì thấy: trang liên tục tạo lại địa chỉ `blob:` của video. Một địa chỉ đọc được vài giây trước có thể đã bị huỷ.

Kết quả mong đợi:

- Muse đã làm xong và video cuối còn trên trang thì app lấy được video đó, kể cả khi địa chỉ blob vừa đọc đã bị huỷ.
- Việc giao nhiều bước (`agent-video`) bị lỗi thì dừng ở trạng thái lỗi, không tự giao lại cho tài khoản nào. Chủ dự án tự bấm làm lại khi muốn.
- Các loại việc khác (ảnh, video thường) giữ nguyên cách tự thử lại như hiện nay.
- Giữ nguyên cách gọi hàm `MuseFleetRunner._finish_agent_turn(acc, page, context, task, text_before, prompt, pre_srcs, ...)`: 7 tham số đầu như hiện có. Nếu còn tham số sau thì phải có giá trị mặc định.
- Ràng buộc để chấm được (test ẩn giả lập trang Muse): runner chỉ đọc trang qua các đoạn JS đã có trong `muse_fleet_runner.py` (`LOG_TEXT_JS`, `FIND_NEW_MEDIA_JS`, `SCROLL_LOG_JS`, `agent_turn.STREAMING_JS`…) và tải media qua `self._download_media(page, context, src)` như hiện nay. Không thêm đoạn JS mới để tải video trong trang.

Phạm vi được sửa: thư mục `backend/`, thư mục `tests/`; cập nhật `CLAUDE.md`, `FEATURE_MAP.md`, `TASKS.md` khi quy tắc dự án yêu cầu; `tools/ruff_baseline.json` chỉ được hạ mốc. Không sửa file khác.
