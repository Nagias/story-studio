"""
Investigation Board Engine (True Crime Corkboard & Causal DAG)
--------------------------------------------------------------
Features:
1. Procedural 1920x1080 Corkboard Canvas:
   - Warm organic cork grain texture with procedural noise and vignette.
   - Beveled mahogany/oak wooden frame with metallic corner brackets and rivets.
2. Fixed-Anchor Grid Layout:
   - Permanent (X, Y) coordinates assigned once (pinned=True) and NEVER recalculated
     in subsequent scenes, guaranteeing visual consistency across the entire video.
   - Grid sized by the total card count: one cell per card, cells separated by a gap, so cards never
     overlap; with many cards every card shrinks by the same metadata["card_scale"].
3. Cumulative Rendering (State = ΔNodes_k + ΔEdges_k):
   - Scene K only displays nodes and edges introduced up to time K.
4. Natural Gravitational Bezier Red Threads:
   - True gravity sag calculation based on Euclidean distance.
   - Multi-layer drawing: drop shadow, 3px crimson yarn fiber, center highlight.
   - Drawn above the cards (below the pushpins) so threads stay visible where they cross a card.
5. High-Resolution Evidence Cards:
   - Polaroid styled cards with subtle seeded tilt angles (-3° to +3°).
   - Node-type badges, detective silhouette placeholders, rubber stamps ("ALIBI", "CONFIRMED", "X").
   - 3D glossy pushpins with metallic needles and specular highlights.
6. 1080p Static Image & 5s Dynamic Animated MP4 Video Clip Generation.
"""

import os
import math
import random
import shutil
import hashlib
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageColor, ImageOps

import config

from models.evidence_schemas import (
    EvidenceNode,
    RelationEdge,
    BoardState,
    FictionalCasePlan,
)

# Canvas Configuration
CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
FRAME_THICKNESS = 36

# Cache for procedural corkboard background
_CORKBOARD_CACHE: Optional[Image.Image] = None

# Badge Color Palettes
NODE_TYPE_PALETTE = {
    "victim": {"bg": (127, 29, 29), "text": (254, 226, 226), "label": "NẠN NHÂN"},
    "suspect": {"bg": (185, 28, 28), "text": (254, 242, 242), "label": "NGHI PHẠM"},
    "weapon": {"bg": (194, 65, 12), "text": (255, 247, 237), "label": "HUNG KHÍ"},
    "clue": {"bg": (4, 120, 87), "text": (236, 253, 245), "label": "MANH MỐI"},
    "forensic_report": {"bg": (29, 78, 216), "text": (239, 246, 255), "label": "PHÁP Y / GIÁM ĐỊNH"},
    "location": {"bg": (67, 56, 202), "text": (238, 242, 255), "label": "HIỆN TRƯỜNG"},
    "timeline_event": {"bg": (75, 85, 99), "text": (243, 244, 246), "label": "DÒNG THỜI GIAN"},
}

# Nhãn huy hiệu tiếng Anh (bảng ghim bản tiếng Anh): thẻ đặt metadata["badge_label"] thì dùng nhãn đó
# thay cho NODE_TYPE_PALETTE[...]["label"] tiếng Việt.
NODE_TYPE_LABELS_EN = {
    "victim": "VICTIM",
    "suspect": "SUSPECT",
    "weapon": "WEAPON",
    "clue": "CLUE",
    "forensic_report": "FORENSICS",
    "location": "SCENE",
    "timeline_event": "TIMELINE",
}

PIN_COLORS = {
    "red": {"base": (220, 38, 38), "shadow": (127, 29, 29)},
    "yellow": {"base": (234, 179, 8), "shadow": (161, 98, 7)},
    "silver": {"base": (203, 213, 225), "shadow": (100, 116, 139)},
    "blue": {"base": (37, 99, 235), "shadow": (30, 58, 138)},
}


# ==============================================================================
# 1. PROCEDURAL CORKBOARD GENERATOR
# ==============================================================================

# Font đóng gói (config.FONTS_DIR); thiếu file thì dùng font Windows như trước. Chữ máy đánh chữ (con dấu "ALIBI"...) giữ
# Courier của Windows.
_BUNDLED_FONTS = {"regular": "BeVietnamPro-Regular.ttf", "bold": "BeVietnamPro-Bold.ttf",
                  "handwriting": "PatrickHand-Regular.ttf"}


def get_font(size: int = 16, bold: bool = False, typewriter: bool = False,
             handwriting: bool = False) -> ImageFont.ImageFont:
    """Font đóng gói nếu có (chữ thường, đậm, viết tay), không thì font hệ thống, cuối cùng là font mặc định của PIL."""
    if not typewriter:
        key = "handwriting" if handwriting else ("bold" if bold else "regular")
        bundled = config.FONTS_DIR / _BUNDLED_FONTS[key]
        if bundled.exists():
            return ImageFont.truetype(str(bundled), size)
    font_candidates = []
    if typewriter:
        font_candidates = ["courbd.ttf", "cour.ttf", "consola.ttf", "arialbd.ttf", "arial.ttf"]
    elif bold:
        font_candidates = ["arialbd.ttf", "segoeuib.ttf", "tahomabd.ttf", "arial.ttf"]
    else:
        font_candidates = ["arial.ttf", "segoeui.ttf", "tahoma.ttf"]

    for name in font_candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def generate_corkboard_background(width: int = CANVAS_WIDTH, height: int = CANVAS_HEIGHT) -> Image.Image:
    """
    Procedurally synthesizes a photo-realistic corkboard texture with:
    - Warm organic cork grain flecks (multi-tone brown/amber).
    - Radial vignette simulating overhead detective desk spotlight.
    - Beveled walnut/oak wood frame with brass corner brackets.
    """
    global _CORKBOARD_CACHE
    if _CORKBOARD_CACHE is not None and _CORKBOARD_CACHE.size == (width, height):
        return _CORKBOARD_CACHE.copy()

    # 1. Base cork tone (warm golden amber cork)
    base_color = (196, 150, 102)
    img = Image.new("RGB", (width, height), base_color)
    draw = ImageDraw.Draw(img)

    # Deterministic seed for reproducible background grain
    rng = random.Random(42)

    # 2. Add thousands of organic cork flecks and cellular variations
    cork_tones = [
        (160, 112, 70),   # dark brown speckle
        (142, 96, 56),    # deep amber grain
        (220, 178, 130),  # light beige fleck
        (235, 195, 150),  # pale cork pore
        (175, 128, 85),   # mid tone
    ]

    for _ in range(35000):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        radius = rng.choice([1, 1, 1, 2, 2, 3])
        tone = rng.choice(cork_tones)
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=tone)

    # Add subtle horizontal fibrous streaks
    for _ in range(800):
        sx = rng.randint(0, width - 40)
        sy = rng.randint(0, height - 5)
        length = rng.randint(8, 35)
        tone = rng.choice([(150, 105, 65), (225, 185, 140)])
        draw.line([sx, sy, sx + length, sy + rng.randint(-1, 1)], fill=tone, width=1)

    # Apply slight Gaussian blur to integrate noise seamlessly
    img = img.filter(ImageFilter.GaussianBlur(radius=0.7))

    # 3. Radial Vignette (darker edges, warm lit center)
    vignette = Image.new("L", (width, height), 255)
    v_draw = ImageDraw.Draw(vignette)
    cx, cy = width / 2.0, height / 2.0
    max_radius = math.hypot(cx, cy)
    for r in range(int(max_radius), 0, -20):
        factor = r / max_radius
        # Center is bright (255), edges darken to ~165
        gray = int(165 + (255 - 165) * (1.0 - factor ** 1.8))
        v_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=gray)

    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=30))
    # Blend vignette into cork image
    img = Image.composite(img, Image.new("RGB", (width, height), (35, 22, 12)), vignette)

    # 4. Wooden Frame (Deep Mahogany / Aged Oak with Bevel)
    t = FRAME_THICKNESS
    draw = ImageDraw.Draw(img)

    # Frame outer wood
    draw.rectangle([0, 0, width, t], fill=(62, 36, 18))  # Top
    draw.rectangle([0, height - t, width, height], fill=(50, 28, 14))  # Bottom
    draw.rectangle([0, 0, t, height], fill=(56, 32, 16))  # Left
    draw.rectangle([width - t, 0, width, height], fill=(45, 25, 12))  # Right

    # Bevel highlight on inner frame edges
    draw.line([t, t, width - t, t], fill=(110, 68, 38), width=3)  # Inner top highlight
    draw.line([t, t, t, height - t], fill=(95, 58, 32), width=3)   # Inner left highlight
    draw.line([t, height - t, width - t, height - t], fill=(28, 14, 6), width=3)  # Inner bottom shadow
    draw.line([width - t, t, width - t, height - t], fill=(24, 12, 5), width=3)   # Inner right shadow

    # Inner corkboard drop shadow
    shadow_w = 12
    for i in range(shadow_w):
        s_rect = [t + i, t + i, width - t - i, height - t - i]
        # Darkening top & left borders
        draw.line([s_rect[0], s_rect[1], s_rect[2], s_rect[1]], fill=(30, 18, 10), width=1)
        draw.line([s_rect[0], s_rect[1], s_rect[0], s_rect[3]], fill=(30, 18, 10), width=1)

    # 5. Brass Corner Brackets & Rivets
    bracket_size = 70
    bracket_gold = (180, 140, 50)
    bracket_highlight = (230, 195, 95)
    bracket_dark = (110, 80, 20)

    corners = [
        (0, 0, 1, 1),
        (width - 1, 0, -1, 1),
        (0, height - 1, 1, -1),
        (width - 1, height - 1, -1, -1),
    ]

    for ox, oy, dx, dy in corners:
        # L-shaped brass bracket
        # Arm 1: along horizontal
        x1 = ox
        y1 = oy
        x2 = ox + dx * bracket_size
        y2 = oy + dy * (t + 10)
        draw.rectangle([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)], fill=bracket_gold)

        # Arm 2: along vertical
        x3 = ox
        y3 = oy
        x4 = ox + dx * (t + 10)
        y4 = oy + dy * bracket_size
        draw.rectangle([min(x3, x4), min(y3, y4), max(x3, x4), max(y3, y4)], fill=bracket_gold)

        # Brass highlight and bevel
        draw.rectangle(
            [min(ox, ox + dx * 20), min(oy, oy + dy * 20), max(ox, ox + dx * 20), max(oy, oy + dy * 20)],
            fill=bracket_highlight
        )

        # Brass rivets (screw heads)
        rivet_points = [
            (ox + dx * (t // 2 + 5), oy + dy * (bracket_size - 18)),
            (ox + dx * (bracket_size - 18), oy + dy * (t // 2 + 5)),
        ]
        for rx, ry in rivet_points:
            draw.ellipse([rx - 4, ry - 4, rx + 4, ry + 4], fill=bracket_dark)
            draw.ellipse([rx - 3, ry - 3, rx + 3, ry + 3], fill=bracket_highlight)
            draw.line([rx - 2, ry, rx + 2, ry], fill=(40, 30, 10), width=1)

    _CORKBOARD_CACHE = img.copy()
    return img


# ==============================================================================
# 2. FIXED-ANCHOR GRID LAYOUT
# ==============================================================================

# Thẻ ở cỡ gốc (tỉ lệ 1). Bảng nhiều thẻ thì mọi thẻ cùng được thu nhỏ theo metadata["card_scale"].
CARD_WIDTH = 250
CARD_HEIGHT = 310
PHOTO_WIDTH = 216
PHOTO_HEIGHT = 186

# Vùng đặt thẻ (x1, y1, x2, y2): trừ khung gỗ, phía trên chừa chỗ cho tiêu đề.
BOARD_SAFE_AREA = (60, 96, 1860, 1030)
BOARD_CENTER = ((BOARD_SAFE_AREA[0] + BOARD_SAFE_AREA[2]) / 2, (BOARD_SAFE_AREA[1] + BOARD_SAFE_AREA[3]) / 2)
CARD_GAP_X = 28             # khe hở tối thiểu giữa hai ô lưới cạnh nhau, đủ để thấy sợi chỉ và mặt bần
CARD_GAP_Y = 22
MAX_TILT_DEG = 3.2          # độ nghiêng lớn nhất mà compute_deterministic_tilt sinh ra
MAX_JITTER = 40             # thẻ lệch khỏi tâm ô tối đa chừng này px cho tự nhiên, nhưng không bao giờ ra khỏi ô
_PINNED_MARGIN = 8          # khe hở tối thiểu với thẻ đã ghim từ trước

# Điểm mà từng loại thẻ muốn đứng gần (khung 1920x1080): nghi phạm hàng trên, nạn nhân giữa bảng, hung khí và
# giám định hàng dưới, hiện trường bên trái. Loại khác đứng gần giữa bảng. Thẻ lấy ô trống gần điểm đó nhất.
# Nghi phạm đứng chéo phía trên nạn nhân chứ không thẳng cột: sợi chỉ nghi phạm -> nạn nhân (quan hệ hay gặp nhất)
# mà chạy dọc thì đè ngay lên tên thẻ nghi phạm.
TYPE_PREFERRED_POINTS = {
    "victim": (960, 480),
    "suspect": (560, 250),
    "weapon": (700, 790),
    "forensic_report": (1220, 790),
    "location": (300, 560),
    "timeline_event": (960, 830),
}
# Thẻ hiện cùng một cảnh: loại đứng trước được chọn ô trước.
TYPE_LAYOUT_PRIORITY = {"victim": 0, "suspect": 1, "weapon": 2, "forensic_report": 3, "location": 4, "timeline_event": 5}

Rect = Tuple[float, float, float, float]


def _tilted_box(scale: float, tilt_deg: float) -> Tuple[float, float]:
    """(rộng, cao) của khung bao thẻ đã thu nhỏ `scale` và nghiêng `tilt_deg` độ."""
    rad = math.radians(abs(tilt_deg))
    w = CARD_WIDTH * math.cos(rad) + CARD_HEIGHT * math.sin(rad)
    h = CARD_HEIGHT * math.cos(rad) + CARD_WIDTH * math.sin(rad)
    return w * scale, h * scale


def _rect_at(cx: float, cy: float, w: float, h: float) -> Rect:
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def _rects_overlap(a: Rect, b: Rect, margin: float = 0.0) -> bool:
    return a[0] < b[2] + margin and b[0] < a[2] + margin and a[1] < b[3] + margin and b[1] < a[3] + margin


def card_scale(node: EvidenceNode) -> float:
    """Tỉ lệ thu nhỏ thẻ do assign_fixed_anchor_layout ghi vào metadata["card_scale"]; thẻ không có thì cỡ gốc."""
    try:
        scale = float((node.metadata or {}).get("card_scale", 1.0))
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(scale):
        return 1.0
    return min(1.0, max(0.2, scale))


def choose_board_grid(count: int, tilt_deg: float = MAX_TILT_DEG) -> Tuple[int, int, float]:
    """(số cột, số hàng, tỉ lệ thẻ) để `count` thẻ nằm trong vùng đặt thẻ, mỗi thẻ một ô, không thẻ nào chạm nhau.

    Chọn lưới cho thẻ to nhất (không quá cỡ gốc). Các lưới cho thẻ gần to bằng nhau thì lấy lưới có tỉ lệ
    cột/hàng gần với dáng bảng nhất, để thẻ trải đều thay vì xếp một hàng dài.
    """
    count = max(1, count)
    x1, y1, x2, y2 = BOARD_SAFE_AREA
    area_w, area_h = x2 - x1, y2 - y1
    box_w, box_h = _tilted_box(1.0, tilt_deg)
    ideal_ratio = (area_w / box_w) / (area_h / box_h)
    options = []
    for rows in range(1, count + 1):
        cols = math.ceil(count / rows)
        if math.ceil(count / cols) < rows:
            continue                                # hàng cuối trống hẳn: đã có lưới ít hàng hơn cùng số cột
        cell_w = (area_w - (cols - 1) * CARD_GAP_X) / cols
        cell_h = (area_h - (rows - 1) * CARD_GAP_Y) / rows
        scale = min(1.0, cell_w / box_w, cell_h / box_h)
        if scale > 0:
            options.append((scale, cols, rows))
    if not options:                                 # quá nhiều thẻ, không lưới nào còn chỗ: thẻ nhỏ nhất, chấp nhận chạm
        side = math.ceil(math.sqrt(count))
        return side, side, 0.2
    best = max(scale for scale, _, _ in options)
    scale, cols, rows = min(
        (o for o in options if o[0] >= best - 0.03),
        key=lambda o: (abs(o[1] / o[2] - ideal_ratio), -o[0]),
    )
    return cols, rows, scale


def _grid_cells(cols: int, rows: int) -> List[Rect]:
    """Các ô lưới (x1, y1, x2, y2) phủ vùng đặt thẻ, cách nhau CARD_GAP_X/CARD_GAP_Y; thứ tự trái->phải, trên->dưới."""
    x1, y1, x2, y2 = BOARD_SAFE_AREA
    cell_w = max(1.0, (x2 - x1 - (cols - 1) * CARD_GAP_X) / cols)
    cell_h = max(1.0, (y2 - y1 - (rows - 1) * CARD_GAP_Y) / rows)
    cells = []
    for r in range(rows):
        for c in range(cols):
            cx1 = x1 + c * (cell_w + CARD_GAP_X)
            cy1 = y1 + r * (cell_h + CARD_GAP_Y)
            cells.append((cx1, cy1, cx1 + cell_w, cy1 + cell_h))
    return cells


def _jitter(node_id: str, slack: float, axis: str) -> float:
    """Độ lệch cố định theo id thẻ, trong khoảng ±min(MAX_JITTER, slack/2): thẻ lệch nhẹ nhưng vẫn nằm trọn trong ô."""
    h = int(hashlib.md5(f"{node_id}:{axis}".encode("utf-8")).hexdigest()[:6], 16)
    unit = (h % 2001) / 1000.0 - 1.0
    return unit * min(MAX_JITTER, max(0.0, slack) / 2)


def _is_placed(node: EvidenceNode) -> bool:
    """Thẻ đã có chỗ cố định thì không bao giờ bị xếp lại.

    (0, 0) và toạ độ mặc định (960, 540) của EvidenceNode không tính là đã có chỗ (mọi loại thẻ, kể cả nạn nhân),
    trừ khi chính hàm xếp chỗ đã đặt thẻ ở đó (có metadata["card_scale"]).
    """
    if not node.pinned:
        return False
    if "card_scale" in (node.metadata or {}):
        return True
    return (node.x, node.y) not in ((0, 0), (960, 540))


def assign_fixed_anchor_layout(
    nodes: List[EvidenceNode],
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> List[EvidenceNode]:
    """
    Gán toạ độ cố định (x, y) cho từng thẻ; thẻ đã có chỗ (xem _is_placed) giữ nguyên, không bao giờ bị dời.

    - Lưới tính theo tổng số thẻ (choose_board_grid): mỗi thẻ một ô, ô cách nhau một khe, nên không thẻ nào đè thẻ
      nào. Nhiều thẻ thì mọi thẻ cùng thu nhỏ; tỉ lệ ghi vào metadata["card_scale"], nên gọi một lần với toàn bộ thẻ
      của cả video thì thẻ không đổi cỡ giữa các cảnh.
    - Thứ tự chọn ô: cảnh hiện sớm trước, cùng cảnh thì theo TYPE_LAYOUT_PRIORITY (nạn nhân, nghi phạm...). Mỗi thẻ
      lấy ô trống gần TYPE_PREFERRED_POINTS của loại mình nhất, rồi lệch nhẹ trong ô theo id.
    - Đặt pinned=True cho mọi thẻ. Danh sách trả về giữ nguyên thứ tự.
    """

    # Deterministic rotation based on node id hash
    def compute_deterministic_tilt(node_id: str) -> float:
        h = int(hashlib.md5(node_id.encode("utf-8")).hexdigest()[:6], 16)
        # Range -3.2 to +3.2 degrees
        return ((h % 65) - 32) * 0.1

    for node in nodes:
        # Compute deterministic tilt for natural polaroid aesthetic
        if abs(node.rotation_deg) < 0.01:
            node.rotation_deg = compute_deterministic_tilt(node.id)

    placed = [n for n in nodes if _is_placed(n)]
    todo = [n for n in nodes if not _is_placed(n)]
    for node in placed:
        node.pinned = True
    if not todo:
        return nodes

    tilt = max([MAX_TILT_DEG] + [abs(n.rotation_deg) for n in nodes])
    taken: List[Rect] = [_rect_at(n.x, n.y, *_tilted_box(card_scale(n), n.rotation_deg)) for n in placed]
    # Thẻ ghim từ trước có thể nằm lệch lưới và chặn vài ô: lưới thêm ô (thẻ nhỏ đi) tới khi đủ ô trống cho thẻ mới.
    grid_size = len(nodes)
    while True:
        cols, rows, scale = choose_board_grid(grid_size, tilt)
        cells = _grid_cells(cols, rows)
        blocked = {i for i, cell in enumerate(cells) if any(_rects_overlap(cell, t, _PINNED_MARGIN) for t in taken)}
        if len(cells) - len(blocked) >= len(todo) or scale <= 0.2:
            break
        grid_size += 1
    used_cells: set = set(blocked)

    todo.sort(key=lambda n: (n.appearance_scene_order, TYPE_LAYOUT_PRIORITY.get(n.node_type, len(TYPE_LAYOUT_PRIORITY))))
    for node in todo:
        preferred = TYPE_PREFERRED_POINTS.get(node.node_type, BOARD_CENTER)
        w, h = _tilted_box(scale, node.rotation_deg)

        def distance(i: int) -> float:
            cx1, cy1, cx2, cy2 = cells[i]
            return math.hypot((cx1 + cx2) / 2 - preferred[0], (cy1 + cy2) / 2 - preferred[1])

        free = [i for i in range(len(cells)) if i not in used_cells]
        if free:
            i = min(free, key=lambda i: (distance(i), i))
            used_cells.add(i)
            cx1, cy1, cx2, cy2 = cells[i]
            x = (cx1 + cx2) / 2 + _jitter(node.id, (cx2 - cx1) - w, "x")
            y = (cy1 + cy2) / 2 + _jitter(node.id, (cy2 - cy1) - h, "y")
        else:                                       # quá nhiều thẻ (thẻ đã nhỏ hết mức): ô hợp nhất, chấp nhận chạm
            cx1, cy1, cx2, cy2 = cells[min(range(len(cells)), key=lambda i: (distance(i), i))]
            x, y = (cx1 + cx2) / 2, (cy1 + cy2) / 2

        node.x, node.y = int(round(x)), int(round(y))
        node.pinned = True
        node.metadata["card_scale"] = round(scale, 4)

    return nodes


# ==============================================================================
# 3. POLAROID CARD & RUBBER STAMP RENDERING
# ==============================================================================


def render_node_placeholder_icon(draw: ImageDraw.ImageDraw, rect: List[int], node_type: str, label: str):
    """Draws a dramatic neo-noir icon silhouette when no custom image is supplied."""
    x1, y1, x2, y2 = rect
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    # Dark background with spotlight circle
    draw.rectangle(rect, fill=(24, 28, 36))
    draw.ellipse([cx - 55, cy - 55, cx + 55, cy + 55], fill=(36, 44, 58))

    if node_type == "victim":
        # Skull or victim tape silhouette
        draw.ellipse([cx - 26, cy - 35, cx + 26, cy + 15], fill=(220, 220, 225))
        draw.rectangle([cx - 18, cy + 8, cx + 18, cy + 28], fill=(220, 220, 225))
        # Eye sockets
        draw.ellipse([cx - 16, cy - 10, cx - 6, cy], fill=(24, 28, 36))
        draw.ellipse([cx + 6, cy - 10, cx + 16, cy], fill=(24, 28, 36))
        # Nose cavity
        draw.polygon([(cx, cy + 4), (cx - 4, cy + 11), (cx + 4, cy + 11)], fill=(24, 28, 36))
        # Teeth lines
        for dx in [-10, -5, 0, 5, 10]:
            draw.line([cx + dx, cy + 16, cx + dx, cy + 24], fill=(24, 28, 36), width=2)

    elif node_type == "suspect":
        # Fedora hat and mysterious trenchcoat silhouette
        # Hat brim
        draw.ellipse([cx - 48, cy - 25, cx + 48, cy - 12], fill=(15, 18, 22))
        # Hat crown
        draw.rectangle([cx - 28, cy - 46, cx + 28, cy - 20], fill=(15, 18, 22))
        draw.line([cx - 28, cy - 46, cx + 28, cy - 46], fill=(195, 30, 30), width=3)  # Red ribbon on hat
        # Collar and silhouette shoulders
        draw.polygon([(cx - 42, cy + 45), (cx - 14, cy + 5), (cx, cy + 20), (cx + 14, cy + 5), (cx + 42, cy + 45)], fill=(15, 18, 22))
        # Glowing mysterious eyes under hat
        draw.ellipse([cx - 14, cy - 8, cx - 6, cy - 4], fill=(250, 204, 21))
        draw.ellipse([cx + 6, cy - 8, cx + 14, cy - 4], fill=(250, 204, 21))

    elif node_type == "weapon":
        # Knife silhouette with dramatic crimson reflection
        blade = [(cx - 25, cy - 35), (cx + 15, cy + 20), (cx + 25, cy + 12), (cx - 15, cy - 40)]
        draw.polygon(blade, fill=(210, 215, 225))
        # Blood splatter highlight on tip
        draw.ellipse([cx + 8, cy + 8, cx + 26, cy + 26], fill=(185, 28, 28))
        # Handle
        draw.line([cx - 18, cy - 36, cx - 38, cy - 54], fill=(45, 30, 20), width=9)

    elif node_type == "forensic_report":
        # Document sheet with magnifying glass
        draw.rectangle([cx - 30, cy - 35, cx + 18, cy + 30], fill=(245, 245, 240))
        for line_y in range(cy - 25, cy + 25, 9):
            draw.line([cx - 24, line_y, cx + 12, line_y], fill=(160, 160, 165), width=2)
        # Magnifying glass
        draw.ellipse([cx - 2, cy - 10, cx + 32, cy + 24], outline=(200, 160, 40), width=4)
        draw.line([cx + 26, cy + 20, cx + 44, cy + 38], fill=(120, 60, 20), width=6)

    elif node_type == "location":
        # Silhouette buildings / crime scene tape
        draw.rectangle([cx - 40, cy - 10, cx - 15, cy + 40], fill=(15, 20, 30))
        draw.rectangle([cx - 10, cy - 30, cx + 20, cy + 40], fill=(20, 25, 38))
        draw.rectangle([cx + 25, cy + 5, cx + 45, cy + 40], fill=(15, 20, 30))
        # Glowing windows
        draw.rectangle([cx - 5, cy - 20, cx + 2, cy - 12], fill=(245, 158, 11))
        draw.rectangle([cx + 8, cy - 20, cx + 15, cy - 12], fill=(245, 158, 11))

    else:
        # Default Clue / Magnifying Glass
        draw.ellipse([cx - 25, cy - 25, cx + 15, cy + 15], outline=(220, 180, 40), width=5)
        draw.line([cx + 10, cy + 10, cx + 35, cy + 35], fill=(160, 80, 30), width=7)
        draw.ellipse([cx - 10, cy - 10, cx, cy], fill=(255, 255, 255))


_LABEL_SIZES = (30, 26, 22)          # cỡ chữ nhãn thẻ, thử từ lớn tới nhỏ
_LABEL_MAX_W = CARD_WIDTH - 24


def _card_label_lines(draw: ImageDraw.ImageDraw, label: str) -> tuple[list[str], ImageFont.ImageFont]:
    """Ngắt nhãn thành tối đa 2 dòng vừa thẻ, chữ to nhất có thể; vẫn không vừa thì cắt dòng 2, thêm "…"."""
    words = label.split()
    font = None
    for size in _LABEL_SIZES:
        font = get_font(size=size, handwriting=True)
        lines: list[str] = []
        for word in words:
            if lines and draw.textlength(f"{lines[-1]} {word}", font=font) <= _LABEL_MAX_W:
                lines[-1] = f"{lines[-1]} {word}"
            else:
                lines.append(word)
        if len(lines) <= 2 and all(draw.textlength(line, font=font) <= _LABEL_MAX_W for line in lines):
            return lines, font
    lines = lines[:2]
    while lines and draw.textlength(lines[-1] + "…", font=font) > _LABEL_MAX_W and len(lines[-1]) > 1:
        lines[-1] = lines[-1][:-1]
    lines[-1] = lines[-1].rstrip() + "…"
    return lines, font


def render_polaroid_card(node: EvidenceNode) -> Image.Image:
    """
    Renders an individual Polaroid card with:
    - Card border, photo area (or silhouette icon), title, and type badge.
    - Rubber stamp overlay if stamped ("ALIBI", "CONFIRMED", "ELIMINATED", "X").
    - Top-center pushpin with 3D gradient highlight.
    """
    # Create card base with transparent padding for rotation
    card = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    # 1. Polaroid paper background (warm off-white)
    card_paper_color = (250, 248, 242, 255)
    draw.rounded_rectangle([0, 0, CARD_WIDTH - 1, CARD_HEIGHT - 1], radius=6, fill=card_paper_color)

    # Subtle aged paper border line
    draw.rounded_rectangle([0, 0, CARD_WIDTH - 1, CARD_HEIGHT - 1], radius=6, outline=(215, 208, 195, 255), width=1)

    # 2. Photo Area (Inset)
    px1 = 17
    py1 = 20
    px2 = px1 + PHOTO_WIDTH
    py2 = py1 + PHOTO_HEIGHT

    loaded_photo = False
    if node.image_path and os.path.exists(node.image_path):
        try:
            with Image.open(node.image_path) as pimg:
                pimg_rgb = pimg.convert("RGBA")
                # cắt cho vừa khung ảnh thẻ, không kéo méo (ảnh cảnh 16:9 vào khung gần vuông)
                pimg_resized = ImageOps.fit(pimg_rgb, (PHOTO_WIDTH, PHOTO_HEIGHT), Image.Resampling.LANCZOS)
                card.paste(pimg_resized, (px1, py1))
                loaded_photo = True
        except Exception:
            loaded_photo = False

    if not loaded_photo:
        render_node_placeholder_icon(draw, [px1, py1, px2, py2], node.node_type, node.label)

    # Photo inner inset border
    draw.rectangle([px1, py1, px2, py2], outline=(70, 70, 70, 180), width=1)

    # 3. Node Type Badge (Pill)
    palette = NODE_TYPE_PALETTE.get(node.node_type, NODE_TYPE_PALETTE["clue"])
    badge_text = str((node.metadata or {}).get("badge_label") or palette["label"])
    badge_font = get_font(size=12, bold=True)
    badge_w = int(draw.textlength(badge_text, font=badge_font)) + 14
    badge_h = 20
    bx1 = px1 + 6
    by1 = py1 + 6
    draw.rounded_rectangle([bx1, by1, bx1 + badge_w, by1 + badge_h], radius=4, fill=(*palette["bg"], 235))
    draw.text((bx1 + 7, by1 + 2), badge_text, font=badge_font, fill=palette["text"])

    # 4. Nhãn thẻ: chữ viết tay to, tối đa 2 dòng (gặp 26/10/2026: chữ Courier 14 px cắt ở 26 ký tự, xem video không đọc nổi)
    label_lines, title_font = _card_label_lines(draw, node.label.strip())
    ty = py2 + 8
    for line in label_lines:
        tw = int(draw.textlength(line, font=title_font))
        draw.text(((CARD_WIDTH - tw) // 2, ty), line, font=title_font, fill=(28, 28, 30))
        ty += int(title_font.size * 1.12) if hasattr(title_font, "size") else 26

    # Optional sub-description line
    if node.description:
        sub_desc = node.description.strip()
        if len(sub_desc) > 34:
            sub_desc = sub_desc[:32] + ".."
        sub_font = get_font(size=11, bold=False)
        sw = int(draw.textlength(sub_desc, font=sub_font))
        sx = (CARD_WIDTH - sw) // 2
        draw.text((sx, ty + 20), sub_desc, font=sub_font, fill=(90, 90, 95))

    # 5. Rubber Stamp Overlay ("ALIBI", "CONFIRMED", "ELIMINATED", "X")
    if node.stamp:
        stamp_text = node.stamp.upper().strip()
        stamp_img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(stamp_img)

        stamp_color = (220, 38, 38, 235)  # Crimson stamp default
        if stamp_text == "ALIBI":
            stamp_color = (22, 163, 74, 235)  # Green for verified alibi
        elif stamp_text == "CONFIRMED":
            stamp_color = (220, 38, 38, 245)

        s_font = get_font(size=28, bold=True, typewriter=True)
        stw = int(s_draw.textlength(stamp_text, font=s_font))
        sth = 32

        scx = CARD_WIDTH // 2
        scy = py1 + PHOTO_HEIGHT // 2

        pad_x = 12
        pad_y = 6
        rect_stamp = [scx - stw // 2 - pad_x, scy - sth // 2 - pad_y, scx + stw // 2 + pad_x, scy + sth // 2 + pad_y]

        # Double-lined stamp border with grunge look
        s_draw.rectangle(rect_stamp, outline=stamp_color, width=3)
        s_draw.rectangle(
            [rect_stamp[0] + 3, rect_stamp[1] + 3, rect_stamp[2] - 3, rect_stamp[3] - 3],
            outline=stamp_color,
            width=1
        )
        s_draw.text((scx - stw // 2, scy - sth // 2 - 2), stamp_text, font=s_font, fill=stamp_color)

        # Rotate stamp by -18 degrees
        stamp_rotated = stamp_img.rotate(18, resample=Image.Resampling.BICUBIC, center=(scx, scy))
        card = Image.alpha_composite(card, stamp_rotated)

    return card


def render_pushpin(color_name: str = "red", radius: int = 12) -> Image.Image:
    """
    Renders a photo-realistic 3D pushpin with glossy spherical reflection and cast shadow.
    """
    size = radius * 4
    pin_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(pin_img)

    cx = size // 2
    cy = size // 2

    # Drop shadow cast by pin
    draw.ellipse([cx - radius + 3, cy - radius + 4, cx + radius + 3, cy + radius + 4], fill=(0, 0, 0, 90))

    # Metallic needle tip visible beneath pin
    draw.line([cx, cy, cx, cy + radius + 3], fill=(120, 120, 125, 255), width=2)

    # Pin head base sphere
    palette = PIN_COLORS.get(color_name, PIN_COLORS["red"])
    base_color = palette["base"]
    shadow_color = palette["shadow"]

    # Shaded base
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(*shadow_color, 255))
    draw.ellipse([cx - radius + 1, cy - radius + 1, cx + radius - 1, cy + radius - 1], fill=(*base_color, 255))

    # 3D specular highlight sphere (gloss reflection)
    hl_x = cx - radius // 3
    hl_y = cy - radius // 3
    hl_r = max(2, radius // 3)
    draw.ellipse([hl_x - hl_r, hl_y - hl_r, hl_x + hl_r, hl_y + hl_r], fill=(255, 255, 255, 230))
    # Secondary tiny highlight dot
    draw.point((hl_x - 1, hl_y - 1), fill=(255, 255, 255, 255))

    return pin_img


# ==============================================================================
# 4. RED THREAD (BEZIER WITH GRAVITATIONAL SAG)
# ==============================================================================

def compute_bezier_points(
    p0: Tuple[float, float],
    p2: Tuple[float, float],
    steps: int = 48,
    sag_factor: float = 0.13,
) -> List[Tuple[float, float]]:
    """
    Calculates points along a natural gravitational sagging Bezier curve between P0 and P2.
    The gravity sag is scaled proportionally to Euclidean distance.
    """
    x1, y1 = p0
    x2, y2 = p2
    dist = math.hypot(x2 - x1, y2 - y1)

    # Natural gravitational catenary approximation via quadratic Bezier
    sag = min(115.0, max(25.0, dist * sag_factor))
    mx = (x1 + x2) / 2.0
    my = (y1 + y2) / 2.0 + sag

    points: List[Tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / float(steps)
        # B(t) = (1-t)^2 * P0 + 2*(1-t)*t * P1 + t^2 * P2
        bx = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * mx + t ** 2 * x2
        by = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * my + t ** 2 * y2
        points.append((bx, by))

    return points


def draw_red_thread(
    canvas_draw: ImageDraw.ImageDraw,
    shadow_draw: ImageDraw.ImageDraw,
    p0: Tuple[float, float],
    p2: Tuple[float, float],
    color_hex: str = "#dc2626",
    progress: float = 1.0,
    label: Optional[str] = None,
    label_avoid: Optional[List[Rect]] = None,
):
    """
    Draws a realistic yarn/thread line with:
    - Drop shadow (two soft strokes, no blur needed) on whatever lies under the thread: cork or cards.
    - 3px crimson cord body.
    - 1px lighter core fiber reflection.
    - Animated progression support (progress from 0.0 to 1.0).
    The thread is drawn above the cards (see render_board_image), so it stays visible where it crosses a card.
    `label_avoid`: card/tag rectangles the tag should not cover; the placed tag is appended to it.
    """
    raw_points = compute_bezier_points(p0, p2, steps=50)

    # Slice points according to animated drawing progress
    num_pts = max(2, int(len(raw_points) * max(0.01, min(1.0, progress))))
    active_points = raw_points[:num_pts]

    # 1. Thread Drop Shadow (offset down by 5px): wide faint stroke + narrow darker core
    shadow_points = [(x + 2, y + 5) for (x, y) in active_points]
    for width, alpha in ((7, 40), (3, 75)):
        for i in range(len(shadow_points) - 1):
            shadow_draw.line([shadow_points[i], shadow_points[i + 1]], fill=(15, 8, 4, alpha), width=width)

    # 2. Main Red Thread Body
    c = ImageColor.getrgb(color_hex) if color_hex.startswith("#") else (220, 38, 38)
    for i in range(len(active_points) - 1):
        canvas_draw.line([active_points[i], active_points[i + 1]], fill=(*c, 255), width=3)

    # 3. Inner fiber highlight (faint pinkish-white specular reflection)
    highlight_color = (254, 202, 202, 190)
    for i in range(len(active_points) - 1):
        canvas_draw.line([active_points[i], active_points[i + 1]], fill=highlight_color, width=1)

    # 4. Optional Evidence Thread Tag
    if label and progress >= 0.95:
        tag_font = get_font(size=15, bold=True)
        tw = int(canvas_draw.textlength(label, font=tag_font)) + 12
        th = 24
        tx, ty = _label_spot(active_points, tw, th, label_avoid)
        tag_rect = (tx - tw // 2, ty - th // 2, tx + tw // 2, ty + th // 2)
        # Paper tag background
        canvas_draw.rectangle(list(tag_rect), fill=(255, 253, 235), outline=(140, 110, 60))
        canvas_draw.text((tx - tw // 2 + 5, ty - th // 2 + 2), label, font=tag_font, fill=(30, 25, 20))
        if label_avoid is not None:
            label_avoid.append(tag_rect)            # nhãn của sợi sau né nhãn này


def _overlap_area(a: Rect, b: Rect) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _label_spot(points: List[Tuple[float, float]], tag_w: int, tag_h: int,
                avoid: Optional[List[Rect]]) -> Tuple[int, int]:
    """Chỗ đặt nhãn trên đoạn giữa sợi chỉ (20%..80%): chỗ đè lên thẻ và nhãn khác ít nhất, hoà thì gần giữa sợi nhất.
    Chỉ nằm trên thẻ nên nhãn đặt bừa ở giữa sợi dễ che mất tên thẻ."""
    mid = len(points) // 2
    if not avoid:
        return int(points[mid][0]), int(points[mid][1])
    candidates = range(int(len(points) * 0.2), int(len(points) * 0.8) + 1)
    best = min(
        candidates,
        key=lambda i: (
            sum(_overlap_area(_rect_at(points[i][0], points[i][1], tag_w, tag_h), r) for r in avoid),
            abs(i - mid),
        ),
    )
    return int(points[best][0]), int(points[best][1])


# ==============================================================================
# 5. CUMULATIVE STATE CALCULATOR
# ==============================================================================

def get_cumulative_board_state(plan: FictionalCasePlan, scene_order: int) -> BoardState:
    """
    Computes cumulative board snapshot at scene K:
    - Visible nodes: all nodes with appearance_scene_order <= K.
    - Visible edges: all edges with appearance_scene_order <= K AND both endpoint nodes visible.
    - Delta nodes/edges: items specifically debuting in scene K.
    """
    visible_nodes = [n for n in plan.nodes if n.appearance_scene_order <= scene_order]
    visible_node_ids = {n.id for n in visible_nodes}

    visible_edges = [
        e for e in plan.edges
        if e.appearance_scene_order <= scene_order and e.source_id in visible_node_ids and e.target_id in visible_node_ids
    ]

    delta_nodes = [n for n in plan.nodes if n.appearance_scene_order == scene_order]
    delta_edges = [
        e for e in plan.edges
        if e.appearance_scene_order == scene_order and e.source_id in visible_node_ids and e.target_id in visible_node_ids
    ]

    return BoardState(
        scene_order=scene_order,
        title=f"Hồ Sơ Điều Tra - Phân Cảnh {scene_order}",
        cumulative_nodes=visible_nodes,
        cumulative_edges=visible_edges,
        delta_nodes=delta_nodes,
        delta_edges=delta_edges,
        canvas_width=CANVAS_WIDTH,
        canvas_height=CANVAS_HEIGHT,
    )


# ==============================================================================
# 6. STATIC IMAGE RENDERER
# ==============================================================================

def _card_image(node: EvidenceNode) -> Image.Image:
    """Thẻ đã thu nhỏ theo card_scale và nghiêng theo rotation_deg (expand=True), tâm ảnh đặt tại (node.x, node.y)."""
    card = render_polaroid_card(node)
    scale = card_scale(node)
    if scale < 0.999:
        size = (max(1, round(CARD_WIDTH * scale)), max(1, round(CARD_HEIGHT * scale)))
        card = card.resize(size, Image.Resampling.LANCZOS)
    return card.rotate(node.rotation_deg, resample=Image.Resampling.BICUBIC, expand=True)


def _paste_origin(node: EvidenceNode, card_img: Image.Image) -> Tuple[int, int]:
    return node.x - card_img.width // 2, node.y - card_img.height // 2


def card_footprint(node: EvidenceNode) -> Tuple[int, int, int, int]:
    """Vùng (x1, y1, x2, y2) mà thẻ thật sự phủ trên bảng (phần ảnh thẻ có alpha > 0), đúng như render_board_image dán."""
    card_img = _card_image(node)
    left, top = _paste_origin(node, card_img)
    bbox = card_img.getchannel("A").getbbox() or (0, 0, 0, 0)
    return left + bbox[0], top + bbox[1], left + bbox[2], top + bbox[3]


def _pin_position(node: EvidenceNode) -> Tuple[float, float]:
    """Toạ độ đinh ghim: giữa mép trên của thẻ (chưa nghiêng), cách mép 12 px ở cỡ gốc, xoay theo thẻ."""
    scale = card_scale(node)
    local_dx = 0.0
    local_dy = -(CARD_HEIGHT * scale / 2.0) + 12.0 * scale
    rad = math.radians(-node.rotation_deg)
    return (node.x + (local_dx * math.cos(rad) - local_dy * math.sin(rad)),
            node.y + (local_dx * math.sin(rad) + local_dy * math.cos(rad)))


def _star_points(cx: float, cy: float, r_outer: float) -> List[Tuple[float, float]]:
    r_inner = r_outer * 0.42
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        r = r_outer if i % 2 == 0 else r_inner
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


def _missing_glyphs(font, text: str) -> set:
    """Ký tự trong `text` mà font không có glyph: PIL vẽ chúng thành ô vuông .notdef, giống hệt ký tự U+E000."""
    def signature(ch: str):
        left, top, right, bottom = font.getbbox(ch)
        img = Image.new("L", (max(1, right - left), max(1, bottom - top)), 0)
        ImageDraw.Draw(img).text((-left, -top), ch, font=font, fill=255)
        return img.size, img.tobytes()

    try:
        notdef = signature("\ue000")
        return {ch for ch in set(text) if not ch.isspace() and signature(ch) == notdef}
    except Exception:
        return set()


def title_banner_text_and_font(title: str):
    """Chữ in trên băng tiêu đề và font dùng cho nó. Font máy đánh chữ thiếu glyph nào thì đổi sang font đậm thường;
    hai ngôi sao hai bên vẽ bằng đa giác vì font Courier/Arial của Windows không có glyph "★" (hiện thành ô vuông)."""
    text = " ".join(str(title or "").upper().split())
    font = get_font(size=24, bold=True, typewriter=True)
    if font is not None and _missing_glyphs(font, text):
        fallback = get_font(size=24, bold=True)
        if fallback is not None and not _missing_glyphs(fallback, text):
            font = fallback
    return text, font


def _draw_title_banner(canvas: Image.Image, title: str) -> None:
    """Băng tiêu đề màu giấy manila ở giữa mép trên, chữ in hoa giữa hai ngôi sao đỏ."""
    draw = ImageDraw.Draw(canvas)
    text, font = title_banner_text_and_font(title)
    star_r = 8
    side = 16 + 2 * star_r + 12                     # lề + ngôi sao + khoảng cách tới chữ, mỗi bên
    max_w = canvas.width - 2 * (FRAME_THICKNESS + 40)
    text_w = draw.textlength(text, font=font)
    while text and text_w + 2 * side > max_w:       # tiêu đề quá dài: cắt bớt, thêm ".."
        text = text[:-3].rstrip() + ".."
        text_w = draw.textlength(text, font=font)

    banner_w = int(max(460, text_w + 2 * side))
    banner_h = 42
    bx = (canvas.width - banner_w) // 2
    by = FRAME_THICKNESS + 4
    draw.rounded_rectangle([bx, by, bx + banner_w, by + banner_h], radius=5, fill=(244, 238, 222, 235),
                           outline=(130, 105, 65, 255), width=2)
    if text:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        tx = bx + (banner_w - (right - left)) / 2 - left
        ty = by + (banner_h - (bottom - top)) / 2 - top
        draw.text((tx, ty), text, font=font, fill=(35, 30, 25))
    cy = by + banner_h / 2
    for cx in (bx + 16 + star_r, bx + banner_w - 16 - star_r):
        draw.polygon(_star_points(cx, cy, star_r), fill=(153, 27, 27, 255))


def _compose_cards(board_state: BoardState):
    """(mặt bảng, lớp đinh ghim, toạ độ đinh theo id thẻ, vùng các thẻ).

    Mặt bảng gồm bần + bóng thẻ + thẻ + băng tiêu đề. Sợi chỉ được dán giữa mặt bảng và lớp đinh: trên thẻ, dưới đinh.
    """
    canvas = generate_corkboard_background(board_state.canvas_width, board_state.canvas_height).convert("RGBA")
    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    card_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    pin_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    pin_positions: Dict[str, Tuple[float, float]] = {}
    card_rects: List[Rect] = []

    for node in board_state.cumulative_nodes:
        scale = card_scale(node)
        card_img = _card_image(node)
        paste_x, paste_y = _paste_origin(node, card_img)
        shadow_draw.rounded_rectangle(
            [paste_x + 8 * scale, paste_y + 12 * scale,
             paste_x + card_img.width + 4 * scale, paste_y + card_img.height + 6 * scale],
            radius=8, fill=(15, 10, 5, 95),
        )
        card_layer.alpha_composite(card_img, (paste_x, paste_y))
        card_rects.append((paste_x, paste_y, paste_x + card_img.width, paste_y + card_img.height))

        pin_cx, pin_cy = _pin_position(node)
        pin_positions[node.id] = (pin_cx, pin_cy)
        pin_img = render_pushpin(color_name=node.pin_color, radius=max(7, round(12 * scale)))
        pin_layer.alpha_composite(pin_img, (int(pin_cx - pin_img.width // 2), int(pin_cy - pin_img.height // 2)))

    canvas = Image.alpha_composite(canvas, shadow_layer.filter(ImageFilter.GaussianBlur(radius=5.0)))
    canvas = Image.alpha_composite(canvas, card_layer)
    _draw_title_banner(canvas, board_state.title)
    return canvas, pin_layer, pin_positions, card_rects


def _thread_layer(size: Tuple[int, int], edges: List[RelationEdge], pin_positions: Dict[str, Tuple[float, float]],
                  progress_of, avoid: List[Rect]) -> Image.Image:
    """Một lớp trong suốt chứa các sợi chỉ (cả bóng và nhãn); `progress_of(edge)` là phần sợi đã kéo, 0..1.
    Nhãn sợi chỉ né các vùng trong `avoid` (thẻ) và né nhau."""
    shadow_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    thread_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    thread_draw = ImageDraw.Draw(thread_layer)
    avoid = list(avoid)
    for edge in edges:
        p0 = pin_positions.get(edge.source_id)
        p2 = pin_positions.get(edge.target_id)
        if p0 and p2:
            draw_red_thread(
                canvas_draw=thread_draw,
                shadow_draw=shadow_draw,
                p0=p0,
                p2=p2,
                color_hex=edge.color,
                progress=progress_of(edge),
                label=edge.label,
                label_avoid=avoid,
            )
    return Image.alpha_composite(shadow_layer, thread_layer)


def render_board_image(
    board_state: BoardState,
    output_path: Optional[str] = None,
    delta_thread_progress: float = 1.0,
) -> Image.Image:
    """
    Renders the complete 1920x1080 Investigation Corkboard, bottom to top:
    1. Corkboard background, blurred card shadows, rotated (and scaled) Polaroid cards, title banner.
    2. Red threads with their shadows and tags, ABOVE the cards so a thread crossing a card stays visible.
    3. Pushpin heads on top, covering the thread ends.
    """
    base, pin_layer, pin_positions, card_rects = _compose_cards(board_state)
    delta_edge_ids = {e.id for e in board_state.delta_edges}
    threads = _thread_layer(
        base.size, board_state.cumulative_edges, pin_positions,
        lambda edge: delta_thread_progress if edge.id in delta_edge_ids else 1.0,
        card_rects,
    )
    canvas = Image.alpha_composite(base, threads)
    canvas = Image.alpha_composite(canvas, pin_layer)

    # Convert to RGB for saving / display
    final_img = canvas.convert("RGB")

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        final_img.save(str(out_file), quality=95)
        board_state.render_image_path = str(out_file)

    return final_img


# ==============================================================================
# 7. DYNAMIC VIDEO CLIP GENERATOR (5-SECOND ANIMATED THREAD & PUSH-IN)
# ==============================================================================

def render_board_animation_clip(
    board_state: BoardState,
    output_video_path: str,
    duration_sec: float = 5.0,
    fps: int = 24,
) -> str:
    """
    Renders an exhilarating 5-second 1080p MP4 clip:
    - If new evidence/threads are revealed (Delta > 0):
      * Phase 1 (0.0s - 1.2s): Camera pushes slightly toward new clue.
      * Phase 2 (1.2s - 3.4s): Red yarn smoothly animates stretching across the board.
      * Phase 3 (3.4s - 5.0s): Rubber stamp / conclusion locks in place with slow cinematic settle.
    - If no delta (static review):
      * Cinematic Ken Burns slow-pan sweep across the evidence network.
    Uses FFmpeg pipe or fast frame rendering for high performance and stability.
    """
    out_path = Path(output_video_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_frames = max(24, int(duration_sec * fps))

    # Fast optimization: If no ffmpeg installed, render static frame and return
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        img_fallback = out_path.with_suffix(".jpg")
        render_board_image(board_state, str(img_fallback))
        return str(img_fallback)

    # Determine focal point for subtle Ken Burns zoom
    if board_state.delta_nodes:
        target_focus_x = board_state.delta_nodes[0].x
        target_focus_y = board_state.delta_nodes[0].y
    elif board_state.cumulative_nodes:
        target_focus_x = board_state.cumulative_nodes[-1].x
        target_focus_y = board_state.cumulative_nodes[-1].y
    else:
        target_focus_x = CANVAS_WIDTH // 2
        target_focus_y = CANVAS_HEIGHT // 2

    # Render keyframes and feed to FFmpeg stdin pipe (zero disk IO bottleneck)
    ffmpeg_cmd = [
        ffmpeg_bin, "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{CANVAS_WIDTH}x{CANVAS_HEIGHT}",
        "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",
        "-crf", "22",
        str(out_path),
    ]

    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # Optimization: Pre-render static layers once so frames render in milliseconds.
        # Same layer order as render_board_image: cards -> threads -> pins.
        cork_and_cards, pin_layer, node_pin_positions, card_rects = _compose_cards(board_state)

        delta_edge_ids = {e.id for e in board_state.delta_edges}
        has_animated_threads = bool(board_state.delta_edges)

        # Pre-render static non-delta threads onto the card board
        static_edges = [e for e in board_state.cumulative_edges if e.id not in delta_edge_ids]
        board_with_static_threads = Image.alpha_composite(
            cork_and_cards,
            _thread_layer(cork_and_cards.size, static_edges, node_pin_positions, lambda edge: 1.0, card_rects),
        )
        static_frame = Image.alpha_composite(board_with_static_threads, pin_layer)

        # Generate each frame fast
        for frame_idx in range(total_frames):
            time_sec = frame_idx / float(fps)

            # Thread progression
            if has_animated_threads:
                if time_sec < 1.0:
                    prog = 0.05
                elif time_sec < 3.2:
                    linear_t = (time_sec - 1.0) / 2.2
                    prog = linear_t * linear_t * (3.0 - 2.0 * linear_t)
                else:
                    prog = 1.0

                delta_threads = _thread_layer(
                    cork_and_cards.size, board_state.delta_edges, node_pin_positions, lambda edge: prog, card_rects
                )
                frame_composite = Image.alpha_composite(board_with_static_threads, delta_threads)
                frame_composite = Image.alpha_composite(frame_composite, pin_layer)
            else:
                frame_composite = static_frame

            # Subtle camera push-in zoom (1.00 -> 1.03)
            zoom = 1.0 + 0.03 * (frame_idx / float(total_frames))
            frame_rgb = frame_composite.convert("RGB")
            if zoom > 1.002:
                crop_w = int(CANVAS_WIDTH / zoom)
                crop_h = int(CANVAS_HEIGHT / zoom)
                crop_x1 = max(0, min(CANVAS_WIDTH - crop_w, int(target_focus_x - crop_w // 2)))
                crop_y1 = max(0, min(CANVAS_HEIGHT - crop_h, int(target_focus_y - crop_h // 2)))
                cropped = frame_rgb.crop((crop_x1, crop_y1, crop_x1 + crop_w, crop_y1 + crop_h))
                frame_rgb = cropped.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.BILINEAR)

            proc.stdin.write(frame_rgb.tobytes())

        proc.stdin.close()
        proc.wait(timeout=30)
    except Exception as e:
        if proc.stdin:
            try:
                proc.stdin.close()
            except Exception:
                pass
        proc.kill()
        raise e

    board_state.render_video_path = str(out_path)
    return str(out_path)
