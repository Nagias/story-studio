"""Luật video Muse ở một nơi (services/video_rules.py): nhận clip, đếm giây, ngưỡng cử động.

Rà soát 17–18/11/2026: mỗi nơi tự đặt con số (Fleet Runner nhận clip từ 3 giây, app chỉ nhận từ 5 giây; video theo lời
thoại có chèn khung đứng yên vẫn đếm đủ) nên tỉ lệ video nhảy qua bốn lần đổi cách đếm."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from services import climax_video, clip_motion, dialogue_video, video_rules, video_service, video_share  # noqa: E402


def test_every_module_reads_the_same_numbers():
    """Một tên cho mỗi con số (rà soát 18/11/2026: bỏ các tên phụ CLIMAX_RATIO, GATE_MIN, ROUND_HEAD_EXPRESSION_RULE_EN):
    không module nào còn tự đặt con số hay tên riêng cho mục tiêu, mức chặn, ngưỡng cử động."""
    for mod in (climax_video, video_share, clip_motion, video_service):
        for name in ("CLIMAX_RATIO", "GATE_MIN", "REAL_MOTION_MIN", "MAX_CLIP_STRETCH", "moving_seconds"):
            assert not hasattr(mod, name), f"{mod.__name__}.{name}"
    assert video_service.clip_stretch is video_rules.clip_stretch          # dùng thẳng hàm của video_rules


def test_short_muse_clip_is_accepted_but_counts_only_its_running_part():
    # Muse trả 4 giây cho mục tiêu 15 giây: nhận (không bỏ phí lượt đã tốn), chỉ đếm phần chạy
    assert video_rules.clip_length_ok(4.0, 15) and not video_rules.clip_length_ok(2.0, 15)
    assert not video_rules.clip_length_ok(40.0, 15)
    assert video_rules.moving_seconds(4.0, 15.0) == 5.0          # kéo chậm tối đa 1,25 lần
    assert video_rules.counted_seconds(False, 15.0, 15.0) == 0.0


def test_dialogue_video_padding_is_not_counted_as_video():
    # 3 đoạn 6 giây; Muse trả 5, 6, 4 giây: video giữa đủ, hai video kia có khung đứng yên chèn thêm
    segs = [{"start": 0, "end": 6}, {"start": 6, "end": 12}, {"start": 12, "end": 18}]
    assert dialogue_video.running_part(segs, [5.0, 6.0, 4.0]) == 15.0
    # video cuối dài hơn đoạn cuối: giữ trọn, đếm trọn
    assert dialogue_video.running_part(segs, [6.0, 6.0, 9.0]) == 21.0
