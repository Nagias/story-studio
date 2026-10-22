# Việc: lọc chữ từ máy chủ trước khi chèn vào thông báo và thư viện ảnh Muse

Lỗi bảo mật giao diện (đường cấm 9 trong `CLAUDE.md`): `showToast()` hiển thị HTML, mà nhiều chỗ chèn thẳng chữ lấy từ lỗi, từ máy chủ hay từ máy người dùng vào thông báo chưa qua lọc. Vì vậy chèn được mã HTML vào trang (ví dụ lỗi máy chủ chứa `<img src=x onerror=...>` sẽ chạy). Thẻ trong thư viện ảnh Muse (Gallery) cũng chèn thẳng link, mã cảnh, mã task lấy từ máy chủ vào HTML.

Kết quả mong đợi:

1. Mọi `showToast()` trong `backend/static/app.js` và `backend/static/true_crime.js` có chữ thuộc các loại sau đều phải lọc qua `escapeHtml()` (app.js) hoặc `tcEsc()` (true_crime.js):
   - chữ lấy từ lỗi hay máy chủ (trong code thường là `err.message`, `.detail`, `errText`, `errMsg`);
   - tên file người dùng chọn (`file.name`);
   - mã hay tên tài khoản Muse (`aid`, `accLabel`).
2. Thẻ trong thư viện ảnh Muse lọc mọi giá trị lấy từ máy chủ trước khi chèn vào HTML: link ảnh/video, link tải, mã cảnh, mã task, đường dẫn file.
3. `escapeHtml()` nhận được mọi kiểu giá trị mà không văng lỗi:
   - số thành chuỗi số (0 thành "0");
   - đối tượng lỗi thành chữ đã lọc;
   - null/undefined thành chuỗi rỗng.
4. Chữ bình thường vẫn hiển thị như cũ; không đổi giao diện.

Phạm vi được sửa: `backend/static/app.js`, `backend/static/true_crime.js`, thư mục `tests/`; cập nhật `CLAUDE.md`, `FEATURE_MAP.md`, `TASKS.md` khi quy tắc dự án yêu cầu; `tools/ruff_baseline.json` chỉ được hạ mốc. Không sửa file khác.
