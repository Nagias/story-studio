"""Xem trước prompt thật gửi Muse cho một cảnh (thẻ cảnh: "Prompt đầy đủ gửi Muse", "Video gửi Muse").

Chủ dự án 15/11/2026: "Prompt thực tế như nào cũng phải có trên tool luôn", và khi muốn làm lại ảnh/video một cảnh
thì phải biết prompt lấy ở đâu. File này không ghép chữ riêng: nó gọi đúng các hàm mà đường thật gọi.
- Ảnh ("Muse 2K"): prompt gốc như `generateSceneWithMuse()` trong app.js → `muse_image_task.image_task_fields()`
  (như `routers/muse_bridge.create_task`) → `scene_locks.scene_locks()` + `apply_to_image_task()` →
  `muse_prompt_format.format_image_prompt()` (như Fleet Runner).
- Video ("Muse Video"): cảnh đang chọn làm video cao trào (`metadata.climax_video`) thì bản giao việc của
  `services/climax_brief.py` theo đúng cách `climax_video.run_scene_climax_video()` chọn; không thì
  `dialogue_video.scene_plan()` + `segment_prompt()` từng đoạn.

Không tạo việc Muse, không ghi project.json. Ngoại lệ đã biết: khoá nhân vật có bảng đã duyệt thì
`character_sheets.cast_board()` có thể ghi ảnh ghép `board_<hash>.jpg` (bộ nhớ đệm, đường thật cũng ghi đúng file đó).
"""
from pathlib import Path

from models.schemas import Project, Scene
from services import character_sheets as cs
from services import climax_video, location_sheets, scene_locks
from services import dialogue_video as dv
from services.climax_brief import crowd_brief, landscape_brief, scene_brief, target_seconds
from services.muse_image_task import image_task_fields
from services.muse_prompt_format import format_image_prompt, task_attachments

JS_DEFAULT_STYLE = "spartan_epic_mythology"   # app.js generateSceneWithMuse() dùng khi dự án không có phong cách
DONE_TOKEN_PLACEHOLDER = "<MÃ-XONG>"            # mã thật sinh ngẫu nhiên lúc chạy (XONG-xxxxxxxx)
ATTACHMENT_ROLE_VI = {"characters": "bảng nhân vật", "previous_scene": "khung cảnh trước", "location": "ảnh chuẩn bối cảnh",
                      "person": "ảnh tham chiếu nhân vật", "reference": "ảnh tham chiếu"}


class PromptPreviewError(ValueError):
    """Chưa xem trước được (thiếu giọng đọc, thiếu nhân vật...); lời nhắn tiếng Việt hiện thẳng cho người dùng."""


def base_image_prompt(project: Project, scene: Scene) -> str:
    """Prompt gốc mà nút "Muse 2K" gửi (app.js generateSceneWithMuse, mode image)."""
    text = scene.image_prompt or getattr(scene, "visual_prompt", "") or scene.text or ""
    anchor = project.character_anchor or ""
    if anchor and anchor not in text:
        text = f"{anchor}, {text}"
    return text


def image_preview(project: Project, scene: Scene) -> dict:
    """Chuỗi cuối cùng Muse nhận cho ảnh 2K của cảnh, ảnh đính kèm (tên file, vai), khoá đã áp."""
    prompt = base_image_prompt(project, scene)
    style = project.style_preset or JS_DEFAULT_STYLE
    params = {"resolution": "2K", "aspect_ratio": "16:9", "style_preset": style, "duration_sec": 5, "fps": 25,
              "action_cues": prompt}
    task = image_task_fields(prompt, params, negative_prompt=getattr(scene, "negative_prompt", "") or "")
    try:
        locks = scene_locks.scene_locks(project.id, scene.id, prompt)
    except ValueError as e:   # file danh sách hỏng: báo rõ như đường thật (409 ở create_task)
        raise PromptPreviewError(f"Không đọc được khoá hình của cảnh: {e}") from e
    scene_locks.apply_to_image_task(task, locks["location"], locks["characters"])
    attachments = task_attachments(task)
    roles = (task.get("parameters") or {}).get("attachment_roles") or []
    return {
        "kind": "image",
        "prompt": format_image_prompt(task, has_reference=bool(attachments)),
        "style_preset": style,
        "attachments": [{"name": Path(a).name,
                         "role": roles[i] if i < len(roles) else "reference",
                         "role_vi": ATTACHMENT_ROLE_VI.get(roles[i] if i < len(roles) else "reference", "ảnh tham chiếu")}
                        for i, a in enumerate(attachments)],
        "locks": {"characters": list((locks["characters"] or {}).get("names") or []),
                  "location": (locks["location"] or {}).get("name_vi")},
    }


def _climax_preview(project: Project, scene: Scene, state: dict) -> dict:
    try:
        seconds = climax_video._scene_seconds(scene)
    except climax_video.ClimaxVideoError as e:
        raise PromptPreviewError(e.message) from e
    approved = bool(state.get("grid_approved"))
    if approved:   # như run_scene_clips: tin cờ đã lưu khi grid đã duyệt
        crowd = state.get("crowd") is True
        kind = "unnamed" if crowd else ("none" if state.get("landscape") is True else "cast")
    else:          # như run_scene_climax_video: xếp loại lại mỗi lần
        kind = climax_video.scene_people_kind(project, scene)
    grid_count = 0
    if kind != "cast":
        lock = location_sheets.scene_lock(project.id, scene.id, scene.image_prompt or "")
        plate = (lock or {}).get("plate_path")
        brief = crowd_brief if kind == "unnamed" else landscape_brief
        prompt = brief(project, scene, seconds, DONE_TOKEN_PLACEHOLDER, (lock or {}).get("prompt_line"), bool(plate))
    else:
        cast = cs.peek_cast(project)
        people = cs.scene_characters(project, cast, scene) if cast else []
        if not people:
            raise PromptPreviewError("Chưa chọn nhân vật cho cảnh: bấm chip nhân vật trên thẻ cảnh hoặc mở Bảng nhân vật")
        grids = state.get("grid_paths") if approved else None
        grid_count = len(grids) if grids else len(climax_video.grid_plan(climax_video.clip_count(seconds)))
        prompt = scene_brief(project, scene, people, grid_count, seconds, DONE_TOKEN_PLACEHOLDER)
    return {"kind": "climax", "brief_kind": kind, "narration_seconds": round(seconds, 2),
            "target_seconds": target_seconds(seconds), "grid_count": grid_count,
            "needs_grid_first": kind == "cast" and not approved, "done_token_placeholder": DONE_TOKEN_PLACEHOLDER,
            "prompt": prompt}


def video_preview(project: Project, scene: Scene) -> dict:
    """Prompt video Muse của cảnh: bản giao việc cao trào, hoặc prompt từng đoạn video theo lời thoại."""
    state = climax_video._scene_state(scene)
    if state.get("status"):
        return _climax_preview(project, scene, state)
    try:
        plan = dv.scene_plan(project, scene)
    except dv.DialogueVideoError as e:
        raise PromptPreviewError(str(e)) from e
    segments = plan["segments"]
    lock = location_sheets.scene_lock(project.id, scene.id, scene.image_prompt or "")
    has_plate = bool((lock or {}).get("plate_path"))
    return {"kind": "dialogue", "video_count": len(segments), "narration_seconds": plan["narration_seconds"],
            "estimated": plan["estimated"],
            "segments": [{"index": seg["index"], "seconds": seg["seconds"], "text": seg["text"],
                          "prompt": dv.segment_prompt(project, scene, segments, k, lock, has_plate)}
                         for k, seg in enumerate(segments, 1)]}
