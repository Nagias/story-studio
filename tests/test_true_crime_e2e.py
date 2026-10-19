"""
End-to-end qua HTTP cho luồng chuyển thể vụ án thật thành truyện song ngữ (spec 7.8, 7.11)
==========================================================================================
Phân tích (hàng việc, LLM giả) -> xem lại/sửa -> tạo dự án bản Việt -> bảng ghim -> tạo bản Anh:

1. Không lọt tên thật (người, địa danh, biển số, số điện thoại của bài mẫu "Kỳ án Cảng Tân Hải") vào kế hoạch gửi ra,
   file dự án bản Việt và dự án bản Anh.
2. Dự án bản Việt: cảnh miễn trừ đứng đầu, cảnh bảng ghim và miễn trừ được vẽ thẳng vào thư mục dự án, các cảnh còn lại
   chờ Muse; không ghi gì vào backend/static (thư mục công khai).
3. Bảng ghim tích luỹ: thẻ giữ nguyên vị trí qua các cảnh và qua hai ngôn ngữ, chỉ khác chữ.
4. Sửa lời kể làm lọt tên thật thì bị chặn (409), thêm tên vào bảng tên thì gỡ được.
5. Bản Anh dùng lại ảnh và clip của bản Việt, chỉ đổi lời kể, giọng, ảnh có chữ; hai dự án liên kết hai chiều.
6. Các route mới nằm sau LocalAccessMiddleware (máy khác và trang web lạ bị chặn).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops

# Setup project and backend paths
TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from models.case_adaptation_schemas import DISCLAIMER, CaseAdaptationPlan
from services import case_store, project_service
from services.case_adaptation_checks import fold
from services.case_project_builder import plan_board_items
from services.investigation_board_engine import CANVAS_HEIGHT, CANVAS_WIDTH, get_cumulative_board_state
from services.project_service import get_project
from tests.test_case_project_builder import prepare_source_media, scene_by_order
from tests.test_case_worker import DOSSIER
from tests.test_true_crime_router import (  # noqa: F401  (client, small_chunks là fixture dùng lại)
    BASE,
    EN_VOICE,
    REGEX_ONLY_NAME,
    VI_VOICE,
    client,
    create_vi_project,
    finished_case,
    get_plan,
    scene_of,
    small_chunks,
    wait_job,
)

# Tên thật trong bài mẫu (tests/fixtures/case_adaptation/dossier.txt): không được lọt vào bất kỳ đầu ra nào.
# Không đưa các cách gọi tắt như "ông Trọng" vào đây: bỏ dấu thì "ong trong" trùng chữ thường gặp ("ông trong căn phòng").
REAL_TERMS = [
    "Nguyễn Văn Hùng", "Lê Thị Mai", "Vũ Đình Trọng", "Cảng Tân Hải", "Đường Lê Lợi", "TP Hải Phòng", "Hải Phòng",
    "Công ty Vận tải Biển Đông", "15B1-987.65", "0912345678",
]


@pytest.fixture
def flow(client, small_chunks, monkeypatch):
    """Một vụ án đã phân tích xong và dự án bản Việt đã tạo qua API."""
    case_id = finished_case(client, monkeypatch)
    project_id = create_vi_project(client, case_id)
    return SimpleNamespace(client=client, case_id=case_id, project_id=project_id, plan=get_plan(client, case_id))


def assert_no_real_names(text: str, where: str) -> None:
    folded = fold(text)
    for term in REAL_TERMS:
        assert fold(term) not in folded, f"Lọt tên thật '{term}' vào {where}"


def project_text(project_id: str) -> str:
    """Toàn bộ file văn bản của dự án (project.json...)."""
    root = project_service._get_project_dir(project_id)
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(root.rglob("*.json")))


def plan_output_texts(plan: dict) -> str:
    """Mọi chữ của kế hoạch sẽ đi vào video: tên tập, lời kể vi/en, prompt, nhãn bảng ghim."""
    bible = plan["bible"]
    texts = [bible[k] for k in ("title_vi", "title_en", "logline_vi", "logline_en", "setting_notes_en")]
    for scene in plan["scenes"]:
        texts += [scene[k] for k in ("narration_vi", "narration_en", "image_prompt", "video_prompt")]
    for item in bible["evidence"] + bible["relations"]:
        texts += [item["label_vi"], item["label_en"]]
    return "\n".join(texts)


# ==============================================================================
# 1. KHÔNG LỌT TÊN THẬT
# ==============================================================================
def test_no_real_names_in_plan_or_either_project(flow):
    # Tiền đề: bài mẫu có đủ các tên thật này, và bảng tên của kế hoạch ghi nhận chúng.
    assert all(term in DOSSIER for term in ("Nguyễn Văn Hùng", "Lê Thị Mai", "Hải Phòng", "15B1-987.65", "0912345678"))
    known = {n for e in flow.plan["bible"]["entities"] for n in e["real_names"]}
    assert {"Nguyễn Văn Hùng", "Lê Thị Mai", "15B1-987.65", "0912345678"} <= known

    assert_no_real_names(plan_output_texts(flow.plan), "kế hoạch")
    assert_no_real_names(project_text(flow.project_id), "dự án bản Việt")

    job = wait_job(flow.client, flow.client.post(f"/api/projects/{flow.project_id}/create-language-version",
                                                 json={"language": "en"}).json()["job_id"])
    assert job["status"] == "done", job
    assert_no_real_names(project_text(job["result"]["project_id"]), "dự án bản Anh")


# ==============================================================================
# 2. DỰ ÁN BẢN VIỆT
# ==============================================================================
def test_vi_project_structure_and_images_stay_in_the_project_folder(flow):
    project = get_project(flow.project_id)
    plan = flow.plan

    assert project.voice == VI_VOICE
    assert project.style_preset == "neo_noir_silhouette"
    assert project.bgm_overall_genre == "mysterious_dark"
    assert project.target_aspect_ratio == "16:9"
    assert project.name == plan["bible"]["title_vi"]
    assert [s.id for s in project.scenes] == [f"scene_{n:03d}" for n in range(1, len(plan["scenes"]) + 1)]
    assert project.scenes[0].text == DISCLAIMER["vi"]

    shot_types = {s.shot_type for s in project.scenes}
    assert shot_types == {"A_ROLL_NOIR", "B_ROLL_BOARD"}                  # xen kẽ cảnh ảnh/video và cảnh bảng ghim
    for scene, adapted in zip(project.scenes, plan["scenes"]):
        assert scene.text == adapted["narration_vi"]
        assert scene.metadata["narration"] == {"vi": adapted["narration_vi"], "en": adapted["narration_en"]}
        assert scene.metadata["case_id"] == flow.case_id
        assert scene.image_prompt == adapted["image_prompt"] and scene.video_prompt == adapted["video_prompt"]

    root = project_service._get_project_dir(flow.project_id)
    for scene in project.scenes:
        drawn = scene.metadata["visual_kind"] in ("board", "disclaimer")
        assert (scene.status_image == "ready") == drawn                      # chỉ ảnh có chữ được vẽ sẵn, còn lại chờ Muse
        if drawn:
            image = Path(scene.image_path)
            assert image.parent == root / "images" and image.stat().st_size > 30000
            assert scene.image_url == f"/api/projects/{flow.project_id}/media/images/{image.name}"
            with Image.open(image) as img:
                assert img.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
    assert any(s.shot_type == "B_ROLL_BOARD" and s.image_path for s in project.scenes)

    static_boards = BACKEND_DIR / "static" / "evidence_boards" / flow.case_id
    assert not static_boards.exists()                                        # bảng ghim không ghi vào thư mục công khai


# ==============================================================================
# 3. BẢNG GHIM TÍCH LUỸ
# ==============================================================================
def test_cumulative_board_keeps_cards_in_place_across_scenes_and_languages(flow):
    plan = CaseAdaptationPlan.model_validate(flow.plan)
    nodes_vi, edges_vi = plan_board_items(plan, "vi")
    nodes_en, edges_en = plan_board_items(plan, "en")

    for node in nodes_vi:                                                    # toạ độ cố định, nằm trong vùng an toàn
        assert node.pinned is True
        assert 100 <= node.x <= CANVAS_WIDTH - 100 and 150 <= node.y <= CANVAS_HEIGHT - 150
    assert {n.id: (n.x, n.y) for n in nodes_vi} == {n.id: (n.x, n.y) for n in nodes_en}
    assert [n.label for n in nodes_vi] != [n.label for n in nodes_en]         # cùng bảng, khác chữ

    seen: dict[str, tuple[int, int]] = {}
    previous = (0, 0)
    for order in range(1, len(plan.scenes) + 1):
        state = get_cumulative_board_state(SimpleNamespace(nodes=nodes_vi, edges=edges_vi), order)
        counts = (len(state.cumulative_nodes), len(state.cumulative_edges))
        assert counts[0] >= previous[0] and counts[1] >= previous[1]         # chỉ tăng, không bao giờ mất thẻ
        previous = counts
        for node in state.cumulative_nodes:                                  # đã hiện thì không nhảy chỗ
            assert seen.setdefault(node.id, (node.x, node.y)) == (node.x, node.y)
    assert previous[0] >= 1


def test_render_board_scene_images_follow_language(flow):
    paths = {}
    for language in ("vi", "en"):
        response = flow.client.post(f"{BASE}/render-board-scene/6", json={"case_id": flow.case_id, "language": language})
        assert response.status_code == 200, response.text
        paths[language] = Path(response.json()["image_path"])
        assert paths[language].is_file() and paths[language].stat().st_size > 30000
    with Image.open(paths["vi"]) as a, Image.open(paths["en"]) as b:
        assert a.size == b.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
        assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is not None


# ==============================================================================
# 4. SỬA LỜI KỂ LÀM LỌT TÊN THẬT -> BỊ CHẶN -> THÊM TÊN VÀO BẢNG TÊN
# ==============================================================================
def test_leaked_name_blocks_until_it_is_added_to_the_name_table(flow):
    client, case_id = flow.client, flow.case_id
    case_store.save_source(case_id, case_store.load_source(case_id) + f"\nÔng {REGEX_ONLY_NAME} là tài xế xe tải.")
    leak = f"Trong màn mưa, {REGEX_ONLY_NAME} lặng lẽ đứng canh bên chiếc xe tải ở cuối bãi, không ai để ý tới ông cả."
    assert client.put(f"{BASE}/cases/{case_id}/scenes/3", json={"narration_vi": leak}).status_code == 200

    body = {"language": "vi", "voice": VI_VOICE}
    blocked = client.post(f"{BASE}/cases/{case_id}/create-project", json=body)
    assert blocked.status_code == 409
    assert "3" in blocked.json()["detail"] and "Tuấn" not in blocked.json()["detail"]

    added = client.put(f"{BASE}/cases/{case_id}/entities", json={"additions": [
        {"kind": "person", "real_names": [REGEX_ONLY_NAME], "alias_vi": "Lục Gia Bảo", "alias_en": "Luc Gia Bao"}]})
    assert added.status_code == 200
    assert "Lục Gia Bảo" in scene_of(added.json(), 3)["narration_vi"]
    assert "Luc Gia Bao" not in scene_of(added.json(), 3)["narration_vi"]

    created = client.post(f"{BASE}/cases/{case_id}/create-project", json=body)
    assert created.status_code == 200, created.text
    project = get_project(created.json()["project_id"])
    assert "Lục Gia Bảo" in scene_by_order(project, 3).text
    assert REGEX_ONLY_NAME not in project_text(project.id)

    # Bản Anh của dự án này: lời Anh của cảnh 3 chưa bị sửa nên dùng lại lời kế hoạch, cũng không có tên thật.
    job = wait_job(client, client.post(f"/api/projects/{project.id}/create-language-version",
                                       json={"language": "en"}).json()["job_id"])
    assert job["status"] == "done", job
    assert REGEX_ONLY_NAME not in project_text(job["result"]["project_id"])


# ==============================================================================
# 5. BẢN TIẾNG ANH
# ==============================================================================
def test_english_version_reuses_media_and_swaps_text_voice_and_board_labels(flow):
    source = prepare_source_media(get_project(flow.project_id))
    plan = flow.plan

    response = flow.client.post(f"/api/projects/{source.id}/create-language-version",
                                json={"language": "en", "voice": EN_VOICE})
    assert response.status_code == 200
    job = wait_job(flow.client, response.json()["job_id"])
    assert job["status"] == "done", job
    assert job["result"]["rewritten_orders"] == []
    new = get_project(job["result"]["project_id"])

    assert new.id != source.id
    assert new.voice == EN_VOICE and new.name == plan["bible"]["title_en"]
    assert new.metadata["language"] == "en" and new.metadata["case_id"] == flow.case_id
    assert [s.text for s in new.scenes] == [s["narration_en"] for s in plan["scenes"]]
    assert new.scenes[0].text == DISCLAIMER["en"]
    assert new.metadata["voices"] == {"vi": VI_VOICE, "en": EN_VOICE}

    # Ảnh và clip Muse của bản Việt được chép sang; giọng, phụ đề, video cuối thì không.
    new_root = project_service._get_project_dir(new.id)
    with Image.open(new_root / "images" / "scene_002.jpg") as copied:
        assert copied.size == (64, 36)
    assert (new_root / "videos" / "scene_003_muse.mp4").read_bytes() == b"fake-muse-clip"
    assert not list((new_root / "audio").iterdir()) and not list((new_root / "renders").iterdir())
    assert new.final_video_path is None and scene_by_order(new, 2).voice_audio_path is None

    # Ảnh có chữ vẽ lại bằng tiếng Anh; cùng kích thước, khác nội dung.
    for order in (1, 6):
        name = f"scene_{order:03d}.jpg"
        with Image.open(project_service._get_project_dir(source.id) / "images" / name) as a, \
                Image.open(new_root / "images" / name) as b:
            assert a.size == b.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
            assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is not None

    # Liên kết hai chiều
    assert get_project(new.id).metadata["sibling_project_ids"] == [source.id]
    assert get_project(source.id).metadata["sibling_project_ids"] == [new.id]


# ==============================================================================
# 6. TRUY CẬP
# ==============================================================================
def test_new_routes_are_behind_local_access_middleware(flow):
    remote = TestClient(app, base_url="http://127.0.0.1:8000", client=("10.0.0.5", 50000))
    cross_site = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000),
                            headers={"origin": "http://evil.example"})
    for denied in (remote, cross_site):
        assert denied.get(f"{BASE}/cases/{flow.case_id}").status_code == 403
        assert denied.post(f"{BASE}/analyze", json={"raw_report": DOSSIER}).status_code == 403
        assert denied.post(f"/api/projects/{flow.project_id}/create-language-version",
                           json={"language": "en"}).status_code == 403
        assert denied.get(f"{BASE}/jobs/job_00000000").status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
