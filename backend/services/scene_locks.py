"""Khoá hình của một cảnh, dùng chung cho mọi đường tạo ảnh cảnh (luồng chung truyện chữ và vụ án, 03/11/2026).

Chủ dự án (CLAUDE.md mục 1.2 câu 17): quan trọng nhất là khoá bối cảnh và khoá nhân vật.
- Khoá nhân vật: người có mặt trong cảnh (`character_sheets.scene_cast`) -> câu mô tả ngoại hình cố định của từng người;
  ai có bảng nhân vật ĐÃ DUYỆT thì ghép bảng (`cast_board`) đính kèm cho Muse.
- Khoá bối cảnh: `location_sheets.scene_lock` (mô tả cố định, ảnh chuẩn).

`scene_locks()` trả cả hai cho một cảnh; `apply_to_image_task()` là nơi DUY NHẤT xếp ảnh đính kèm của việc tạo ảnh Muse
(bảng nhân vật, ảnh tham chiếu hoặc cảnh trước, ảnh chuẩn bối cảnh) và ghi vai trò từng ảnh vào
`parameters.attachment_roles` để Fleet Runner dặn Muse đúng. Dự án có khoá nhân vật thì bỏ "nhân vật chính chung" cũ
(`character_anchor` một người cho mọi cảnh), vì nó ép một người vào cả cảnh không có người đó.
"""
from pathlib import Path
from typing import Optional

from security import is_safe_id
from services import character_sheets as cs
from services import location_sheets, project_service

CHARACTER_LINE_EN = ("FIXED CHARACTERS in this scene (draw each one exactly as described: same head shape, face, "
                     "hairstyle, clothes and colours as in every other scene; this overrides any other description of "
                     "their looks in this prompt, and they are still drawn in the drawing style of this prompt):")
BOARD_LINE_EN = ("The attached CHARACTER SHEET shows {names} from every angle: copy their design exactly, do not copy "
                 "the sheet layout into the scene.")
MAX_ATTACHMENTS = 3


def character_lock(project_id: str, scene_id: str) -> Optional[dict]:
    """Gói khoá nhân vật của cảnh, hoặc None nếu dự án chưa có nhân vật hay cảnh không có ai. Gói: entity_ids, names,
    prompt_line, board_path (ảnh ghép bảng đã duyệt của người trong cảnh, None nếu chưa ai được duyệt)."""
    if not (is_safe_id(project_id) and is_safe_id(scene_id)):
        return None
    project = project_service.get_project(project_id)
    scene = next((s for s in project.scenes if s.id == scene_id), None) if project else None
    if project is None or scene is None:
        return None
    cast = cs.peek_cast(project)
    if cast is None or not cast.characters:
        return None
    people = cs.scene_characters(project, cast, scene)
    if not people:
        return None
    lines = [CHARACTER_LINE_EN]
    for p in people:
        rule = cs.hair_rule_line(p.design_en, cs.hair_rule_for(project, p.entity_id))
        lines.append(f"- {p.name_vi}: {cs.look_text(p.design_en)}" + (f" {rule}" if rule else ""))
    approved = [p for p in people if p.status == "approved" and p.sheet_path and Path(p.sheet_path).is_file()]
    board = None
    if approved:
        board = str(cs.cast_board(project_id, [p.entity_id for p in approved]))
        lines.append(BOARD_LINE_EN.format(names=", ".join(p.name_vi for p in approved)))
    return {"entity_ids": [p.entity_id for p in people], "names": [p.name_vi for p in people],
            "prompt_line": "\n".join(lines), "board_path": board}


def scene_locks(project_id: str, scene_id: str, scene_prompt: str = "") -> dict:
    """{"location": gói khoá bối cảnh hoặc None, "characters": gói khoá nhân vật hoặc None}. File danh sách hỏng thì
    báo lỗi (ValueError), không coi như không có khoá."""
    return {"location": location_sheets.scene_lock(project_id, scene_id, scene_prompt),
            "characters": character_lock(project_id, scene_id)}


def lock_prompt(prompt: str, location: Optional[dict], characters: Optional[dict]) -> str:
    """Prompt có thêm câu khoá (mỗi câu một lần)."""
    out = (prompt or "").strip()
    for lock in (characters, location):
        line = (lock or {}).get("prompt_line")
        if line and line not in out:
            out = f"{out}\n{line}" if out else line
    return out


def apply_to_image_task(task: dict, location: Optional[dict] = None, characters: Optional[dict] = None) -> dict:
    """Sửa việc tạo ảnh Muse theo khoá của cảnh: thêm câu khoá vào prompt, xếp ảnh đính kèm theo thứ tự bảng nhân vật,
    ảnh tham chiếu sẵn có (cảnh trước hoặc ảnh nhân vật), ảnh chuẩn bối cảnh; ghi vai trò từng ảnh."""
    if not location and not characters:
        return task
    task["prompt"] = lock_prompt(task.get("prompt") or "", location, characters)
    params = task.setdefault("parameters", {})
    if location:
        params["location_id"] = location["location_id"]
    board = (characters or {}).get("board_path")
    if characters:
        params["character_ids"] = list(characters["entity_ids"])
        task["character_anchor"] = ""
        params.pop("character_anchor", None)
    ref = next((str(r) for r in (task.get("reference_image_path"), task.get("reference_image"),
                                 task.get("reference_image_url")) if r), None)
    ref_role = "previous_scene" if params.get("reference_role") == "previous_scene" else "person"
    if characters and ref_role == "person":
        # Ảnh nhân vật cũ (một người cho cả dự án) không đúng với cảnh có người khác: khoá nhân vật thay cho nó
        ref = None
        for key in ("reference_image", "reference_image_path", "reference_image_url"):
            task[key] = None
        params.pop("reference_image", None)
    plate = (location or {}).get("plate_path")
    pairs = [(board, "characters"), (ref, ref_role), (plate, "location")]
    pairs = [(path, role) for path, role in pairs if path]
    if len(pairs) > MAX_ATTACHMENTS:
        pairs = pairs[:MAX_ATTACHMENTS]
    if board or plate:
        task["attachments"] = [path for path, _ in pairs]
        params["attachment_roles"] = [role for _, role in pairs]
        if plate:
            params["location_reference"] = True
    return task
