"""Đọc ghi file an toàn, dùng chung cho mọi dữ liệu người dùng (dự án, vụ án).

- Ghi qua file tạm rồi đổi tên (`os.replace`): tắt máy hay lỗi giữa chừng không để lại file cụt, file cũ còn nguyên.
- Windows báo PermissionError khi file đang bị tiến trình/luồng khác mở (đọc đúng lúc đổi tên, hoặc đổi tên đúng lúc
  có người đọc). Khoá chỉ kéo dài vài ms nên tự thử lại vài lần rồi mới báo lỗi.
"""
import os
import time
import uuid
from pathlib import Path
from typing import Optional

TRIES = 8           # số lần thử khi file đang bị khoá (chỉ tốn thời gian khi thật sự bị khoá)
RETRY_DELAY = 0.02  # giây chờ sau lần thử đầu, tăng tuyến tính ở các lần sau (20, 40, ... 140 ms)


def retry_if_locked(action):
    for attempt in range(TRIES):
        try:
            return action()
        except PermissionError:
            if attempt == TRIES - 1:
                raise
            time.sleep(RETRY_DELAY * (attempt + 1))  # chờ lâu dần


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        retry_if_locked(lambda: os.replace(tmp, path))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_text(path: Path) -> Optional[str]:
    """Nội dung file UTF-8, hoặc None nếu file không tồn tại."""
    try:
        return retry_if_locked(lambda: path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
