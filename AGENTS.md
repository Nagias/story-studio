# Story Studio — studio dựng video YouTube (storyboard, true-crime, truyện tranh)

Backend FastAPI: `backend/main.py`, API trong `backend/routers/`, logic trong `backend/services/`, giao diện web trong `backend/static/`. Git khởi tạo ngày 19/10/2026: commit message bằng tiếng Việt.

## Lệnh
- Chạy: `run.bat` (hoặc `.venv\Scripts\python.exe run.py`), mở http://localhost:8000.
- Python: luôn dùng `.venv\Scripts\python.exe` (Python 3.14), không dùng `python` của hệ thống.
- Cài thư viện: `.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt` (phiên bản đã ghim); Playwright cần thêm `.venv\Scripts\python.exe -m playwright install chromium`.
- Test một file: `.venv\Scripts\python.exe -m pytest tests\test_xxx.py -q`. Cả bộ kèm báo cáo QA: `.venv\Scripts\python.exe run_all_tests.py`.
- Giao diện dùng `backend/static/tailwind.css` build sẵn (không dùng CDN). Thêm class Tailwind mới thì build lại: `cd tools\tailwind`, `npm install --cache .npm-cache`, `npm run build`.
- Đóng gói bán: `.venv\Scripts\python.exe tools\build_release.py` (chỉ lấy file trong danh sách cho phép, tự kiểm tra không lọt bí mật).
- Công cụ ngoài cần có: ffmpeg/ffprobe trong PATH, `uv` (giọng VieNeu), Chrome hoặc Edge.

## Lưu ý
- `backend/chrome_profiles/` và `backend/config/muse_fleet_accounts.json` là tài khoản Muse đã đăng nhập thật (không commit). `tests/conftest.py` chặn test tự bật Fleet Runner; riêng `*e2e*` và `*live*` gọi dịch vụ thật (Edge-TTS, 9router): chỉ chạy khi được yêu cầu.
- `.env` chứa API key: không in ra, không chép vào code hay test.
- Thư viện tuỳ chọn (openai, faster-whisper, av, rembg) có thể chưa cài và code tự bỏ qua: thiếu chúng không phải lỗi.
- Trước khi sửa nhiều file, nói rõ sẽ sửa những gì; không xoá file hay dự án của người dùng khi chưa hỏi (dọn thì chuyển vào Thùng rác).
- Không thêm script chạy thử ở gốc dự án; test đặt trong `tests/`, công cụ đặt trong `tools/`.
