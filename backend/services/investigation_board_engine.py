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
3. Cumulative Rendering (State = ΔNodes_k + ΔEdges_k):
   - Scene K only displays nodes and edges introduced up to time K.
4. Natural Gravitational Bezier Red Threads:
   - True gravity sag calculation based on Euclidean distance.
   - Multi-layer drawing: drop shadow, 3.5px crimson yarn fiber, center highlight.
5. High-Resolution Evidence Cards:
   - Polaroid styled cards with subtle seeded tilt angles (-3° to +3°).
   - Node-type badges, detective silhouette placeholders, rubber stamps ("ALIBI", "CONFIRMED", "X").
   - 3D glossy pushpins with metallic needles and specular highlights.
6. 1080p Static Image & 5s Dynamic Animated MP4 Video Clip Generation.
"""

import os
import io
import math
import random
import shutil
import hashlib
import tempfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageColor

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

def get_font(size: int = 16, bold: bool = False, typewriter: bool = False) -> ImageFont.ImageFont:
    """Load system font safely with fallback to default PIL font."""
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
        alpha = int(140 * (1.0 - i / shadow_w))
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

# Canonical semantic board layout slots for 1920x1080 canvas
SEMANTIC_ANCHOR_SLOTS = {
    # Center focus: Victim or primary incident
    "victim_center": (960, 480),
    # Top tier: Suspects and primary POIs
    "suspect_culprit": (460, 270),
    "suspect_red_herring": (1460, 270),
    "suspect_secondary": (960, 230),
    # Lower tier: Physical evidence, forensics, weapon
    "weapon_primary": (700, 790),
    "forensic_report": (1220, 790),
    # Lateral flanks: crime scene location, timeline, surveillance
    "location_flank": (300, 560),
    "witness_flank": (1620, 560),
    "timeline_flank": (960, 830),
}

# Grid matrix for dynamic slot assignment (safe area: x [280..1640], y [240..820])
GRID_SLOTS = [
    # Row 1 (top)
    (420, 260), (780, 240), (1140, 240), (1500, 260),
    # Row 2 (mid)
    (340, 530), (740, 520), (1180, 520), (1580, 530),
    # Row 3 (bottom)
    (440, 800), (800, 810), (1120, 810), (1480, 800),
]


def assign_fixed_anchor_layout(
    nodes: List[EvidenceNode],
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> List[EvidenceNode]:
    """
    Assigns permanent, fixed-anchor (X, Y) coordinates to each EvidenceNode.
    Once assigned, pinned=True is enforced.
    Subsequent scenes NEVER recompute or shift node coordinates.
    """
    used_positions: List[Tuple[int, int]] = []

    # First, collect already pinned nodes
    for node in nodes:
        if node.pinned and (node.x != 0 or node.y != 0) and not (node.x == 960 and node.y == 540 and node.node_type != "victim"):
            used_positions.append((node.x, node.y))

    # Helper to check collision
    def is_slot_free(x: int, y: int, min_dist: float = 190.0) -> bool:
        for ux, uy in used_positions:
            if math.hypot(x - ux, y - uy) < min_dist:
                return False
        return True

    # Deterministic rotation based on node id hash
    def compute_deterministic_tilt(node_id: str) -> float:
        h = int(hashlib.md5(node_id.encode("utf-8")).hexdigest()[:6], 16)
        # Range -3.2 to +3.2 degrees
        return ((h % 65) - 32) * 0.1

    grid_idx = 0

    for node in nodes:
        # Compute deterministic tilt for natural polaroid aesthetic
        if abs(node.rotation_deg) < 0.01:
            node.rotation_deg = compute_deterministic_tilt(node.id)

        # If already pinned with valid position, keep it untouched!
        if node.pinned and (node.x, node.y) in used_positions:
            continue

        assigned = False

        # Attempt semantic role-based slot
        if node.node_type == "victim" and is_slot_free(*SEMANTIC_ANCHOR_SLOTS["victim_center"]):
            node.x, node.y = SEMANTIC_ANCHOR_SLOTS["victim_center"]
            assigned = True
        elif node.node_type == "suspect":
            if "culprit" in node.id.lower() or "chinh" in node.id.lower():
                target = SEMANTIC_ANCHOR_SLOTS["suspect_culprit"]
                if is_slot_free(*target):
                    node.x, node.y = target
                    assigned = True
            elif "red_herring" in node.id.lower() or "gia" in node.id.lower() or "phu" in node.id.lower():
                target = SEMANTIC_ANCHOR_SLOTS["suspect_red_herring"]
                if is_slot_free(*target):
                    node.x, node.y = target
                    assigned = True

        elif node.node_type == "weapon" and is_slot_free(*SEMANTIC_ANCHOR_SLOTS["weapon_primary"]):
            node.x, node.y = SEMANTIC_ANCHOR_SLOTS["weapon_primary"]
            assigned = True

        elif node.node_type == "forensic_report" and is_slot_free(*SEMANTIC_ANCHOR_SLOTS["forensic_report"]):
            node.x, node.y = SEMANTIC_ANCHOR_SLOTS["forensic_report"]
            assigned = True

        elif node.node_type == "location" and is_slot_free(*SEMANTIC_ANCHOR_SLOTS["location_flank"]):
            node.x, node.y = SEMANTIC_ANCHOR_SLOTS["location_flank"]
            assigned = True

        # Fallback to predefined grid matrix slots
        if not assigned:
            while grid_idx < len(GRID_SLOTS):
                candidate = GRID_SLOTS[grid_idx]
                grid_idx += 1
                if is_slot_free(*candidate):
                    node.x, node.y = candidate
                    assigned = True
                    break

        # Ultimate fallback with deterministic jitter
        if not assigned:
            h = int(hashlib.md5(node.id.encode("utf-8")).hexdigest()[:6], 16)
            jitter_x = ((h % 80) - 40)
            jitter_y = (((h >> 3) % 80) - 40)
            node.x = max(260, min(width - 260, 960 + jitter_x * 8))
            node.y = max(220, min(height - 220, 540 + jitter_y * 5))

        # Enforce pinned=True
        node.pinned = True
        used_positions.append((node.x, node.y))

    return nodes


# ==============================================================================
# 3. POLAROID CARD & RUBBER STAMP RENDERING
# ==============================================================================

CARD_WIDTH = 250
CARD_HEIGHT = 310
PHOTO_WIDTH = 216
PHOTO_HEIGHT = 186


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
                pimg_resized = pimg_rgb.resize((PHOTO_WIDTH, PHOTO_HEIGHT), Image.Resampling.LANCZOS)
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

    # 4. Card Label / Title (Typewriter Courier font)
    title_font = get_font(size=14, bold=True, typewriter=True)
    clean_label = node.label.strip()
    # Truncate if too long
    if len(clean_label) > 28:
        clean_label = clean_label[:26] + ".."

    tw = int(draw.textlength(clean_label, font=title_font))
    tx = (CARD_WIDTH - tw) // 2
    ty = py2 + 14
    draw.text((tx, ty), clean_label, font=title_font, fill=(28, 28, 30))

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
):
    """
    Draws a realistic yarn/thread line with:
    - Soft drop shadow on corkboard surface (alpha blurred).
    - 3.5px crimson cord body.
    - 1px lighter core fiber reflection.
    - Animated progression support (progress from 0.0 to 1.0).
    """
    raw_points = compute_bezier_points(p0, p2, steps=50)

    # Slice points according to animated drawing progress
    num_pts = max(2, int(len(raw_points) * max(0.01, min(1.0, progress))))
    active_points = raw_points[:num_pts]

    # 1. Thread Drop Shadow (offset down by 6px)
    shadow_points = [(x + 2, y + 6) for (x, y) in active_points]
    for i in range(len(shadow_points) - 1):
        shadow_draw.line([shadow_points[i], shadow_points[i + 1]], fill=(15, 8, 4, 110), width=4)

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
        mid_idx = len(active_points) // 2
        tx, ty = active_points[mid_idx]
        tag_font = get_font(size=11, bold=True)
        tw = int(canvas_draw.textlength(label, font=tag_font)) + 10
        th = 18
        # Paper tag background
        canvas_draw.rectangle([tx - tw // 2, ty - th // 2, tx + tw // 2, ty + th // 2], fill=(255, 253, 235), outline=(140, 110, 60))
        canvas_draw.text((tx - tw // 2 + 5, ty - th // 2 + 2), label, font=tag_font, fill=(30, 25, 20))


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

def render_board_image(
    board_state: BoardState,
    output_path: Optional[str] = None,
    delta_thread_progress: float = 1.0,
) -> Image.Image:
    """
    Renders the complete 1920x1080 Investigation Corkboard:
    1. Base corkboard background.
    2. Shadow layer for cards & threads.
    3. Thread DAG connecting pinned cards.
    4. Rotated Polaroid cards with stamps & badges.
    5. Pushpin heads on top of threads and cards.
    6. Case header banner at top center.
    """
    # 1. Base Canvas
    canvas = generate_corkboard_background(board_state.canvas_width, board_state.canvas_height)
    canvas = canvas.convert("RGBA")

    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)

    card_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    thread_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    thread_draw = ImageDraw.Draw(thread_layer)

    pin_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))

    # Pre-render cards and map pin coordinates on canvas
    node_pin_positions: Dict[str, Tuple[float, float]] = {}

    for node in board_state.cumulative_nodes:
        card_img = render_polaroid_card(node)

        # Rotate card according to fixed tilt
        rot_deg = node.rotation_deg
        rotated_card = card_img.rotate(rot_deg, resample=Image.Resampling.BICUBIC, expand=True)

        # Card center coordinate
        cx, cy = node.x, node.y
        paste_x = cx - rotated_card.width // 2
        paste_y = cy - rotated_card.height // 2

        # Draw card drop shadow onto shadow layer
        shadow_rect = [
            paste_x + 8,
            paste_y + 12,
            paste_x + rotated_card.width + 4,
            paste_y + rotated_card.height + 6,
        ]
        shadow_draw.rounded_rectangle(shadow_rect, radius=8, fill=(15, 10, 5, 95))

        # Paste rotated card
        card_layer.alpha_composite(rotated_card, (paste_x, paste_y))

        # Calculate exact canvas position of pushpin (top-center of unrotated card)
        # Offset from card center: dx=0, dy = -(CARD_HEIGHT // 2) + 12
        local_dx = 0.0
        local_dy = -(CARD_HEIGHT / 2.0) + 12.0
        rad = math.radians(-rot_deg)
        pin_cx = cx + (local_dx * math.cos(rad) - local_dy * math.sin(rad))
        pin_cy = cy + (local_dx * math.sin(rad) + local_dy * math.cos(rad))
        node_pin_positions[node.id] = (pin_cx, pin_cy)

    # 2. Draw Red Threads
    delta_edge_ids = {e.id for e in board_state.delta_edges}

    for edge in board_state.cumulative_edges:
        p0 = node_pin_positions.get(edge.source_id)
        p2 = node_pin_positions.get(edge.target_id)
        if p0 and p2:
            progress = delta_thread_progress if edge.id in delta_edge_ids else 1.0
            draw_red_thread(
                canvas_draw=thread_draw,
                shadow_draw=shadow_draw,
                p0=p0,
                p2=p2,
                color_hex=edge.color,
                progress=progress,
                label=edge.label,
            )

    # 3. Draw Pushpins on top of threads and cards
    for node in board_state.cumulative_nodes:
        pin_pos = node_pin_positions.get(node.id)
        if pin_pos:
            pin_img = render_pushpin(color_name=node.pin_color, radius=12)
            px = int(pin_pos[0] - pin_img.width // 2)
            py = int(pin_pos[1] - pin_img.height // 2)
            pin_layer.alpha_composite(pin_img, (px, py))

    # 4. Composite all layers
    # Corkboard -> Shadow (blurred) -> Thread Layer -> Card Layer -> Pin Layer
    shadow_blurred = shadow_layer.filter(ImageFilter.GaussianBlur(radius=5.0))
    canvas = Image.alpha_composite(canvas, shadow_blurred)
    canvas = Image.alpha_composite(canvas, thread_layer)
    canvas = Image.alpha_composite(canvas, card_layer)
    canvas = Image.alpha_composite(canvas, pin_layer)

    # 5. Case Title Header Tag (Top Center Manila folder tab)
    top_banner = ImageDraw.Draw(canvas)
    banner_w = 460
    banner_h = 42
    bx = (board_state.canvas_width - banner_w) // 2
    by = FRAME_THICKNESS + 4

    top_banner.rounded_rectangle([bx, by, bx + banner_w, by + banner_h], radius=5, fill=(244, 238, 222, 235), outline=(130, 105, 65, 255), width=2)
    b_font = get_font(size=16, bold=True, typewriter=True)
    b_text = f"★ {board_state.title.upper()} ★"
    btw = int(top_banner.textlength(b_text, font=b_font))
    top_banner.text((bx + (banner_w - btw) // 2, by + 10), b_text, font=b_font, fill=(35, 30, 25))

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
        # Optimization: Pre-render static base layers once so frames render in milliseconds
        # 1. Base Canvas
        canvas_base = generate_corkboard_background(board_state.canvas_width, board_state.canvas_height).convert("RGBA")
        shadow_layer = Image.new("RGBA", canvas_base.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        card_layer = Image.new("RGBA", canvas_base.size, (0, 0, 0, 0))
        pin_layer = Image.new("RGBA", canvas_base.size, (0, 0, 0, 0))

        node_pin_positions: Dict[str, Tuple[float, float]] = {}

        for node in board_state.cumulative_nodes:
            card_img = render_polaroid_card(node)
            rot_deg = node.rotation_deg
            rotated_card = card_img.rotate(rot_deg, resample=Image.Resampling.BICUBIC, expand=True)
            cx, cy = node.x, node.y
            paste_x = cx - rotated_card.width // 2
            paste_y = cy - rotated_card.height // 2
            shadow_rect = [
                paste_x + 8,
                paste_y + 12,
                paste_x + rotated_card.width + 4,
                paste_y + rotated_card.height + 6,
            ]
            shadow_draw.rounded_rectangle(shadow_rect, radius=8, fill=(15, 10, 5, 95))
            card_layer.alpha_composite(rotated_card, (paste_x, paste_y))

            local_dx = 0.0
            local_dy = -(CARD_HEIGHT / 2.0) + 12.0
            rad = math.radians(-rot_deg)
            pin_cx = cx + (local_dx * math.cos(rad) - local_dy * math.sin(rad))
            pin_cy = cy + (local_dx * math.sin(rad) + local_dy * math.cos(rad))
            node_pin_positions[node.id] = (pin_cx, pin_cy)

            pin_img = render_pushpin(color_name=node.pin_color, radius=12)
            px = int(pin_cx - pin_img.width // 2)
            py = int(pin_cy - pin_img.height // 2)
            pin_layer.alpha_composite(pin_img, (px, py))

        # Composite base background + cards (without threads)
        shadow_blurred = shadow_layer.filter(ImageFilter.GaussianBlur(radius=5.0))
        cork_and_cards = Image.alpha_composite(canvas_base, shadow_blurred)
        cork_and_cards = Image.alpha_composite(cork_and_cards, card_layer)

        # Header banner
        top_banner = ImageDraw.Draw(cork_and_cards)
        banner_w = 460
        banner_h = 42
        bx = (board_state.canvas_width - banner_w) // 2
        by = FRAME_THICKNESS + 4
        top_banner.rounded_rectangle([bx, by, bx + banner_w, by + banner_h], radius=5, fill=(244, 238, 222, 235), outline=(130, 105, 65, 255), width=2)
        b_font = get_font(size=16, bold=True, typewriter=True)
        b_text = f"★ {board_state.title.upper()} ★"
        btw = int(top_banner.textlength(b_text, font=b_font))
        top_banner.text((bx + (banner_w - btw) // 2, by + 10), b_text, font=b_font, fill=(35, 30, 25))

        delta_edge_ids = {e.id for e in board_state.delta_edges}
        has_animated_threads = bool(board_state.delta_edges)

        # Pre-render static non-delta threads
        static_thread_layer = Image.new("RGBA", canvas_base.size, (0, 0, 0, 0))
        static_thread_draw = ImageDraw.Draw(static_thread_layer)
        static_shadow_layer = Image.new("RGBA", canvas_base.size, (0, 0, 0, 0))
        static_shadow_draw = ImageDraw.Draw(static_shadow_layer)

        for edge in board_state.cumulative_edges:
            if edge.id not in delta_edge_ids:
                p0 = node_pin_positions.get(edge.source_id)
                p2 = node_pin_positions.get(edge.target_id)
                if p0 and p2:
                    draw_red_thread(static_thread_draw, static_shadow_draw, p0, p2, edge.color, 1.0, edge.label)

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

                frame_thread_layer = static_thread_layer.copy()
                frame_thread_draw = ImageDraw.Draw(frame_thread_layer)
                frame_shadow_layer = static_shadow_layer.copy()
                frame_shadow_draw = ImageDraw.Draw(frame_shadow_layer)

                for edge in board_state.delta_edges:
                    p0 = node_pin_positions.get(edge.source_id)
                    p2 = node_pin_positions.get(edge.target_id)
                    if p0 and p2:
                        draw_red_thread(frame_thread_draw, frame_shadow_draw, p0, p2, edge.color, prog, edge.label)

                frame_composite = Image.alpha_composite(cork_and_cards, frame_shadow_layer)
                frame_composite = Image.alpha_composite(frame_composite, frame_thread_layer)
                frame_composite = Image.alpha_composite(frame_composite, pin_layer)
            else:
                frame_composite = Image.alpha_composite(cork_and_cards, static_shadow_layer)
                frame_composite = Image.alpha_composite(frame_composite, static_thread_layer)
                frame_composite = Image.alpha_composite(frame_composite, pin_layer)

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
