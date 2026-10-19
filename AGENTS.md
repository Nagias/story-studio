# Story Studio — studio dựng video YouTube (storyboard, true-crime, truyện tranh)

Backend FastAPI: `backend/main.py`, API trong `backend/routers/`, logic trong `backend/services/`, giao diện web trong `backend/static/`. Dự án chưa có git.

## Lệnh
- Chạy: `run.bat` (hoặc `.venv\Scripts\python.exe run.py`), mở http://localhost:8000.
- Python: luôn dùng `.venv\Scripts\python.exe` (Python 3.14), không dùng `python` của hệ thống.
- Cài thư viện: `.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`; Playwright cần thêm `.venv\Scripts\python.exe -m playwright install chromium`.
- Test một file: `.venv\Scripts\python.exe -m pytest tests\test_xxx.py -q`. Cả bộ kèm báo cáo QA: `.venv\Scripts\python.exe run_all_tests.py`.
- Công cụ ngoài cần có: ffmpeg/ffprobe trong PATH, `uv` (giọng VieNeu), Chrome hoặc Edge.

## Lưu ý
- `backend/chrome_profiles/` và `backend/config/muse_fleet_accounts.json` là tài khoản Muse đã đăng nhập thật. Các test như `test_muse_*`, `test_live_browser_reality.py`, `*e2e*` có thể mở trình duyệt bằng các tài khoản này: chỉ chạy khi được yêu cầu.
- `.env` chứa API key: không in ra, không chép vào code hay test.
- Thư viện tuỳ chọn (openai, faster-whisper, av, rembg) có thể chưa cài và code tự bỏ qua: thiếu chúng không phải lỗi.
- Chưa có git: trước khi sửa nhiều file, nói rõ sẽ sửa những gì; không xoá file cũ khi chưa hỏi.
- Gốc dự án có nhiều script chạy thử một lần (`run_full_novel_test.py`, `click_approve_and_download.py`…): không thêm script mới ở gốc, đặt test trong `tests/`.
