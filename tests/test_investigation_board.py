"""
Unit tests for Investigation Board Engine (Corkboard, Fixed-Anchor, Cumulative State, Bezier Red Threads, Video Clip)
"""

import sys
import os
from itertools import combinations
from pathlib import Path

import pytest
from PIL import Image

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
    card_footprint,
    title_banner_text_and_font,
    _draw_title_banner,
    _missing_glyphs,
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    FRAME_THICKNESS,
)

NODE_TYPES = ["victim", "suspect", "suspect", "weapon", "forensic_report", "location", "clue", "timeline_event", "clue"]
BANNER_BOTTOM = FRAME_THICKNESS + 4 + 42        # mép dưới băng tiêu đề


def make_unplaced_nodes(count: int) -> list:
    return [
        EvidenceNode(id=f"card_{i:02d}", label=f"Thẻ số {i}", node_type=NODE_TYPES[i % len(NODE_TYPES)],
                     x=0, y=0, pinned=False, appearance_scene_order=1 + i // 5)
        for i in range(count)
    ]


def boxes_overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def assert_cards_apart_and_inside(nodes):
    """Vùng thẻ thật sự phủ (đúng như lúc vẽ) không chạm nhau và nằm trong mặt bần, dưới băng tiêu đề."""
    boxes = {n.id: card_footprint(n) for n in nodes}
    for (id_a, a), (id_b, b) in combinations(boxes.items(), 2):
        assert not boxes_overlap(a, b), f"Thẻ {id_a} {a} đè thẻ {id_b} {b}"
    for node_id, (x1, y1, x2, y2) in boxes.items():
        assert x1 >= FRAME_THICKNESS and x2 <= CANVAS_WIDTH - FRAME_THICKNESS, (node_id, x1, x2)
        assert y1 >= BANNER_BOTTOM and y2 <= CANVAS_HEIGHT - FRAME_THICKNESS, (node_id, y1, y2)


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


# ---------------------------------------------------------------- sức chứa: nhiều thẻ vẫn không đè nhau

@pytest.mark.parametrize("count", [1, 2, 3, 5, 8, 12, 13, 16, 20, 24, 30])
def test_layout_never_overlaps_cards(count):
    nodes = assign_fixed_anchor_layout(make_unplaced_nodes(count))

    assert all(n.pinned for n in nodes)
    assert_cards_apart_and_inside(nodes)
    assert len({n.metadata["card_scale"] for n in nodes}) == 1      # mọi thẻ cùng một cỡ


def test_twenty_cards_shrink_evenly_but_stay_readable():
    few = assign_fixed_anchor_layout(make_unplaced_nodes(5))
    many = assign_fixed_anchor_layout(make_unplaced_nodes(20))

    assert {n.metadata["card_scale"] for n in few} == {1.0}             # ít thẻ: cỡ gốc
    scale = many[0].metadata["card_scale"]
    assert 0.8 <= scale < 1.0                                          # 20 thẻ: thu nhỏ nhưng chữ vẫn đọc được


def test_layout_puts_early_cards_near_the_middle_and_victim_first():
    nodes = assign_fixed_anchor_layout(make_unplaced_nodes(20))
    victim = next(n for n in nodes if n.node_type == "victim")
    assert abs(victim.x - 960) < 200 and abs(victim.y - 540) < 200      # nạn nhân (hiện ở cảnh 1) giữa bảng

    first_scene = [n for n in nodes if n.appearance_scene_order == 1]
    last_scene = [n for n in nodes if n.appearance_scene_order == max(m.appearance_scene_order for m in nodes)]
    def spread(group):
        return sum(abs(n.x - 960) + abs(n.y - 540) for n in group) / len(group)
    assert spread(first_scene) < spread(last_scene)                    # cảnh đầu không bị dồn ra mép bảng


def test_default_coordinates_do_not_pin_cards_on_top_of_each_other():
    """EvidenceNode mặc định pinned=True ở (960, 540): kể cả thẻ nạn nhân cũng phải được xếp chỗ riêng."""
    nodes = [EvidenceNode(id=f"d{i}", label=f"Thẻ {i}", node_type=t) for i, t in enumerate(NODE_TYPES)]
    assign_fixed_anchor_layout(nodes)
    assert_cards_apart_and_inside(nodes)


def test_new_cards_avoid_cards_pinned_before():
    pinned = [
        EvidenceNode(id="old_1", label="Cũ 1", node_type="suspect", x=460, y=270, pinned=True, rotation_deg=2.0),
        EvidenceNode(id="old_2", label="Cũ 2", node_type="victim", x=960, y=480, pinned=True, rotation_deg=-1.0),
        EvidenceNode(id="old_3", label="Cũ 3", node_type="weapon", x=1460, y=790, pinned=True, rotation_deg=1.0),
    ]
    before = {n.id: (n.x, n.y) for n in pinned}
    nodes = assign_fixed_anchor_layout(pinned + make_unplaced_nodes(10))

    assert {n.id: (n.x, n.y) for n in nodes[:3]} == before            # thẻ đã ghim không bao giờ bị dời
    assert_cards_apart_and_inside(nodes)


# ---------------------------------------------------------------- tiêu đề

def test_title_banner_uses_only_glyphs_the_font_has():
    for title in ("Hồ sơ điều tra", "Case file", "Kỳ Án Đêm Trăng: Manh Mối Ban Đầu"):
        text, font = title_banner_text_and_font(title)
        assert text == " ".join(title.upper().split())
        assert "★" not in text                                         # sao vẽ bằng đa giác, không phải chữ
        assert _missing_glyphs(font, text) == set(), (title, _missing_glyphs(font, text))

    _, font = title_banner_text_and_font("x")
    assert _missing_glyphs(font, "A\ue000") == {"\ue000"}              # bộ dò glyph thiếu bắt được ô vuông


def test_title_banner_draws_two_stars_around_the_title():
    canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 255))
    _draw_title_banner(canvas, "Case file")
    star = (153, 27, 27, 255)
    xs = [x for x in range(CANVAS_WIDTH) for y in range(FRAME_THICKNESS, BANNER_BOTTOM + 1)
          if canvas.getpixel((x, y)) == star]
    assert any(x < 960 - 100 for x in xs) and any(x > 960 + 100 for x in xs)


# ---------------------------------------------------------------- sợi chỉ nằm trên thẻ

def test_thread_is_drawn_over_the_cards_it_crosses():
    left = EvidenceNode(id="a", label="A", node_type="suspect", x=400, y=400, appearance_scene_order=1)
    right = EvidenceNode(id="b", label="B", node_type="suspect", x=1500, y=400, appearance_scene_order=1)
    middle = EvidenceNode(id="c", label="C", node_type="clue", x=950, y=420, appearance_scene_order=1)
    edge = RelationEdge(id="e", source_id="a", target_id="b", appearance_scene_order=1)
    state = BoardState(scene_order=1, title="Test", cumulative_nodes=[left, right, middle], cumulative_edges=[edge])

    img = render_board_image(state)

    pin_y = 400 - 310 / 2 + 12                                         # đinh ghim: giữa mép trên thẻ (không nghiêng)
    curve = compute_bezier_points((400, pin_y), (1500, pin_y), steps=50)
    x1, y1, x2, y2 = card_footprint(middle)
    over_card = [(x, y) for x, y in curve if x1 + 20 < x < x2 - 20 and y1 + 20 < y < y2 - 20]
    assert over_card, "sợi chỉ thử phải đi ngang qua thẻ ở giữa"
    for x, y in over_card:
        near = [img.getpixel((int(x) + dx, int(y) + dy)) for dx in (-1, 0, 1) for dy in (-2, -1, 0, 1, 2)]
        assert any(r > 150 and g < 90 and b < 90 for r, g, b in near), f"không thấy chỉ đỏ ở {(x, y)}: {near}"


if __name__ == "__main__":
    import tempfile
    test_corkboard_background_generation()
    test_fixed_anchor_layout()
    test_cumulative_state()
    test_bezier_sagging()
    with tempfile.TemporaryDirectory() as td:
        test_render_board_image_and_video(Path(td))
    print("\n🎉 ALL INVESTIGATION BOARD ENGINE TESTS PASSED 100%!")
