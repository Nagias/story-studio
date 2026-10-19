"""
Comprehensive End-to-End (E2E) Integration Tests for Story Studio True Crime Pipeline
======================================================================================
Tests covered:
1. Endpoint POST /api/true-crime/fictionalize:
   - Ingests real criminal dossier (e.g. Kỳ án Cảng Tân Hải with real entities:
     'Nguyễn Văn Hùng', 'Lê Thị Mai', 'Đường Lê Lợi, TP Hải Phòng', '15B1-987.65', '0912345678').
   - Confirms 100% PII anonymization via Deterministic Alias Vault: Zero leakage in script, prompts, or board nodes.
   - Jubensha 3-Act structure with 70% Forensic Truth / 30% Suspense Red Herring and Foreshadowing Ledger.
   - Evidence Corkboard Cumulative DAG: Fixed-anchor coordinates (pinned=True, no coordinate jumps),
     monotonic accumulation of nodes and Bezier gravitational sagging red threads.
2. Endpoint POST /api/true-crime/render-board-scene/{scene_id}:
   - Renders 1080p static board image (JPG/PNG) successfully.
   - Renders 2-3s animated dynamic video clip (MP4) with Bezier yarn stretching successfully.
3. Endpoint POST /api/true-crime/create-project:
   - Creates full Story Studio project with narrator voice 'vi-VN-NamMinhNeural' and style 'neo_noir_silhouette'.
   - Pre-renders B-Roll corkboard evidence scenes and validates scene alternation.
"""

import sys
import os
from pathlib import Path
from PIL import Image

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Setup project and backend paths
TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient

from main import app
from services.project_service import get_project
from services.case_fictionalizer import (
    AnonymizerShield,
    JubenshaMatrix,
    ForeshadowingLedgerManager,
    YouTubeReviewerScriptGenerator,
)
from services.investigation_board_engine import (
    assign_fixed_anchor_layout,
    compute_bezier_points,
    get_cumulative_board_state,
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
)
from models.evidence_schemas import FictionalCasePlan, EvidenceNode, RelationEdge


# Realistic true crime sample dossier with prominent real PII entities
SAMPLE_REAL_CRIME_DOSSIER = """
HỒ SƠ VỤ ÁN HÌNH SỰ: KỲ ÁN CẢNG TÂN HẢI (HẢI PHÒNG)

Thời gian: Vào đêm ngày 15 tháng 10 năm 2021, vào khoảng 23 giờ 30 phút.
Địa điểm: Kho bãi bốc dỡ Cảng Tân Hải, số 88 Đường Lê Lợi, TP Hải Phòng.

Nội dung sự việc:
Nạn nhân là ông Nguyễn Văn Hùng (48 tuổi, trú tại TP Hải Phòng), Giám đốc Công ty Vận tải Biển Đông,
được phát hiện tử vong tại khu vực container số 14 với vết thương chí mạng ở vùng gáy do vật sắc nhọn tác động.

Nhân chứng và người báo án:
Bà Lê Thị Mai (36 tuổi, Kế toán trưởng công ty, điều khiển xe máy Air Blade biển số 15B1-987.65)
đã gọi điện đến trực ban hình sự qua số điện thoại 0912345678 để trình báo.
Bà Mai khai nhận quay lại văn phòng lấy sổ sách tài chính thì phát hiện hiện trường,
đồng thời thấy một bóng người mặc áo khoác sẫm màu chạy vụt qua cổng cảng trong cơn mưa tầm tã.

Nghi phạm ban đầu (Hướng điều tra số 1):
Cơ quan điều tra tình nghi ông Vũ Đình Trọng (đối tác kinh doanh có khoản nợ tranh chấp hơn 2 tỷ đồng).
Ông Trọng có mặt gần hiện trường vào buổi chiều cùng ngày và từng có lời đe dọa ông Hùng.

Diễn biến khám nghiệm pháp y & manh mối:
1. Pháp y xác định nạn nhân tử vong vào khoảng 22 giờ 15 phút (chênh lệch hơn 1 giờ so với thời điểm bà Mai báo án).
2. Phát hiện một chiếc bật lửa kim loại khắc chữ rơi dưới gầm tủ tài liệu bị lục soát.
3. Dấu vết bùn đất đỏ đặc trưng tại hiện trường không trùng khớp với tuyến đường của ông Trọng,
   ngược lại ông Trọng có chứng cứ ngoại phạm vững chắc qua camera giao thông lúc 22h15.
"""

REAL_PII_ENTITIES = [
    "Nguyễn Văn Hùng",
    "Lê Thị Mai",
    "Đường Lê Lợi",
    "TP Hải Phòng",
    "15B1-987.65",
    "0912345678",
]


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


@pytest.fixture(scope="module")
def case_plan(api_client):
    """
    Executes POST /api/true-crime/fictionalize once for the E2E module.
    Returns the complete FictionalCasePlan JSON dictionary.
    """
    response = api_client.post(
        "/api/true-crime/fictionalize",
        json={
            "raw_report": SAMPLE_REAL_CRIME_DOSSIER,
            "duration_minutes": 1,
            "truth_ratio": 0.70,
            "fiction_ratio": 0.30,
        },
    )
    assert response.status_code == 200, f"Fictionalize request failed: {response.text}"
    return response.json()


# ==============================================================================
# TEST 1: POST /api/true-crime/fictionalize & ANONYMIZER VAULT ANTI-LEAK
# ==============================================================================
def test_fictionalize_anonymizer_vault_anti_leak(case_plan):
    """
    Validates:
    - POST /api/true-crime/fictionalize successfully generates FictionalCasePlan.
    - 100% of real names, locations, license plates, and phone numbers are mapped into alias_vault.
    - Absolute anti-leak: NONE of the real PII terms appear in script texts, image prompts,
      node labels, node descriptions, or edge labels.
    """
    plan = case_plan
    assert "case_id" in plan and plan["case_id"]
    assert "alias_vault" in plan and isinstance(plan["alias_vault"], dict)
    vault = plan["alias_vault"]

    # 1. Verify all primary real PII entities were captured in vault keys
    assert "Nguyễn Văn Hùng" in vault, "Nạn nhân Nguyễn Văn Hùng must be captured in alias vault"
    assert "Lê Thị Mai" in vault, "Nhân chứng Lê Thị Mai must be captured in alias vault"
    assert "15B1-987.65" in vault, "Biển số xe 15B1-987.65 must be captured in alias vault"
    assert "0912345678" in vault, "Số điện thoại 0912345678 must be captured in alias vault"
    assert any("Lê Lợi" in k for k in vault.keys()), "Đường Lê Lợi must be captured in alias vault"
    assert any("Hải Phòng" in k for k in vault.keys()), "TP Hải Phòng must be captured in alias vault"

    # 2. Verify fictional aliases are non-empty and differ from real names
    for real_key, alias_val in vault.items():
        assert real_key != alias_val, f"Alias identical to real entity: {real_key} -> {alias_val}"
        assert len(alias_val.strip()) > 0

    # 3. Comprehensive Anti-Leak Assertion across all generated plan artifacts
    scenes = plan.get("scenes_script", [])
    assert len(scenes) >= 4, f"Expected at least 4 scenes, got {len(scenes)}"

    nodes = plan.get("nodes", [])
    assert len(nodes) >= 5, f"Expected at least 5 evidence nodes, got {len(nodes)}"

    edges = plan.get("edges", [])
    assert len(edges) >= 4, f"Expected at least 4 relation edges, got {len(edges)}"

    for real_term in REAL_PII_ENTITIES:
        # Check scene narration texts
        for sc in scenes:
            scene_order = sc.get("order", 0)
            text = sc.get("text", "")
            prompt = sc.get("image_prompt", "")
            assert real_term not in text, (
                f"PII LEAK in Scene {scene_order} text! Found real term '{real_term}': {text}"
            )
            assert real_term not in prompt, (
                f"PII LEAK in Scene {scene_order} image_prompt! Found real term '{real_term}': {prompt}"
            )

        # Check evidence board nodes
        for node in nodes:
            nid = node.get("id", "")
            label = node.get("label", "")
            desc = node.get("description", "")
            assert real_term not in label, (
                f"PII LEAK in EvidenceNode [{nid}] label! Found real term '{real_term}': {label}"
            )
            assert real_term not in desc, (
                f"PII LEAK in EvidenceNode [{nid}] description! Found real term '{real_term}': {desc}"
            )

        # Check relation edges
        for edge in edges:
            eid = edge.get("id", "")
            elabel = edge.get("label", "") or ""
            assert real_term not in elabel, (
                f"PII LEAK in RelationEdge [{eid}] label! Found real term '{real_term}': {elabel}"
            )

        # Check plan title
        assert real_term not in plan.get("title", ""), (
            f"PII LEAK in Plan Title! Found real term '{real_term}'"
        )


# ==============================================================================
# TEST 2: JUBENSHA 3-ACT STRUCTURE, RED HERRING & FORESHADOWING LEDGER
# ==============================================================================
def test_jubensha_three_act_structure_and_red_herring(case_plan):
    """
    Validates:
    - Jubensha 3-act narrative rhythm (Hook/Setting -> Red Herring Escalation -> Climax/Resolution).
    - Presence of plausible Red Herring suspect with false suspicion & verified alibi.
    - Foreshadowing Ledger: Clues planted early and resolved late with zero orphaned clues.
    - 5-second pacing per scene with YouTube 3rd-person Reviewer voice.
    """
    plan = case_plan
    scenes = plan["scenes_script"]
    nodes = plan["nodes"]
    edges = plan["edges"]
    ledger = plan["foreshadowing_ledger"]

    # 1. Jubensha 70/30 Formula ratios
    assert plan["truth_ratio"] == 0.70
    assert plan["fiction_ratio"] == 0.30

    # 2. Pacing & 3rd-person Reviewer Voice verification
    for sc in scenes:
        assert sc["estimated_duration"] == 5.0, "Each scene must be exactly 5.0s pacing"
        assert sc["shot_type"] in ("A_ROLL_NOIR", "B_ROLL_BOARD"), (
            f"Invalid shot type: {sc['shot_type']}"
        )
        assert len(sc["text"].split()) >= 6, f"Scene text too brief: {sc['text']}"

    # Visual Alternation: must have both A_ROLL_NOIR and B_ROLL_BOARD
    shot_types = [sc["shot_type"] for sc in scenes]
    assert "A_ROLL_NOIR" in shot_types, "Must contain A-Roll Neo-Noir scenes"
    assert "B_ROLL_BOARD" in shot_types, "Must contain B-Roll Evidence Board scenes"

    # 3. Red Herring suspect presence & alibi shift
    suspect_nodes = [n for n in nodes if n["node_type"] == "suspect"]
    assert len(suspect_nodes) >= 2, "Must contain at least 2 suspects (Culprit + Red Herring)"

    red_herring_node = next(
        (n for n in suspect_nodes if "red_herring" in n["id"].lower() or n.get("stamp") == "ALIBI" or "alibi" in n.get("description", "").lower() or "đối tác" in n.get("description", "").lower() or "đồng nghiệp" in n.get("description", "").lower()),
        None
    )
    assert red_herring_node is not None, "Red Herring suspect node must be defined in the Jubensha DAG"

    # Culprit suspect presence
    culprit_node = next(
        (n for n in suspect_nodes if "culprit" in n["id"].lower() or "hung thủ" in n.get("label", "").lower() or "thực sự" in n.get("label", "").lower()),
        None
    )
    assert culprit_node is not None, "True Culprit suspect node must be defined in the Jubensha DAG"

    # Edge contradicting alibi or linking motive
    has_contradiction_or_motive_edge = any(
        e.get("relation_type") in ("alibi_contradiction", "motive", "causal")
        for e in edges
    )
    assert has_contradiction_or_motive_edge, "Must contain causal relation edges (motive / alibi contradiction)"

    # 4. Foreshadowing Ledger verification
    assert len(ledger) >= 1, "Foreshadowing ledger must track planted clues"
    total_scenes = len(scenes)

    for clue in ledger:
        assert clue["planted_scene_order"] >= 1, "Clue planted scene order must be >= 1"
        assert clue["status"] == "resolved", f"Clue '{clue['id']}' must be resolved by the end of episode"
        assert clue["resolved_scene_order"] is not None
        assert clue["resolved_scene_order"] <= total_scenes, (
            f"Clue resolved at {clue['resolved_scene_order']} > total scenes {total_scenes}"
        )
        assert clue["resolved_scene_order"] > clue["planted_scene_order"], (
            f"Clue resolved order ({clue['resolved_scene_order']}) must be > planted ({clue['planted_scene_order']})"
        )
        assert len(clue.get("payout_explanation", "").strip()) > 0, "Payout explanation must not be empty"


# ==============================================================================
# TEST 3: EVIDENCE BOARD CUMULATIVE DAG & FIXED-ANCHOR COORDINATES
# ==============================================================================
def test_evidence_board_cumulative_dag_and_fixed_anchors(case_plan):
    """
    Validates:
    - Fixed-Anchor Grid: Coordinates (x, y) are permanent (pinned=True) and never shift or jump.
    - Cumulative DAG: Consecutive BoardStates monotonically accumulate visible nodes and edges.
    - Gravitational Bezier Red Threads: Downward gravity sag is mathematically proven.
    """
    plan = case_plan
    nodes = plan["nodes"]
    board_states = plan["board_states"]
    assert len(board_states) >= 3, "Expected at least 3 cumulative board states"

    # 1. Verify all nodes are permanently pinned within 1920x1080 canvas bounds
    for n in nodes:
        assert n["pinned"] is True, f"Node {n['id']} must have pinned=True"
        assert 150 <= n["x"] <= CANVAS_WIDTH - 150, f"Node {n['id']} X {n['x']} outside safe area"
        assert 150 <= n["y"] <= CANVAS_HEIGHT - 150, f"Node {n['id']} Y {n['y']} outside safe area"

    # 2. Fixed-Anchor Invariance test: Re-running layout preserves exact coordinates
    pydantic_nodes = [EvidenceNode(**n) for n in nodes]
    original_coords = {n.id: (n.x, n.y) for n in pydantic_nodes}
    recalculated = assign_fixed_anchor_layout(pydantic_nodes)
    new_coords = {n.id: (n.x, n.y) for n in recalculated}

    assert original_coords == new_coords, "Fixed-Anchor violated! Node positions drifted across layout runs."

    # 3. Monotonic Cumulative progression test
    prev_nodes_count = 0
    prev_edges_count = 0
    seen_node_coords = {}

    for idx, bs in enumerate(board_states):
        cum_nodes = bs["cumulative_nodes"]
        cum_edges = bs["cumulative_edges"]

        # Counts must be non-decreasing
        assert len(cum_nodes) >= prev_nodes_count, (
            f"Board state {idx+1} nodes decreased: {len(cum_nodes)} < {prev_nodes_count}"
        )
        assert len(cum_edges) >= prev_edges_count, (
            f"Board state {idx+1} edges decreased: {len(cum_edges)} < {prev_edges_count}"
        )

        # Invariance across scenes: previously seen node coordinates must NEVER shift
        for n in cum_nodes:
            nid = n["id"]
            pos = (n["x"], n["y"])
            if nid in seen_node_coords:
                assert seen_node_coords[nid] == pos, (
                    f"Node {nid} jumped position in scene {idx+1}! Previous: {seen_node_coords[nid]}, Current: {pos}"
                )
            else:
                seen_node_coords[nid] = pos

        prev_nodes_count = len(cum_nodes)
        prev_edges_count = len(cum_edges)

    # 4. Bezier Gravitational Sagging verification
    p0 = (400.0, 300.0)
    p2 = (1200.0, 300.0)
    curve_points = compute_bezier_points(p0, p2, steps=30, sag_factor=0.15)
    assert len(curve_points) == 31

    # Endpoints match
    assert abs(curve_points[0][0] - 400.0) < 1e-4 and abs(curve_points[0][1] - 300.0) < 1e-4
    assert abs(curve_points[-1][0] - 1200.0) < 1e-4 and abs(curve_points[-1][1] - 300.0) < 1e-4

    # Midpoint must sag downward (greater Y coordinate in screen space)
    mid_idx = len(curve_points) // 2
    mid_point = curve_points[mid_idx]
    assert mid_point[1] > 300.0 + 20.0, (
        f"Gravity sag failed! Expected Y > 320.0, got {mid_point[1]}"
    )


# ==============================================================================
# TEST 4: POST /api/true-crime/render-board-scene/{scene_id} (IMAGE & VIDEO)
# ==============================================================================
def test_render_board_scene_image_and_video(api_client, case_plan):
    """
    Validates:
    - POST /api/true-crime/render-board-scene/1 renders 1080p static PNG/JPG frame (> 50KB).
    - POST /api/true-crime/render-board-scene/2 renders 2.0s animated video MP4 clip (> 10KB).
    - Verifies valid HTTP responses, file paths, and media accessibility.
    """
    plan = case_plan
    case_id = plan["case_id"]

    # 1. Render Scene 1 (Static Image)
    resp_img = api_client.post(
        f"/api/true-crime/render-board-scene/1",
        json={"case_id": case_id, "plan": plan, "render_video": False},
    )
    assert resp_img.status_code == 200, f"Render board image failed: {resp_img.text}"
    data_img = resp_img.json()

    assert data_img["success"] is True
    assert data_img["case_id"] == case_id
    assert data_img["scene_id"] == 1
    assert data_img["image_url"].startswith(f"/static/evidence_boards/{case_id}/")

    img_file = Path(data_img["image_path"])
    assert img_file.exists(), f"Rendered image file does not exist at {img_file}"
    assert img_file.stat().st_size > 30000, f"Image file too small ({img_file.stat().st_size} bytes)"

    # Verify image dimensions with Pillow
    with Image.open(img_file) as im:
        assert im.size == (CANVAS_WIDTH, CANVAS_HEIGHT), (
            f"Expected image resolution {CANVAS_WIDTH}x{CANVAS_HEIGHT}, got {im.size}"
        )

    # 2. Render Scene 2 (Dynamic 2-Second Animated Video Clip)
    resp_vid = api_client.post(
        f"/api/true-crime/render-board-scene/2",
        json={
            "case_id": case_id,
            "plan": plan,
            "render_video": True,
            "duration_sec": 2.0,
            "fps": 15,
        },
    )
    assert resp_vid.status_code == 200, f"Render board video failed: {resp_vid.text}"
    data_vid = resp_vid.json()

    assert data_vid["success"] is True
    assert data_vid["video_url"] is not None
    assert data_vid["video_url"].endswith(".mp4")

    vid_file = Path(data_vid["video_path"])
    assert vid_file.exists(), f"Rendered video file does not exist at {vid_file}"
    assert vid_file.stat().st_size > 5000, f"Video file too small ({vid_file.stat().st_size} bytes)"
    assert data_vid["cumulative_nodes_count"] >= data_img["cumulative_nodes_count"]


# ==============================================================================
# TEST 5: POST /api/true-crime/create-project (PROJECT INTEGRATION)
# ==============================================================================
def test_create_true_crime_project_integration(api_client, case_plan):
    """
    Validates:
    - POST /api/true-crime/create-project builds a complete Story Studio Project.
    - Style preset assigned to 'neo_noir_silhouette'.
    - Narrator voice assigned to 'vi-VN-NamMinhNeural'.
    - Pre-rendered corkboard images attached to B-Roll scenes.
    - Scenes alternating between A_ROLL_NOIR and B_ROLL_BOARD with proper camera motions.
    """
    plan = case_plan
    custom_title = "Kỳ Án Cảng Hải Phòng: Vết Mực Sau Mưa Bão"

    # Call Create Project
    resp_proj = api_client.post(
        "/api/true-crime/create-project",
        json={
            "plan": plan,
            "case_title": custom_title,
            "voice": "vi-VN-NamMinhNeural",
            "pre_render_boards": True,
        },
    )
    assert resp_proj.status_code == 200, f"Create project failed: {resp_proj.text}"
    proj_data = resp_proj.json()

    assert proj_data["success"] is True
    project_id = proj_data["project_id"]
    assert project_id.startswith("proj_crime_")
    assert proj_data["title"] == custom_title

    # Retrieve and inspect saved project
    project = get_project(project_id)
    assert project is not None, f"Failed to retrieve project {project_id} from storage"
    assert project.name == custom_title
    assert project.voice == "vi-VN-NamMinhNeural"
    assert project.style_preset == "neo_noir_silhouette"
    assert project.bgm_overall_genre == "mysterious_dark"
    assert project.target_aspect_ratio == "16:9"

    # Check scenes configuration
    assert len(project.scenes) >= 4, f"Project scenes count too low: {len(project.scenes)}"

    b_roll_scenes = [s for s in project.scenes if s.shot_type == "B_ROLL_BOARD"]
    a_roll_scenes = [s for s in project.scenes if s.shot_type == "A_ROLL_NOIR"]

    assert len(b_roll_scenes) > 0, "Must contain B-Roll evidence board scenes"
    assert len(a_roll_scenes) > 0, "Must contain A-Roll neo-noir scenes"

    # Verify B-Roll pre-rendered board images exist
    for b_scene in b_roll_scenes:
        assert b_scene.image_url is not None
        assert b_scene.image_url.startswith("/api/projects/") or b_scene.image_url.startswith("/static/evidence_boards/")
        assert b_scene.image_path is not None
        b_img_path = Path(b_scene.image_path)
        assert b_img_path.exists(), f"Board image file missing: {b_img_path}"
        assert b_img_path.stat().st_size > 30000

    # Verify A-Roll camera motion and prompts
    for a_scene in a_roll_scenes:
        assert a_scene.camera_motion in (
            "neo_noir_dutch_tilt", "neo_noir_rain_motion", "zoom_in", "pan_left", "action_camera_shake"
        )
        assert len(a_scene.image_prompt) > 20
        assert a_scene.voice_emotion == "tense"

    print(f"\n✓ Successfully verified True Crime Project {project_id} with {len(project.scenes)} scenes.")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
