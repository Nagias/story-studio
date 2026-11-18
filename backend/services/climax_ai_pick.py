"""AI (Gemini qua 9router) chọn cảnh làm video cao trào, thay cho cách chấm điểm theo nhãn kịch bản.

Chủ dự án 15/11/2026: "có nút chọn cảnh cao trào mà người dùng có thể chọn, kèm theo là có AI chọn riêng ra", "Sử dụng
model gemini để làm tác vụ này". Model là NINEROUTER_LLM_MODEL (config.py), gọi qua services/case_adaptation_llm.py.

Cách làm (LLM 9router hay làm tắt khi việc lớn: chia nhỏ, kiểm từng phần, chạy lần lượt):
1. Cảnh đủ điều kiện (`climax_video.is_eligible`) chia thành nhóm GROUP_SIZE cảnh; mỗi nhóm kèm CONTEXT_SCENES cảnh
   trước và sau làm ngữ cảnh chỉ đọc.
2. Mỗi nhóm một lượt `ask_validated`: LLM chấm từng cảnh 0–10 "đáng làm video chuyển động" kèm một câu lý do. Code kiểm
   đủ mọi id của nhóm, không id lạ, không trùng, điểm là số 0–10, lý do không rỗng; sai thì hỏi lại kèm lý do.
3. Gộp điểm, xếp giảm dần (bằng điểm: cảnh có nhân vật trước, rồi cảnh đứng trước), lấy tới khi lời kể của các cảnh
   chọn đạt video_rules.TARGET_SHARE tổng thời lượng lời kể; chưa có giọng đọc thì lấy ceil(video_rules.TARGET_SHARE * số cảnh).

AI lỗi hẳn (hết lượt thử) thì StepFailed nổi lên: không âm thầm quay về cách chấm theo nhãn (CLAUDE.md đường cấm 3, 4);
người dùng tự bấm "Chọn theo nhãn kịch bản" nếu muốn. Module này không ghi project.json (router ghi), không import
routers/. LLM truyền vào được để test.
"""
import asyncio
import math
from typing import Any, Optional

from models.schemas import Project, Scene
from services import climax_video, project_service
from services import video_rules
from services.case_adaptation_llm import LLMCall, call_llm_json
from services.case_adaptation_steps import StepRejected, ask_validated

GROUP_SIZE = 14          # số cảnh chấm trong một lượt gọi (brief: 12–15)
CONTEXT_SCENES = 2       # số cảnh trước và sau nhóm gửi kèm làm ngữ cảnh (không chấm)
SCORE_MIN, SCORE_MAX = 0, 10
REASON_MAX = 200
TASK_MARKER = "CHAM_CAO_TRAO"

SYSTEM_PROMPT = """\
Bạn là đạo diễn dựng video YouTube kể chuyện (truyện, vụ án). Mỗi cảnh hiện là một ảnh tĩnh; chỉ khoảng một nửa thời
lượng được làm thành video chuyển động thật bằng AI, nên phải chọn đúng cảnh đáng làm video nhất. Bạn đọc lời kể từng
cảnh và chấm điểm. Chỉ trả về đúng một JSON object, không thêm chữ nào."""


class ClimaxPickError(RuntimeError):
    """Không chọn được (dự án không có, không có cảnh đủ điều kiện). Lời nhắn tiếng Việt hiện thẳng cho người dùng."""


def eligible_scenes(project: Project) -> list[Scene]:
    return [s for s in project.scenes if climax_video.is_eligible(s)]


def groups(scenes: list[Scene], size: Optional[int] = None) -> list[list[Scene]]:
    """Chia danh sách cảnh thành các nhóm liền nhau, mỗi nhóm tối đa `size` cảnh (mặc định GROUP_SIZE)."""
    size = GROUP_SIZE if size is None else size
    if size < 1:
        raise ValueError("size phải >= 1")
    return [scenes[i:i + size] for i in range(0, len(scenes), size)]


def _one_line(text: str) -> str:
    return " ".join((text or "").split())


def _scene_line(scene: Scene, has_people: Optional[bool]) -> str:
    dur = f"{scene.duration:.1f} giây" if scene.duration else "chưa có giọng đọc"
    people = "" if has_people is None else (" · có nhân vật" if has_people else " · không có nhân vật")
    return f"[{scene.id}] ({dur}{people}) {_one_line(scene.text)}"


def group_prompt(project: Project, group: list[Scene], index: int, total: int,
                 people: dict[str, bool]) -> str:
    """Prompt chấm một nhóm. Dòng đầu là marker (LLM giả trong test nhận ra lượt gọi)."""
    order = {s.id: i for i, s in enumerate(project.scenes)}
    first, last = order[group[0].id], order[group[-1].id]
    before = project.scenes[max(0, first - CONTEXT_SCENES):first]
    after = project.scenes[last + 1:last + 1 + CONTEXT_SCENES]
    lines = [
        f"TASK: {TASK_MARKER} {index}",
        f"Nhóm {index}/{total} của video \"{_one_line(project.name)}\".",
        "",
        "Chấm MỖI cảnh trong mục CẢNH CẦN CHẤM một điểm nguyên hoặc thập phân từ 0 đến 10: cảnh này đáng làm video "
        "chuyển động đến mức nào. Điểm cao khi cảnh có: kịch tính, căng thẳng; hành động (đuổi, đánh, chạy, phát hiện); "
        "cảm xúc mạnh (sợ hãi, đau buồn, giận dữ); bước ngoặt của câu chuyện. Điểm thấp khi cảnh chỉ giới thiệu, giải "
        "thích, kể bối cảnh tĩnh hoặc tóm lại. Cảnh có nhân vật làm video dễ đẹp hơn cảnh không người, nhưng chấm theo "
        "nội dung là chính.",
        "Mỗi cảnh kèm một câu lý do tiếng Việt ngắn (dưới 25 chữ), nói cảnh có gì đáng (hoặc không đáng) làm video.",
        "Chấm đủ mọi cảnh, không bỏ cảnh nào, không thêm id nào khác, mỗi id đúng một lần.",
        "",
    ]
    if before:
        lines += ["NGỮ CẢNH TRƯỚC (chỉ để hiểu mạch truyện, KHÔNG chấm):",
                  *[_scene_line(s, None) for s in before], ""]
    lines += ["CẢNH CẦN CHẤM:", *[_scene_line(s, people.get(s.id)) for s in group], ""]
    if after:
        lines += ["NGỮ CẢNH SAU (chỉ để hiểu mạch truyện, KHÔNG chấm):",
                  *[_scene_line(s, None) for s in after], ""]
    lines += ['Trả về JSON: {"scenes": [{"id": "<id cảnh>", "score": <0-10>, "reason": "<một câu>"}, ...]}']
    return "\n".join(lines)


def validate_group(raw: Any, ids: list[str]) -> dict[str, tuple[float, str]]:
    """{id: (điểm, lý do)} khi đủ mọi id của nhóm; StepRejected (lý do gửi lại cho LLM) khi sai."""
    items = raw.get("scenes") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise StepRejected('Thiếu mảng "scenes".')
    wanted = set(ids)
    out: dict[str, tuple[float, str]] = {}
    problems: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            problems.append("có phần tử không phải object")
            continue
        sid = str(item.get("id") or "").strip()
        if sid not in wanted:
            problems.append(f"id lạ {sid or '(trống)'} (chỉ chấm cảnh trong mục CẢNH CẦN CHẤM)")
            continue
        if sid in seen:
            problems.append(f"id {sid} xuất hiện hai lần")
            continue
        seen.add(sid)
        score = item.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) \
                or not SCORE_MIN <= score <= SCORE_MAX:
            problems.append(f"điểm của {sid} không phải số từ {SCORE_MIN} đến {SCORE_MAX}")
            continue
        reason = _one_line(str(item.get("reason") or ""))
        if not reason:
            problems.append(f"lý do của {sid} trống")
            continue
        out[sid] = (float(score), reason[:REASON_MAX])
    missing = [i for i in ids if i not in seen]
    if missing:
        problems.append("thiếu cảnh " + ", ".join(missing[:12]))
    if problems:
        raise StepRejected("; ".join(problems[:12]))
    return out


def choose(project: Project, scores: dict[str, float], people: dict[str, bool]) -> list[str]:
    """Cảnh điểm cao trước (bằng điểm: có nhân vật trước, rồi cảnh đứng trước), lấy tới khi đạt video_rules.TARGET_SHARE tổng
    thời lượng lời kể; chưa có giọng đọc thì ceil(video_rules.TARGET_SHARE * số cảnh được chấm). Trả theo thứ tự cảnh."""
    order = {s.id: i for i, s in enumerate(project.scenes)}
    by_id = {s.id: s for s in project.scenes}
    ranked = sorted((sid for sid in scores if sid in by_id),
                    key=lambda sid: (-scores[sid], not people.get(sid, True), order[sid]))
    total = sum(s.duration or 0 for s in project.scenes)
    chosen: set[str] = set()
    if total > 0:
        covered = 0.0
        for sid in ranked:
            if covered >= video_rules.TARGET_SHARE * total:
                break
            chosen.add(sid)
            covered += by_id[sid].duration or 0
    else:
        chosen = set(ranked[:math.ceil(video_rules.TARGET_SHARE * len(ranked))])
    return [s.id for s in project.scenes if s.id in chosen]


def _people_map(project: Project, scenes: list[Scene]) -> dict[str, bool]:
    return {sid: kind != "none" for sid, kind in climax_video.scene_people_kinds(project, scenes).items()}


async def ai_pick(project_id: str, llm: Optional[LLMCall] = None) -> dict:
    """Chấm mọi cảnh đủ điều kiện bằng LLM (từng nhóm, lần lượt) rồi chọn đủ video_rules.TARGET_SHARE thời lượng.
    Trả {chosen, reasons, scores, coverage}. Không ghi gì. LLM hỏng hẳn: StepFailed."""
    project = await asyncio.to_thread(project_service.get_project, project_id)
    if project is None:
        raise ClimaxPickError(f"Không có dự án {project_id}")
    pool = eligible_scenes(project)
    if not pool:
        raise ClimaxPickError("Dự án chưa có cảnh vẽ nào làm video được (bảng ghim, thẻ miễn trừ, ảnh thật thì không)")
    people = await asyncio.to_thread(_people_map, project, pool)
    base = llm or call_llm_json

    async def call(_system: str, user: str, **kwargs: Any) -> Any:
        return await base(SYSTEM_PROMPT, user, **kwargs)

    parts = groups(pool)
    scores: dict[str, float] = {}
    reasons: dict[str, str] = {}
    for n, group in enumerate(parts, start=1):
        ids = [s.id for s in group]
        result = await ask_validated(group_prompt(project, group, n, len(parts), people),
                                     lambda raw, ids=ids: validate_group(raw, ids), llm=call, temperature=0.2,
                                     step_label=f"AI chấm cảnh cao trào (nhóm {n}/{len(parts)})")
        for sid, (score, reason) in result.items():
            scores[sid], reasons[sid] = score, reason
    chosen = choose(project, scores, people)
    return {"chosen": chosen, "reasons": reasons, "scores": scores,
            "coverage": climax_video.coverage(project, chosen)}
