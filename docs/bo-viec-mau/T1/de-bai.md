# Việc: ảnh Muse của dự án này bị gắn link sang dự án khác

Lỗi: Muse trả ảnh về cho dự án `proj_a`, nhưng file lại nằm trong thư mục của dự án `proj_ab`, vậy mà app vẫn gắn link `/api/projects/proj_a/media/...` cho ảnh đó. Chỗ sai là `complete_task()` trong `backend/routers/muse_bridge.py`: so đường dẫn bằng chuỗi `startswith`, nên `proj_a` khớp nhầm cả `proj_ab`. Đây là đường cấm 7 trong `CLAUDE.md` (tự kiểm id/đường dẫn bằng regex riêng hoặc `str.startswith`). `backend/services/project_service.py` cũng đang tự kiểm id bằng regex riêng.

Kết quả mong đợi:

1. File không nằm trong thư mục của đúng dự án thì không được gắn link của dự án đó. Khi ấy ảnh lấy link trong thư viện ảnh Muse `/static/muse_outputs/<task_id>.<đuôi file>`, như ảnh không thuộc dự án nào.
2. Code backend không còn so đường dẫn bằng `startswith`; bảng ngoại lệ của đường cấm 7 trong `tests/test_architecture.py` về 0.
3. `project_service.py` kiểm id bằng hàm của `backend/security.py`, không tự viết regex; id sai vẫn bị chặn như cũ.

Phạm vi được sửa: `backend/routers/muse_bridge.py`, `backend/services/project_service.py`, `backend/security.py` (nếu cần), thư mục `tests/`; cập nhật `CLAUDE.md`, `FEATURE_MAP.md`, `TASKS.md` khi quy tắc dự án yêu cầu; `tools/ruff_baseline.json` chỉ được hạ mốc. Không sửa file khác.
