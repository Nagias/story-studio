"""Phần ảnh của việc tạo ảnh Muse (`POST /api/muse-bridge/tasks/create`, chế độ text-to-image).

`routers/muse_bridge.create_task` và nút xem trước prompt trên thẻ cảnh (`services/scene_prompt_preview.py`) cùng gọi
`image_task_fields()`, để prompt xem trước đúng là prompt của việc thật. Sau đó cả hai cùng áp khoá hình của cảnh
(`services/scene_locks.py`), rồi Fleet Runner bọc chữ bằng `services/muse_prompt_format.py`.
"""
from typing import Any, Optional

from services.image_service import with_style
from services.prompt_rules import negative_for


def image_task_fields(prompt: str, params: dict, *, aspect_ratio: Optional[str] = None,
                      character_anchor: Optional[str] = None, negative_prompt: Optional[str] = None,
                      reference_image: Any = None, reference_image_url: Optional[str] = None,
                      reference_image_path: Optional[str] = None) -> dict:
    """Các khoá ảnh của việc Muse: prompt có câu phong cách, tham số mặc định (16:9, 2K), ảnh tham chiếu. Sửa `params`
    tại chỗ (như route trước đây) và trả nó trong khoá "parameters"."""
    aspect = aspect_ratio or params.get("aspect_ratio") or "16:9"
    anchor = character_anchor or params.get("character_anchor") or ""
    params.setdefault("aspect_ratio", aspect)
    params.setdefault("resolution", "2K")
    if anchor:
        params.setdefault("character_anchor", anchor)
    return {
        "mode": "text-to-image",
        # câu mô tả phong cách như mọi đường tạo ảnh khác (Muse không hiểu mã phong cách trần)
        "prompt": with_style(prompt, params.get("style_preset")),
        # danh sách cấm của phong cách được gửi (trước 18/11/2026 viết sẵn trong STYLE_PRESETS mà không bao giờ gửi)
        "negative_prompt": negative_prompt or negative_for(params.get("style_preset")) or None,
        "parameters": params,
        "reference_image": reference_image,
        "reference_image_url": reference_image_url,
        "reference_image_path": reference_image_path,
        "character_anchor": anchor,
        "aspect_ratio": aspect,
    }
