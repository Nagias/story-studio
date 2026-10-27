"""Bảng nhân vật đủ góc cho dự án vụ án (chủ dự án chốt 28/10/2026).

Mỗi người (CaseEntity kind "person") của vụ án có một bảng nhân vật: toàn thân trước, trái, sau, phải và đầu trước,
trái, sau, phải, trên. Muse vẽ trên tài khoản VIDEO (cùng loại tài khoản làm video cao trào); vẽ lại thì làm trong đúng
side chat cũ để Muse thấy bản sai trước. Chủ dự án duyệt bảng rồi mới dùng làm tham chiếu cho ảnh grid và clip.

Kiểu tóc không có mặc định (mỗi người một kiểu): thiết kế lấy từ câu tả ngoại hình của chính người đó (appearance_en),
thêm quy tắc chung giữ tóc/đầu/áo y hệt ở mọi góc. Chủ dự án sửa thiết kế từng người được.

Dữ liệu ở `projects/<id>/characters/characters.json` — chỉ module này ghi (giao diện tự lưu dự án không đè được).
Không gọi LLM; không import routers/ (`muse_call` truyền vào).
"""
import asyncio
import hashlib
import logging
import math
import re
import shutil
import threading
from pathlib import Path
from typing import Awaitable, Callable, Literal, Optional

from PIL import Image
from pydantic import BaseModel, Field

from config import PROJECTS_DIR, STATIC_DIR
from models.case_adaptation_schemas import CaseEntity
from models.schemas import Project, Scene
from security import is_within
from services import case_store, project_service, safe_files

logger = logging.getLogger("story_studio.character_sheets")

SheetStatus = Literal["draft", "drawing", "review", "approved", "failed"]
MuseCall = Callable[[dict], Awaitable[dict]]

ANGLE_RULE_EN = (
    "The head shape, face, hairstyle, clothes, shoes and colours described above are FIXED: draw them identically in "
    "every view. Decide once exactly where the hair grows on the head (hairline, top of the head, parting, length) and "
    "keep that exactly the same from the front, the sides, the back and the top: the hair must never cover the head in "
    "one view and leave it bare in another."
)
SHEET_LAYOUT_EN = (
    "Layout on a plain light grey background, no text, no labels: row 1 = full body FRONT, LEFT SIDE, BACK, RIGHT SIDE; "
    "row 2 = head close-ups FRONT, LEFT SIDE, BACK, RIGHT SIDE, TOP. Same proportions in every view. Before answering, "
    "check every view against the design."
)
MIN_RUN_WORDS = 5          # đoạn chữ trùng liên tiếp tối thiểu giữa câu tả ngoại hình và prompt ảnh cảnh
DISTINCT_MAX_PEOPLE = 2    # chữ "riêng" = chỉ xuất hiện trong câu tả của tối đa chừng này người
BOARD_W = 2048
BOARD_H = 1152
FEEDBACK_MAX = 500

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class CharacterSheet(BaseModel):
    entity_id: str
    name_vi: str
    role: str = "other"
    design_en: str
    status: SheetStatus = "draft"
    sheet_path: Optional[str] = None
    versions: list[str] = Field(default_factory=list)
    account_id: Optional[str] = None
    thread_url: Optional[str] = None
    error: Optional[str] = None
    feedback: list[str] = Field(default_factory=list)


class ProjectCast(BaseModel):
    characters: dict[str, CharacterSheet] = Field(default_factory=dict)
    scene_cast: dict[str, list[str]] = Field(default_factory=dict)   # chủ dự án đã chỉnh tay: ghi đè đoán tự động


class CastError(ValueError):
    """Lỗi dữ liệu bảng nhân vật; lời nhắn tiếng Việt hiện thẳng cho người dùng."""


# ------------------------------------------------------------------------------------------------------ lưu trữ
def _lock(project_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(project_id, threading.Lock())


def characters_dir(project_id: str) -> Path:
    d = project_service.ensure_project_dirs(project_id) / "characters"
    d.mkdir(exist_ok=True)
    return d


def _cast_path(project_id: str) -> Path:
    return characters_dir(project_id) / "characters.json"


def _project(project_id: str) -> Project:
    project = project_service.get_project(project_id)
    if project is None:
        raise LookupError(f"Không có dự án {project_id}")
    return project


def case_people(project: Project) -> list[CaseEntity]:
    """Người của vụ án gốc (rỗng nếu không phải dự án vụ án hoặc vụ đã mất)."""
    case_id = (project.metadata or {}).get("case_id")
    plan = case_store.load_plan(case_id) if case_id else None
    return [e for e in plan.bible.entities if e.kind == "person"] if plan else []


def default_design(entity: CaseEntity, style_id: str) -> str:
    """Thiết kế mặc định: ngoại hình riêng của người đó + nét vẽ của phong cách dự án + quy tắc giữ nguyên mọi góc."""
    from services.image_service import STYLE_PRESETS   # nạp muộn: image_service nặng và chỉ cần chuỗi phong cách
    style = (STYLE_PRESETS.get(style_id) or {}).get("prompt_suffix", "")
    parts = [f"Appearance: {entity.appearance_en.strip()}" if entity.appearance_en else
             f"A {entity.age_range} {entity.gender} person ({entity.role})."]
    if style:
        parts.append(f"Drawing style: {style}")
    parts.append(ANGLE_RULE_EN)
    return "\n".join(parts)


def load_cast(project_id: str) -> ProjectCast:
    """Bảng nhân vật của dự án; lần đầu (hoặc khi vụ án có thêm người) dựng từ kế hoạch vụ án, trạng thái "draft"."""
    project = _project(project_id)   # trước mọi thao tác thư mục: id sai không được sinh thư mục rác
    with _lock(project_id):
        text = safe_files.read_text(_cast_path(project_id))
        cast = ProjectCast.model_validate_json(text) if text else ProjectCast()
        added = False
        for e in case_people(project):
            if e.id not in cast.characters:
                cast.characters[e.id] = CharacterSheet(entity_id=e.id, name_vi=e.alias_vi, role=e.role,
                                                       design_en=default_design(e, project.style_preset))
                added = True
        if added or text is None:
            safe_files.write_text_atomic(_cast_path(project_id), cast.model_dump_json(indent=2))
        return cast


def save_cast(project_id: str, cast: ProjectCast) -> None:
    """Nơi duy nhất ghi characters.json."""
    with _lock(project_id):
        safe_files.write_text_atomic(_cast_path(project_id), cast.model_dump_json(indent=2))


def _update(project_id: str, entity_id: str, change: Callable[[CharacterSheet], None]) -> CharacterSheet:
    cast = load_cast(project_id)
    sheet = cast.characters.get(entity_id)
    if sheet is None:
        raise CastError(f"Dự án không có nhân vật {entity_id}")
    change(sheet)
    save_cast(project_id, cast)
    return sheet


# ------------------------------------------------------------------------------------------- nhân vật của cảnh
def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def guess_scene_cast(scene_prompt: str, appearances: dict[str, str]) -> list[str]:
    """Người có mặt trong cảnh: câu tả ngoại hình của họ trùng với prompt ảnh cảnh một đoạn ≥ MIN_RUN_WORDS chữ liên
    tiếp CÓ chữ riêng của họ (chữ chung như "east asian man in his early 30s" không tính). Thứ tự theo vị trí trong prompt.
    Prompt ảnh cảnh được viết từ chính câu tả ngoại hình nên đoạn trùng thường dài; đoán sai thì chủ dự án sửa tay."""
    prompt = _tokens(scene_prompt)
    toks = {eid: _tokens(text) for eid, text in appearances.items() if text}
    owners: dict[str, set[str]] = {}
    for eid, ts in toks.items():
        for t in set(ts):
            owners.setdefault(t, set()).add(eid)
    best: dict[str, tuple[int, int]] = {}   # eid -> (độ dài đoạn trùng dài nhất hợp lệ, vị trí bắt đầu trong prompt)
    for eid, ts in toks.items():
        prev = [0] * (len(ts) + 1)
        for i in range(1, len(prompt) + 1):
            cur = [0] * (len(ts) + 1)
            for j in range(1, len(ts) + 1):
                if prompt[i - 1] == ts[j - 1]:
                    cur[j] = prev[j - 1] + 1
                    n = cur[j]
                    if (n >= MIN_RUN_WORDS and n > best.get(eid, (0, 0))[0]
                            and any(len(owners[t]) <= DISTINCT_MAX_PEOPLE for t in ts[j - n:j])):
                        best[eid] = (n, i - n)
            prev = cur
    # Hai người khớp cùng một đoạn của prompt (câu tả giống nhau, vd "a slender East Asian woman in her"): chỉ giữ người
    # có đoạn trùng dài hơn.
    kept: list[tuple[int, int, str]] = []
    for eid, (n, start) in sorted(best.items(), key=lambda kv: -kv[1][0]):
        if all(start + n <= s or s + m <= start for m, s, _ in kept):
            kept.append((n, start, eid))
    return [eid for _, _, eid in sorted(kept, key=lambda k: k[1])]


def scene_cast(project: Project, cast: ProjectCast) -> dict[str, list[str]]:
    """scene_id -> entity_id có mặt: chủ dự án đã chỉnh thì theo đó, không thì đoán từ prompt ảnh."""
    appearances = {e.id: e.appearance_en for e in case_people(project)}
    out = {}
    for s in project.scenes:
        if s.id in cast.scene_cast:
            out[s.id] = list(cast.scene_cast[s.id])
        elif (s.metadata or {}).get("visual_kind") in ("image", "video"):
            out[s.id] = guess_scene_cast(s.image_prompt, appearances)
    return out


def set_scene_cast(project_id: str, scene_id: str, entity_ids: list[str]) -> list[str]:
    project = _project(project_id)
    if not any(s.id == scene_id for s in project.scenes):
        raise LookupError(f"Dự án không có cảnh {scene_id}")
    cast = load_cast(project_id)
    unknown = [e for e in entity_ids if e not in cast.characters]
    if unknown:
        raise CastError(f"Không có nhân vật: {', '.join(unknown)}")
    cast.scene_cast[scene_id] = list(dict.fromkeys(entity_ids))
    save_cast(project_id, cast)
    return cast.scene_cast[scene_id]


def reference_image(project: Project, cast: ProjectCast, entity_id: str) -> Optional[Path]:
    """Ảnh cảnh đầu tiên có người này (để Muse vẽ bảng đúng nét của dự án)."""
    by_scene = scene_cast(project, cast)
    for s in project.scenes:
        if entity_id in by_scene.get(s.id, []) and s.image_path:
            p = Path(s.image_path)
            if p.is_file() and is_within(p, PROJECTS_DIR, STATIC_DIR):
                return p
    return None


# ------------------------------------------------------------------------------------------------- vẽ, duyệt
def sheet_prompt(sheet: CharacterSheet) -> str:
    lines = [
        "tạo cho tôi 1 hình ảnh 2K tỉ lệ 16:9: CHARACTER TURNAROUND SHEET of ONE character, drawn in exactly the same "
        "art style as the attached scene image.",
        f"CHARACTER DESIGN:\n{sheet.design_en.strip()}",
        SHEET_LAYOUT_EN,
    ]
    for fb in sheet.feedback:
        lines.append(f"Bản trước SAI: {fb.strip()} — sửa đúng chỗ này, các góc còn lại giữ nguyên thiết kế.")
    return "\n".join(lines)


def _clear_thread(sheet: CharacterSheet) -> None:
    sheet.thread_url = None
    sheet.account_id = None


async def draw_sheet(project_id: str, entity_id: str, muse_call: MuseCall, reference: Path) -> CharacterSheet:
    """Muse (tài khoản video) vẽ bảng nhân vật; vẽ lại thì dùng đúng side chat cũ. Xong: trạng thái "review"."""
    cast = await asyncio.to_thread(load_cast, project_id)
    sheet = cast.characters.get(entity_id)
    if sheet is None:
        raise CastError(f"Dự án không có nhân vật {entity_id}")
    n = len(sheet.versions) + 1
    out = characters_dir(project_id) / entity_id / f"sheet_v{n}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    task = {"mode": "text-to-image", "route_kind": "video", "raw_prompt": True, "prompt": sheet_prompt(sheet),
            "attachments": [str(reference)], "aspect_ratio": "16:9", "parameters": {"aspect_ratio": "16:9"},
            "output_path": str(out)}
    if sheet.thread_url and sheet.account_id:
        task.update(thread_url=sheet.thread_url, assigned_account=sheet.account_id, pin_account=True)
    await asyncio.to_thread(_update, project_id, entity_id, lambda s: setattr(s, "status", "drawing"))
    try:
        result = await muse_call(task)
        got = Path(result.get("output_path") or "") if isinstance(result, dict) else Path()
        if not got.is_file():
            raise RuntimeError("Muse báo xong nhưng không có file ảnh")
        if got.resolve() != out.resolve():
            await asyncio.to_thread(shutil.copy2, got, out)
    except (RuntimeError, TimeoutError, OSError, ValueError) as e:
        err = e
        dirty = isinstance(err, TimeoutError) or "side chat" in str(err) or "THREAD_OPEN_FAILED" in str(err)

        def failed(s: CharacterSheet) -> None:
            s.status, s.error = "failed", f"Muse không vẽ được bảng nhân vật: {err}"
            if dirty:
                _clear_thread(s)   # chat có thể còn việc dở hoặc tài khoản chủ chat hỏng: lần sau mở chat mới
        sheet = await asyncio.to_thread(_update, project_id, entity_id, failed)
        logger.warning(f"Bảng nhân vật {project_id}/{entity_id} lỗi: {err}")
        return sheet

    def done(s: CharacterSheet) -> None:
        s.status, s.error = "review", None
        s.sheet_path = str(out)
        s.versions.append(str(out))
        s.thread_url = result.get("thread_url") or s.thread_url
        s.account_id = result.get("executed_by") or s.account_id
    return await asyncio.to_thread(_update, project_id, entity_id, done)


def approve_sheet(project_id: str, entity_id: str) -> CharacterSheet:
    def change(s: CharacterSheet) -> None:
        if not (s.sheet_path and Path(s.sheet_path).is_file()):
            raise CastError(f"{s.name_vi} chưa có bảng nhân vật để duyệt")
        s.status, s.error = "approved", None
    return _update(project_id, entity_id, change)


def reject_sheet(project_id: str, entity_id: str, feedback: str) -> CharacterSheet:
    fb = (feedback or "").strip()
    if not fb:
        raise CastError("Ghi rõ bảng sai chỗ nào để Muse vẽ lại đúng chỗ đó")
    if len(fb) > FEEDBACK_MAX:
        raise CastError(f"Ghi chú tối đa {FEEDBACK_MAX} ký tự")

    def change(s: CharacterSheet) -> None:
        s.feedback.append(fb)
        s.status = "draft"
    return _update(project_id, entity_id, change)


def set_design(project_id: str, entity_id: str, design_en: str) -> CharacterSheet:
    text = (design_en or "").strip()
    if not text:
        raise CastError("Thiết kế nhân vật không được để trống")

    def change(s: CharacterSheet) -> None:
        s.design_en = text
        if s.status == "approved":
            s.status = "draft"   # đổi thiết kế thì bảng cũ không còn đúng
    return _update(project_id, entity_id, change)


def import_approved_sheet(project_id: str, entity_id: str, image: Path, design_en: Optional[str] = None,
                          thread_url: Optional[str] = None, account_id: Optional[str] = None) -> CharacterSheet:
    """Nhận một bảng đã được chủ dự án duyệt ngoài app (vd lần thăm dò 28/10) làm bảng duyệt sẵn."""
    load_cast(project_id)
    dest = characters_dir(project_id) / entity_id / "sheet_v1.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image, dest)

    def change(s: CharacterSheet) -> None:
        if design_en:
            s.design_en = design_en.strip()
        s.sheet_path, s.versions, s.status, s.error = str(dest), [str(dest)], "approved", None
        s.thread_url, s.account_id = thread_url, account_id
    return _update(project_id, entity_id, change)


# --------------------------------------------------------------------------------------------- bảng diễn viên
def board_positions(n: int) -> list[str]:
    """Tên vị trí từng bảng trong ảnh ghép (để prompt nói ai ở đâu)."""
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    names = []
    for i in range(n):
        r, c = divmod(i, cols)
        vert = "" if rows == 1 else ("top" if r == 0 else "bottom" if r == rows - 1 else "middle")
        horiz = "" if cols == 1 else ("left" if c == 0 else "right" if c == cols - 1 else "centre")
        names.append(" ".join(x for x in (vert, horiz) if x) or "whole image")
    return names


def cast_board(project_id: str, entity_ids: list[str]) -> Path:
    """Ghép bảng ĐÃ DUYỆT của các nhân vật thành một ảnh 16:9 (giữ 2 ảnh đính kèm mỗi tin nhắn Muse)."""
    if not entity_ids:
        raise CastError("Cảnh chưa có nhân vật nào")
    cast = load_cast(project_id)
    sheets = []
    for eid in entity_ids:
        s = cast.characters.get(eid)
        if s is None:
            raise CastError(f"Dự án không có nhân vật {eid}")
        if s.status != "approved" or not (s.sheet_path and Path(s.sheet_path).is_file()):
            raise CastError(f"{s.name_vi} chưa có bảng nhân vật được duyệt")
        sheets.append(Path(s.sheet_path))
    key = hashlib.sha1("|".join(f"{p}:{p.stat().st_mtime_ns}" for p in sheets).encode()).hexdigest()[:12]
    out = characters_dir(project_id) / f"board_{key}.jpg"
    if out.is_file():
        return out
    cols = math.ceil(math.sqrt(len(sheets)))
    rows = math.ceil(len(sheets) / cols)
    cw, ch = BOARD_W // cols, BOARD_H // rows
    board = Image.new("RGB", (BOARD_W, BOARD_H), (225, 225, 225))
    for i, p in enumerate(sheets):
        r, c = divmod(i, cols)
        with Image.open(p) as raw:
            img = raw.convert("RGB")
        img.thumbnail((cw - 8, ch - 8), Image.Resampling.LANCZOS)
        board.paste(img, (c * cw + (cw - img.width) // 2, r * ch + (ch - img.height) // 2))
    board.save(out, "JPEG", quality=92)
    return out


def scene_characters(project: Project, cast: ProjectCast, scene: Scene) -> list[CharacterSheet]:
    return [cast.characters[e] for e in scene_cast(project, cast).get(scene.id, []) if e in cast.characters]
