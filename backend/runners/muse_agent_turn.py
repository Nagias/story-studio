"""Chế độ giao việc nhiều bước (`agent-video`) của Fleet Runner: phần quyết định thuần, test được không cần trình duyệt.

Muse là agent có máy ảo: một yêu cầu làm nhiều bước (tạo, tự kiểm, làm lại, ghép) rồi mới gửi bản cuối; giữa chừng có
thể gửi bản nháp và viết "lỗi", "loại" khi kể clip nó đã bỏ. Vì vậy chỉ coi là xong khi chữ Muse viết kết thúc bằng
`done_token` (dòng bản giao việc dặn), và không bỏ ngang vì chữ báo lỗi: thí nghiệm 28/10/2026 có lúc chữ đứng yên
18 phút trong khi Muse vẫn đang làm. Hết giờ chờ thì thất bại AGENT_TIMEOUT.
"""
from __future__ import annotations

import string
from typing import Optional

AGENT_VIDEO_MODE = "agent-video"   # trùng services/climax_brief.AGENT_VIDEO_MODE (runner là tiến trình riêng, không nạp services)
AGENT_STABLE_SEC = 90          # chữ đứng yên chừng này sau dòng kết thúc mới tải (Muse gửi file sau cùng)
AGENT_MAX_VIDEOS = 6           # giới hạn Muse tự khai cho một yêu cầu; chỉ để cảnh báo, runner không chặn được Muse
AGENT_MAX_IMAGES = 4
REPLY_MAX_CHARS = 8000
# Dấu Muse hay thêm sau dòng kết thúc: in đậm, mã, dấu chấm, ngoặc kép (giám khảo 28/10/2026)
TRAILING_MARKS = string.whitespace + ".。!*`_" + '"' + "'"
DOWNLOAD_TRIES = 5             # đọc lại trang rồi tải lại khi địa chỉ blob vừa bị Muse huỷ

# Trang Muse đánh dấu tin đang gõ: data-hatch-markdown-streaming="true" (đo DOM 28/10/2026)
STREAMING_JS = ("() => !!document.querySelector('[role=log] [data-hatch-markdown-streaming=\"true\"], "
                "[data-hatch-markdown-streaming=\"true\"]')")


def turn_done(said: str, token: str) -> bool:
    """`said` = chữ Muse viết sau prompt (đã bỏ chính prompt, xem `_muse_reply_part`). Xong khi kết thúc bằng token
    (bỏ qua các dấu `TRAILING_MARKS` ở cuối)."""
    return bool(token) and said.rstrip(TRAILING_MARKS).endswith(token)


def pick_final_video(srcs: list[str]) -> Optional[str]:
    """Video cuối cùng Muse gửi sau prompt (bản giao việc dặn tin cuối chỉ có một video)."""
    return srcs[-1] if srcs else None


def budget_warnings(videos: int, images: int, final_videos: int = 1) -> list[str]:
    """Cảnh báo cho chủ dự án: Muse dùng quá ngân sách, hoặc gửi nhiều video nên app phải tự chọn video cuối."""
    out = []
    if videos > AGENT_MAX_VIDEOS:
        out.append(f"Muse đã gửi {videos} video, quá ngân sách {AGENT_MAX_VIDEOS} video")
    if images > AGENT_MAX_IMAGES:
        out.append(f"Muse đã gửi {images} ảnh, quá ngân sách {AGENT_MAX_IMAGES} ảnh")
    if final_videos > 1:
        out.append(f"Muse gửi {final_videos} video trong lượt, app lấy video cuối cùng")
    return out
