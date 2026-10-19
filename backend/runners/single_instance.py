"""
Khóa chạy 1 bản duy nhất cho Fleet Runner (Windows + Linux/macOS).

Dùng file lock của hệ điều hành thay vì kiểm tra PID: khóa tự nhả khi process chết
(kể cả bị kill cứng), nên không bao giờ bị kẹt hoặc sinh nhiều bản chạy song song.
"""
import os
import sys
from pathlib import Path
from typing import Optional

RUNNERS_DIR = Path(__file__).resolve().parent
LOCK_FILE = RUNNERS_DIR / ".fleet_runner.lock"

if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


_held_fd: Optional[int] = None


def acquire_runner_lock() -> bool:
    """Giữ khóa suốt vòng đời process. False nếu đã có Fleet Runner khác đang chạy."""
    global _held_fd
    if _held_fd is not None:
        return True
    fd = os.open(str(LOCK_FILE), os.O_RDWR | os.O_CREAT, 0o600)
    if not _try_lock(fd):
        os.close(fd)
        return False
    # Ghi PID ra sau byte đầu tiên (byte 0 là vùng bị khóa) để tiện tra cứu
    try:
        os.lseek(fd, 1, os.SEEK_SET)
        data = f"{os.getpid()}\n".encode()
        os.write(fd, data)
        os.ftruncate(fd, 1 + len(data))
    except OSError:
        pass
    _held_fd = fd
    return True


def release_runner_lock() -> None:
    global _held_fd
    if _held_fd is None:
        return
    _unlock(_held_fd)
    os.close(_held_fd)
    _held_fd = None


def is_runner_running() -> bool:
    """Có Fleet Runner nào đang giữ khóa không (thử khóa rồi nhả ngay)."""
    if _held_fd is not None:
        return True
    try:
        fd = os.open(str(LOCK_FILE), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return False
    try:
        if _try_lock(fd):
            _unlock(fd)
            return False
        return True
    finally:
        os.close(fd)


def autostart_disabled() -> bool:
    """Tắt tự khởi động runner (dùng khi chạy test để không đụng tài khoản Muse thật)."""
    return os.getenv("STORY_STUDIO_DISABLE_FLEET_AUTOSTART", "").strip().lower() in ("1", "true", "yes")
