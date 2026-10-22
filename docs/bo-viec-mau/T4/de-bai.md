# Việc: ngày tháng thật lọt vào tên tập và nhãn bằng chứng của video vụ án

Lỗi: chạy thật một vụ án, nhãn bằng chứng ra vẫn còn "ngày 28 tháng 2" / "February 28". Nhãn hiện lên bảng ghim trong video nên ngày thật lộ trên hình, mà màn xem lại không sửa được nhãn. Hiện `check_plan()` (`backend/services/case_adaptation_checks.py`) chỉ cảnh báo khi tên tập hay nhãn có ngày tháng.

Kết quả mong đợi:

1. `check_plan()` tự bỏ ngày tháng, năm cụ thể (những gì `find_dates()` nhận ra) khỏi tên tập (`title_vi`, `title_en`) và nhãn bằng chứng/quan hệ (`label_vi`, `label_en`). Bỏ luôn chữ nối đứng ngay trước ngày ("ngày", "năm", "vào", "lúc", "on", "from", "in"...). Ví dụ:

   | Trước | Sau |
   |---|---|
   | Biên bản đối chất ngày 28 tháng 2 | Biên bản đối chất |
   | Confrontation record on February 28 | Confrontation record |
   | Hồ sơ năm 2014 | Hồ sơ |
   | File from 2014 | File |
   | Cuộc gọi lúc 02:21 ngày 2/8 | Cuộc gọi lúc 02:21 |
   | Call on August 2 | Call |
   | (tên tập) Vụ án năm 2014 | Vụ án |

2. Mỗi lần tự bỏ thì ghi một dòng vào `warnings` của kế hoạch, dạng `Đã tự bỏ ngày tháng cụ thể 'ngày 28 tháng 2' ở <chỗ> (<trường>).`
   - Ngày ghi trong ngoặc đơn, đúng như `find_dates()` trả về.
   - `<chỗ>` có mã bằng chứng/quan hệ (vd `ev1`, `r1`) hoặc chỉ ra tên tập.
   - `<trường>` là tên trường (vd `title_vi`, `label_en`).

   Chỗ đã tự bỏ thì không còn cảnh báo trong `check_warnings`.
3. Nhãn chỉ có ngày (bỏ xong thành rỗng, vd "28/2/2015") thì giữ nguyên và chỉ cảnh báo trong `check_warnings` như cũ.
4. Ngày trong prompt hình vẫn chỉ cảnh báo, không tự sửa. Không thêm cờ chặn mới.
5. Chạy `check_plan()` lần nữa trên kết quả thì không đổi gì và không thêm ghi chú trùng.
6. Prompt bước đọc bài (`backend/services/case_adaptation_prompts.py`) dặn LLM không ghi ngày, tháng, năm trong nhãn bằng chứng và nhãn quan hệ.

Phạm vi được sửa: `backend/services/case_adaptation_checks.py`, `backend/services/case_adaptation_prompts.py`, thư mục `tests/`; cập nhật `CLAUDE.md`, `FEATURE_MAP.md`, `TASKS.md` khi quy tắc dự án yêu cầu; `tools/ruff_baseline.json` chỉ được hạ mốc. Không sửa file khác.
