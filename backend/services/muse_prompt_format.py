"""Ghép chữ prompt tạo ảnh gửi chat Muse (thuần chuỗi, không đọc đĩa, không gọi mạng).

Fleet Runner (`backend/runners/muse_fleet_runner.py`, tiến trình riêng) và nút xem trước prompt trên thẻ cảnh
(`services/scene_prompt_preview.py`) cùng dùng file này, để chữ chủ dự án thấy trên app đúng là chữ Muse nhận.
File này chỉ import thư viện chuẩn: runner nạp thẳng theo đường dẫn file khi chạy riêng (không qua gói `services`).
"""
from typing import Any, Dict, List


def task_attachments(task: Dict[str, Any]) -> List[str]:
    """Ảnh đính kèm theo thứ tự: `attachments` nếu có, không thì một ảnh như cũ (ảnh đầu vào của video, ảnh tham chiếu
    của ảnh)."""
    atts = task.get("attachments")
    if isinstance(atts, list) and atts:
        return [str(a) for a in atts]
    params = task.get("parameters") or {}
    if "video" in str(task.get("mode", "")).lower():
        keys = ("input_image_url", "input_image_path")
    else:
        keys = ("reference_image_path", "reference_image_url", "reference_image")
    for k in keys:
        v = task.get(k) or params.get(k)
        if v:
            return [str(v)]
    return []


def attachment_role_tags(roles: List[str]) -> List[str]:
    """Câu dặn Muse vai trò từng ảnh đính kèm (thứ tự do services/scene_locks.py xếp)."""
    n = len(roles)
    tags = []
    for i, role in enumerate(roles):
        if n == 1:
            which = "Ảnh đính kèm"
        elif i == 0:
            which = "Ảnh đính kèm đầu tiên"
        elif i == n - 1:
            which = "Ảnh đính kèm cuối cùng"
        else:
            which = "Ảnh đính kèm thứ hai"
        if role == "characters":
            tags.append(f"{which} là BẢNG NHÂN VẬT (FIXED CHARACTERS bên dưới), vẽ mỗi người từ mọi góc: vẽ đúng "
                        "dáng đầu, gương mặt, kiểu tóc, trang phục, màu sắc của họ; không chép bố cục của bảng, "
                        "không vẽ bảng vào cảnh")
        elif role == "previous_scene":
            tags.append(f"{which} là khung hình của cảnh ngay trước trong cùng câu chuyện: giữ đúng nhân vật "
                        "(gương mặt, kiểu tóc, trang phục), cùng bối cảnh và cùng phong cách vẽ; vẽ khung hình TIẾP "
                        "THEO theo mô tả dưới đây (đổi góc máy, hành động tiếp diễn), không chép lại ảnh đính kèm")
        elif role == "location":
            tags.append(f"{which} là ẢNH CHUẨN CỦA BỐI CẢNH (FIXED LOCATION bên dưới): vẽ đúng nơi này (kiến "
                        "trúc, bố cục, đồ vật cố định, màu sắc, nguồn sáng), chỉ đổi góc máy theo mô tả; không "
                        "chép bố cục khung hình của ảnh đó")
        else:
            tags.append(f"Giữ đúng gương mặt, trang phục và đặc điểm nhân vật trong {which.lower()} (ảnh tham chiếu)")
    return tags


def format_image_prompt(task: Dict[str, Any], has_reference: bool = False) -> str:
    """Định dạng prompt tạo ảnh gửi tới chat Muse AI."""
    raw_prompt = task.get("prompt", "").strip()
    params = task.get("parameters", {}) or {}
    aspect_ratio = params.get("aspect_ratio", "16:9")
    anchor = task.get("character_anchor") or params.get("character_anchor")
    lighting = params.get("lighting", "")
    negative = task.get("negative_prompt", "")

    tags = []
    roles = params.get("attachment_roles")
    n_attach = len(task_attachments(task))
    if has_reference and isinstance(roles, list) and len(roles) == n_attach:
        # Khoá hình của cảnh (services/scene_locks.py): vai trò từng ảnh đính kèm theo đúng thứ tự
        tags += attachment_role_tags(roles)
        roles_done = True
    else:
        roles_done = False
    # Khoá bối cảnh: ảnh chuẩn của bối cảnh là ảnh đính kèm CUỐI; ảnh trước nó (nếu có) là ảnh tham chiếu như cũ
    location_ref = bool(has_reference and params.get("location_reference")) and not roles_done
    person_ref = has_reference and not roles_done and (not location_ref or n_attach > 1)
    first = "Ảnh đính kèm đầu tiên" if location_ref else "Ảnh đính kèm"
    if person_ref and params.get("reference_role") == "previous_scene":
        # vẽ nối tiếp (chủ dự án 26/10/2026: mỗi ảnh như một câu chuyện riêng, không liên quan nhau)
        tags.append(f"{first} là khung hình của cảnh ngay trước trong cùng câu chuyện: giữ đúng nhân vật (gương mặt, "
                    "kiểu tóc, trang phục), cùng bối cảnh và cùng phong cách vẽ; vẽ khung hình TIẾP THEO theo mô tả "
                    "dưới đây (đổi góc máy, hành động tiếp diễn), không chép lại ảnh đính kèm")
    elif person_ref:
        tags.append(f"Giữ đúng gương mặt, trang phục và đặc điểm nhân vật trong {first.lower()} (ảnh tham chiếu)")
    if location_ref:
        tags.append("Ảnh đính kèm cuối cùng là ẢNH CHUẨN CỦA BỐI CẢNH (FIXED LOCATION bên dưới): vẽ đúng nơi này "
                    "(kiến trúc, bố cục, đồ vật cố định, màu sắc, nguồn sáng), chỉ đổi góc máy theo mô tả; không "
                    "chép bố cục khung hình của ảnh đó")
    if anchor:
        tags.append(f"Character Anchor: {anchor}")
    # Không ghi mã phong cách trần ("Style: horror_cartoon_2d"): Muse không hiểu mã, câu mô tả phong cách đã nằm trong
    # prompt (image_service.with_style). Rà soát 18/11/2026.
    tags.append(f"Scene Details: {raw_prompt}")
    if lighting:
        tags.append(f"Atmosphere: {lighting}")
    tags.append("16:9 widescreen cinematic" if aspect_ratio == "16:9" else f"{aspect_ratio}")
    if negative:
        tags.append(f"Avoid: {negative}")

    return f"tạo cho tôi 1 hình ảnh 2K tỉ lệ {aspect_ratio}: " + ", ".join(tags)
