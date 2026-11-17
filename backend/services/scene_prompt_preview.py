"""Xem trước prompt thật gửi Muse cho một cảnh (thẻ cảnh: "Prompt đầy đủ gửi Muse", "Video gửi Muse").

Chủ dự án 15/11/2026: "Prompt thực tế như nào cũng phải có trên tool luôn", và khi muốn làm lại ảnh/video một cảnh
thì phải biết prompt lấy ở đâu. File này không ghép chữ riêng: nó gọi đúng các hàm mà đường thật gọi.
- Ảnh ("Muse 2K"): prompt gốc như `generateSceneWithMuse()` trong app.js → `muse_image_task.image_task_fields()`
  (như `routers/muse_bridge.create_task`) → `scene_locks.scene_locks()` + `apply_to_image_task()` →
  `muse_prompt_format.format_image_prompt()` (như Fleet Runner).
- Video: nút "Muse Video" trên thẻ luôn gửi prompt từng đoạn (`dialogue_video.scene_plan()` + `segment_prompt()`);
  cảnh đang chọn làm video cao trào (`metadata.climax_video`) thì thêm bản giao việc của `services/climax_brief.py` mà
  nút làm video cao trào gửi, chọn và kiểm điều kiện bằng chính các hàm của `services/climax_video.py`.

Không tạo việc Muse, không ghi project.json. Ngoại lệ đã biết: khoá nhân vật có bảng đã duyệt thì
`character_sheets.cast_board()` có thể ghi ảnh ghép `board_<hash>.jpg` (bộ nhớ đệm, đường thật cũng ghi đúng file đó).
"""
from pathlib import Path
from typing import Optional

from config import DEFAULT_STYLE
from models.schemas import Project, Scene
from services import character_sheets as cs
from services import climax_video, location_sheets, scene_locks
from services import dialogue_video as dv
from services.climax_brief import agent_parts, crowd_brief, landscape_brief, part_panels, scene_brief, target_seconds
from services.muse_image_task import image_task_fields
from services.muse_prompt_format import format_image_prompt, task_attachments

JS_DEFAULT_STYLE = DEFAULT_STYLE   # app.js DEFAULT_STYLE_PRESET (cùng giá trị, test_prompt_rules kiểm)
DONE_TOKEN_PLACEHOLDER = "<MÃ-XONG>"            # mã thật sinh ngẫu nhiên lúc chạy (XONG-xxxxxxxx)
ATTACHMENT_ROLE_VI = {"characters": "bảng nhân vật", "previous_scene": "khung cảnh trước", "location": "ảnh chuẩn bối cảnh",
                      "person": "ảnh tham chiếu nhân vật", "reference": "ảnh tham chiếu"}


class PromptPreviewError(ValueError):
    """Chưa xem trước được (thiếu giọng đọc, thiếu nhân vật...); lời nhắn tiếng Việt hiện thẳng cho người dùng."""


def base_image_prompt(project: Project, scene: Scene) -> str:
    """Prompt gốc mà nút "Muse 2K" gửi (app.js generateSceneWithMuse, mode image)."""
    # Không ghép "nhân vật chính chung" cũ (character_anchor) vào prompt: khoá nhân vật theo cảnh thay nó
    # (services/scene_locks.py); ghép vào thì ép một người vào cả cảnh không có họ (rà soát 18/11/2026).
    return scene.image_prompt or getattr(scene, "visual_prompt", "") or scene.text or ""


def image_task(project: Project, scene: Scene) -> tuple[dict, dict]:
    """(việc ảnh Muse 2K của cảnh trước khi vào Fleet Runner, khoá đã áp) — đúng như nút "Muse 2K" gửi qua
    `routers/muse_bridge.create_task`. Nút "Tạo hình cho cả dự án" (services/one_pass_visuals.py) gửi đúng việc này."""
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
    return task, locks


def image_preview(project: Project, scene: Scene) -> dict:
    """Chuỗi cuối cùng Muse nhận cho ảnh 2K của cảnh, ảnh đính kèm (tên file, vai), khoá đã áp."""
    task, locks = image_task(project, scene)
    style = task["parameters"]["style_preset"]
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


def _join_parts(briefs: list[str]) -> str:
    """Các bản giao việc của một cảnh (mỗi phần lời kể một việc Muse, climax_brief.AGENT_PART_MAX_SEC)."""
    if len(briefs) == 1:
        return briefs[0]
    return "\n\n".join(f"===== VIỆC MUSE {k}/{len(briefs)} =====\n{b}" for k, b in enumerate(briefs, 1))


def climax_preview(project: Project, scene: Scene) -> Optional[dict]:
    """Bản giao việc mà nút làm video cao trào (#btn-climax-video-run) sẽ gửi Muse cho cảnh, hoặc None nếu cảnh không
    được chọn. Đường thật sẽ dừng (thiếu giọng, thiếu ảnh, bảng nhân vật chưa duyệt, grid không khớp...) thì
    `blocked` ghi đúng lời nhắn của đường thật và không có `prompt`. Cùng thứ tự kiểm như run_scene_climax_video."""
    state = climax_video.scene_state(scene)
    if not state.get("status"):
        return None
    out = {"brief_kind": None, "narration_seconds": None, "target_seconds": None, "grid_count": 0,
           "needs_grid_first": False, "done_token_placeholder": DONE_TOKEN_PLACEHOLDER, "prompt": None, "blocked": None}
    approved = bool(state.get("grid_approved"))
    try:
        if approved:   # như run_scene_clips: tin cờ đã lưu khi grid đã duyệt
            kind = "unnamed" if state.get("crowd") is True else ("none" if state.get("landscape") is True else "cast")
        else:          # như run_scene_climax_video: xếp loại lại mỗi lần
            kind = climax_video.scene_people_kind(project, scene)
        out.update(brief_kind=kind, needs_grid_first=kind == "cast" and not approved)
        seconds, _image = climax_video.prepare_scene(scene, project.id)
        parts = agent_parts(scene, seconds)
        n = len(parts)
        out.update(narration_seconds=round(seconds, 2), target_seconds=target_seconds(seconds), part_count=n)
        if kind != "cast":
            lock = location_sheets.scene_lock(project.id, scene.id, scene.image_prompt or "")
            plate = (lock or {}).get("plate_path")
            brief = crowd_brief if kind == "unnamed" else landscape_brief
            out["prompt"] = _join_parts([brief(project, scene, seconds, DONE_TOKEN_PLACEHOLDER,
                                               (lock or {}).get("prompt_line"), bool(plate), part=p, n_parts=n)
                                         for p in parts])
            return out
        people, _positions, _board = climax_video.cast_for(project, scene)
        if approved:
            grid_count = len(climax_video.approved_grid_files(project.id, scene.id, state, seconds))
        else:
            grid_count = len(climax_video.grid_plan(climax_video.clip_count(seconds)))
        out["grid_count"] = grid_count
        grid_slots = [object()] * grid_count   # như run_scene_clips: mỗi phần chỉ đính kèm lưới chứa ô của nó
        briefs = []
        for p in parts:
            grids, panels = climax_video._grids_for(grid_slots, part_panels(p))
            briefs.append(scene_brief(project, scene, people, len(grids), seconds, DONE_TOKEN_PLACEHOLDER, part=p,
                                      n_parts=n, panels=panels if n > 1 else None))
        out["prompt"] = _join_parts(briefs)
    except climax_video.ClimaxVideoError as e:
        out["blocked"] = e.message
    except (cs.CastError, ValueError) as e:   # danh sách nhân vật/bối cảnh hỏng: đường thật cũng dừng ở đây
        out["blocked"] = str(e)
    return out


def dialogue_preview(project: Project, scene: Scene) -> dict:
    """Prompt từng video mà nút "Muse Video" trên thẻ (runSceneMuseVideo → dialogue_video) gửi. Đường thật sẽ từ chối
    (chưa có giọng, chưa có ảnh) thì `blocked` ghi lời nhắn của nó; lời kể không chia được thì `error`."""
    try:
        plan = dv.scene_plan(project, scene)
    except dv.DialogueVideoError as e:
        return {"error": str(e), "blocked": str(e), "segments": []}
    try:
        dv.check_ready(project.id, scene)
        blocked = None
    except dv.DialogueVideoError as e:
        blocked = str(e)
    segments = plan["segments"]
    lock = location_sheets.scene_lock(project.id, scene.id, scene.image_prompt or "")
    has_plate = bool((lock or {}).get("plate_path"))
    return {"video_count": len(segments), "narration_seconds": plan["narration_seconds"],
            "estimated": plan["estimated"], "blocked": blocked, "error": None,
            "segments": [{"index": seg["index"], "seconds": seg["seconds"], "text": seg["text"],
                          "prompt": dv.segment_prompt(project, scene, segments, k, lock, has_plate)}
                         for k, seg in enumerate(segments, 1)]}


def video_preview(project: Project, scene: Scene) -> dict:
    """Cả hai đường video của cảnh, mỗi đường ghi rõ nút nào gửi: `dialogue` (nút "Muse Video" trên thẻ, luôn có) và
    `climax` (nút làm video cao trào, chỉ khi cảnh được chọn làm video cao trào)."""
    return {"kind": "video", "dialogue": dialogue_preview(project, scene), "climax": climax_preview(project, scene)}
