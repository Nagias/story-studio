"""Cắt viền sáng ở mép clip video Muse.

Muse tự ghép nhiều đoạn bằng ffmpeg trên máy của nó, đôi khi để lại dải trắng ở mép hình (gặp 13/11/2026: 8 clip của
hai vụ, dày 3–30 điểm ảnh, vd vụ xưởng sắt cảnh 007, vụ Khang Cúc Hoa cảnh 040). Đo độ sáng các hàng/cột sát mép ở nhiều
thời điểm; có viền thì cắt khung bên trong (giữ đúng tỉ lệ khung gốc) rồi phóng về cỡ gốc.
"""
import io
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger("story_studio.clip_border")

BRIGHT = 200          # độ sáng trung bình (0–255) của một hàng/cột coi là viền trắng
MAX_BORDER = 80       # không đo xa hơn chừng này điểm ảnh tính từ mép
MIN_BORDER = 3        # viền mỏng hơn thì bỏ qua
MARGIN = 2            # cắt thêm chừng này vào trong cho sạch
SAMPLES = (0.05, 0.18, 0.31, 0.44, 0.57, 0.7, 0.83, 0.97)


class ClipBorderError(RuntimeError):
    """Không đọc được clip để đo hoặc cắt viền."""


def _run(cmd: list[str], what: str) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ClipBorderError(f"Không {what}: {e}") from e
    if proc.returncode != 0:
        raise ClipBorderError(f"Không {what}: {proc.stderr.decode('utf-8', 'ignore')[-300:]}")
    return proc


def _probe(path: Path) -> tuple[int, int, float]:
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                "-of", "default=nw=1", str(path)], "đo clip").stdout.decode("utf-8", "ignore")
    vals = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    try:
        return int(vals["width"]), int(vals["height"]), float(vals["duration"])
    except (KeyError, ValueError) as e:
        raise ClipBorderError(f"Không đọc được cỡ/độ dài clip {path.name}") from e


def _edge(rows: np.ndarray) -> int:
    n = 0
    while n < min(MAX_BORDER, len(rows)) and rows[n].mean() > BRIGHT:
        n += 1
    return n


def border_widths(path: Path) -> tuple[int, int, int, int]:
    """Viền sáng dày nhất (trên, dưới, trái, phải) qua các thời điểm mẫu."""
    path = Path(path)
    _, _, duration = _probe(path)
    worst = [0, 0, 0, 0]
    for f in SAMPLES:
        png = _run(["ffmpeg", "-v", "error", "-ss", f"{duration * f:.2f}", "-i", str(path), "-frames:v", "1",
                    "-f", "image2pipe", "-vcodec", "png", "-"], "trích khung clip").stdout
        if not png:
            continue
        a = np.asarray(Image.open(io.BytesIO(png)).convert("L")).astype(float)
        for i, rows in enumerate((a, a[::-1], a.T, a.T[::-1])):
            worst[i] = max(worst[i], _edge(rows))
    return worst[0], worst[1], worst[2], worst[3]


def crop_box(width: int, height: int, borders: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """(w, h, x, y) của khung cắt nằm trong phần không viền, cùng tỉ lệ với khung gốc, cỡ chẵn."""
    top, bottom, left, right = (b + MARGIN if b else 0 for b in borders)
    x0, y0, iw, ih = left, top, width - left - right, height - top - bottom
    ratio = width / height
    if iw / ih > ratio:
        ch, cw = ih, int(ih * ratio)
    else:
        cw, ch = iw, int(iw / ratio)
    cw, ch = cw - cw % 2, ch - ch % 2
    return cw, ch, x0 + (iw - cw) // 2, y0 + (ih - ch) // 2


def trim_in_place(path: Path, backup_dir: Optional[Path] = None) -> Optional[tuple[int, int, int, int]]:
    """Có viền (>= MIN_BORDER) thì cắt viền, giữ cỡ khung gốc, ghi đè clip (bản cũ chép vào backup_dir nếu có).
    Trả độ dày viền đã cắt, hoặc None nếu không có viền."""
    path = Path(path)
    borders = border_widths(path)
    if max(borders) < MIN_BORDER:
        return None
    width, height, _ = _probe(path)
    cw, ch, x, y = crop_box(width, height, borders)
    if backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)
    tmp = path.with_name(path.stem + ".vien.tmp" + path.suffix)
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vf",
          f"crop={cw}:{ch}:{x}:{y},scale={width}:{height}:flags=lanczos,setsar=1", "-c:v", "libx264", "-crf", "16",
          "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "copy", str(tmp)], "cắt viền clip")
    tmp.replace(path)
    logger.info(f"Cắt viền sáng {path.name}: trên/dưới/trái/phải {borders}")
    return borders
