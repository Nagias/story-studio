"""Việc làm video gửi Muse phải đòi cử động thật và giữ máy quay đứng yên (services/prompt_rules.py).

Gặp 10/11/2026 (vụ xưởng sắt): 48 clip "Muse Video theo lời thoại" chỉ lia/zoom ảnh tĩnh; việc video mặc định xin
"cinematic slow tracking pan" và prompt không đòi người cử động."""
import sys
from pathlib import Path

from starlette.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402
from models.schemas import Project, Scene  # noqa: E402
from services import dialogue_video as dv  # noqa: E402
from services.prompt_rules import LOCKED_CAMERA_EN, video_rules_vi  # noqa: E402

TEXT = "Người thám tử bước vào xưởng, ngồi xổm xuống cạnh vũng nước. Ông cầm đèn pin soi vào góc tường."


def _scene_and_project():
    scene = Scene(id="scene_005", order=5, text=TEXT, image_prompt="Medium shot of a detective in a workshop.",
                  metadata={"visual_kind": "image"})
    return Project(id="proj_motion01", name="Thử", style_preset="horror_cartoon_2d", scenes=[scene]), scene


def test_dialogue_video_prompt_demands_body_motion_and_still_camera():
    project, scene = _scene_and_project()
    segments = dv.plan_segments(scene.text, 9.0)
    for k in range(1, len(segments) + 1):
        prompt = dv.segment_prompt(project, scene, segments, k, None, False)
        for rule in video_rules_vi(project):
            assert rule in prompt
        assert "lia máy" not in prompt.lower() or "không lia" in prompt.lower()


def test_video_task_default_camera_is_locked_not_a_pan():
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    resp = client.post("/api/muse-bridge/tasks/create", json={
        "mode": "image-to-video", "prompt": "detective kneels down",
        "input_image_url": "http://127.0.0.1:8000/static/demo_images/scene_1.jpg", "duration": 5})
    assert resp.status_code == 200
    task = resp.json()["task"]
    assert task["camera_motion"] == LOCKED_CAMERA_EN
    assert task["parameters"]["camera_motion"] == LOCKED_CAMERA_EN


def test_no_code_asks_muse_for_a_slow_camera_pan_by_default():
    root = BACKEND_DIR
    for path in [*root.glob("routers/*.py"), *root.glob("services/*.py"), *root.glob("static/*.js")]:
        assert "cinematic slow tracking pan" not in path.read_text(encoding="utf-8"), path.name
