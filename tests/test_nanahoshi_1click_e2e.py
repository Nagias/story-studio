import re
import sys
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

# Gọi 9router (chia cảnh) và Edge-TTS thật
pytestmark = pytest.mark.live

# Ensure UTF-8 console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from services.project_service import delete_project
from services.tts_service import generate_speech
from services.video_service import render_scene_video

@pytest.fixture
def anyio_backend():
    return "asyncio"

# Chính xác nội dung truyện chữ Nanahoshi của người dùng
NANAHOSHI_ORIGINAL_SCRIPT = (
    "Tên tôi là Nanahoshi. Nanahoshi Shizuka. Là một nữ sinh trung học từ một thế giới khác đến thế giới này. "
    "Tôi không có chút ma lực nào như những người xung quanh, và cơ thể tôi cũng chẳng hề già đi theo năm tháng. "
    "Tại học viện ma thuật Ranoa, tôi đã giam mình trong góc phòng thí nghiệm suốt nhiều năm trời, "
    "điên cuồng nghiên cứu các vòng tròn ma pháp triệu hồi với một hy vọng cháy bỏng duy nhất: tìm được con đường trở về Nhật Bản."
)

VIETNAMESE_DIACRITICS_REGEX = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE
)

# Các cụm từ tiếng Anh hay bị dịch sai khi LLM không tuân thủ luật tiếng Việt
BANNED_ENGLISH_TRANSLATIONS = [
    "twelve days",
    "to everyone else",
    "my name is",
    "i am a high school",
    "stolen life",
    "sky citadel",
    "rotting away",
    "suspended in time",
]

@pytest.mark.asyncio
async def test_nanahoshi_1click_pipeline_vietnamese_script_preservation():
    """
    E2E Test 1: Kiểm thử tích hợp Pipeline 1-Click với kịch bản Nanahoshi:
    - POST /api/projects/create-from-script
    - Xác nhận trường text của tất cả scenes giữ nguyên 100% TIẾNG VIỆT tự nhiên.
    - Không có bất kỳ câu nào bị dịch sang tiếng Anh.
    - Giọng đọc được gán chuẩn tiếng Việt (vi-VN-NamMinhNeural hoặc HoaiMyNeural).
    - Image provider là meta_muse_cloud.
    - Lưu đúng character_reference_image.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        req_payload = {
            "name": "Truyện Nanahoshi Shizuka - Dị Giới Ký",
            "text": NANAHOSHI_ORIGINAL_SCRIPT,
            "pacing": "fast",
            "style_preset": "manga_murata_battle",
            "character_anchor": "Nanahoshi Shizuka, Japanese high school student with dark hair, white school uniform shirt, dark travel cape",
            "character_reference_image": "https://example.com/demo_nanahoshi_ref.png",
            "voice": "vi-VN-NamMinhNeural",
            "image_provider": "meta_muse_cloud",
            "generate_initial_images": False,
        }

        resp = await client.post("/api/projects/create-from-script", json=req_payload)
        assert resp.status_code == 200, f"Create project failed: {resp.text}"
        project = resp.json()
        project_id = project.id if hasattr(project, "id") else project.get("id")
        assert project_id, "Project ID must be generated"

        try:
            # 1. Kiểm tra cấu hình dự án
            assert project["voice"] in ("vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural", "vieneu-MaiAnh"), \
                f"Giọng đọc không phải tiếng Việt: {project['voice']}"
            assert project["image_provider"] == "meta_muse_cloud", \
                f"Image provider không phải meta_muse_cloud: {project['image_provider']}"
            assert project["character_reference_image"] == "https://example.com/demo_nanahoshi_ref.png", \
                "character_reference_image không được lưu đúng"

            # 2. Kiểm tra danh sách phân cảnh (scenes)
            scenes = project.get("scenes", [])
            assert len(scenes) >= 2, f"Phải tách được ít nhất 2 scenes, nhận được: {len(scenes)}"

            # 3. Kiểm tra TIÊU CHÍ CỐT LÕI: Toàn bộ scene.text là TIẾNG VIỆT tự nhiên, KHÔNG bị dịch
            full_vietnamese_text = ""
            for idx, sc in enumerate(scenes, start=1):
                scene_text = sc.get("text", "")
                image_prompt = sc.get("image_prompt", "")

                assert len(scene_text.strip()) > 0, f"Scene #{idx} text không được rỗng"
                full_vietnamese_text += " " + scene_text

                # a) Kiểm tra chứa ký tự tiếng Việt có dấu
                has_vietnamese = bool(VIETNAMESE_DIACRITICS_REGEX.search(scene_text))
                assert has_vietnamese, f"Scene #{idx} text không chứa ký tự tiếng Việt: '{scene_text}'"

                # b) Kiểm tra TUYỆT ĐỐI KHÔNG chứa cụm từ tiếng Anh dịch ẩu
                scene_text_lower = scene_text.lower()
                for banned in BANNED_ENGLISH_TRANSLATIONS:
                    assert banned not in scene_text_lower, \
                        f"Scene #{idx} bị dịch sang tiếng Anh ('{banned}') trong trường text: '{scene_text}'"

                # c) Kiểm tra image_prompt là tiếng Anh chi tiết phục vụ AI
                assert len(image_prompt) > 20, f"Scene #{idx} image_prompt quá ngắn: '{image_prompt}'"

            # d) Kiểm tra cốt truyện Nanahoshi được phản ánh trong text
            assert "nanahoshi" in full_vietnamese_text.lower(), "Văn bản phải giữ tên nhân vật Nanahoshi"
            assert ("thế giới" in full_vietnamese_text.lower() or "nữ sinh" in full_vietnamese_text.lower()), \
                "Văn bản phải giữ bối cảnh nữ sinh / thế giới khác"

        finally:
            # Dọn dẹp project test
            delete_project(project_id)


@pytest.mark.asyncio
async def test_nanahoshi_dedicated_1click_pipeline_endpoint():
    """
    E2E Test 2: Kiểm tra endpoint chuyên dụng POST /api/projects/create-1click-pipeline
    - Đảm bảo endpoint 1-click chuyên dụng xử lý đồng nhất với kịch bản Nanahoshi.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        req_payload = {
            "name": "Nanahoshi 1-Click Pipeline Test",
            "text": NANAHOSHI_ORIGINAL_SCRIPT,
            "style_preset": "manga_murata_battle",
            "voice": "vi-VN-NamMinhNeural",
            "image_provider": "meta_muse_cloud",
            "character_reference_image": "https://example.com/demo_nanahoshi_ref.png",
            "generate_initial_images": False,
        }

        resp = await client.post("/api/projects/create-1click-pipeline", json=req_payload)
        assert resp.status_code == 200, f"1-Click pipeline endpoint failed: {resp.text}"
        project = resp.json()
        project_id = project["id"]

        try:
            assert project["voice"] == "vi-VN-NamMinhNeural"
            assert project["image_provider"] == "meta_muse_cloud"
            assert len(project["scenes"]) >= 2
            # Kiểm tra kịch bản phân cảnh chứa nhân vật Nanahoshi
            first_scene_text = project["scenes"][0]["text"]
            assert any("Nanahoshi" in sc["text"] for sc in project["scenes"])
            assert bool(VIETNAMESE_DIACRITICS_REGEX.search(first_scene_text))
        finally:
            delete_project(project_id)


@pytest.mark.asyncio
async def test_nanahoshi_voice_generation_edge_tts(tmp_path):
    """
    E2E Test 3: Kiểm tra render voice tiếng Việt chuẩn bằng Edge-TTS:
    - Text: Câu mở đầu truyện Nanahoshi
    - Voice: vi-VN-NamMinhNeural
    - Xác nhận sinh file .mp3 và .srt hợp lệ, có thời lượng > 0 và phụ đề chứa đúng text tiếng Việt.
    """
    scene_text = "Tên tôi là Nanahoshi. Nanahoshi Shizuka. Là một nữ sinh trung học từ một thế giới khác đến thế giới này."
    out_audio = tmp_path / "nanahoshi_voice.mp3"
    out_srt = tmp_path / "nanahoshi_voice.srt"

    res = await generate_speech(
        text=scene_text,
        voice="vi-VN-NamMinhNeural",
        output_audio_path=str(out_audio),
        output_srt_path=str(out_srt),
    )

    # 1. Kiểm tra metadata trả về
    assert res["duration"] > 0, f"Duration phải > 0, nhận được: {res['duration']}"
    assert res["voice"] == "vi-VN-NamMinhNeural"
    assert res["detected_language"] == "vi"

    # 2. Kiểm tra file âm thanh vật lý trên đĩa
    assert out_audio.exists(), "File mp3 không tồn tại"
    assert out_audio.stat().st_size > 2000, f"File mp3 quá nhỏ ({out_audio.stat().st_size} bytes)"

    # 3. Kiểm tra file phụ đề SRT
    assert out_srt.exists(), "File srt không tồn tại"
    srt_content = out_srt.read_text(encoding="utf-8")
    assert "00:00:" in srt_content, "SRT không có timestamp chuẩn"
    assert "Nanahoshi" in srt_content, "SRT phải chứa từ khóa Nanahoshi"
    assert "thế giới khác" in srt_content, "SRT phải chứa nội dung tiếng Việt có dấu"


@pytest.mark.asyncio
async def test_nanahoshi_muse_bridge_task_payload_with_reference_image():
    """
    E2E Test 4: Kiểm tra định tuyến tác vụ sang Meta Muse Cloud kèm ảnh tham chiếu (reference_image):
    - Đảm bảo task gửi sang Muse Bridge mang đầy đủ reference_image, reference_image_url, character_anchor.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # Tạo task text-to-image với reference image
        ref_url = "https://example.com/demo_nanahoshi_ref.png"
        anchor_prompt = "Nanahoshi Shizuka, dark hair, school uniform over dark travel tunic"

        task_payload = {
            "mode": "text-to-image",
            "prompt": "Yusuke Murata manga style, Nanahoshi Shizuka standing in magic lab",
            "reference_image": ref_url,
            "reference_image_url": ref_url,
            "character_anchor": anchor_prompt,
            "parameters": {
                "aspect_ratio": "16:9",
                "resolution": "2K",
                "style_preset": "manga_murata_battle",
                "reference_image": ref_url,
                "character_anchor": anchor_prompt,
            },
        }

        resp = await client.post("/api/muse-bridge/tasks/create", json=task_payload)
        assert resp.status_code == 200, f"Create Muse task failed: {resp.text}"
        data = resp.json()
        task_id = data["task_id"]
        assert task_id.startswith("task_m_")

        # Kiểm tra chi tiết task qua GET /tasks/{task_id}
        get_resp = await client.get(f"/api/muse-bridge/tasks/{task_id}")
        assert get_resp.status_code == 200
        task_detail = get_resp.json()["task"]

        assert task_detail["reference_image"] == ref_url
        assert task_detail["reference_image_url"] == ref_url
        assert task_detail["character_anchor"] == anchor_prompt
        assert task_detail["parameters"]["style_preset"] == "manga_murata_battle"


@pytest.mark.asyncio
async def test_nanahoshi_scene_video_render_service(tmp_path):
    """
    E2E Test 5: Kiểm tra tích hợp Video Service (render_scene_video):
    - Dùng audio tiếng Việt Edge-TTS vừa tạo
    - Dùng ảnh tĩnh mẫu
    - Render scene video với hiệu ứng chuyển động Ken Burns 'zoom_in'
    - Đảm bảo video .mp4 được xuất bản thành công với FFmpeg.
    """
    scene_text = "Tên tôi là Nanahoshi. Nanahoshi Shizuka. Nữ sinh trung học đến từ thế giới khác."
    out_audio = tmp_path / "scene_voice.mp3"
    out_srt = tmp_path / "scene_voice.srt"
    out_video = tmp_path / "scene_rendered.mp4"

    # 1. Sinh Voice
    voice_res = await generate_speech(
        text=scene_text,
        voice="vi-VN-NamMinhNeural",
        output_audio_path=str(out_audio),
        output_srt_path=str(out_srt),
    )
    duration = voice_res["duration"]

    # 2. Tạo một ảnh test mẫu (hoặc dùng demo_images/scene_1.jpg nếu có)
    demo_image = BACKEND_DIR / "static" / "demo_images" / "scene_1.jpg"
    test_image_path = tmp_path / "scene_image.jpg"
    if demo_image.exists():
        test_image_path.write_bytes(demo_image.read_bytes())
    else:
        # Tạo ảnh đen trắng tối giản 1280x720
        from PIL import Image
        img = Image.new("RGB", (1280, 720), color=(25, 25, 35))
        img.save(test_image_path, "JPEG")

    # 3. Render video phân cảnh
    render_res = await render_scene_video(
        image_path=str(test_image_path),
        audio_path=str(out_audio),
        output_path=str(out_video),
        duration=duration,
        camera_motion="zoom_in",
        resolution="720p",
        fps=25,
    )

    assert out_video.exists(), "File video phân cảnh .mp4 không được tạo ra"
    assert out_video.stat().st_size > 10000, f"File video quá nhỏ: {out_video.stat().st_size} bytes"
    assert render_res["video_path"] == str(out_video)
    assert render_res["duration"] > 0
    assert render_res["motion"] == "zoom_in"
