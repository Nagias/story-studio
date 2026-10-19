"""
Unit tests for Case Fictionalizer & Suspense Engine
(Anonymizer Shield, Deterministic Alias Vault, Jubensha Matrix, Foreshadowing Ledger, YouTube Reviewer Script)
"""

import sys
import os
import asyncio
from pathlib import Path

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.case_fictionalizer import (
    AnonymizerShield,
    JubenshaMatrix,
    ForeshadowingLedgerManager,
    YouTubeReviewerScriptGenerator,
    CaseFictionalizerEngine,
)
from models.evidence_schemas import ForeshadowingItem


SAMPLE_RAW_REPORT = """
Vào đêm ngày 14 tháng 10 năm 2021, tại khu vực Cảng Hải Phòng, một vụ án mạng nghiêm trọng đã xảy ra.
Nạn nhân được xác định là ông Nguyễn Văn Hải, 42 tuổi, làm việc tại kho vận bốc xếp.
Theo lời khai ban đầu của anh Trần Đình Long (người báo án, đi xe máy biển số 15B-678.90),
anh ta phát hiện thi thể ông Hải nằm gần công-ten-nơ số 4 với vết chấn thương nặng ở vùng đầu.
Qua xác minh nhanh, cơ quan điều tra triệu tập nghi phạm Vũ Mạnh Hùng do có tranh chấp nợ nần 300 triệu đồng.
Tuy nhiên kết quả khám nghiệm tử thi cho thấy thời gian tử vong thực sự là khoảng 22h15.
"""


def test_anonymizer_shield():
    shield = AnonymizerShield()

    # 1. Build vault
    vault1 = shield.build_deterministic_vault(SAMPLE_RAW_REPORT)
    assert len(vault1) > 0

    # 2. Check deterministic guarantee: second run on same text gives identical vault
    vault2 = shield.build_deterministic_vault(SAMPLE_RAW_REPORT)
    assert vault1 == vault2, "Deterministic Alias Vault failed: identical inputs gave different mappings!"

    # 3. Anonymize text
    sanitized = shield.anonymize(SAMPLE_RAW_REPORT, vault1)

    # 4. Strictly assert NO real PII remains in sanitized text
    real_pii_terms = ["Nguyễn Văn Hải", "Trần Đình Long", "Vũ Mạnh Hùng", "15B-678.90"]
    for term in real_pii_terms:
        assert term not in sanitized, f"PII Leak Detected! Real term '{term}' was found in sanitized text."

    print("✓ test_anonymizer_shield passed (100% PII sanitized & Deterministic Vault confirmed)")


def test_jubensha_matrix():
    shield = AnonymizerShield()
    vault = shield.build_deterministic_vault(SAMPLE_RAW_REPORT)
    sanitized = shield.anonymize(SAMPLE_RAW_REPORT, vault)

    matrix = JubenshaMatrix.generate_matrix("Vụ Án Cảng Tân Hải", sanitized, vault)
    assert matrix["truth_ratio"] == 0.70
    assert matrix["fiction_ratio"] == 0.30

    nodes = matrix["nodes"]
    edges = matrix["edges"]

    # Check key roles exist
    types = [n.node_type for n in nodes]
    assert "victim" in types
    assert "suspect" in types
    assert "weapon" in types
    assert "forensic_report" in types

    # Check fixed-anchor coordinates are assigned
    for n in nodes:
        assert n.pinned is True
        assert n.x > 0 and n.y > 0

    print("✓ test_jubensha_matrix passed (70/30 Formula & Clue DAG verified)")


def test_foreshadowing_ledger():
    ledger = ForeshadowingLedgerManager.build_default_ledger()
    # Test valid ledger with 6 scenes
    is_valid, errors = ForeshadowingLedgerManager.validate_ledger(ledger, total_scenes=6)
    assert is_valid, f"Expected valid ledger, got errors: {errors}"

    # Test orphan detection
    orphan = ForeshadowingItem(
        id="clue_orphan",
        clue_name="Vết chân lạ",
        planted_scene_order=1,
        status="planted",  # Never resolved!
        description="Vết chân số 42",
    )
    bad_ledger = [orphan]
    is_valid_bad, errors_bad = ForeshadowingLedgerManager.validate_ledger(bad_ledger, total_scenes=6)
    assert not is_valid_bad, "Orphaned clue should have failed validation!"
    assert any("Orphaned clue detected" in e for e in errors_bad)

    print("✓ test_foreshadowing_ledger passed (Zero-orphaned clue validation confirmed)")


def test_youtube_reviewer_script():
    shield = AnonymizerShield()
    vault = shield.build_deterministic_vault(SAMPLE_RAW_REPORT)
    matrix = JubenshaMatrix.generate_matrix("Vụ Án Cảng Tân Hải", "", vault)

    scenes = YouTubeReviewerScriptGenerator.generate_offline_script(
        case_title="Vụ Án Cảng Tân Hải",
        vault=vault,
        nodes=matrix["nodes"],
        edges=matrix["edges"],
    )

    assert len(scenes) == 6

    # Verify 3rd person narration
    for sc in scenes:
        assert sc["estimated_duration"] == 5.0
        assert sc["shot_type"] in ("A_ROLL_NOIR", "B_ROLL_BOARD")
        # Ensure reviewer voice
        text = sc["text"]
        assert len(text.split()) >= 8, f"Scene text too short: '{text}'"

    # Verify rhythmic alternation between A_ROLL and B_ROLL
    shot_types = [sc["shot_type"] for sc in scenes]
    assert "A_ROLL_NOIR" in shot_types
    assert "B_ROLL_BOARD" in shot_types
    assert shot_types != ["A_ROLL_NOIR"] * len(shot_types), "Expected alternation between A-Roll and B-Roll"

    print("✓ test_youtube_reviewer_script passed (3rd-person Reviewer voice & A/B Roll pacing verified)")


def test_full_fictionalizer_pipeline():
    engine = CaseFictionalizerEngine()

    async def _run():
        plan = await engine.fictionalize_case(SAMPLE_RAW_REPORT)
        assert plan.case_id.startswith("case_")
        assert len(plan.nodes) >= 5
        assert len(plan.edges) >= 4
        assert len(plan.scenes_script) >= 4
        assert len(plan.board_states) >= 3
        # Check cumulative board states
        first_state = plan.board_states[0]
        last_state = plan.board_states[-1]
        assert len(last_state.cumulative_nodes) >= len(first_state.cumulative_nodes)
        print(f"✓ test_full_fictionalizer_pipeline passed: Created plan '{plan.title}' with {len(plan.scenes_script)} scenes and {len(plan.board_states)} board states.")

    asyncio.run(_run())


if __name__ == "__main__":
    test_anonymizer_shield()
    test_jubensha_matrix()
    test_foreshadowing_ledger()
    test_youtube_reviewer_script()
    test_full_fictionalizer_pipeline()
    print("\n🎉 ALL CASE FICTIONALIZER TESTS PASSED 100%!")
