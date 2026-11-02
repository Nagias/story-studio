"""Bản giao việc nhiều bước cho Muse làm video một cảnh cao trào (khuôn trong code, không gọi LLM).

Đo thật 28/10/2026: gửi Muse từng prompt clip rồi lấy video đầu tiên thì 14/14 clip vẽ lại đầu tròn sau ~1 giây;
giao một việc nhiều bước (Muse tự tạo, tự trích khung kiểm, tự làm lại) với ảnh góc sau vẽ riêng cho đoạn quay lưng
thì đạt suốt 12 giây (`.cache/thu-muse-28-lan2/`). Khung chữ dưới đây theo bản giao việc của lần đạt đó.
Thiết kế: docs/superpowers/specs/2026-10-28-video-cao-trao-giao-viec-muse-design.md.
"""
from __future__ import annotations

import math

from models.schemas import Project, Scene
from services.character_sheets import CharacterSheet, hair_rule_for
from services.image_service import FEMALE_HAIR_RULE_EN, ROUND_HEAD_STYLES

AGENT_MAX_VIDEOS = 6        # giới hạn của Muse cho một yêu cầu (Muse tự khai 28/10/2026)
AGENT_MAX_IMAGES = 4
AGENT_MAX_SECONDS = 24      # 6 video ~10 giây mà còn chừa lượt làm lại; lời kể dài hơn: giữ khung cuối khi dựng
AGENT_MIN_SECONDS = 5
DESIGN_MAX_CHARS = 1500       # thiết kế đã duyệt thật dài 920–1340 ký tự (đo 28/10/2026): giữ đủ phần quần áo, luật FIXED
NEW_SCENE_IMAGE_TAG = "ANH_CANH_MOI"
AGENT_VIDEO_MODE = "agent-video"   # chế độ việc giao nhiều bước (Fleet Runner nhận ra theo tên này)
AGENT_REPLY_MAX_CHARS = 8000        # báo cáo của Muse giữ lại tối đa chừng này ký tự


def target_seconds(narration_sec: float) -> int:
    """Độ dài video xin Muse: bằng lời kể (làm tròn lên), trong khoảng [5, 24] giây."""
    return max(AGENT_MIN_SECONDS, min(AGENT_MAX_SECONDS, math.ceil(narration_sec - 1e-9)))


def _attachment_lines(grid_count: int) -> list[str]:
    lines = [
        "- Ảnh 1 — KHUNG CẢNH ĐÃ DUYỆT: chuẩn về bố cục, bối cảnh, ánh sáng, nét vẽ 2D, quần áo của cảnh.",
        "- Ảnh 2 — BẢNG DIỄN VIÊN: mỗi nhân vật của cảnh đủ các góc (trước, nghiêng, sau, đỉnh đầu). Đây là chuẩn của "
        "dáng đầu, mái tóc và quần áo ở mọi góc.",
    ]
    for g in range(1, grid_count + 1):
        lines.append(f"- Ảnh {g + 2} — STORYBOARD 3x3 đã duyệt" + (f" (phần {g}/{grid_count} của lời kể)" if grid_count > 1 else "")
                     + ", đọc trái sang phải, trên xuống dưới.")
    return lines


def _cast_lines(project: Project, people: list[CharacterSheet]) -> list[str]:
    lines = []
    for p in people:
        rule = hair_rule_for(project, p.entity_id)
        # Câu quy tắc có thể nằm sẵn trong thiết kế (thiết kế mặc định chép phong cách vẽ), ở sau chỗ cắt: bỏ khỏi thiết
        # kế rồi luôn ghi một dòng riêng, để cắt bao nhiêu cũng không rơi mất (giám khảo 28/10/2026)
        design = p.design_en.replace(rule, " ") if rule else p.design_en
        lines.append(f"- {p.name_vi}: {' '.join(design.split())[:DESIGN_MAX_CHARS]}")
        if rule:
            lines.append("  This hair rule overrides any other hair placement in the design: "
                         "the female hair rule below.")
    return lines


def _female_hair_lines(project: Project) -> list[str]:
    """Phong cách đầu tròn: quy tắc tóc cho MỌI nhân vật nữ trong cảnh, kể cả người chưa có bảng nhân vật (cảnh 41,
    29/10/2026: cô gái không có bảng nên ảnh cảnh vẫn đầu trọc mà bản giao việc không nhắc)."""
    if project.style_preset not in ROUND_HEAD_STYLES:
        return []
    return ["", "Quy tắc tóc cho mọi nhân vật nữ trong cảnh, kể cả người không có trong bảng diễn viên: "
            f"{FEMALE_HAIR_RULE_EN}"]


def scene_brief(project: Project, scene: Scene, people: list[CharacterSheet], grid_count: int, seconds: float,
                done_token: str) -> str:
    """Bản giao việc tiếng Việt gửi nguyên văn cho Muse; đính kèm theo thứ tự: ảnh cảnh, bảng diễn viên, các lưới."""
    target = target_seconds(seconds)
    parts = [
        "Làm video cho một cảnh của phần mềm của mình. Tự làm trọn từ đầu tới cuối trong yêu cầu này, không hỏi lại "
        f"giữa chừng. Ngân sách: tối đa {AGENT_MAX_VIDEOS} video và tối đa {AGENT_MAX_IMAGES} ảnh.",
        "",
        "Ảnh đính kèm, theo thứ tự:",
        *_attachment_lines(grid_count),
        "",
        f"Lời kể của cảnh (video cần dài khoảng {target} giây): \"{scene.text.strip()}\"",
        "",
        "Nhân vật của cảnh (thiết kế đã duyệt):",
        *_cast_lines(project, people),
        *_female_hair_lines(project),
        "",
        "Mục tiêu (không cần hoàn hảo): phong cách đồng bộ từ đầu tới cuối. Nhân vật đầu tròn luôn là quả bóng tròn "
        "trắng RẤT TO, mặt trắng phẳng, hai chấm mắt và một nét miệng, KHÔNG BAO GIỜ thành mặt người hay mặt anime "
        "(không mũi, không mắt có tròng, không lông mi, không môi chi tiết). Được biểu cảm bằng nét đơn giản cùng kiểu "
        "vẽ: lông mày một nét nhíu hoặc nhướn, nước mắt, giọt mồ hôi, miệng há, nửa mặt tô xám khi sợ. Quần áo, màu sắc, "
        "bối cảnh giữ như ảnh đã duyệt. Nhân vật cử "
        "động ít hoặc chạy tại chỗ vẫn đạt; đổi sang mặt người thì không bao giờ đạt.",
        "",
        "Luật bắt buộc (đo thật: video hỏng ở đúng các chỗ này):",
        "- Tuyệt đối không clip nào được để nhân vật xoay người từ trước ra sau (hoặc từ sau ra trước): sau tóc sẽ mọc một đĩa "
        "trắng như vầng hào quang. Chỗ đổi hướng là một cú cắt cảnh giữa hai clip.",
        "- Đoạn nhân vật quay lưng phải bắt đầu từ một ảnh góc sau vẽ riêng (cùng nhân vật, cùng phong cách, chỉ thấy "
        "tóc phủ kín đầu, không chút màu trắng nào của đầu), dùng ảnh đó làm khung đầu của clip.",
        "- Máy quay đứng yên hoặc lia rất chậm; không zoom sát mặt.",
        "- Ảnh 1 khác Ảnh 2 ở dáng đầu hay mái tóc, hoặc có nhân vật nữ đầu trọc (tóc chỉ là một chỏm sau gáy), thì vẽ "
        "lại Ảnh 1 trước (giữ nguyên mọi thứ khác, chỉ sửa dáng đầu, mái tóc cho đúng), rồi dùng ảnh đã sửa làm khung "
        "đầu.",
        "",
        "Các bước:",
        "1. Tự lập danh sách clip từ lời kể và storyboard: ô nào góc trước/nghiêng, ô nào góc sau, mỗi clip làm gì, cắt "
        "cảnh ở đâu. Ghi danh sách clip đó vào báo cáo.",
        "2. Vẽ các ảnh khởi đầu cần thiết (ảnh cảnh đã sửa, ảnh góc sau) và tự kiểm với Ảnh 2.",
        "3. Làm từng clip từ ảnh khởi đầu của nó. Sau mỗi clip: trích khung mỗi giây và khung cuối, tự so với ảnh khởi "
        "đầu và Ảnh 2. Loại nếu có bất kỳ khung nào: mặt người hay mặt anime, đầu nhỏ lại hoặc méo, nhân vật nữ mất tóc "
        "trên đỉnh đầu, đĩa trắng sau tóc, đổi màu quần áo, thêm người, cắt cảnh trong clip. Bị loại thì tạo lại (viết "
        "prompt khác, giảm cử động), trong ngân sách.",
        f"4. Ghép các đoạn tốt nhất thành một video khoảng {target} giây, chỉnh màu các đoạn cho khớp nhau.",
        "",
        "GIAO KẾT QUẢ trong tin nhắn cuối (gửi file trong chat để mình tải về):",
        "- Đúng chỉ một video: video cuối đã ghép (16:9, càng nét càng tốt). Không gửi kèm clip nháp trong tin cuối.",
        f"- Nếu đã vẽ lại Ảnh 1: gửi kèm đúng một ảnh đó (cùng khung với Ảnh 1) và ghi một dòng "
        f"\"{NEW_SCENE_IMAGE_TAG}: có\"; không vẽ lại thì ghi \"{NEW_SCENE_IMAGE_TAG}: không\".",
        "- Báo cáo ngắn: danh sách clip đã lập; tổng số video và ảnh đã tạo; mỗi video đạt hay bị loại ở khung nào, vì "
        "sao; kết quả cuối ĐẠT hay KHÔNG ĐẠT theo mục tiêu trên.",
        "",
        f"Dòng cuối cùng của tin nhắn cuối cùng ghi đúng nguyên văn: {done_token}",
    ]
    return "\n".join(parts)
