# Story Studio

Studio dựng video YouTube (truyện chữ kể kiểu review, vụ án có thật viết lại, truyện tranh) chạy ngay trên máy của bạn.
Giao diện là một trang web mở ở `http://localhost:8000`. Ảnh và video do AI tạo (Muse, Gemini), lời kể do AI viết qua 9router,
giọng đọc bằng Edge-TTS hoặc VieNeu, video dựng bằng ffmpeg.

Hướng dẫn này dành cho người tải repo về máy lần đầu. Làm lần lượt từ mục 1 đến mục 6.

## 1. Cài phần mềm cần có (một lần cho mỗi máy)

App chỉ chạy trên **Windows 10 hoặc 11**. Mở **PowerShell** (bấm phím Windows, gõ `PowerShell`, Enter) rồi chạy từng lệnh.
Cài xong thì **đóng PowerShell và mở lại** để Windows nhận lệnh mới.

| Phần mềm | Để làm gì | Lệnh cài |
|---|---|---|
| Git | tải repo về và cập nhật bản mới | `winget install --id Git.Git -e` |
| Python 3.14 | chạy app (các thư viện được ghim theo bản 3.14) | `winget install --id Python.Python.3.14 -e` |
| ffmpeg | dựng và ghép video, đo độ dài giọng đọc | `winget install --id Gyan.FFmpeg -e` |
| Node.js 18 trở lên | chạy 9router (cổng AI viết lời kể) | `winget install --id OpenJS.NodeJS.LTS -e` |
| Google Chrome hoặc Microsoft Edge | đăng nhập và điều khiển tài khoản Muse | Edge có sẵn trong Windows |
| uv (tuỳ chọn) | giọng đọc VieNeu; không có thì vẫn dùng giọng Edge | `winget install --id astral-sh.uv -e` |

Không dùng Python bản Microsoft Store: bản đó hay lỗi đường dẫn. Nếu máy không có `winget`, tải bộ cài từ trang chủ của từng phần mềm
(python.org, ffmpeg.org, nodejs.org, git-scm.com); khi cài Python nhớ tích ô **Add python.exe to PATH**.

Kiểm tra đã cài đủ (mỗi lệnh phải in ra số phiên bản):

```powershell
git --version
py -3.14 --version
ffmpeg -version
node --version
```

## 2. Tải repo về

Chọn thư mục muốn đặt app (nên để ổ D nếu ổ C gần đầy, vì dự án và video sinh ra khá nặng), rồi chạy:

```powershell
cd D:\
git clone https://github.com/Nagias/story-studio.git
cd story-studio
```

Repo đang để riêng tư: chủ repo phải mời tài khoản GitHub của bạn vào repo (Settings, Collaborators) thì lệnh `git clone` mới tải được.
Lần đầu tải, Git sẽ mở cửa sổ đăng nhập GitHub.

## 3. Cài app

Bấm đúp file `tools\cai_dat.bat` (hoặc chạy `tools\cai_dat.bat` trong PowerShell ở thư mục `story-studio`). File này:

1. tạo môi trường Python riêng `.venv` trong thư mục app (không đụng Python chung của máy);
2. cài thư viện theo `backend\requirements.txt` (lần đầu mất vài phút, tải khoảng vài trăm MB);
3. cài trình duyệt Chromium cho Playwright;
4. tạo file cấu hình `.env` từ `.env.example` nếu chưa có;
5. báo còn thiếu ffmpeg, Node.js, 9router hay uv không.

Chạy lại file này nhiều lần cũng không sao: nó dùng lại `.venv` và giữ nguyên `.env` đã có.

Cài bằng tay (nếu không muốn dùng file .bat):

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
copy .env.example .env
```

## 4. Bật 9router và điền khoá vào `.env`

9router là chương trình chạy trên máy, làm cổng để app gọi các mô hình AI (viết lời kể, chia cảnh, phân tích vụ án).
Không có 9router thì app vẫn mở được, nhưng các nút dùng AI viết chữ sẽ báo lỗi.

```powershell
npm install -g 9router
9router
```

Để cửa sổ 9router chạy. Mở trang quản lý `http://127.0.0.1:20128/dashboard`, kết nối tài khoản nhà cung cấp AI và lấy API key.
Sau đó mở file `.env` trong thư mục app bằng Notepad, điền vào dòng:

```
NINEROUTER_API_KEY=khoa-cua-ban
```

Các dòng khác trong `.env` để mặc định là chạy được; ý nghĩa từng dòng ghi ngay trong `.env.example`.
**Không gửi file `.env` cho ai và không đưa nó lên GitHub** (repo đã chặn sẵn file này).

## 5. Đăng nhập tài khoản Muse (để tạo ảnh và video)

Bấm đúp `setup_muse_accounts.bat`, chọn một số tài khoản (1 đến 5 là tài khoản tạo ảnh, 6 đến 10 là tài khoản tạo video),
rồi đăng nhập Muse trên cửa sổ trình duyệt vừa mở. Có bao nhiêu tài khoản thì đăng nhập bấy nhiêu, không cần đủ 10.

Phiên đăng nhập được lưu trong thư mục `backend\chrome_profiles\`. Thư mục này chứa đăng nhập thật của bạn: không chép cho ai,
và repo đã chặn để nó không bao giờ lên GitHub.

## 6. Chạy app

Bấm đúp `run.bat`. Trình duyệt tự mở `http://localhost:8000`. Fleet Runner (phần tự điều khiển Muse để tạo ảnh và video)
tự bật cùng app; muốn chạy riêng thì dùng `start_muse_fleet.bat`. Bấm `run.bat` lần nữa khi app đang chạy thì nó chỉ mở lại trang web,
không bật thêm bản thứ hai.

Dự án và video bạn làm nằm trong thư mục `projects\` (không lên GitHub).

## Cập nhật bản mới

Trong thư mục `story-studio`:

```powershell
git pull
tools\cai_dat.bat
```

Chạy lại `cai_dat.bat` để cài thêm thư viện nếu bản mới có đổi. Dữ liệu trong `projects\`, file `.env` và đăng nhập Muse được giữ nguyên.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân hay gặp | Cách xử lý |
|---|---|---|
| `run.bat` báo `FFmpeg was not detected` | chưa cài ffmpeg, hoặc cài rồi mà chưa mở lại cửa sổ | cài theo mục 1, đóng mọi cửa sổ PowerShell/cmd rồi mở lại |
| Báo cổng 8000 đang bị chương trình khác dùng | có app khác chiếm cổng 8000 | tắt app đó, hoặc sửa `STORY_STUDIO_PORT=8001` trong `.env` |
| Nút dùng AI báo lỗi 401 hoặc không kết nối được | 9router chưa bật, hoặc `NINEROUTER_API_KEY` sai | bật `9router`, kiểm lại khoá trong `.env`, chạy lại `run.bat` |
| Cài thư viện báo lỗi phiên bản | `.venv` được tạo bằng Python khác 3.14 | xoá thư mục `.venv`, cài Python 3.14, chạy lại `tools\cai_dat.bat` |
| Muse không tạo ảnh hay video | chưa đăng nhập Muse, hoặc phiên đăng nhập hết hạn | chạy lại `setup_muse_accounts.bat` cho tài khoản đó |

## Dành cho người phát triển

- Quy tắc làm việc, kiến trúc và các khoá cứng: `CLAUDE.md`. Bản đồ nút bấm và API: `FEATURE_MAP.md`. Nhật ký việc: `TASKS.md`.
- Cài thêm công cụ test: `.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt`.
- Chạy test (không gọi dịch vụ thật): `.venv\Scripts\python.exe -m pytest -q`. Test gọi dịch vụ thật: `-m live`.
- Kiểm tra trước khi commit: `.venv\Scripts\python.exe tools\check.py` (bản đầy đủ thêm `--full`).
  Cài hook git một lần sau khi clone: `.venv\Scripts\python.exe tools\check.py --install-hook`
  (hook chặn commit thẳng lên `master` và chặn commit message sai dạng `<vùng>: <mô tả>`).
- Giao diện dùng Tailwind build sẵn (`backend/static/tailwind.css`). Thêm class Tailwind mới thì build lại (cần Node.js):

```powershell
cd tools\tailwind
npm install --cache .npm-cache
npm run build
```
