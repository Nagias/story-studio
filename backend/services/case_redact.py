"""
Ẩn tên thật khỏi thông báo lỗi trả cho giao diện (spec mục 5: không lọt tên thật ra ngoài).

Thông báo của một việc hỏng trích dẫn thẳng chữ LLM vừa viết hoặc bảng tên ("có tên thật 'X'", "tên hư cấu trùng tên thật
'X'", tóm tắt sự việc quá ngắn...). hide_real_names thay mọi tên thật đã biết của vụ án trong thông báo bằng MASK.

Tên đã biết gồm: real_names của kế hoạch (nếu đã có), kết quả các việc đã xong (tên đã đọc ở từng đoạn, nhóm tên, bảng tên)
và tên mà regex bắt được trên bài gốc. Như mọi lớp kiểm lọt tên (spec mục 10), chỉ ẩn được những tên đã biết.
"""
import dataclasses
import logging
from types import SimpleNamespace

from services import case_store
from services.case_adaptation_checks import apply_aliases, build_forbidden_names, is_kept_term

logger = logging.getLogger(__name__)

MASK = "[tên đã ẩn]"


def _strings(items) -> list[str]:
    return [s for s in items if isinstance(s, str)] if isinstance(items, list) else []


def _dicts(items) -> list[dict]:
    return [d for d in items if isinstance(d, dict)] if isinstance(items, list) else []


def _plan_names(case_id: str) -> list[str]:
    plan = case_store.load_plan(case_id)
    return [n for e in plan.bible.entities for n in e.real_names] if plan is not None else []


def _step_names(case_id: str) -> list[str]:
    pipeline = case_store.load_pipeline(case_id)
    names: list[str] = []
    for step in pipeline.steps if pipeline is not None else []:
        if step.status != "done" or step.kind not in ("extract_chunk", "cluster_names", "assign_aliases"):
            continue
        data = case_store.load_step_output(case_id, step.id)
        if not isinstance(data, dict):
            continue
        if step.kind == "extract_chunk":
            names += [n.get("name") for n in _dicts(data.get("names"))]
        elif step.kind == "cluster_names":
            for group in _dicts(data.get("groups")):
                names += _strings(group.get("real_names"))
        else:
            for entity in _dicts(data.get("entities")):
                names += _strings(entity.get("real_names"))
    return [n for n in names if isinstance(n, str)]


def hide_real_names(case_id: str, text: str, fallback: str) -> str:
    """`text` với mọi tên thật đã biết của vụ án `case_id` đổi thành MASK. Không bao giờ raise: không đọc được dữ liệu
    của vụ án thì trả `fallback` (chữ cố định, không chứa tên)."""
    if not text:
        return text
    try:
        names = [n for n in dict.fromkeys(_plan_names(case_id) + _step_names(case_id))
                 if n.strip() and not is_kept_term(n)]
        # build_forbidden_names chỉ đọc entities[].{id, kind, real_names, alias_vi, alias_en}; thêm cả tên regex bắt được.
        bible = SimpleNamespace(entities=[SimpleNamespace(id="known", kind="person", real_names=names,
                                                          alias_vi="", alias_en="")])
        forbidden = build_forbidden_names(bible, case_store.load_source(case_id) or "")
        masked = [dataclasses.replace(f, alias_vi=MASK, alias_en=MASK) for f in forbidden]
        # any_case: thông báo lỗi trích nguyên chữ LLM viết, có thể viết thường cả tên; ẩn thừa ở đây không hại gì.
        return apply_aliases(text, masked, "vi", any_case=True)[0]
    except Exception:
        logger.exception("Vụ %s: không ẩn được tên thật trong thông báo; dùng thông báo chung", case_id)
        return fallback
