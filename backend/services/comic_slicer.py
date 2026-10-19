"""
Comic and Webtoon Slicer Service
Splits comic pages and webtoon strips into panels using OpenCV and Pillow.
Supports:
  1. Grid Layout: Manga / Comic page with traditional panel boxes and reading orders (LTR, RTL).
  2. Strip Layout: Webtoon / Manhwa vertical scroll strips with horizontal gutter detection.
  3. Aspect Ratio & Camera Motion assignment:
     - Aspect ratio > 1.5: pan_left or pan_right
     - Aspect ratio <= 1.5: zoom_in
"""

import io
import uuid
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Union

import cv2
import numpy as np
from PIL import Image

from config import COMIC_SLICES_DIR

def load_image(image_input: Union[str, Path, bytes, Image.Image]) -> Tuple[np.ndarray, Image.Image]:
    """
    Load image from file path, bytes, or PIL Image into both OpenCV (BGR) and PIL Image.
    """
    if isinstance(image_input, Image.Image):
        pil_img = image_input.convert("RGB")
        img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return img_bgr, pil_img

    if isinstance(image_input, bytes):
        nparr = np.frombuffer(image_input, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            raise ValueError("Failed to decode image from bytes.")
        pil_img = Image.open(io.BytesIO(image_input)).convert("RGB")
        return img_bgr, pil_img

    # Path or string path
    path = Path(image_input)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    # Use cv2.imdecode with numpy to support non-ASCII paths on Windows
    with open(path, "rb") as f:
        img_bytes = f.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError(f"Failed to read image at: {path}")

    pil_img = Image.open(path).convert("RGB")
    return img_bgr, pil_img

def assign_camera_motion(width: int, height: int, index: int = 0) -> str:
    """
    Assign camera motion based on aspect ratio:
    - Wide frame (aspect ratio > 1.5): 'pan_left' or 'pan_right' for dynamic cinematic panning.
    - Vertical / square / close-up frame (aspect ratio <= 1.5): 'zoom_in' for dramatic focus.
    """
    if height <= 0:
        return "zoom_in"
    ar = width / float(height)
    if ar > 1.5:
        # Alternate pan direction for visual dynamism
        return "pan_right" if (index % 2 == 0) else "pan_left"
    return "zoom_in"

def remove_contained_and_overlapping_boxes(
    boxes: List[Tuple[int, int, int, int]],
    img_w: int,
    img_h: int,
    containment_threshold: float = 0.85,
    iou_threshold: float = 0.65,
) -> List[Tuple[int, int, int, int]]:
    """
    Filter out:
    1. Outer page border boxes (spans > 96% width and height).
    2. Sub-boxes contained inside a larger panel box.
    3. Highly overlapping duplicate boxes (IoU > iou_threshold).
    """
    filtered = []
    for (x, y, w, h) in boxes:
        # Ignore full-page outer boundary
        if w >= 0.96 * img_w and h >= 0.96 * img_h:
            continue
        filtered.append((x, y, w, h))

    if not filtered:
        return []

    # Sort by area descending so we keep larger enclosing panels
    filtered.sort(key=lambda b: b[2] * b[3], reverse=True)

    keep: List[Tuple[int, int, int, int]] = []
    for box_a in filtered:
        xa, ya, wa, ha = box_a
        area_a = wa * ha
        is_sub_box = False

        for box_b in keep:
            xb, yb, wb, hb = box_b
            area_b = wb * hb

            # Calculate intersection
            xi1 = max(xa, xb)
            yi1 = max(ya, yb)
            xi2 = min(xa + wa, xb + wb)
            yi2 = min(ya + ha, yb + hb)
            inter_w = max(0, xi2 - xi1)
            inter_h = max(0, yi2 - yi1)
            inter_area = inter_w * inter_h

            # If box_a is heavily contained inside box_b
            if area_a > 0 and (inter_area / float(area_a)) >= containment_threshold:
                is_sub_box = True
                break

            # If IoU is high
            union_area = area_a + area_b - inter_area
            if union_area > 0 and (inter_area / float(union_area)) >= iou_threshold:
                is_sub_box = True
                break

        if not is_sub_box:
            keep.append(box_a)

    return keep

def sort_reading_order(
    boxes: List[Tuple[int, int, int, int]],
    reading_order: str = "ltr",
) -> List[Tuple[int, int, int, int]]:
    """
    Sort panel boxes according to comic reading order:
    1. Group boxes into tiers / rows based on vertical overlap.
    2. Sort tiers from Top to Bottom.
    3. Within each tier:
       - 'ltr': Left to Right (Western comics, Manhwa, Webtoon)
       - 'rtl': Right to Left (Traditional Japanese Manga)
    """
    if not boxes:
        return []

    # Initial sort by y
    sorted_by_y = sorted(boxes, key=lambda b: (b[1], b[0]))

    rows: List[List[Tuple[int, int, int, int]]] = []
    for box in sorted_by_y:
        x, y, w, h = box
        placed = False
        for row in rows:
            row_y_min = min(b[1] for b in row)
            row_y_max = max(b[1] + b[3] for b in row)
            row_h = row_y_max - row_y_min

            overlap_min = max(y, row_y_min)
            overlap_max = min(y + h, row_y_max)
            overlap = max(0, overlap_max - overlap_min)

            # Significant vertical overlap or center point inside row bounds
            y_center = y + h / 2.0
            if overlap >= 0.35 * min(h, row_h) or (row_y_min <= y_center <= row_y_max):
                row.append(box)
                placed = True
                break

        if not placed:
            rows.append([box])

    # Sort rows by average Y
    rows.sort(key=lambda r: sum(b[1] for b in r) / len(r))

    # Sort panels within each row
    ordered_boxes: List[Tuple[int, int, int, int]] = []
    is_rtl = reading_order.lower().strip() == "rtl"

    for row in rows:
        if is_rtl:
            row.sort(key=lambda b: b[0], reverse=True)
        else:
            row.sort(key=lambda b: b[0])
        ordered_boxes.extend(row)

    return ordered_boxes

def recursive_xy_cut(
    binary_content: np.ndarray,
    offset_x: int,
    offset_y: int,
    w: int,
    h: int,
    total_page_area: int,
    min_area_ratio: float = 0.03,
    max_depth: int = 4,
) -> List[Tuple[int, int, int, int]]:
    """
    Recursive XY-Cut algorithm to split pages along zero-content horizontal or vertical gutters.
    binary_content: 255 for ink/panel content, 0 for empty white gutter.
    """
    if max_depth <= 0 or w * h < min_area_ratio * total_page_area:
        return [(offset_x, offset_y, w, h)]

    region = binary_content[offset_y:offset_y + h, offset_x:offset_x + w]
    if region.size == 0:
        return []

    # 1. Check horizontal projection (rows)
    h_proj = np.sum(region > 0, axis=1)  # number of content pixels per row
    zero_rows = np.where(h_proj <= max(3, int(w * 0.01)))[0]

    # Find widest horizontal gap not at edges
    min_gutter_thickness = max(8, int(h * 0.015))
    h_gutters = []
    if len(zero_rows) > 0:
        gap_start = zero_rows[0]
        for i in range(1, len(zero_rows)):
            if zero_rows[i] != zero_rows[i - 1] + 1:
                gap_end = zero_rows[i - 1]
                if (gap_end - gap_start) >= min_gutter_thickness and gap_start > int(h * 0.08) and gap_end < int(h * 0.92):
                    h_gutters.append((gap_start, gap_end))
                gap_start = zero_rows[i]
        gap_end = zero_rows[-1]
        if (gap_end - gap_start) >= min_gutter_thickness and gap_start > int(h * 0.08) and gap_end < int(h * 0.92):
            h_gutters.append((gap_start, gap_end))

    if h_gutters:
        # Split at widest horizontal gutter
        h_gutters.sort(key=lambda g: g[1] - g[0], reverse=True)
        g_s, g_e = h_gutters[0]
        top_boxes = recursive_xy_cut(binary_content, offset_x, offset_y, w, g_s, total_page_area, min_area_ratio, max_depth - 1)
        bottom_boxes = recursive_xy_cut(binary_content, offset_x, offset_y + g_e, w, h - g_e, total_page_area, min_area_ratio, max_depth - 1)
        return top_boxes + bottom_boxes

    # 2. Check vertical projection (columns)
    v_proj = np.sum(region > 0, axis=0)  # number of content pixels per column
    zero_cols = np.where(v_proj <= max(3, int(h * 0.01)))[0]

    v_gutters = []
    if len(zero_cols) > 0:
        gap_start = zero_cols[0]
        for i in range(1, len(zero_cols)):
            if zero_cols[i] != zero_cols[i - 1] + 1:
                gap_end = zero_cols[i - 1]
                if (gap_end - gap_start) >= min_gutter_thickness and gap_start > int(w * 0.08) and gap_end < int(w * 0.92):
                    v_gutters.append((gap_start, gap_end))
                gap_start = zero_cols[i]
        gap_end = zero_cols[-1]
        if (gap_end - gap_start) >= min_gutter_thickness and gap_start > int(w * 0.08) and gap_end < int(w * 0.92):
            v_gutters.append((gap_start, gap_end))

    if v_gutters:
        # Split at widest vertical gutter
        v_gutters.sort(key=lambda g: g[1] - g[0], reverse=True)
        g_s, g_e = v_gutters[0]
        left_boxes = recursive_xy_cut(binary_content, offset_x, offset_y, g_s, h, total_page_area, min_area_ratio, max_depth - 1)
        right_boxes = recursive_xy_cut(binary_content, offset_x + g_e, offset_y, w - g_e, h - g_e, total_page_area, min_area_ratio, max_depth - 1)
        return left_boxes + right_boxes

    return [(offset_x, offset_y, w, h)]

def slice_grid_layout(
    img_cv: np.ndarray,
    reading_order: str = "ltr",
    min_area_ratio: float = 0.03,
) -> List[Tuple[int, int, int, int]]:
    """
    Extract panels for traditional comic/manga grid layout:
    - Binarization (Otsu threshold).
    - Morphological closing to seal internal lines.
    - Contour detection of panel bounding boxes.
    - Filtering of tiny frames (< 3% page area) and outer margins.
    - Reading order sorting (LTR or RTL).
    """
    H, W = img_cv.shape[:2]
    page_area = H * W
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY) if len(img_cv.shape) == 3 else img_cv

    # Detect gutter polarity (light vs dark page)
    border_pixels = np.concatenate([
        gray[:10, :].flatten(),
        gray[-10:, :].flatten(),
        gray[:, :10].flatten(),
        gray[:, -10:].flatten(),
    ])
    median_border = float(np.median(border_pixels))
    is_light_bg = median_border > 127

    # Gaussian blur to filter screentone halftones
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Binarize with Otsu
    if is_light_bg:
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Morphological Closing: bridges small panel gaps and text lines inside a panel
    kernel_dim = max(9, int(min(W, H) * 0.015))
    if kernel_dim % 2 == 0:
        kernel_dim += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_dim, kernel_dim))

    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    dilated = cv2.dilate(closed, kernel, iterations=1)

    # Find contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    min_area = min_area_ratio * page_area
    candidate_boxes = []

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h >= min_area:
            # Filter out outer border of the entire page
            if w < 0.96 * W or h < 0.96 * H:
                # Add slight margin expansion if within page boundaries
                candidate_boxes.append((x, y, w, h))

    # Remove contained and overlapping boxes
    candidate_boxes = remove_contained_and_overlapping_boxes(candidate_boxes, W, H)

    # Fallback to recursive XY-cut if contour detection found 0 or only 1 box on a multi-panel page
    if len(candidate_boxes) <= 1:
        xy_boxes = recursive_xy_cut(binary, 0, 0, W, H, page_area, min_area_ratio)
        valid_xy = [b for b in xy_boxes if b[2] * b[3] >= min_area and (b[2] < 0.96 * W or b[3] < 0.96 * H)]
        if len(valid_xy) > len(candidate_boxes):
            candidate_boxes = remove_contained_and_overlapping_boxes(valid_xy, W, H)

    # If still empty (e.g., solid single image), return entire page
    if not candidate_boxes:
        candidate_boxes = [(0, 0, W, H)]

    # Sort in specified reading order
    ordered_boxes = sort_reading_order(candidate_boxes, reading_order)
    return ordered_boxes

def slice_strip_layout(
    img_cv: np.ndarray,
    min_gutter_height: int = 15,
    min_panel_height: int = 60,
) -> List[Tuple[int, int, int, int]]:
    """
    Extract panels for vertical scroll Webtoon / Manhwa strip:
    - Analyzes rows for uniform horizontal white, black, or monochrome separator bands.
    - Groups contiguous gutter rows into gutter blocks.
    - Splits image into chronological top-to-bottom panels.
    - Fallback energy gradient cut if strip lacks distinct monochrome gutters.
    """
    H, W = img_cv.shape[:2]
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY) if len(img_cv.shape) == 3 else img_cv

    row_means = np.mean(gray, axis=1)
    row_stds = np.std(gray, axis=1)

    if len(img_cv.shape) == 3:
        rgb_color_variance = np.mean(np.std(img_cv, axis=2), axis=1)
    else:
        rgb_color_variance = np.zeros(H)

    # Determine gutter rows
    is_gutter_row = np.zeros(H, dtype=bool)
    for y in range(H):
        std_val = row_stds[y]
        mean_val = row_means[y]
        col_var = rgb_color_variance[y]

        # White separator band
        if std_val < 15.0 and mean_val >= 235:
            is_gutter_row[y] = True
        # Black separator band
        elif std_val < 12.0 and mean_val <= 25:
            is_gutter_row[y] = True
        # Solid uniform color separator band
        elif std_val < 4.0 and col_var < 4.0:
            is_gutter_row[y] = True

    # Group contiguous gutter rows
    gutter_intervals = []
    in_gutter = False
    g_start = 0
    for y in range(H):
        if is_gutter_row[y]:
            if not in_gutter:
                in_gutter = True
                g_start = y
        else:
            if in_gutter:
                in_gutter = False
                if (y - g_start) >= min_gutter_height:
                    gutter_intervals.append((g_start, y))
    if in_gutter and (H - g_start) >= min_gutter_height:
        gutter_intervals.append((g_start, H))

    # Extract panel boxes between gutters
    panel_boxes = []
    current_y = 0
    for (g_start, g_end) in gutter_intervals:
        if g_start - current_y >= min_panel_height:
            panel_boxes.append((0, current_y, W, g_start - current_y))
        current_y = g_end
    if H - current_y >= min_panel_height:
        panel_boxes.append((0, current_y, W, H - current_y))

    # Fallback for tall continuous webtoon strips without flat gutters
    if len(panel_boxes) <= 1 and H > 2.0 * W:
        grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        row_energy = np.mean(np.abs(grad_y), axis=1)

        # Estimate panel count (aiming for roughly ~1:1 to 1:1.5 panel aspect ratio)
        target_panels = max(2, min(10, int(round(H / (W * 1.2)))))
        segment_h = H / target_panels

        panel_boxes = []
        last_cut = 0
        for p in range(1, target_panels):
            search_center = int(p * segment_h)
            search_range = int(segment_h * 0.25)
            y_min = max(last_cut + min_panel_height, search_center - search_range)
            y_max = min(H - min_panel_height, search_center + search_range)
            if y_min < y_max:
                best_cut = y_min + int(np.argmin(row_energy[y_min:y_max]))
                panel_boxes.append((0, last_cut, W, best_cut - last_cut))
                last_cut = best_cut
        if H - last_cut >= min_panel_height:
            panel_boxes.append((0, last_cut, W, H - last_cut))

    if not panel_boxes:
        panel_boxes = [(0, 0, W, H)]

    return panel_boxes

def draw_annotated_preview(
    img_bgr: np.ndarray,
    panels: List[Dict[str, Any]],
) -> np.ndarray:
    """
    Draw colorful bounding boxes, panel numbers, and camera motion indicators
    onto a copy of the original image for visual preview.
    """
    annotated = img_bgr.copy()
    h_img, w_img = annotated.shape[:2]
    line_thickness = max(2, int(min(w_img, h_img) * 0.003))

    colors = [
        (255, 99, 71),   # Coral
        (50, 205, 50),   # LimeGreen
        (30, 144, 255),  # DodgerBlue
        (255, 165, 0),   # Orange
        (186, 85, 211),  # MediumOrchid
        (0, 206, 209),   # DarkTurquoise
    ]

    for idx, p in enumerate(panels):
        bbox = p["bbox"]
        x, y, w, h = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
        color = colors[idx % len(colors)]
        motion = p.get("camera_motion", "zoom_in")

        # Draw bounding rectangle
        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, line_thickness)

        # Label banner: #Index • Motion • AR
        label = f"#{p['index']} [{motion.upper()}] AR:{p['aspect_ratio']:.2f}"
        font_scale = max(0.5, min(1.2, min(w_img, h_img) * 0.0007))
        font_thick = max(1, int(font_scale * 2))

        (lbl_w, lbl_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thick)
        
        # Draw background label box
        lbl_y1 = max(0, y - lbl_h - 8)
        lbl_y2 = y
        lbl_x1 = x
        lbl_x2 = min(w_img, x + lbl_w + 12)

        cv2.rectangle(annotated, (lbl_x1, lbl_y1), (lbl_x2, lbl_y2), color, -1)
        cv2.putText(
            annotated,
            label,
            (x + 6, y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            font_thick,
            cv2.LINE_AA,
        )

    return annotated

def slice_comic(
    image_input: Union[str, Path, bytes, Image.Image],
    output_dir: Optional[Union[str, Path]] = None,
    mode: str = "grid",
    reading_order: str = "ltr",
    min_area_ratio: float = 0.03,
    url_prefix: str = "/api/comic/media",
) -> Dict[str, Any]:
    """
    Main entry point for comic & webtoon slicing.
    
    Parameters:
    - image_input: File path, bytes, or PIL Image.
    - output_dir: Directory to save cropped panel images. If None, saves to COMIC_SLICES_DIR/<session_id>.
    - mode: 'grid' (traditional manga/comic page) or 'strip' (webtoon/manhwa vertical scroll).
    - reading_order: 'ltr' (Left-to-Right) or 'rtl' (Right-to-Left).
    - min_area_ratio: Minimum panel area as a fraction of page area (default 0.03 = 3%).
    - url_prefix: Web URL prefix for serving sliced panel images.
    
    Returns:
    Dict containing:
      - success: bool
      - mode: str
      - reading_order: str
      - total_panels: int
      - source_dimensions: {'width': W, 'height': H}
      - panels: list of panel dictionaries with bbox, aspect_ratio, camera_motion, image_path, image_url.
      - annotated_preview_url: url to full image with labeled bounding boxes.
    """
    img_bgr, pil_img = load_image(image_input)
    H, W = img_bgr.shape[:2]

    clean_mode = mode.lower().strip()
    clean_order = reading_order.lower().strip()
    if clean_order not in ("ltr", "rtl"):
        clean_order = "ltr"

    # Extract bounding boxes based on mode
    if clean_mode == "strip":
        boxes = slice_strip_layout(img_bgr, min_gutter_height=15, min_panel_height=60)
    else:
        clean_mode = "grid"
        boxes = slice_grid_layout(img_bgr, reading_order=clean_order, min_area_ratio=min_area_ratio)

    # Prepare output directory
    session_id = uuid.uuid4().hex[:8]
    if output_dir:
        out_path = Path(output_dir)
    else:
        out_path = COMIC_SLICES_DIR / session_id
    out_path.mkdir(parents=True, exist_ok=True)

    panels_result: List[Dict[str, Any]] = []

    for idx, (x, y, w, h) in enumerate(boxes, start=1):
        panel_id = f"panel_{idx:02d}_{uuid.uuid4().hex[:6]}"
        ar = round(w / float(h), 3) if h > 0 else 1.0
        motion = assign_camera_motion(w, h, index=idx)

        # Crop panel using Pillow for maximum fidelity and crisp saving
        # Box format in Pillow: (left, upper, right, lower)
        crop_box = (max(0, x), max(0, y), min(W, x + w), min(H, y + h))
        cropped_pil = pil_img.crop(crop_box)

        filename = f"{panel_id}.jpg"
        save_file = out_path / filename
        cropped_pil.save(save_file, "JPEG", quality=95)

        img_url = f"{url_prefix.rstrip('/')}/{filename}"

        panels_result.append({
            "id": panel_id,
            "index": idx,
            "bbox": {
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
            },
            "aspect_ratio": ar,
            "camera_motion": motion,
            "width": int(w),
            "height": int(h),
            "is_wide": ar > 1.5,
            "image_path": str(save_file),
            "image_url": img_url,
        })

    # Save annotated preview image
    annotated_bgr = draw_annotated_preview(img_bgr, panels_result)
    preview_filename = f"annotated_preview_{session_id}.jpg"
    preview_file_path = out_path / preview_filename
    
    # Save preview image with numpy imencode for unicode safety
    _, enc = cv2.imencode(".jpg", annotated_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    with open(preview_file_path, "wb") as f:
        f.write(enc.tobytes())

    preview_url = f"{url_prefix.rstrip('/')}/{preview_filename}"

    return {
        "success": True,
        "mode": clean_mode,
        "reading_order": clean_order,
        "total_panels": len(panels_result),
        "source_dimensions": {
            "width": W,
            "height": H,
        },
        "panels": panels_result,
        "annotated_preview_path": str(preview_file_path),
        "annotated_preview_url": preview_url,
    }
