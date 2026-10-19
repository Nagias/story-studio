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
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.case_adaptation_schemas import DISCLAIMER, MAX_ATTEMPTS, CaseBible, CasePipeline
from services import case_store
from services.case_adaptation_checks import fold, has_blocking_flags
from services.case_adaptation_llm import LLMError
from services.case_adaptation_steps import (
    SoftRejected,
    StepFailed,
    StepRejected,
    ask_validated,
    chunk_source,
    initial_steps,
    rewrite_english,
    run_step,
)
from services.video_service import CAMERA_MOTIONS
from tests.case_adaptation_fakes import FIXTURES_DIR, load_fixture, make_fake_llm

DOSSIER = (FIXTURES_DIR / "dossier.txt").read_text(encoding="utf-8")
RETRY_MARK = "LẦN TRƯỚC BỊ LOẠI VÌ"
FULL_ORDER = [
    "EXTRACT 0", "EXTRACT 1", "CLUSTER", "ALIASES", "OUTLINE",
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
    """Chạy hàng việc như worker; trả kết quả của việc cuối cùng đã chạy."""
    result, i = None, 0
    while i < len(pipeline.steps):
        step = pipeline.steps[i]
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
        "extract_00", "extract_01", "cluster", "aliases", "outline", "write_vi_p1", "write_en_p1", "write_prompts_p1",
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
        assert all(fold(real) not in fold(t) for t in texts), real


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
    assert calls == FULL_ORDER[:5]
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
        assert fold(real) not in fold(prompt), real


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


def test_write_vi_short_narration_and_unknown_reveal_rejected(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("WRITE_VI p2"))
    bad["scenes"][0]["narration_vi"] = "Ông Lâm bị nghi ngờ."           # 5 từ
    bad["scenes"][1]["board_reveal"] = ["evd_1", "evd_99"]
    llm, calls = make_fake_llm({"WRITE_VI p2": [bad, load_fixture("WRITE_VI p2")]})
    _run_pipeline(pipeline, llm, stop_after="write_vi_p2")
    assert calls.count("WRITE_VI p2") == 2
    reason = _reason(llm)
    assert "evd_99" in reason and "25" in reason and "cảnh 1" in reason


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
    assert "3 cảnh" in reason and "20" in reason


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
    assert "5" in _reason(llm, 1) and "20" in _reason(llm, 2)
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
