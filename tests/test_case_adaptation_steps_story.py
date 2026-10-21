"""
G5–G7 của luồng chuyển thể vụ án: dàn ý, viết lời Việt → lời Anh → prompt hình cho từng nhịp, ráp kế hoạch.

- LLM giả (tests/case_adaptation_fakes.py) đọc marker ở dòng đầu prompt và trả fixture trong
  tests/fixtures/case_adaptation/; không gọi 9router thật.
- Mỗi test chạy cả hàng việc như worker: chạy từng việc theo thứ tự, lưu kết quả, chèn các việc mới sinh ra
  ngay sau việc vừa chạy.
- Đầu ra mỏng (thiếu cảnh, lời quá ngắn, bỏ sót sự việc) bị loại và gọi lại kèm lý do; hỏng 3 lần thì StepFailed.
"""
import asyncio
import copy
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.case_adaptation_schemas import DISCLAIMER, MAX_ATTEMPTS, TARGET_SCENES, CaseBible, CaseEntity, CasePipeline
from services import case_store
from services.case_adaptation_checks import fold, has_blocking_flags
from services.case_adaptation_llm import LLMError
from services.case_adaptation_prompts import outline_prompt
from services.case_adaptation_steps import (
    STEP_TIMEOUTS,
    SoftRejected,
    StepFailed,
    StepRejected,
    _TextGuard,
    ask_validated,
    chunk_source,
    initial_steps,
    rewrite_english,
    run_step,
)
from services.video_service import CAMERA_MOTIONS
from tests.case_adaptation_fakes import FIXTURES_DIR, load_fixture, make_fake_llm, marker_of

DOSSIER = (FIXTURES_DIR / "dossier.txt").read_text(encoding="utf-8")
RETRY_MARK = "LẦN TRƯỚC BỊ LOẠI VÌ"
FULL_ORDER = [
    "EXTRACT 0", "EXTRACT 1", "CLUSTER", "ALIASES", "DEDUPE", "OUTLINE",
    "WRITE_VI p1", "WRITE_EN p1", "PROMPTS p1", "WRITE_VI p2", "WRITE_EN p2", "PROMPTS p2",
]
REAL_NAMES = [n for g in load_fixture("CLUSTER")["groups"] for n in g["real_names"]] + ["Lê Lợi"]


# ---------------------------------------------------------------- helpers

def _new_pipeline(target_minutes: int = 8) -> CasePipeline:
    """Vụ án mẫu trên đĩa tạm: bài gốc, 2 đoạn (chunk_chars=900) và hàng việc ban đầu."""
    now = datetime.now(timezone.utc).isoformat()
    case_id = case_store.new_case_id()
    chunks = chunk_source(DOSSIER, 900)
    pipeline = CasePipeline(
        case_id=case_id, target_minutes=target_minutes, visual_style="cinematic noir", chunk_chars=900,
        created_at=now, updated_at=now, steps=initial_steps(len(chunks)),
    )
    case_store.save_source(case_id, DOSSIER)
    case_store.save_chunks(case_id, chunks)
    case_store.save_pipeline(pipeline)
    return pipeline


def _run_pipeline(pipeline: CasePipeline, llm, *, stop_after: str = ""):
    """Chạy hàng việc như worker (bỏ qua việc đã xong); trả kết quả của việc cuối cùng đã chạy."""
    result, i = None, 0
    while i < len(pipeline.steps):
        step = pipeline.steps[i]
        if step.status == "done":
            i += 1
            continue
        result = asyncio.run(run_step(pipeline, step, llm=llm))
        case_store.save_step_output(pipeline.case_id, step.id, result.output)
        step.status = "done"
        pipeline.steps[i + 1:i + 1] = result.new_steps
        case_store.save_pipeline(pipeline)
        if step.id == stop_after:
            break
        i += 1
    return result


def _reason(llm, index: int = -1) -> str:
    """Lý do bị loại nối vào prompt thứ `index`."""
    prompt = llm.prompts[index]
    assert RETRY_MARK in prompt, prompt[-300:]
    return prompt.split(RETRY_MARK, 1)[1]


def _prompt_for(llm, marker: str, nth: int = 0) -> str:
    hits = [p for p in llm.prompts if p.split("\n", 1)[0] == f"TASK: {marker}"]
    return hits[nth]


def _has_word(text: str, phrase: str) -> bool:
    """`phrase` xuất hiện trong `text` theo ranh giới từ ("ong trong" không khớp trong "động trong")."""
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None


def _bible(pipeline: CasePipeline) -> CaseBible:
    return CaseBible.model_validate(case_store.load_step_output(pipeline.case_id, "aliases"))


# ---------------------------------------------------------------- cả hàng việc

def test_full_pipeline_produces_plan(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm()

    result = _run_pipeline(pipeline, llm)

    assert calls == FULL_ORDER
    assert result.output == {"case_id": pipeline.case_id}
    assert [s.id for s in pipeline.steps] == [
        "extract_00", "extract_01", "cluster", "aliases", "dedupe", "outline", "write_vi_p1", "write_en_p1", "write_prompts_p1",
        "write_vi_p2", "write_en_p2", "write_prompts_p2", "assemble",
    ]
    plan = case_store.load_plan(pipeline.case_id)
    assert plan is not None
    assert len(plan.scenes) == 7
    first = plan.scenes[0]
    assert first.visual_kind == "disclaimer"
    assert first.narration_vi == DISCLAIMER["vi"] and first.narration_en == DISCLAIMER["en"]
    assert [s.order for s in plan.scenes] == list(range(1, 8))
    assert [s.part_id for s in plan.scenes[1:]] == ["p1"] * 3 + ["p2"] * 3
    assert [p.id for p in plan.parts] == ["p1", "p2"]
    assert not has_blocking_flags(plan) and plan.flags == []
    assert all(s.flags == [] for s in plan.scenes)
    assert plan.check_warnings == []                       # mọi bằng chứng đều hiện ra, không còn ngày tháng
    assert plan.target_minutes == 8 and plan.visual_style == "cinematic noir"

    # mỗi cảnh ghép đúng lời Việt, lời Anh và prompt của cùng vị trí
    vi, en, pr = load_fixture("WRITE_VI p2"), load_fixture("WRITE_EN p2"), load_fixture("PROMPTS p2")
    board = plan.scenes[5]
    assert board.narration_vi == vi["scenes"][1]["narration_vi"]
    assert board.narration_en == en["scenes"][1]["narration_en"]
    assert board.image_prompt == pr["scenes"][1]["image_prompt"]
    assert board.visual_kind == "board" and board.board_reveal == vi["scenes"][1]["board_reveal"]
    assert board.covers_event_ids == ["ev_1_3", "ev_1_4"]
    video = plan.scenes[6]
    assert video.visual_kind == "video" and video.video_prompt == pr["scenes"][2]["video_prompt"]
    assert plan.scenes[1].camera_motion == "neo_noir_rain_motion" and plan.scenes[1].sfx_cue == ["heavy_rain_loop"]

    # không lọt tên thật vào lời kể, prompt, dàn ý
    texts = [t for s in plan.scenes for t in (s.narration_vi, s.narration_en, s.image_prompt, s.video_prompt)]
    texts += [p.summary_vi for p in plan.parts]
    for real in REAL_NAMES:
        assert not any(_has_word(fold(t), fold(real)) for t in texts), real


def test_each_step_kind_gets_its_own_timeout(isolated_projects_dir):
    fake, _calls = make_fake_llm()
    seen: dict[str, set] = {}

    async def llm(system, user, *, temperature=0.4, timeout=None, client=None):
        seen.setdefault(marker_of(user).split(" ")[0], set()).add(timeout)
        return await fake(system, user, temperature=temperature)

    pipeline = _new_pipeline()
    _run_pipeline(pipeline, llm)
    asyncio.run(rewrite_english(_bible(pipeline), [(3, "Run rẩy, bà Đặng Thu Hà gọi đến trực ban hình sự.")], llm=llm))

    assert seen == {"EXTRACT": {240.0}, "CLUSTER": {240.0}, "ALIASES": {240.0}, "DEDUPE": {600.0}, "OUTLINE": {600.0},
                    "WRITE_VI": {360.0}, "WRITE_EN": {360.0}, "PROMPTS": {360.0}, "REWRITE_EN": {360.0}}
    assert STEP_TIMEOUTS["build_outline"] == 600.0 and STEP_TIMEOUTS["write_prompts"] == 360.0


def test_short_material_warns(isolated_projects_dir):
    pipeline = _new_pipeline(target_minutes=8)
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm)
    plan = case_store.load_plan(pipeline.case_id)
    notice = [w for w in plan.warnings if "khoảng 2 phút" in w]
    assert notice == ["Bài chỉ đủ tư liệu cho khoảng 2 phút (bạn chọn 8 phút)."]
    assert not has_blocking_flags(plan)


def test_outline_new_steps_follow_parts(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm()
    result = _run_pipeline(pipeline, llm, stop_after="outline")
    assert calls == FULL_ORDER[:6]
    assert [(s.id, s.kind, s.params) for s in result.new_steps] == [
        ("write_vi_p1", "write_vi", {"part_id": "p1"}),
        ("write_en_p1", "write_en", {"part_id": "p1"}),
        ("write_prompts_p1", "write_prompts", {"part_id": "p1"}),
        ("write_vi_p2", "write_vi", {"part_id": "p2"}),
        ("write_en_p2", "write_en", {"part_id": "p2"}),
        ("write_prompts_p2", "write_prompts", {"part_id": "p2"}),
        ("assemble", "assemble", {}),
    ]
    assert result.output["supported_minutes"] == 2
    assert [p["scene_count"] for p in result.output["parts"]] == [3, 3]


# ---------------------------------------------------------------- G5: dàn ý

def test_outline_lazy_retried(isolated_projects_dir):
    pipeline = _new_pipeline()
    lazy = copy.deepcopy(load_fixture("OUTLINE"))
    lazy["parts"][1]["event_ids"].remove("ev_1_6")
    llm, calls = make_fake_llm({"OUTLINE": [lazy, load_fixture("OUTLINE")]})

    _run_pipeline(pipeline, llm, stop_after="outline")

    assert calls.count("OUTLINE") == 2
    assert "ev_1_6" in _reason(llm)
    assert RETRY_MARK not in _prompt_for(llm, "OUTLINE", 0)


def _outline_with(**changes) -> dict:
    out = copy.deepcopy(load_fixture("OUTLINE"))
    for key, value in changes.items():
        if key == "parts":
            out["parts"] = value
        else:
            out[key] = value
    return out


ALL_EVENTS = [f"ev_{c}_{n}" for c in (0, 1) for n in range(1, 7)]


@pytest.mark.parametrize("bad, hint", [
    (_outline_with(parts=[{"id": "p1", "kind": "hook", "summary_vi": "x", "event_ids": ALL_EVENTS[:6], "scene_count": 7},
                          {"id": "p2", "kind": "investigation", "summary_vi": "y", "event_ids": ALL_EVENTS[6:], "scene_count": 3}]),
     "từ 2 đến 6"),
    (_outline_with(parts=[{"id": "p1", "kind": "hook", "summary_vi": "x", "event_ids": ALL_EVENTS[:6], "scene_count": 1},
                          {"id": "p2", "kind": "investigation", "summary_vi": "y", "event_ids": ALL_EVENTS[6:], "scene_count": 3}]),
     "từ 2 đến 6"),
    (_outline_with(parts=[{"id": f"p{i}", "kind": "investigation", "summary_vi": "x", "event_ids": ALL_EVENTS, "scene_count": 6}
                          for i in range(1, 10)]),                       # 54 cảnh > 40 * 1,2
     "48"),
    (_outline_with(supported_minutes=8), "35"),                          # đủ tư liệu 8 phút mà chỉ có 6 cảnh: lười
    (_outline_with(parts=[{"id": "p1", "kind": "hook", "summary_vi": "x", "event_ids": [*ALL_EVENTS, "ev_9_9"], "scene_count": 6}]),
     "ev_9_9"),
    (_outline_with(parts=[{"id": "p1", "kind": "hook", "summary_vi": "x", "event_ids": ALL_EVENTS, "scene_count": 2}]),
     "3 sự việc"),                                                       # 12 sự việc dồn vào 2 cảnh
    (_outline_with(parts=[{"id": "p1", "kind": "spaceship", "summary_vi": "x", "event_ids": ALL_EVENTS, "scene_count": 6}]),
     "kind"),
])
def test_outline_rejections(isolated_projects_dir, bad, hint):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm({"OUTLINE": [bad, load_fixture("OUTLINE")]})
    _run_pipeline(pipeline, llm, stop_after="outline")
    assert calls.count("OUTLINE") == 2
    assert hint in _reason(llm)


def _parts(*specs) -> list[dict]:
    """specs: (kind, event_ids, scene_count) cho từng nhịp."""
    return [{"id": f"p{n}", "kind": kind, "summary_vi": "x", "event_ids": list(ids), "scene_count": count}
            for n, (kind, ids, count) in enumerate(specs, start=1)]


def _outline_reason(outline: dict, *, pipeline: CasePipeline = None) -> str:
    """Chạy việc dàn ý với `outline` ở lần đầu, fixture ở lần sau; trả lý do bị loại."""
    pipeline = pipeline or _new_pipeline()
    llm, calls = make_fake_llm({"OUTLINE": [outline, load_fixture("OUTLINE")]})
    _run_pipeline(pipeline, llm, stop_after="outline")
    assert calls.count("OUTLINE") == 2
    return _reason(llm)


def test_outline_rejects_events_repeated_across_parts(isolated_projects_dir):
    # (A) 7 nhịp × 6 cảnh, nhịp nào cũng kể lại cả 12 sự việc: đủ 43 cảnh nhưng là độn.
    padded = _outline_with(supported_minutes=8, parts=_parts(*[("investigation", ALL_EVENTS, 6)] * 7))
    reason = _outline_reason(padded)
    assert "nhiều nhịp" in reason and "ev_0_1" in reason


def test_outline_rejects_one_event_stretched_over_many_scenes(isolated_projects_dir):
    # (B) mỗi nhịp 1 sự việc kéo dài 3 cảnh: 36 cảnh + cảnh miễn trừ vừa mục tiêu, nhưng là kéo dài cho đủ.
    stretched = _outline_with(supported_minutes=8, parts=_parts(*[("investigation", [e], 3) for e in ALL_EVENTS]))
    reason = _outline_reason(stretched)
    assert "tối đa 2 cảnh" in reason and "nhiều nhịp" not in reason


def test_outline_hook_may_borrow_one_later_event_only(isolated_projects_dir):
    one = _outline_with(parts=_parts(("hook", ["ev_1_6", *ALL_EVENTS[:6]], 3), ("investigation", ALL_EVENTS[6:], 3)))
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm({"OUTLINE": one})
    result = _run_pipeline(pipeline, llm, stop_after="outline")
    assert calls.count("OUTLINE") == 1
    assert result.output["parts"][0]["event_ids"][0] == "ev_1_6"

    two = _outline_with(parts=_parts(("hook", ["ev_1_5", "ev_1_6", *ALL_EVENTS[:6]], 3),
                                     ("investigation", ALL_EVENTS[6:], 3)))
    reason = _outline_reason(two)
    assert "mượn" in reason and "ev_1_5" in reason


def test_outline_total_capped_by_supported_minutes(isolated_projects_dir):
    # Bài chỉ đủ 2 phút (khoảng 8 cảnh, tối đa floor(2 × 4 × 1,2) = 9) mà dàn ý có 12 cảnh.
    padded = _outline_with(supported_minutes=2, parts=_parts(("hook", ALL_EVENTS[:6], 6),
                                                             ("investigation", ALL_EVENTS[6:], 6)))
    reason = _outline_reason(padded)
    assert "tối đa 9 cảnh" in reason and "2 phút" in reason


def test_outline_too_few_events_for_target_asks_to_lower_supported_minutes(isolated_projects_dir):
    # 12 sự việc: tối đa 2 × 12 = 24 cảnh (25 kể cả cảnh miễn trừ) < 35, nên không thể "thêm cảnh" cho đủ 8 phút.
    claims_full = _outline_with(supported_minutes=8)
    lowered = _outline_with(supported_minutes=6)
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm({"OUTLINE": [claims_full, lowered]})

    result = _run_pipeline(pipeline, llm, stop_after="outline")

    assert calls.count("OUTLINE") == 2
    reason = _reason(llm)
    assert "12 sự việc" in reason and "tối đa 24 cảnh" in reason and "35" in reason
    assert "hạ supported_minutes" in reason and "6 phút" in reason
    assert "thêm cảnh" not in reason.replace("thay vì thêm cảnh", "")
    assert result.output["supported_minutes"] == 6


def _pipeline_with_events(n_events: int) -> CasePipeline:
    """Hàng việc đã qua bước đặt tên hư cấu, dòng thời gian thay bằng `n_events` sự việc (đều ở đoạn 0)."""
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="aliases")
    bible = case_store.load_step_output(pipeline.case_id, "aliases")
    bible["timeline"] = [{"id": f"ev_0_{i}", "order": i, "chunk_index": 0, "time_label": "", "entity_ids": [],
                          "summary": f"Sự việc thứ {i} trong cuộc điều tra kéo dài nhiều tuần ở thành phố cảng."}
                         for i in range(1, n_events + 1)]
    case_store.save_step_output(pipeline.case_id, "aliases", bible)
    return pipeline


def test_outline_cap_counts_the_disclaimer_scene(isolated_projects_dir):
    ids = [f"ev_0_{i}" for i in range(1, 31)]
    groups = [ids[i:i + 4] for i in range(0, 24, 4)] + [ids[24:27], ids[27:30]]   # 6 nhịp × 4 + 2 nhịp × 3 sự việc
    at_cap = _outline_with(supported_minutes=8, parts=_parts(*[("investigation", g, 6) for g in groups]))  # 48 cảnh
    under = copy.deepcopy(at_cap)
    under["parts"][-1]["scene_count"] = 5                                          # 47 cảnh + cảnh miễn trừ = 48
    pipeline = _pipeline_with_events(30)
    llm, calls = make_fake_llm({"OUTLINE": [at_cap, under]})

    result = _run_pipeline(pipeline, llm, stop_after="outline")

    assert calls == ["DEDUPE", "OUTLINE", "OUTLINE"]
    reason = _reason(llm)
    assert "48" in reason and "miễn trừ" in reason
    assert sum(p["scene_count"] for p in result.output["parts"]) == 47


def test_outline_too_few_scenes_with_enough_events_asks_for_more_scenes(isolated_projects_dir):
    ids = [f"ev_0_{i}" for i in range(1, 31)]
    thin = _outline_with(supported_minutes=8, parts=_parts(*[("investigation", ids[i:i + 3], 2) for i in range(0, 30, 3)]))
    groups = [ids[i:i + 4] for i in range(0, 24, 4)] + [ids[24:27], ids[27:30]]
    full = _outline_with(supported_minutes=8, parts=_parts(*[("investigation", g, 6) for g in groups[:-1]],
                                                           ("investigation", groups[-1], 5)))      # 47 cảnh
    pipeline = _pipeline_with_events(30)
    llm, calls = make_fake_llm({"OUTLINE": [thin, full]})
    _run_pipeline(pipeline, llm, stop_after="outline")
    assert calls == ["DEDUPE", "OUTLINE", "OUTLINE"]
    reason = _reason(llm)
    assert "chỉ có 20" in reason and "tăng scene_count" in reason and "tối đa 47 cảnh" in reason


def test_outline_prompt_does_not_anchor_supported_minutes_to_target(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="outline")
    prompt = _prompt_for(llm, "OUTLINE")
    assert '"supported_minutes": 8' not in prompt and '"supported_minutes": <' in prompt
    assert "đúng một nhịp" in prompt.lower() and "tối đa 2 cảnh" in prompt


def test_outline_ids_renumbered_and_unsolved_resolution_becomes_open_questions(isolated_projects_dir):
    pipeline = _new_pipeline()
    odd = copy.deepcopy(load_fixture("OUTLINE"))
    odd["parts"][0]["id"] = "Phần 1: mở đầu"                            # id lạ, không dùng được làm id việc
    odd["parts"][1]["id"] = "p1"
    llm, _calls = make_fake_llm({"OUTLINE": odd})
    result = _run_pipeline(pipeline, llm, stop_after="outline")
    assert [p["id"] for p in result.output["parts"]] == ["p1", "p2"]
    assert _bible(pipeline).solved is False
    assert [p["kind"] for p in result.output["parts"]] == ["hook", "open_questions"]   # vụ chưa phá: không "phá án"


def test_prompt_aliasing_leaves_generic_terms_that_fold_like_real_names():
    bible = CaseBible.model_validate({
        "source_language": "vi", "culture": "vietnamese", "solved": False, "title_vi": "Đêm mưa", "title_en": "Rain",
        "entities": [
            {"id": "person_1", "kind": "person", "real_names": ["Hưng Thu"], "alias_vi": "Lê Minh", "alias_en": "Le Minh"},
            {"id": "place_1", "kind": "place", "real_names": ["Gia Định"], "alias_vi": "Phú An", "alias_en": "Phu An"},
        ],
        "timeline": [{"id": "ev_0_1", "order": 1, "chunk_index": 0,
                      "summary": "Cảnh sát chưa tìm ra hung thủ; cả gia đình nạn nhân nghi Hưng Thu ở Bệnh viện Gia Định."}],
        "evidence": [{"id": "evd_1", "label_vi": "Lời khai của gia đình", "label_en": "Family statement"}],
    })
    prompt = outline_prompt(bible, 8, (35, 40))
    assert "Cảnh sát chưa tìm ra hung thủ; cả gia đình nạn nhân nghi Lê Minh ở Bệnh viện Phú An." in prompt
    assert '"Lời khai của gia đình"' in prompt
    assert "Hưng Thu" not in prompt and "Gia Định" not in prompt


def test_pipeline_does_not_treat_generic_term_as_colliding_real_name(isolated_projects_dir):
    # Người thật tên "Hưng Thu" (bỏ dấu trùng "hung thủ"): lời kể có "hung thủ" không bị gọi lại, không bị thay tên.
    pipeline = _new_pipeline()
    first = copy.deepcopy(load_fixture("EXTRACT 0"))
    first["names"].append({"name": "Hưng Thu", "kind": "person", "role": "witness", "context": "Bảo vệ cổng cảng."})
    first["events"][5]["names"].append("Hưng Thu")
    cluster = copy.deepcopy(load_fixture("CLUSTER"))
    cluster["groups"].append({"id": "person_4", "kind": "person", "role": "witness", "real_names": ["Hưng Thu"]})
    aliases = copy.deepcopy(load_fixture("ALIASES"))
    aliases["entities"].append({"id": "person_4", "alias_vi": "Lê Minh", "alias_en": "Le Minh", "gender": "male",
                                "age_range": "60s", "appearance_en": "A Vietnamese man in his sixties, thin, grey "
                                "crew cut, wearing a faded security guard uniform and rubber boots."})
    vi = copy.deepcopy(load_fixture("WRITE_VI p1"))
    vi["scenes"][2]["narration_vi"] = vi["scenes"][2]["narration_vi"].replace(
        "Bóng người ấy là ai?", "Bóng người ấy có phải là hung thủ?")
    llm, calls = make_fake_llm({"EXTRACT 0": first, "CLUSTER": cluster, "ALIASES": aliases, "WRITE_VI p1": vi})

    _run_pipeline(pipeline, llm)

    assert calls.count("WRITE_VI p1") == 1
    assert "Hưng Thu" in [n for e in _bible(pipeline).entities for n in e.real_names]
    plan = case_store.load_plan(pipeline.case_id)
    assert plan.scenes[3].narration_vi.endswith("có phải là hung thủ?") and plan.scenes[3].flags == []
    assert not any("Hưng Thu" in w for w in plan.warnings)


def test_outline_prompt_has_events_with_fictional_names_only(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="outline")
    prompt = _prompt_for(llm, "OUTLINE")
    for eid in ALL_EVENTS:
        assert eid in prompt
    assert "evd_1" in prompt and "35" in prompt and "40" in prompt and "48" in prompt
    assert "Trịnh Quang Vũ" in prompt and "Cảng Hải Yến" in prompt
    for real in REAL_NAMES:
        assert not _has_word(fold(prompt), fold(real)), real


# ---------------------------------------------------------------- G6: lời Việt

def test_write_vi_too_few_scenes_retried(isolated_projects_dir):
    pipeline = _new_pipeline()
    two = copy.deepcopy(load_fixture("WRITE_VI p1"))
    two["scenes"] = two["scenes"][:2]
    llm, calls = make_fake_llm({"WRITE_VI p1": [two, load_fixture("WRITE_VI p1")]})

    _run_pipeline(pipeline, llm, stop_after="write_vi_p1")

    assert calls[-2:] == ["WRITE_VI p1", "WRITE_VI p1"]
    assert RETRY_MARK not in _prompt_for(llm, "WRITE_VI p1", 0)
    second = _prompt_for(llm, "WRITE_VI p1", 1)
    assert RETRY_MARK in second and "3 cảnh" in second.split(RETRY_MARK, 1)[1]
    assert len(case_store.load_step_output(pipeline.case_id, "write_vi_p1")["scenes"]) == 3


def test_write_vi_missing_event_rejected(isolated_projects_dir):
    pipeline = _new_pipeline()
    lazy = copy.deepcopy(load_fixture("WRITE_VI p1"))
    lazy["scenes"][2]["covers_event_ids"] = ["ev_0_5"]                  # bỏ sót ev_0_6
    llm, calls = make_fake_llm({"WRITE_VI p1": lazy})

    with pytest.raises(StepFailed) as info:
        _run_pipeline(pipeline, llm)

    assert calls.count("WRITE_VI p1") == MAX_ATTEMPTS
    assert "lời Việt" in info.value.user_message
    assert "ev_0_6" in info.value.user_message
    assert "WRITE_EN p1" not in calls


def test_write_vi_each_scene_must_cover_one_to_three_events(isolated_projects_dir):
    # (C) cảnh 1 nhận kể cả 6 sự việc, cảnh 2–3 không kể gì; lời toàn chữ "mưa": phải bị loại.
    pipeline = _new_pipeline()
    filler = " ".join(["mưa"] * 30)
    lazy = {"scenes": [
        {"narration_vi": filler, "visual_kind": "image", "board_reveal": [], "covers_event_ids": ALL_EVENTS[:6]},
        {"narration_vi": filler, "visual_kind": "image", "board_reveal": [], "covers_event_ids": []},
        {"narration_vi": filler, "visual_kind": "image", "board_reveal": [], "covers_event_ids": []},
    ]}
    llm, calls = make_fake_llm({"WRITE_VI p1": [lazy, load_fixture("WRITE_VI p1")]})
    _run_pipeline(pipeline, llm, stop_after="write_vi_p1")
    assert calls.count("WRITE_VI p1") == 2
    reason = _reason(llm)
    assert "cảnh 1" in reason and "tối đa 3" in reason
    assert "cảnh 2" in reason and "cảnh 3" in reason and "ít nhất 1" in reason


def test_write_vi_board_scene_without_reveal_rejected(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("WRITE_VI p2"))
    bad["scenes"][1]["board_reveal"] = []                                # cảnh board không hiện gì lên bảng
    llm, calls = make_fake_llm({"WRITE_VI p2": [bad, load_fixture("WRITE_VI p2")]})
    _run_pipeline(pipeline, llm, stop_after="write_vi_p2")
    assert calls.count("WRITE_VI p2") == 2
    reason = _reason(llm)
    assert "cảnh 2" in reason and "board_reveal" in reason and "image" in reason


def test_write_vi_identifying_number_from_source_soft_rejected(isolated_projects_dir):
    # Bài gốc có "số 88 Đường Lê Lợi" và "container số 14": lời kể giữ "số 88" là lộ chi tiết nhận dạng.
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("WRITE_VI p1"))
    bad["scenes"][0]["narration_vi"] = bad["scenes"][0]["narration_vi"].replace(
        "trên Đường Thanh Lam", "ở số 88 Đường Thanh Lam")
    llm, calls = make_fake_llm({"WRITE_VI p1": [bad, load_fixture("WRITE_VI p1")]})
    _run_pipeline(pipeline, llm, stop_after="write_vi_p1")
    assert calls.count("WRITE_VI p1") == 2
    reason = _reason(llm)
    assert "cảnh 1" in reason and "'88'" in reason and "số nhà" in reason


def test_write_vi_times_and_ages_are_not_identifying_numbers(isolated_projects_dir):
    # "14" có trong bài cạnh chữ "số" (container số 14), nhưng "14 giờ", "14:30", "14 tuổi" là giờ và tuổi: giữ.
    pipeline = _new_pipeline()
    ok = copy.deepcopy(load_fixture("WRITE_VI p1"))
    ok["scenes"][0]["narration_vi"] = ("Khoảng 14 giờ chiều hôm trước, rồi lúc 14:30, một cậu bé 14 tuổi còn "
                                       + ok["scenes"][0]["narration_vi"])
    llm, calls = make_fake_llm({"WRITE_VI p1": ok})
    _run_pipeline(pipeline, llm, stop_after="write_vi_p1")
    assert calls.count("WRITE_VI p1") == 1


def test_write_en_identifying_number_soft_rejected(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("WRITE_EN p1"))
    bad["scenes"][0]["narration_en"] = bad["scenes"][0]["narration_en"].replace(
        "on Thanh Lam Street", "at 88 Thanh Lam Street")
    llm, calls = make_fake_llm({"WRITE_EN p1": [bad, load_fixture("WRITE_EN p1")]})
    _run_pipeline(pipeline, llm, stop_after="write_en_p1")
    assert calls.count("WRITE_EN p1") == 2
    assert "'88'" in _reason(llm)


def test_assemble_lists_soft_rejected_numbers_and_vietnamese_forms_in_check_warnings(isolated_projects_dir):
    # Lỗi nhẹ còn sau MAX_ATTEMPTS lần vẫn được nhận; bước ráp phải ghi lại để màn xem lại hiện ra (không chặn).
    pipeline = _new_pipeline()
    vi = copy.deepcopy(load_fixture("WRITE_VI p1"))
    vi["scenes"][0]["narration_vi"] = vi["scenes"][0]["narration_vi"].replace(
        "trên Đường Thanh Lam", "ở số 88 Đường Thanh Lam")
    en = copy.deepcopy(load_fixture("WRITE_EN p1"))
    en["scenes"][1]["narration_en"] = en["scenes"][1]["narration_en"].replace(
        "The person who found him", "At Cang Hai Yen, the person who found him")
    llm, calls = make_fake_llm({"WRITE_VI p1": vi, "WRITE_EN p1": en})
    _run_pipeline(pipeline, llm)
    assert calls.count("WRITE_VI p1") == MAX_ATTEMPTS and calls.count("WRITE_EN p1") == MAX_ATTEMPTS
    plan = case_store.load_plan(pipeline.case_id)
    assert "số 88" in plan.scenes[1].narration_vi and "Cang Hai Yen" in plan.scenes[2].narration_en
    assert any("cảnh 2" in w and "narration_vi" in w and "'88'" in w for w in plan.check_warnings), plan.check_warnings
    assert any("cảnh 3" in w and "narration_en" in w and "'Cảng Hải Yến'" in w and "'Hai Yen Port'" in w
               for w in plan.check_warnings), plan.check_warnings
    assert not has_blocking_flags(plan)


def test_text_guard_catches_real_names_that_differ_only_in_diacritics():
    bible = CaseBible(source_language="vi", culture="vietnamese", title_vi="Đêm Mưa", title_en="Rain", timeline=[],
                      entities=[CaseEntity(id="person_1", kind="person", real_names=["Nguyễn Văn Hùng"],
                                           alias_vi="Trịnh Quang Vũ", alias_en="Trinh Quang Vu"),
                                CaseEntity(id="person_2", kind="person", real_names=["Nguyễn Văn Hưng"],
                                           alias_vi="Lê Minh Tâm", alias_en="Le Minh Tam")])
    guard = _TextGuard(bible)
    assert guard.narration("Nguyễn Văn Hưng bước vào kho.", "vi") == [
        "có tên thật 'Nguyễn Văn Hưng' (thay bằng 'Lê Minh Tâm')"]
    issues = guard.narration("Nguyen Van Hung walked into the yard.", "en")
    assert len(issues) == 1 and "'Trinh Quang Vu'" in issues[0] and "'Le Minh Tam'" in issues[0]
    assert guard.narration("Hung thủ vẫn lẩn trốn, cuộc sống hòa bình đã mất.", "vi") == []


def test_hook_borrowed_event_is_marked_tease_only(isolated_projects_dir):
    pipeline = _new_pipeline()
    outline = _outline_with(parts=_parts(("hook", [*ALL_EVENTS[:6], "ev_1_6"], 3), ("investigation", ALL_EVENTS[6:], 3)))
    vi1 = copy.deepcopy(load_fixture("WRITE_VI p1"))
    vi1["scenes"][0]["covers_event_ids"].append("ev_1_6")
    llm, _calls = make_fake_llm({"OUTLINE": outline, "WRITE_VI p1": vi1})
    _run_pipeline(pipeline, llm, stop_after="write_vi_p2")
    hook, owner = _prompt_for(llm, "WRITE_VI p1"), _prompt_for(llm, "WRITE_VI p2")
    teaser = next(line for line in hook.splitlines() if line.strip().startswith("- ev_1_6"))
    assert "CHỈ GỢI" in teaser
    assert not any("CHỈ GỢI" in line for line in hook.splitlines() if line.strip().startswith("- ev_0_"))
    told = next(line for line in owner.splitlines() if line.strip().startswith("- ev_1_6"))
    assert "hé lộ" in told and "kể đầy đủ" in told
    prompt = _prompt_for(llm, "OUTLINE")
    assert "gợi tò mò" in prompt and "không kể lại trọn" in prompt


def test_write_prompts_forbid_sensational_wording(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="write_en_p1")
    for marker in ("WRITE_VI p1", "WRITE_EN p1"):
        prompt = _prompt_for(llm, marker)
        assert "báo lá cải" in prompt and "số nhà" in prompt, marker
    assert "ghê rợn" in _prompt_for(llm, "WRITE_VI p1") and "gruesome" in _prompt_for(llm, "WRITE_EN p1")


def test_write_vi_short_narration_and_unknown_reveal_rejected(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("WRITE_VI p2"))
    bad["scenes"][0]["narration_vi"] = "Ông Lâm bị nghi ngờ."           # 5 từ
    bad["scenes"][1]["board_reveal"] = ["evd_1", "evd_99"]
    llm, calls = make_fake_llm({"WRITE_VI p2": [bad, load_fixture("WRITE_VI p2")]})
    _run_pipeline(pipeline, llm, stop_after="write_vi_p2")
    assert calls.count("WRITE_VI p2") == 2
    reason = _reason(llm)
    assert "evd_99" in reason and "cần từ 22 đến 51 từ" in reason and "cảnh 1" in reason   # video 8 phút


def test_write_vi_accepts_ids_as_string_and_bare_scene_list(isolated_projects_dir):
    pipeline = _new_pipeline()
    loose = copy.deepcopy(load_fixture("WRITE_VI p1"))["scenes"]           # mảng trần, không bọc {"scenes": ...}
    loose[0]["covers_event_ids"] = "ev_0_1, ev_0_2"
    loose[1]["visual_kind"] = "Photo"
    llm, calls = make_fake_llm({"WRITE_VI p1": [loose]})                # list override = chuỗi câu trả lời
    _run_pipeline(pipeline, llm, stop_after="write_vi_p1")
    assert calls.count("WRITE_VI p1") == 1
    scenes = case_store.load_step_output(pipeline.case_id, "write_vi_p1")["scenes"]
    assert scenes[0]["covers_event_ids"] == ["ev_0_1", "ev_0_2"] and scenes[1]["visual_kind"] == "image"


def test_write_vi_prompt_has_part_events_chunks_names_and_previous_scenes(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="write_vi_p2")
    chunks = case_store.load_chunks(pipeline.case_id)
    p1, p2 = _prompt_for(llm, "WRITE_VI p1"), _prompt_for(llm, "WRITE_VI p2")

    assert chunks[0].strip() in p1 and chunks[1].strip() not in p1      # chỉ đoạn gốc chứa sự việc của nhịp
    assert chunks[1].strip() in p2 and chunks[0].strip() not in p2
    assert "đúng 3 cảnh" in p1
    for eid in ALL_EVENTS[:6]:
        assert eid in p1
    assert "Nguyễn Văn Hùng" in p1 and "Trịnh Quang Vũ" in p1          # bảng tên thật → tên hư cấu
    assert "evd_8" in p1 and "rel_1" in p1
    vi1 = load_fixture("WRITE_VI p1")["scenes"]
    assert vi1[1]["narration_vi"] in p2 and vi1[2]["narration_vi"] in p2   # 2 cảnh cuối của nhịp trước
    assert vi1[0]["narration_vi"] not in p2
    assert "CHƯA" in p2                                                  # vụ chưa phá: dặn không bịa hung thủ


def _block(prompt: str, title: str) -> str:
    """Khối của prompt bắt đầu bằng dòng `title`, tới dòng trống đầu tiên."""
    return prompt.split(title, 1)[1].split("\n\n", 1)[0]


def test_write_vi_prompt_sees_logline_whole_outline_and_characters_already_introduced(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="write_vi_p2")
    bible = _bible(pipeline)
    outline = case_store.load_step_output(pipeline.case_id, "outline")["parts"]
    p1, p2 = _prompt_for(llm, "WRITE_VI p1"), _prompt_for(llm, "WRITE_VI p2")

    for prompt, current in ((p1, 1), (p2, 2)):
        story = _block(prompt, "TOÀN BỘ CÂU CHUYỆN")
        assert bible.logline_vi in story
        for n, part in enumerate(outline, start=1):
            line = next(l for l in story.splitlines() if part["summary_vi"] in l)
            assert f"{n}." in line
            assert ("ĐANG VIẾT" in line) == (n == current)               # đánh dấu đúng nhịp đang viết
        assert REAL_NAMES[0] not in story
    assert "cài cắm" in p1.lower() and "không giới thiệu lại" in p1.lower()

    people = {e.id: e.alias_vi for e in bible.entities if e.kind == "person"}
    by_id = {ev.id: ev for ev in bible.timeline}
    met = [people[i] for e in outline[0]["event_ids"] for i in by_id[e].entity_ids if i in people]
    assert met                                                           # tiền đề: nhịp 1 có nhân vật
    introduced = _block(p2, "NHÂN VẬT ĐÃ XUẤT HIỆN Ở CÁC NHỊP TRƯỚC")
    for alias in met:
        assert alias in introduced
    later = [people[i] for e in outline[1]["event_ids"] for i in by_id[e].entity_ids
             if i in people and people[i] not in met]
    for alias in later:
        assert alias not in introduced                                   # chỉ người đã xuất hiện ở nhịp trước
    assert "nhịp đầu tiên" in _block(p1, "NHÂN VẬT ĐÃ XUẤT HIỆN Ở CÁC NHỊP TRƯỚC")


def test_write_vi_date_and_real_name_retried_then_accepted_on_last_attempt(isolated_projects_dir):
    pipeline = _new_pipeline()
    dated = copy.deepcopy(load_fixture("WRITE_VI p1"))
    dated["scenes"][0]["narration_vi"] = dated["scenes"][0]["narration_vi"].replace("Gần nửa đêm", "Đêm năm 2021")
    dated["scenes"][2]["narration_vi"] = dated["scenes"][2]["narration_vi"].replace("bà Hà", "bà Mai")
    llm, calls = make_fake_llm({"WRITE_VI p1": dated})

    _run_pipeline(pipeline, llm)                                         # vẫn chạy hết: lần cuối được nhận

    assert calls.count("WRITE_VI p1") == MAX_ATTEMPTS
    reason = _prompt_for(llm, "WRITE_VI p1", 1).split(RETRY_MARK, 1)[1]
    assert "2021" in reason and "bà Mai" in reason and "Đặng Thu Hà" in reason
    plan = case_store.load_plan(pipeline.case_id)
    assert [f.kind for f in plan.scenes[1].flags] == ["date"]           # check_plan đánh dấu ngày tháng còn sót
    assert "bà Mai" not in plan.scenes[3].narration_vi                   # tên thật đã có alias thì tự thay
    assert any("bà Mai" in w for w in plan.warnings)


# ---------------------------------------------------------------- G6: lời Anh, prompt hình

def test_write_en_wrong_count_and_short_narration_retried(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("WRITE_EN p1"))
    bad["scenes"] = bad["scenes"][:2]
    bad["scenes"][1]["narration_en"] = "She found him."
    llm, calls = make_fake_llm({"WRITE_EN p1": [bad, load_fixture("WRITE_EN p1")]})
    _run_pipeline(pipeline, llm, stop_after="write_en_p1")
    assert calls.count("WRITE_EN p1") == 2
    reason = _reason(llm)
    assert "3 cảnh" in reason and "cần từ 13 đến 30 từ" in reason                           # video 8 phút


def test_write_en_prompt_maps_vietnamese_aliases_to_english(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="write_en_p1")
    prompt = _prompt_for(llm, "WRITE_EN p1")
    vi = load_fixture("WRITE_VI p1")["scenes"]
    assert all(s["narration_vi"] in prompt for s in vi)
    assert "Trịnh Quang Vũ" in prompt and "Trinh Quang Vu" in prompt
    assert "Cảng Hải Yến" in prompt and "Hai Yen Port" in prompt
    assert "đúng 3 cảnh" in prompt


def test_write_en_vietnamese_form_of_name_retried(isolated_projects_dir):
    # Vụ người Hoa: bản Anh phải dùng pinyin, không dùng tên Hán-Việt.
    pipeline = _new_pipeline()
    aliases = copy.deepcopy(load_fixture("ALIASES"))
    aliases["entities"][0]["alias_vi"], aliases["entities"][0]["alias_en"] = "Lưu Vinh Phú", "Liu Rongfu"
    bad = copy.deepcopy(load_fixture("WRITE_EN p1"))
    bad["scenes"][0]["narration_en"] = bad["scenes"][0]["narration_en"].replace("Trinh Quang Vu", "Luu Vinh Phu")
    llm, calls = make_fake_llm({"ALIASES": aliases, "WRITE_EN p1": [bad, load_fixture("WRITE_EN p1")]})
    _run_pipeline(pipeline, llm, stop_after="write_en_p1")
    assert calls.count("WRITE_EN p1") == 2
    reason = _reason(llm)
    assert "Luu Vinh Phu" in reason or "Lưu Vinh Phú" in reason
    assert "Liu Rongfu" in reason


def test_write_prompts_missing_video_prompt_and_short_image_prompt_retried(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("PROMPTS p2"))
    bad["scenes"][2]["video_prompt"] = ""
    bad["scenes"][0]["image_prompt"] = "A man at a port."
    llm, calls = make_fake_llm({"PROMPTS p2": [bad, load_fixture("PROMPTS p2")]})
    _run_pipeline(pipeline, llm, stop_after="write_prompts_p2")
    assert calls.count("PROMPTS p2") == 2
    reason = _reason(llm)
    assert "video_prompt" in reason and "cảnh 3" in reason and "image_prompt" in reason and "cảnh 1" in reason


def test_write_prompts_names_in_prompt_retried(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("PROMPTS p1"))
    bad["scenes"][1]["image_prompt"] = "Dang Thu Ha, " + bad["scenes"][1]["image_prompt"]
    llm, calls = make_fake_llm({"PROMPTS p1": [bad, load_fixture("PROMPTS p1")]})
    _run_pipeline(pipeline, llm, stop_after="write_prompts_p1")
    assert calls.count("PROMPTS p1") == 2
    assert "Dang Thu Ha" in _reason(llm)


def test_write_prompts_prompt_has_appearance_setting_and_style(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="write_prompts_p2")
    prompt = _prompt_for(llm, "PROMPTS p2")
    aliases = load_fixture("ALIASES")
    assert aliases["entities"][2]["appearance_en"] in prompt
    assert aliases["setting_notes_en"] in prompt
    assert "cinematic noir" in prompt
    assert load_fixture("WRITE_EN p2")["scenes"][2]["narration_en"] in prompt
    for motion in CAMERA_MOTIONS:
        assert motion in prompt


# ---------------------------------------------------------------- G7: ráp kế hoạch

def test_invalid_camera_normalized_and_video_capped(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm)
    plan = case_store.load_plan(pipeline.case_id)
    assert load_fixture("PROMPTS p2")["scenes"][0]["camera_motion"] == "warp_speed"
    assert plan.scenes[4].camera_motion == "zoom_in"
    assert all(s.camera_motion in CAMERA_MOTIONS for s in plan.scenes)

    # mọi cảnh p2 là video: chỉ giữ floor(15% × 7) = 1 cảnh video, phần dư thành image nhưng giữ video_prompt
    pipeline = _new_pipeline()
    all_video = copy.deepcopy(load_fixture("WRITE_VI p2"))
    for scene in all_video["scenes"]:
        scene["visual_kind"] = "video"
        scene["board_reveal"] = []
    all_video["scenes"][0]["board_reveal"] = ["evd_1", "evd_2", "evd_3", "evd_4", "evd_5", "evd_6", "evd_7", "evd_8"]
    prompts = copy.deepcopy(load_fixture("PROMPTS p2"))
    for n, scene in enumerate(prompts["scenes"], start=1):
        scene["video_prompt"] = f"Slow push-in on scene {n} as rain drifts across the frame and the light flickers softly."
    llm, _calls = make_fake_llm({"WRITE_VI p2": all_video, "PROMPTS p2": prompts})
    _run_pipeline(pipeline, llm)
    plan = case_store.load_plan(pipeline.case_id)
    videos = [s for s in plan.scenes if s.visual_kind == "video"]
    assert len(videos) <= 1
    p2 = [s for s in plan.scenes if s.part_id == "p2"]
    assert all(s.video_prompt for s in p2)
    assert sorted(s.visual_kind for s in p2) == ["image", "image", "video"]


def test_assemble_without_previous_output_fails_clearly(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="write_prompts_p1")
    assemble = next(s for s in pipeline.steps if s.id == "assemble")
    with pytest.raises(StepFailed) as info:
        asyncio.run(run_step(pipeline, assemble, llm=llm))
    assert "ráp kế hoạch" in info.value.user_message


# ---------------------------------------------------------------- viết lại lời Anh cho cảnh đã sửa

def test_rewrite_english_returns_map(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="aliases")
    bible = _bible(pipeline)
    text = load_fixture("REWRITE_EN")["scenes"][0]["narration_en"]
    llm, calls = make_fake_llm({"REWRITE_EN": {"scenes": [{"order": 3, "narration_en": text}]}})

    result = asyncio.run(rewrite_english(bible, [(3, "Run rẩy, bà Đặng Thu Hà gọi đến trực ban hình sự.")], llm=llm))

    assert result == {3: text}
    assert calls == ["REWRITE_EN"]
    prompt = llm.prompts[0]
    assert "Đặng Thu Hà" in prompt and "Dang Thu Ha" in prompt and "order 3" in prompt


def test_rewrite_english_missing_order_or_short_text_retried(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="aliases")
    bible = _bible(pipeline)
    items = [(3, "Run rẩy, bà Đặng Thu Hà gọi đến trực ban hình sự."), (5, "Ông Phan Đức Lâm bị nghi ngờ đầu tiên.")]
    good = {"scenes": [{"order": 3, "narration_en": load_fixture("REWRITE_EN")["scenes"][0]["narration_en"]},
                       {"order": 5, "narration_en": load_fixture("WRITE_EN p2")["scenes"][0]["narration_en"]}]}
    short = copy.deepcopy(good)
    short["scenes"][1]["narration_en"] = "Lam was suspected."
    llm, calls = make_fake_llm({"REWRITE_EN": [{"scenes": good["scenes"][:1]}, short, good]})

    result = asyncio.run(rewrite_english(bible, items, llm=llm))

    assert calls == ["REWRITE_EN"] * 3
    assert "5" in _reason(llm, 1) and "cần từ 15 đến 35 từ" in _reason(llm, 2)   # không biết thời lượng: 15 giây
    assert sorted(result) == [3, 5]
    assert asyncio.run(rewrite_english(bible, [], llm=llm)) == {}


def test_rewrite_english_failure_names_step(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="aliases")
    llm, _calls = make_fake_llm({"REWRITE_EN": LLMError("auth", "9router từ chối API key (401).")})
    with pytest.raises(StepFailed) as info:
        asyncio.run(rewrite_english(_bible(pipeline), [(3, "Một câu.")], llm=llm))
    assert "lời Anh" in info.value.user_message and "401" in info.value.user_message


# ---------------------------------------------------------------- ask_validated: lỗi nhẹ

def test_ask_validated_soft_rejection_retried_and_used_if_no_clean_result():
    seen = []

    async def llm(system, user, *, temperature=0.4, timeout=240.0, client=None):
        seen.append(user)
        return {"n": len(seen)}

    def validate(raw):
        if raw["n"] == 1:
            raise SoftRejected("còn năm cụ thể", {"value": "lần 1"})
        raise StepRejected("thiếu cảnh")

    assert asyncio.run(ask_validated("TASK: X", validate, llm=llm, step_label="thử")) == {"value": "lần 1"}
    assert len(seen) == MAX_ATTEMPTS
    assert "còn năm cụ thể" in seen[1] and "thiếu cảnh" in seen[2]

    seen.clear()

    def validate_clean_second(raw):
        if raw["n"] == 1:
            raise SoftRejected("còn tên thật", {"value": "lần 1"})
        return {"value": f"lần {raw['n']}"}

    assert asyncio.run(ask_validated("TASK: X", validate_clean_second, llm=llm, step_label="thử")) == {"value": "lần 2"}
    assert len(seen) == 2


# ---------------------------------------------------------------- kể cuốn: lọc trùng, bỏ chi tiết vụn, câu hỏi treo, không bịa lời

def _retry_reasons(llm, marker: str) -> list[str]:
    """Lý do bị loại nối vào các lần gọi lại của việc `marker`, theo thứ tự."""
    return [p.split(RETRY_MARK, 1)[1] for p in llm.prompts
            if p.split("\n", 1)[0] == f"TASK: {marker}" and RETRY_MARK in p]


def _outline_without(*event_ids: str) -> dict:
    """Dàn ý mẫu bỏ các sự việc `event_ids` khỏi mọi nhịp (chưa ghi vào "dropped")."""
    outline = copy.deepcopy(load_fixture("OUTLINE"))
    for part in outline["parts"]:
        part["event_ids"] = [e for e in part["event_ids"] if e not in event_ids]
    return outline


def test_dedupe_merges_a_repeated_event_into_the_fuller_one(isolated_projects_dir):
    pipeline = _new_pipeline()
    groups = {"duplicates": [{"keep": "ev_1_1", "drop": ["ev_0_6"], "reason": "Cùng một việc, đoạn sau kể kỹ hơn."}]}
    llm, calls = make_fake_llm({"DEDUPE": groups, "OUTLINE": _outline_without("ev_0_6")})

    _run_pipeline(pipeline, llm)

    assert calls.count("DEDUPE") == 1 and calls.count("OUTLINE") == 1
    out = case_store.load_step_output(pipeline.case_id, "dedupe")
    assert out["merged"] == {"ev_0_6": "ev_1_1"}
    timeline = out["bible"]["timeline"]
    assert [ev["id"] for ev in timeline if ev["id"] == "ev_0_6"] == [] and len(timeline) == 11
    assert [ev["order"] for ev in timeline] == list(range(1, 12))
    kept = next(ev for ev in timeline if ev["id"] == "ev_1_1")
    assert kept["extra_chunk_indices"] == [0]                    # đoạn gốc của sự việc trùng vẫn đọc được
    gone = next(ev for ev in _bible(pipeline).timeline if ev.id == "ev_0_6")   # bản G4 giữ nguyên
    assert set(gone.entity_ids) <= set(kept["entity_ids"])

    outline_prompt_text = _prompt_for(llm, "OUTLINE")
    assert "DÒNG THỜI GIAN: 11 sự việc" in outline_prompt_text and "ev_0_6" not in outline_prompt_text
    assert "Nhân chứng và người báo án" in _prompt_for(llm, "WRITE_VI p2")   # đoạn 0, nhờ sự việc đã gộp
    plan = case_store.load_plan(pipeline.case_id)
    assert [ev.id for ev in plan.bible.timeline] == [ev["id"] for ev in timeline]


def test_dedupe_rejects_unknown_ids_overlaps_and_too_many_merges(isolated_projects_dir):
    pipeline = _new_pipeline()
    unknown = {"duplicates": [{"keep": "ev_9_9", "drop": ["ev_0_1"], "reason": "x"}]}
    overlap = {"duplicates": [{"keep": "ev_0_1", "drop": ["ev_0_2"], "reason": "x"},
                              {"keep": "ev_0_2", "drop": ["ev_0_3"], "reason": "x"}]}
    too_many = {"duplicates": [{"keep": "ev_0_1", "drop": ["ev_0_2", "ev_0_3", "ev_0_4", "ev_0_5", "ev_0_6", "ev_1_1",
                                                           "ev_1_2"], "reason": "x"}]}    # 7 trên 12 sự việc
    llm, calls = make_fake_llm({"DEDUPE": [unknown, overlap, too_many]})

    with pytest.raises(StepFailed) as info:
        _run_pipeline(pipeline, llm, stop_after="dedupe")

    assert calls.count("DEDUPE") == MAX_ATTEMPTS
    reasons = _retry_reasons(llm, "DEDUPE")
    assert "ev_9_9" in reasons[0] and "nhóm khác" in reasons[1]
    assert "lọc sự việc trùng" in info.value.user_message and "quá nhiều" in info.value.user_message


def test_dedupe_accepts_no_duplicates_and_keeps_the_timeline(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="dedupe")
    out = case_store.load_step_output(pipeline.case_id, "dedupe")
    assert out["merged"] == {}
    assert out["bible"]["timeline"] == _bible(pipeline).model_dump()["timeline"]
    prompt = _prompt_for(llm, "DEDUPE")
    assert "CÙNG MỘT việc" in prompt and "Trịnh Quang Vũ" in prompt and "Nguyễn Văn Hùng" not in prompt


def test_outline_may_drop_minor_events_with_a_reason(isolated_projects_dir):
    pipeline = _new_pipeline()
    without = _outline_without("ev_1_2")
    no_reason = {**copy.deepcopy(without), "dropped": ["ev_1_2"]}
    still_in_part = {**copy.deepcopy(load_fixture("OUTLINE")), "dropped": [{"event_id": "ev_1_2", "reason": "phụ"}]}
    good = {**without, "dropped": [{"event_id": "ev_1_2", "reason": "Lời đe dọa đã được nhắc ở cảnh trước."}]}
    llm, calls = make_fake_llm({"OUTLINE": [no_reason, still_in_part, good]})

    result = _run_pipeline(pipeline, llm, stop_after="outline")

    assert calls.count("OUTLINE") == 3
    reasons = _retry_reasons(llm, "OUTLINE")
    assert "ev_1_2" in reasons[0] and "thiếu lý do" in reasons[0]
    assert '"dropped"' in reasons[1] and "Nhịp 2" in reasons[1]
    assert result.output["dropped"] == [{"event_id": "ev_1_2", "reason": "Lời đe dọa đã được nhắc ở cảnh trước."}]
    assert "ev_1_2" not in result.output["parts"][1]["event_ids"]


def test_outline_drops_at_most_a_third_of_the_events(isolated_projects_dir):
    pipeline = _new_pipeline()
    five = ["ev_0_2", "ev_0_3", "ev_1_2", "ev_1_3", "ev_1_4"]          # 12 sự việc: bỏ tối đa 4
    greedy = {**_outline_without(*five), "dropped": [{"event_id": e, "reason": "chi tiết phụ"} for e in five]}
    fine = {**_outline_without(*five[:4]), "dropped": [{"event_id": e, "reason": "chi tiết phụ"} for e in five[:4]]}
    llm, calls = make_fake_llm({"OUTLINE": [greedy, fine]})

    result = _run_pipeline(pipeline, llm, stop_after="outline")

    assert calls.count("OUTLINE") == 2
    assert '"dropped" có 5 sự việc, tối đa 4' in _reason(llm)
    assert [d["event_id"] for d in result.output["dropped"]] == five[:4]


def test_outline_prompt_allows_non_linear_telling_and_dropping(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="outline")
    prompt = _prompt_for(llm, "OUTLINE")
    assert "không bắt buộc theo thời gian" in prompt and "quay ngược về bối cảnh" in prompt
    assert '"dropped"' in prompt and "Tối đa 4 sự việc" in prompt and "KHÔNG được bỏ sự việc then chốt" in prompt


def test_last_scene_of_a_part_ends_with_an_open_question(isolated_projects_dir):
    pipeline = _new_pipeline()
    flat = copy.deepcopy(load_fixture("WRITE_VI p1"))
    flat["scenes"][-1]["narration_vi"] = flat["scenes"][-1]["narration_vi"].replace(
        "Bóng người ấy là ai?", "Bóng người ấy đã biến mất.")
    llm, calls = make_fake_llm({"WRITE_VI p1": [flat]})          # lần sau trả fixture (kết bằng câu hỏi)

    _run_pipeline(pipeline, llm)

    assert calls.count("WRITE_VI p1") == 2 and calls.count("WRITE_VI p2") == 1   # nhịp cuối không cần câu hỏi
    assert "cảnh 3 là cảnh cuối nhịp" in _retry_reasons(llm, "WRITE_VI p1")[0]
    p1 = _prompt_for(llm, "WRITE_VI p1")
    next_summary = load_fixture("OUTLINE")["parts"][1]["summary_vi"]
    assert "PHẢI là một câu hỏi bỏ ngỏ" in p1 and next_summary[:40] in p1
    assert "nhịp cuối của video" in _prompt_for(llm, "WRITE_VI p2")
    plan = case_store.load_plan(pipeline.case_id)
    assert plan.scenes[3].narration_vi.endswith("?")


def test_english_keeps_the_open_question_of_the_vietnamese_scene(isolated_projects_dir):
    pipeline = _new_pipeline()
    flat = copy.deepcopy(load_fixture("WRITE_EN p1"))
    flat["scenes"][-1]["narration_en"] = flat["scenes"][-1]["narration_en"].replace(
        "Who was that figure?", "Nobody ever saw that figure again.")
    llm, calls = make_fake_llm({"WRITE_EN p1": [flat]})

    _run_pipeline(pipeline, llm, stop_after="write_en_p1")

    assert calls.count("WRITE_EN p1") == 2
    assert "narration_en chưa kết bằng câu hỏi" in _retry_reasons(llm, "WRITE_EN p1")[0]


def test_invented_quote_is_sent_back_then_flagged_for_review(isolated_projects_dir):
    pipeline = _new_pipeline()
    quoted = copy.deepcopy(load_fixture("WRITE_VI p1"))
    quoted["scenes"][2]["narration_vi"] = quoted["scenes"][2]["narration_vi"].replace(
        "Run rẩy, bà Hà bấm máy gọi đến trực ban hình sự.", 'Bà nói: "Tôi không tin nổi chuyện này."')
    llm, calls = make_fake_llm({"WRITE_VI p1": quoted})            # cả 3 lần đều còn lời trích bịa

    _run_pipeline(pipeline, llm)

    assert calls.count("WRITE_VI p1") == MAX_ATTEMPTS
    assert "lời trích" in _retry_reasons(llm, "WRITE_VI p1")[0]
    plan = case_store.load_plan(pipeline.case_id)                 # lỗi nhẹ: vẫn nhận, nhưng màn xem lại báo
    assert any("Tôi không tin nổi chuyện này" in w and "không có nguyên văn" in w for w in plan.check_warnings)
    assert not has_blocking_flags(plan)


def test_prompts_no_longer_allow_made_up_dialogue(isolated_projects_dir):
    from services.case_adaptation_prompts import SYSTEM_PROMPT
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm)
    texts = [SYSTEM_PROMPT, _prompt_for(llm, "WRITE_VI p1"), _prompt_for(llm, "WRITE_EN p1")]
    assert all("thoại dựng lại" not in t for t in texts)
    assert "Không bịa lời nói" in SYSTEM_PROMPT
    assert "KHÔNG đặt lời vào miệng nhân vật" in texts[1]
    assert "không thêm lời thoại" in texts[2]


# ---------------------------------------------------------------- số chữ mỗi cảnh theo thời lượng video

def test_word_budget_follows_the_chosen_video_length():
    from services.case_adaptation_prompts import EN_WORDS_PER_MINUTE, VI_WORDS_PER_MINUTE
    from services.case_adaptation_steps import scene_budget
    short, longer = scene_budget(8), scene_budget(20)
    assert short.vi_limit == (22, 51) and short.en_limit == (13, 30)
    assert longer.vi_aim[1] > short.vi_aim[1] and longer.en_limit[1] > short.en_limit[1]
    for minutes in (8, 15, 20, 30):                       # đọc đúng mức nhắm thì video ra khoảng đúng số phút đã chọn
        budget = scene_budget(minutes)
        lo, hi = TARGET_SCENES[minutes]
        scenes = (lo + hi) / 2
        assert 0.85 * minutes <= scenes * budget.vi_aim[1] / VI_WORDS_PER_MINUTE <= 1.05 * minutes
        assert 0.85 * minutes <= scenes * budget.en_aim[1] / EN_WORDS_PER_MINUTE <= 1.05 * minutes


def test_write_vi_and_en_reject_scenes_longer_than_the_budget(isolated_projects_dir):
    pipeline = _new_pipeline()                                         # video 8 phút: tối đa 51 chữ Việt, 30 chữ Anh
    wordy_vi = copy.deepcopy(load_fixture("WRITE_VI p1"))
    wordy_vi["scenes"][1]["narration_vi"] += " " + " ".join(["Mưa vẫn rơi."] * 4)       # 49 + 12 từ
    wordy_en = copy.deepcopy(load_fixture("WRITE_EN p1"))
    wordy_en["scenes"][1]["narration_en"] += " The rain kept falling all night long."   # 25 + 7 từ
    llm, calls = make_fake_llm({"WRITE_VI p1": [wordy_vi], "WRITE_EN p1": [wordy_en]})

    _run_pipeline(pipeline, llm, stop_after="write_en_p1")

    assert calls.count("WRITE_VI p1") == 2 and calls.count("WRITE_EN p1") == 2
    assert "cảnh 2: narration_vi dài 61 từ, cần từ 22 đến 51 từ" in _retry_reasons(llm, "WRITE_VI p1")[0]
    assert "cảnh 2: narration_en dài 32 từ, cần từ 13 đến 30 từ" in _retry_reasons(llm, "WRITE_EN p1")[0]
    vi_prompt, en_prompt = _prompt_for(llm, "WRITE_VI p1"), _prompt_for(llm, "WRITE_EN p1")
    assert "khoảng 37–46 từ (khoảng 13 giây đọc" in vi_prompt and "từ 22 đến 51 từ" in vi_prompt
    assert "khoảng 21–27 từ tiếng Anh" in en_prompt and "từ 13 đến 30 từ" in en_prompt


def test_open_question_must_differ_from_the_previous_part(isolated_projects_dir):
    """Chạy thật: 10/12 câu hỏi cuối nhịp mở đầu bằng "Liệu". Prompt đưa câu hỏi nhịp trước vào và đòi đổi cách hỏi."""
    from models.case_adaptation_schemas import StoryPart
    from services.case_adaptation_prompts import _last_question, write_vi_prompt
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="outline")
    outline = case_store.load_step_output(pipeline.case_id, "outline")
    p1, p2 = [StoryPart.model_validate(p) for p in outline["parts"]]
    p3 = p2.model_copy(update={"id": "p3", "kind": "epilogue"})
    prev = load_fixture("WRITE_VI p1")["scenes"][-2:]

    prompt = write_vi_prompt(_bible(pipeline), p2, [], [], prev, outline_parts=[p1, p2, p3])

    assert '"Bóng người ấy là ai?"' in prompt and "không mở đầu bằng cùng từ" in prompt
    assert 'không mở đầu câu hỏi bằng "Liệu"' in prompt
    assert _last_question("Trời mưa. Ai đã đứng đó?") == "Ai đã đứng đó?"
    assert _last_question("Trời mưa.") == ""
