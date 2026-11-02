"""Vụ án: lời Việt mỗi nhịp phải qua bước kiểm đủ ý, không kể lặp / trái điều đã kể (coverage_guard, 02/11/2026).

CLAUDE.md mục 1.2 câu 10, 11, 14, 21. Gặp 29/10/2026: vụ Trạm Dung kể việc phát hiện thi thể hai lần như hai lần
khác nhau. Không gọi LLM thật: tests/case_adaptation_fakes.py.
"""
import asyncio
import copy

import pytest

from services import case_store
from services.case_adaptation_steps import StepFailed, run_step
from tests.case_adaptation_fakes import load_fixture, make_fake_llm
from tests.test_case_adaptation_steps_story import _new_pipeline, _prompt_for, _run_pipeline


def test_verify_reports_missing_event_and_writer_rewrites(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm({"kiem_loi_ke": [{"quotes": [], "issues": [], "facts": []}]})
    result = _run_pipeline(pipeline, llm, stop_after="write_vi_p1")
    assert calls.count("WRITE_VI p1") == 2 and calls.count("kiem_loi_ke") == 2
    assert "CHƯA KỂ các ý sau" in _prompt_for(llm, "WRITE_VI p1", 1)
    assert result.output["verified"] is True and result.output["verify_rounds"] == 2
    assert result.output["facts"]


def test_issue_with_real_quote_forces_rewrite_fake_quote_is_rechecked(isolated_projects_dir):
    pipeline = _new_pipeline()
    narr = load_fixture("WRITE_VI p1")["scenes"][0]["narration_vi"]
    real = " ".join(narr.split()[:8])
    issue = {"quotes": [], "issues": [{"scene": 1, "kind": "lap_lai", "quote": real, "detail": "kể lại phát hiện"}],
             "facts": []}
    fake_quote = {"quotes": [{"point_id": "ev_0_1", "scene": 1, "quote": "một câu không hề có trong lời kể nhé"}],
                  "issues": [], "facts": []}
    llm, calls = make_fake_llm({"kiem_loi_ke": [fake_quote, issue]})
    result = _run_pipeline(pipeline, llm, stop_after="write_vi_p1")
    # lần 1 kiểm bịa câu trích -> kiểm lại; lần 2 bắt lỗi kể lặp có câu trích thật -> viết lại; lần 3 đạt
    assert calls.count("kiem_loi_ke") == 3 and calls.count("WRITE_VI p1") == 2
    assert "kể lại như mới" in _prompt_for(llm, "WRITE_VI p1", 1)
    assert result.output["verify_rounds"] == 2


def test_verify_never_passing_fails_the_step_loudly(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm({"kiem_loi_ke": {"quotes": [], "issues": [], "facts": []}})
    with pytest.raises(StepFailed) as err:
        _run_pipeline(pipeline, llm, stop_after="write_vi_p1")
    assert "chưa đạt khi kiểm" in err.value.user_message
    assert calls.count("WRITE_VI p1") == 3


def test_first_person_narrator_rejected(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("WRITE_VI p1"))
    bad["scenes"][0]["narration_vi"] = "Tôi " + bad["scenes"][0]["narration_vi"]
    llm, calls = make_fake_llm({"WRITE_VI p1": [bad]})
    _run_pipeline(pipeline, llm, stop_after="write_vi_p1")
    assert 'xưng "Tôi"' in _prompt_for(llm, "WRITE_VI p1", 1)


def test_second_part_gets_facts_of_first_part(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="write_vi_p2")
    assert "BẢNG SỰ THẬT CÁC NHỊP TRƯỚC ĐÃ KỂ" in _prompt_for(llm, "WRITE_VI p2")
    assert "đã kể ev_" in _prompt_for(llm, "WRITE_VI p2")


def test_assemble_refuses_unverified_vietnamese(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    _run_pipeline(pipeline, llm, stop_after="write_prompts_p2")
    out = case_store.load_step_output(pipeline.case_id, "write_vi_p1")
    out.pop("verified")
    case_store.save_step_output(pipeline.case_id, "write_vi_p1", out)
    step = next(s for s in pipeline.steps if s.kind == "assemble")
    with pytest.raises(StepFailed) as err:
        asyncio.run(run_step(pipeline, step, llm=llm))
    assert "chưa qua bước kiểm đủ ý" in err.value.user_message
