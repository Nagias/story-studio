# Story Studio

Studio dựng video YouTube (storyboard, true-crime, truyện tranh) chạy trên máy của bạn, giao diện web tại http://localhost:8000.

## Cần có
- Windows 10/11, Python 3.11 trở lên
- ffmpeg và ffprobe trong PATH
- Google Chrome hoặc Microsoft Edge (để chạy tài khoản Muse)
- Tuỳ chọn: `uv` (giọng đọc VieNeu)

## Cài đặt
Mở terminal trong thư mục này:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
copy .env.example .env
```

Mở `.env` và điền `NINEROUTER_API_KEY` (cùng các giá trị khác nếu cần).

## Đăng nhập tài khoản Muse
Chạy `setup_muse_accounts.bat`, chọn tài khoản (1–10) rồi đăng nhập trên cửa sổ trình duyệt vừa mở. Làm lần lượt cho từng tài khoản muốn dùng (5 tài khoản ảnh, 5 tài khoản video). Phiên đăng nhập được lưu trong `backend/chrome_profiles/`, không chia sẻ thư mục này cho ai.

## Chạy
Chạy `run.bat`. Trình duyệt tự mở http://localhost:8000; Fleet Runner (xử lý ảnh/video Muse) tự khởi động cùng server. Nếu cần chạy riêng Fleet Runner: `start_muse_fleet.bat`.

Dự án và video bạn tạo nằm trong thư mục `projects/`.

## Dành cho người phát triển
- Phiên bản thư viện được ghim trong `backend/requirements.txt` (đã chạy ổn trên Python 3.14). Chạy test: cài thêm `backend/requirements-dev.txt` rồi `.venv\Scripts\python.exe -m pytest -q` (mặc định bỏ test gọi dịch vụ thật; chạy chúng bằng `-m live`). Kiểm tra trước khi commit: `.venv\Scripts\python.exe tools\check.py` (cài hook tự chạy: `tools\check.py --install-hook`).
- Giao diện dùng Tailwind build sẵn (`backend/static/tailwind.css`, không cần internet). Thêm class Tailwind mới trong `index.html`/`app.js` thì build lại (cần Node.js):

```bat
cd tools\tailwind
npm install --cache .npm-cache
npm run build
```
