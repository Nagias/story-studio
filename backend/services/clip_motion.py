"""Đo clip có cử động thật hay chỉ có máy quay lia/zoom trên ảnh tĩnh.

Gặp 09–10/11/2026 (vụ xưởng sắt): app báo 65,5% video là clip Muse, nhưng 48 clip chỉ lia/zoom ảnh, người không cử
động; lần kiểm khi đó so khung hình nên không phân biệt được máy quay với người. Cách đo: lấy mẫu khung hình, ước lượng
chuyển động máy quay giữa hai khung liền nhau (dịch, xoay, phóng to), bù nó đi rồi đo phần còn khác (điểm 0–255,
bỏ viền). Ảnh tĩnh zoom còn lại nhiễu nét vẽ; người đi, quay đầu, giơ tay thì còn lại nhiều hơn.

Điểm thấp chỉ là cảnh báo "nên xem lại", không loại clip: cử động rất nhỏ (người ôm đầu lắc nhẹ) có thể ra 0.

Điểm lưu cạnh clip (`<clip>.motion.json`, theo cỡ và giờ sửa file) để lần dựng sau không đo lại."""
import json
import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("story_studio.clip_motion")

SAMPLE_FPS = 1          # khung mẫu mỗi giây: so hai khung cách nhau 1 giây (cách nhau 0,25 giây thì cử động nhỏ chìm)
WORK_WIDTH = 480        # thu nhỏ trước khi đo (nhanh, bớt nhiễu nén)
BORDER = 24             # bỏ viền sau khi bù máy quay (mép ảnh bị kéo vào)
MIN_FEATURES = 12
STRONG_DIFF = 30        # điểm ảnh khác nhau hơn mức này (0–255, sau khi làm mờ nhẹ) mới tính là "đổi thật"
CUT_PERCENT = 40.0      # cặp khung đổi hơn chừng này phần trăm ảnh là chuyển cảnh trong clip, bỏ qua
# Điểm = phần trăm ảnh đổi thật ở cặp khung "động" thứ 90 (bách phân vị 90): clip chỉ lia/zoom hay đứng hình ra 0.
# Đo 11/11/2026: 48 clip lời thoại cũ vụ xưởng sắt và ảnh tĩnh zoom/lia đều dưới ngưỡng; clip người cử động rõ (ép cử
# động cảnh 20: 7,7; Khang Cúc Hoa cảnh 11: 10,6) trên ngưỡng. Cử động rất nhỏ (người ôm đầu lắc nhẹ) có thể ra 0, nên
# điểm thấp chỉ là "nên xem lại", không loại clip.
REAL_MOTION_MIN = 1.0
CACHE_VERSION = 2


class ClipMotionError(RuntimeError):
    pass


def _frames(path: Path) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ClipMotionError(f"Không mở được video {path.name}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        step = max(1, round(fps / SAMPLE_FPS))
        out, i = [], 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % step == 0:
                h, w = frame.shape[:2]
                small = cv2.resize(frame, (WORK_WIDTH, max(2, round(h * WORK_WIDTH / w))), interpolation=cv2.INTER_AREA)
                out.append(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
            i += 1
    finally:
        cap.release()
    if len(out) < 3:
        raise ClipMotionError(f"Video {path.name} quá ngắn để đo chuyển động ({len(out)} khung mẫu)")
    return out


def _changed_percent(a: np.ndarray, b: np.ndarray) -> float:
    """Phần trăm ảnh đổi thật giữa hai khung sau khi bù chuyển động máy quay (dịch, xoay, phóng to)."""
    h, w = a.shape
    matrix = np.eye(2, 3, dtype=np.float32)
    pts = cv2.goodFeaturesToTrack(a, maxCorners=400, qualityLevel=0.01, minDistance=8)
    if pts is not None and len(pts) >= MIN_FEATURES:
        nxt, status, _ = cv2.calcOpticalFlowPyrLK(a, b, pts, None)
        ok = status.reshape(-1) == 1
        if ok.sum() >= MIN_FEATURES:
            est, _ = cv2.estimateAffinePartial2D(pts[ok], nxt[ok], method=cv2.RANSAC, ransacReprojThreshold=2.0)
            if est is not None:
                matrix = est.astype(np.float32)
    warped = cv2.warpAffine(a, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    diff = cv2.absdiff(cv2.GaussianBlur(warped, (5, 5), 0), cv2.GaussianBlur(b, (5, 5), 0))
    return float((diff[BORDER:h - BORDER, BORDER:w - BORDER] > STRONG_DIFF).mean()) * 100


def measure(path: Path) -> float:
    """Điểm cử động của clip (xem REAL_MOTION_MIN). Bỏ cặp khung chuyển cảnh trong clip."""
    frames = _frames(Path(path))
    changed = [c for c in (_changed_percent(a, b) for a, b in zip(frames, frames[1:])) if c < CUT_PERCENT]
    return float(np.percentile(changed, 90)) if changed else 0.0


def _cache_path(path: Path) -> Path:
    return path.with_name(path.name + ".motion.json")


def motion_score(path: Path) -> float:
    """`measure()` có lưu: đo lại khi clip đổi (cỡ file hoặc giờ sửa khác) hoặc cách đo đổi phiên bản."""
    path = Path(path)
    if not path.is_file():
        raise ClipMotionError(f"Không có clip {path}")
    st = path.stat()
    key = {"size": st.st_size, "mtime": int(st.st_mtime), "version": CACHE_VERSION}
    cache = _cache_path(path)
    try:
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if {k: saved.get(k) for k in key} == key:
            return float(saved["score"])
    except FileNotFoundError:
        pass
    except (ValueError, KeyError, OSError) as e:   # file lưu hỏng: đo lại, ghi đè
        logger.warning(f"Bỏ file điểm chuyển động hỏng {cache.name}: {e}")
    score = measure(path)
    try:
        cache.write_text(json.dumps({**key, "score": round(score, 3)}), encoding="utf-8")
    except OSError as e:   # không ghi được thì lần sau đo lại, điểm vẫn đúng
        logger.warning(f"Không ghi được {cache.name}: {e}")
    return score


def has_real_motion(score: Optional[float]) -> bool:
    return score is not None and score >= REAL_MOTION_MIN
