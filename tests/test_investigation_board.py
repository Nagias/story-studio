"""
Unit tests for Investigation Board Engine (Corkboard, Fixed-Anchor, Cumulative State, Bezier Red Threads, Video Clip)
"""

import sys
import os
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

from models.evidence_schemas import (
    EvidenceNode,
    RelationEdge,
    BoardState,
    FictionalCasePlan,
)
from services.investigation_board_engine import (
    generate_corkboard_background,
    assign_fixed_anchor_layout,
    get_cumulative_board_state,
    render_board_image,
    render_board_animation_clip,
    compute_bezier_points,
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
)


def test_corkboard_background_generation():
    bg = generate_corkboard_background(1920, 1080)
    assert bg.size == (1920, 1080)
    assert bg.mode == "RGB"
    print("✓ test_corkboard_background_generation passed")


def test_fixed_anchor_layout():
    nodes = [
        EvidenceNode(id="victim_01", label="Nạn nhân Lê Văn A", node_type="victim", appearance_scene_order=1),
        EvidenceNode(id="suspect_01", label="Nghi phạm Trần B (Hung thủ)", node_type="suspect", appearance_scene_order=1),
        EvidenceNode(id="suspect_02", label="Nghi phạm Nguyễn C (Red Herring)", node_type="suspect", appearance_scene_order=2),
        EvidenceNode(id="weapon_01", label="Dao găm dính máu", node_type="weapon", appearance_scene_order=2),
        EvidenceNode(id="forensic_01", label="Kết quả giám định ADN", node_type="forensic_report", appearance_scene_order=3, stamp="CONFIRMED"),
    ]

    # Assign layout
    laid_out = assign_fixed_anchor_layout(nodes)

    # Check all are pinned
    for n in laid_out:
        assert n.pinned is True
        assert 100 <= n.x <= 1820
        assert 100 <= n.y <= 980

    # Save original coordinates
    coords_first = [(n.id, n.x, n.y) for n in laid_out]

    # Re-run layout: Coordinates MUST remain 100% identical (Fixed-Anchor Guarantee)
    re_laid_out = assign_fixed_anchor_layout(laid_out)
    coords_second = [(n.id, n.x, n.y) for n in re_laid_out]

    assert coords_first == coords_second, "Fixed-Anchor violated! Coordinates changed across layout passes."
    print("✓ test_fixed_anchor_layout passed (Fixed-Anchor invariance verified)")


def test_cumulative_state():
    nodes = [
        EvidenceNode(id="v1", label="Victim", node_type="victim", appearance_scene_order=1),
        EvidenceNode(id="s1", label="Suspect 1", node_type="suspect", appearance_scene_order=1),
        EvidenceNode(id="s2", label="Suspect 2", node_type="suspect", appearance_scene_order=2),
        EvidenceNode(id="w1", label="Weapon", node_type="weapon", appearance_scene_order=3),
    ]
    edges = [
        RelationEdge(id="e1", source_id="s1", target_id="v1", appearance_scene_order=1, label="Motive"),
        RelationEdge(id="e2", source_id="s2", target_id="v1", appearance_scene_order=2, label="Threat"),
        RelationEdge(id="e3", source_id="w1", target_id="v1", appearance_scene_order=3, label="Murder Weapon"),
    ]
    plan = FictionalCasePlan(
        case_id="case_test_01",
        title="Vụ Án Kỳ Bí Số 1",
        nodes=nodes,
        edges=edges,
    )

    # Scene 1: only s1 and v1, edge e1
    state1 = get_cumulative_board_state(plan, scene_order=1)
    assert len(state1.cumulative_nodes) == 2
    assert len(state1.cumulative_edges) == 1
    assert len(state1.delta_nodes) == 2
    assert len(state1.delta_edges) == 1

    # Scene 2: s1, v1, s2, edges e1, e2
    state2 = get_cumulative_board_state(plan, scene_order=2)
    assert len(state2.cumulative_nodes) == 3
    assert len(state2.cumulative_edges) == 2
    assert len(state2.delta_nodes) == 1
    assert state2.delta_nodes[0].id == "s2"
    assert len(state2.delta_edges) == 1
    assert state2.delta_edges[0].id == "e2"

    # Scene 3: all 4 nodes, all 3 edges
    state3 = get_cumulative_board_state(plan, scene_order=3)
    assert len(state3.cumulative_nodes) == 4
    assert len(state3.cumulative_edges) == 3
    assert len(state3.delta_nodes) == 1
    assert state3.delta_nodes[0].id == "w1"

    print("✓ test_cumulative_state passed (ΔNodes_k + ΔEdges_k cumulative progression verified)")


def test_bezier_sagging():
    p0 = (200.0, 300.0)
    p2 = (800.0, 300.0)
    pts = compute_bezier_points(p0, p2, steps=20)
    assert len(pts) == 21
    # Check that midpoint has gravity sag (higher Y coordinate in canvas space)
    mid_pt = pts[10]
    assert mid_pt[1] > 300.0, f"Expected gravity sag Y > 300, got {mid_pt[1]}"
    print("✓ test_bezier_sagging passed (natural gravity curve verified)")


def test_render_board_image_and_video(tmp_path: Path):
    nodes = [
        EvidenceNode(id="v1", label="Nạn nhân Hải", node_type="victim", x=960, y=480, appearance_scene_order=1, stamp="DECEASED"),
        EvidenceNode(id="s1", label="Nghi phạm Long", node_type="suspect", x=460, y=270, appearance_scene_order=1, stamp="ALIBI"),
        EvidenceNode(id="s2", label="Nghi phạm Tuấn", node_type="suspect", x=1460, y=270, appearance_scene_order=1),
        EvidenceNode(id="w1", label="Con dao gấp", node_type="weapon", x=700, y=790, appearance_scene_order=1),
    ]
    edges = [
        RelationEdge(id="e1", source_id="s1", target_id="v1", label="Động cơ tranh chấp", appearance_scene_order=1),
        RelationEdge(id="e2", source_id="s2", target_id="v1", label="Nhân chứng thấy lúc 21h", appearance_scene_order=1),
        RelationEdge(id="e3", source_id="w1", target_id="v1", label="Vết thương khớp hung khí", appearance_scene_order=1),
    ]
    board_state = BoardState(
        scene_order=1,
        title="Kỳ Án Đêm Trăng: Manh Mối Ban Đầu",
        cumulative_nodes=nodes,
        cumulative_edges=edges,
        delta_nodes=nodes,
        delta_edges=edges,
    )

    out_img = tmp_path / "test_board_scene_1.jpg"
    img = render_board_image(board_state, str(out_img))
    assert out_img.exists()
    assert out_img.stat().st_size > 50000  # at least ~50KB
    assert img.size == (1920, 1080)
    print(f"✓ test_render_board_image passed: {out_img} ({out_img.stat().st_size} bytes)")

    out_mp4 = tmp_path / "test_board_clip_1.mp4"
    # Test short 2-second clip for fast test turnaround
    res_clip = render_board_animation_clip(board_state, str(out_mp4), duration_sec=2.0, fps=15)
    assert Path(res_clip).exists()
    assert Path(res_clip).stat().st_size > 10000
    print(f"✓ test_render_board_animation_clip passed: {res_clip} ({Path(res_clip).stat().st_size} bytes)")


if __name__ == "__main__":
    import tempfile
    test_corkboard_background_generation()
    test_fixed_anchor_layout()
    test_cumulative_state()
    test_bezier_sagging()
    with tempfile.TemporaryDirectory() as td:
        test_render_board_image_and_video(Path(td))
    print("\n🎉 ALL INVESTIGATION BOARD ENGINE TESTS PASSED 100%!")
