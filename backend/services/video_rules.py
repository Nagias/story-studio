"""Luật video Muse: nơi DUY NHẤT định nghĩa clip nào được nhận, clip nào được tính là video, tính bao nhiêu giây, và
bao nhiêu phần trăm là đủ. Không import gì của dự án (mọi module khác đọc từ đây, không tự đặt con số riêng).

Vì sao có file này (rà soát 17–18/11/2026): hai lần làm video thật (vụ Khang Cúc Hoa, vụ Vương Nghĩa Tường) rơi vào vòng
sửa không dứt vì mỗi nơi tự định nghĩa: màn chọn cảnh đếm đủ lời kể còn chốt chặn chỉ đếm phần clip chạy, Fleet Runner
nhận clip từ 3 giây còn app chỉ nhận từ 5 giây, clip đứng hình vẫn ghi "xong". Tỉ lệ video vụ xưởng sắt vì thế nhảy
65,5% → 8,2% → 23,9% → 50,3% → 62,3% qua bốn lần đổi cách đếm.

Chủ dự án (CLAUDE.md mục 1.2 câu 24, và 11/11/2026): "50% là video gen từ muse", "Khoảng 50%, chặn dưới 45%".
"""
from typing import Optional

TARGET_SHARE = 0.5          # mục tiêu khi chọn cảnh làm video
GATE_SHARE = 0.45           # dưới mức này không dựng thành phẩm (chỉ bản nháp)

# Clip Muse được nhận (không bỏ phí lượt Muse đã tốn): từ MIN_CLIP_SEC giây tới max_clip_seconds(mục tiêu). Muse đôi khi trả
# clip 3,5–4 giây (vụ xưởng sắt cảnh 009, 063); phần thiếu so với lời kể không được đếm là video (moving_seconds).
MIN_CLIP_SEC = 3.0

# Ngưỡng điểm cử động (services/clip_motion.py đo): dưới mức này clip gần như đứng hình hoặc chỉ lia/zoom ảnh tĩnh.
REAL_MOTION_MIN = 1.0

# Clip ngắn hơn lời kể thì lúc dựng kéo chậm tối đa chừng này lần rồi giữ khung cuối. Bản Anh vụ Khang Cúc Hoa (10/11/2026):
# cần kéo nhiều nhất 1,18 lần; chậm 1,25 lần khó nhận ra.
MAX_CLIP_STRETCH = 1.25


def max_clip_seconds(target_seconds: float) -> float:
    """Clip dài hơn chừng này so với độ dài xin Muse thì không nhận (thường là Muse gửi nhầm video khác)."""
    return 2 * float(target_seconds) + 1


def clip_length_ok(seconds: float, target_seconds: float) -> bool:
    return MIN_CLIP_SEC <= float(seconds) <= max_clip_seconds(target_seconds)


def has_real_motion(score: Optional[float]) -> bool:
    return score is not None and score >= REAL_MOTION_MIN


def clip_stretch(clip_seconds: Optional[float], scene_seconds: Optional[float]) -> float:
    """Hệ số kéo chậm clip cho vừa cảnh: 1 khi clip đủ dài (lệch dưới 0,05 giây) hoặc không đo được clip."""
    if not clip_seconds or not scene_seconds or clip_seconds <= 0 or scene_seconds <= clip_seconds + 0.05:
        return 1.0
    return min(MAX_CLIP_STRETCH, scene_seconds / clip_seconds)


def moving_seconds(clip_seconds: Optional[float], scene_seconds: Optional[float]) -> float:
    """Số giây của cảnh mà clip thật sự chạy khi dựng (kéo chậm tối đa MAX_CLIP_STRETCH, phần còn lại là khung cuối
    đứng yên). `clip_seconds` là phần clip có hình chạy thật (video ghép có chèn khung đứng yên thì truyền phần chạy
    thật, không truyền độ dài file). Không đo được clip: 0 (không tính bừa là video)."""
    scene = float(scene_seconds or 0)
    if not clip_seconds or clip_seconds <= 0 or scene <= 0:
        return 0.0
    return min(scene, clip_seconds * clip_stretch(clip_seconds, scene))


def counted_seconds(clip_ok: bool, running_seconds: Optional[float], scene_seconds: Optional[float]) -> float:
    """Số giây cảnh được tính là video Muse: 0 khi clip không được tính (đứng hình, chưa đo, chưa duyệt)."""
    return moving_seconds(running_seconds, scene_seconds) if clip_ok else 0.0
