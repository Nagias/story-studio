"""
Schema và lưu trữ phân tích vụ án (projects/_cases/<case_id>/): round-trip, thứ tự hàng việc,
giữ nguyên dấu tiếng Việt, ẩn khỏi danh sách dự án, từ chối id không an toàn.
Chạy trong thư mục tạm qua fixture isolated_projects_dir, không đụng projects/ thật.
"""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.case_adaptation_schemas import (
    AdaptedScene,
    CaseAdaptationPlan,
    CaseBible,
    CaseEntity,
    CaseEvidence,
    CasePipeline,
    CaseRelation,
    DISCLAIMER,
    MAX_ATTEMPTS,
    MAX_SOURCE_CHARS,
    MAX_VIDEO_RATIO,
    PipelineStep,
    SceneFlag,
    StoryPart,
    TARGET_SCENES,
    TimelineEvent,
)
from services import case_store, project_service


def _plan(case_id: str = "case_0a1b2c3d") -> CaseAdaptationPlan:
    bible = CaseBible(
        source_language="vi",
        culture="Việt Nam",
        title_vi="Vụ án căn nhà số 7",
        title_en="The Case of House No. 7",
        logline_vi="Một đêm mưa, hàng xóm nghe thấy tiếng động lạ.",
        entities=[
            CaseEntity(
                id="e1", kind="person", real_names=["Nguyễn Văn Hùng", "ông Hùng"],
                role="suspect", alias_vi="Lê Quang Minh", alias_en="Daniel Reyes",
                gender="male", age_range="40-50",
            ),
            CaseEntity(
                id="e2", kind="place", real_names=["Phường Bến Thành"],
                alias_vi="Phường Hòa Phú", alias_en="Riverside District",
            ),
        ],
        timeline=[
            TimelineEvent(id="t1", order=1, chunk_index=0, summary="Hàng xóm nghe tiếng động lạ từ căn nhà lúc nửa đêm.", entity_ids=["e1"]),
        ],
        evidence=[CaseEvidence(id="v1", label_vi="Con dao", label_en="The knife", entity_ids=["e1"])],
        relations=[CaseRelation(id="r1", source_id="e1", target_id="e2", label_vi="sống tại", label_en="lived in")],
    )
    part = StoryPart(
        id="p1", kind="hook", summary_vi="Mở đầu bằng tiếng động lạ.", event_ids=["t1"], scene_count=2,
    )
    scenes = [
        AdaptedScene(
            order=1, part_id="p1", visual_kind="disclaimer",
            narration_vi=DISCLAIMER["vi"], narration_en=DISCLAIMER["en"],
        ),
        AdaptedScene(
            order=2, part_id="p1", visual_kind="image",
            narration_vi="Nửa đêm, tiếng động lạ vang lên từ căn nhà cuối ngõ.",
            narration_en="At midnight, a strange noise came from the house at the end of the alley.",
            covers_event_ids=["t1"], image_prompt="a dark alley at night, rain, a single lit window",
            flags=[SceneFlag(kind="date", field="narration_vi", detail="ngày 15 tháng 10")],
        ),
    ]
    return CaseAdaptationPlan(
        case_id=case_id, created_at="2026-10-19T10:00:00", model="test-model",
        target_minutes=8, visual_style="neo_noir", bible=bible, parts=[part], scenes=scenes,
        warnings=["Cảnh 2 có ngày tháng."],
    )


def _pipeline(case_id: str, created_at: str) -> CasePipeline:
    return CasePipeline(
        case_id=case_id, target_minutes=8, visual_style="neo_noir",
        created_at=created_at, updated_at=created_at,
        steps=[
            PipelineStep(id="extract_chunk_0", kind="extract_chunk", params={"chunk_index": 0}),
            PipelineStep(id="cluster_names", kind="cluster_names"),
        ],
    )


def test_constants_match_global_constraints():
    assert DISCLAIMER == {
        "vi": "Câu chuyện dựa trên một vụ án có thật; tên người và địa danh đã được thay đổi.",
        "en": "This story is based on a real case; names of people and places have been changed.",
    }
    assert TARGET_SCENES == {8: (35, 40), 15: (50, 60), 20: (70, 80), 30: (100, 120)}
    assert MAX_SOURCE_CHARS == 200_000
    assert MAX_VIDEO_RATIO == 0.15
    assert MAX_ATTEMPTS == 3


def test_schema_defaults_do_not_leak_between_instances():
    a = _pipeline("case_aaaaaaaa", "2026-10-19T10:00:00")
    b = _pipeline("case_bbbbbbbb", "2026-10-19T11:00:00")
    a.steps[1].params["x"] = 1
    assert b.steps[1].params == {}
    assert a.steps[1].status == "pending" and a.steps[1].attempts == 0 and a.chunk_chars == 3000
    plan = _plan()
    assert plan.languages == ["vi", "en"]
    assert plan.scenes[0].camera_motion == "zoom_in" and plan.scenes[0].bgm_energy == "tension_buildup"


def test_plan_roundtrip(isolated_projects_dir):
    plan = _plan()
    case_store.save_plan(plan)
    assert case_store.load_plan(plan.case_id) == plan
    assert (isolated_projects_dir / "_cases" / plan.case_id).is_dir()
    assert case_store.load_plan("case_ffffffff") is None


def test_pipeline_roundtrip_and_listing_order(isolated_projects_dir):
    assert case_store.list_pipelines() == []
    newer = _pipeline("case_00000002", "2026-10-19T12:00:00")
    older = _pipeline("case_00000009", "2026-10-19T09:00:00")
    case_store.save_pipeline(newer)
    case_store.save_pipeline(older)
    assert case_store.load_pipeline("case_00000002") == newer
    assert [p.case_id for p in case_store.list_pipelines()] == ["case_00000009", "case_00000002"]
    assert case_store.load_pipeline("case_ffffffff") is None


def test_list_pipelines_skips_unreadable_and_foreign_dirs(isolated_projects_dir):
    good = _pipeline("case_00000001", "2026-10-19T09:00:00")
    case_store.save_pipeline(good)
    broken = isolated_projects_dir / "_cases" / "case_00000002"
    broken.mkdir()
    (broken / "pipeline.json").write_text("{không phải json", encoding="utf-8")
    (isolated_projects_dir / "_cases" / "case_00000003").mkdir()
    (isolated_projects_dir / "_cases" / "ghi chú.txt").write_text("x", encoding="utf-8")
    assert [p.case_id for p in case_store.list_pipelines()] == ["case_00000001"]


def test_step_output_and_chunks_roundtrip(isolated_projects_dir):
    cid = "case_0a1b2c3d"
    data = {"events": [{"summary": "Nguyễn Văn Hùng bị bắt tại Bến Thành"}], "ghi_chú": "đã xong"}
    case_store.save_step_output(cid, "extract_chunk_0", data)
    assert case_store.load_step_output(cid, "extract_chunk_0") == data
    assert case_store.load_step_output(cid, "extract_chunk_1") is None

    chunks = ["Đoạn một: Hà Nội, tháng 10.", "Đoạn hai: 原告 phát biểu."]
    case_store.save_chunks(cid, chunks)
    assert case_store.load_chunks(cid) == chunks
    case_store.save_source(cid, "Bài gốc có dấu: ắ ầ ẫ ộ ữ")
    assert case_store.load_source(cid) == "Bài gốc có dấu: ắ ầ ẫ ộ ữ"
    assert case_store.load_source("case_ffffffff") is None
    assert case_store.load_chunks("case_ffffffff") is None

    case_dir = isolated_projects_dir / "_cases" / cid
    raw = (case_dir / "steps" / "extract_chunk_0.json").read_bytes().decode("utf-8")
    assert "Nguyễn Văn Hùng" in raw  # UTF-8 thật, không bị escape \uXXXX
    assert "Đoạn một" in (case_dir / "chunks.json").read_bytes().decode("utf-8")
    assert "ắ ầ ẫ ộ ữ" in (case_dir / "source.txt").read_bytes().decode("utf-8")


def test_saved_json_files_are_utf8_without_escapes(isolated_projects_dir):
    plan = _plan()
    case_store.save_plan(plan)
    case_store.save_pipeline(_pipeline(plan.case_id, "2026-10-19T10:00:00"))
    case_store.save_chunks(plan.case_id, ["Bến Thành"])
    case_dir = isolated_projects_dir / "_cases" / plan.case_id
    assert "Vụ án căn nhà số 7" in (case_dir / "plan.json").read_bytes().decode("utf-8")
    assert "Bến Thành" in (case_dir / "chunks.json").read_bytes().decode("utf-8")
    assert not list(case_dir.rglob("*.tmp"))  # ghi nguyên tử, không để file tạm


def test_cases_dir_hidden_from_project_list(isolated_projects_dir):
    case_store.save_plan(_plan())
    case_store.save_pipeline(_pipeline("case_0a1b2c3d", "2026-10-19T10:00:00"))
    assert case_store.cases_dir() == isolated_projects_dir / "_cases"
    assert project_service.list_projects() == []


def test_new_case_id_shape_and_uniqueness():
    import re
    ids = {case_store.new_case_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(re.fullmatch(r"case_[0-9a-f]{8}", i) for i in ids)


@pytest.mark.parametrize("bad", ["../x", "..", "a/b", "a\\b", "", "x" * 65, "có dấu", ".hidden"])
def test_rejects_unsafe_case_id(isolated_projects_dir, bad):
    with pytest.raises(ValueError):
        case_store.load_plan(bad)
    with pytest.raises(ValueError):
        case_store.load_pipeline(bad)
    with pytest.raises(ValueError):
        case_store.save_source(bad, "x")
    with pytest.raises(ValueError):
        case_store.save_chunks(bad, ["x"])
    with pytest.raises(ValueError):
        case_store.load_step_output(bad, "extract_chunk_0")
    with pytest.raises(ValueError):
        case_store.save_plan(_plan(case_id=bad))
    with pytest.raises(ValueError):
        case_store.save_pipeline(_pipeline(bad, "2026-10-19T10:00:00"))
    assert not (isolated_projects_dir.parent / "x").exists()


@pytest.mark.parametrize("bad_step", ["../x", "a/b", "", "step.json", "x" * 65])
def test_rejects_unsafe_step_id(isolated_projects_dir, bad_step):
    with pytest.raises(ValueError):
        case_store.save_step_output("case_0a1b2c3d", bad_step, {"a": 1})
    with pytest.raises(ValueError):
        case_store.load_step_output("case_0a1b2c3d", bad_step)
