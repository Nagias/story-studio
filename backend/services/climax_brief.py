"""Bản giao việc nhiều bước cho Muse làm video một cảnh cao trào (khuôn trong code, không gọi LLM).

Đo thật 28/10/2026: gửi Muse từng prompt clip rồi lấy video đầu tiên thì 14/14 clip vẽ lại đầu tròn sau ~1 giây;
giao một việc nhiều bước (Muse tự tạo, tự trích khung kiểm, tự làm lại) với ảnh góc sau vẽ riêng cho đoạn quay lưng
thì đạt suốt 12 giây (`.cache/thu-muse-28-lan2/`). Khung chữ dưới đây theo bản giao việc của lần đạt đó.
Thiết kế: docs/superpowers/specs/2026-10-28-video-cao-trao-giao-viec-muse-design.md.
"""
from __future__ import annotations

import math
from typing import Optional

from models.schemas import Project, Scene
from services.character_sheets import CharacterSheet, hair_rule_for
from services.character_sheets import prompt_design as cs_prompt_design
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
        design = cs_prompt_design(project, p.design_en)
        design = design.replace(rule, " ") if rule else design
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


ROUND_HEAD_GOAL = (
    "Mục tiêu (không cần hoàn hảo): phong cách đồng bộ từ đầu tới cuối. Nhân vật đầu tròn luôn là quả bóng tròn "
    "trắng RẤT TO, mặt trắng phẳng, hai chấm mắt và một nét miệng, KHÔNG BAO GIỜ thành mặt người hay mặt anime "
    "(không mũi, không mắt có tròng, không lông mi, không môi chi tiết). Được biểu cảm bằng nét đơn giản cùng kiểu "
    "vẽ: lông mày một nét nhíu hoặc nhướn, nước mắt, giọt mồ hôi, miệng há, nửa mặt tô xám khi sợ. Quần áo, màu sắc, "
    "bối cảnh giữ như ảnh đã duyệt. Đổi sang mặt người thì không bao giờ đạt. Người già, người gầy cũng chỉ là quả bóng "
    "tròn phẳng như vậy: tuổi thể hiện bằng tóc bạc, dáng người, quần áo; không nếp nhăn, không má hóp, không mũi, kể "
    "cả lúc khóc hay sợ (đo thật 13/11/2026: mặt ông già hay bị vẽ nhăn chi tiết đúng lúc khóc).")


# Thử thật 11/11/2026 (vụ xưởng sắt cảnh 7): clip AI méo đầu ở giây 3, Muse bỏ rồi TỰ DỰNG 3 clip bằng công cụ trên máy
# của nó từ ảnh tĩnh (máy quay di chuyển, đèn nhấp nháy, tối dần) và vẫn tự chấm ĐẠT ("thân người đứng yên").
AI_CLIPS_ONLY = (
    "- Mọi đoạn trong video cuối phải là video do công cụ tạo video AI (Muse Video) làm ra. CẤM tự dựng clip bằng "
    "Python, ffmpeg, PIL hay công cụ khác từ ảnh tĩnh (lia, zoom, đèn nhấp nháy, tối dần, ghép lớp, chuyển động máy "
    "quay giả): video như vậy là KHÔNG ĐẠT dù đẹp. ffmpeg chỉ được dùng để cắt bỏ phần hỏng, ghép các clip AI và chỉnh "
    "màu cho khớp.",
    "- Hết ngân sách mà không đủ clip AI đạt thì ghép những phần AI đạt được, video ngắn hơn cũng được, và báo KHÔNG "
    "ĐẠT ở phần thiếu; không lấp chỗ thiếu bằng ảnh tĩnh chuyển động.",
)


def landscape_brief(project: Project, scene: Scene, seconds: float, done_token: str,
                    location_line: Optional[str], has_plate: bool) -> str:
    """Bản giao việc cho cảnh vẽ không có nhân vật (phong cảnh, căn phòng, đồ vật): chuyển động đến từ vật trong cảnh, máy
    quay đứng yên, không thêm người. Chủ dự án 11/11/2026: cảnh phong cảnh được làm video và được tính vào tỉ lệ video
    Muse (services/video_share.py). Đính kèm: ảnh cảnh, rồi ảnh chuẩn bối cảnh nếu nơi đó đã khoá."""
    target = target_seconds(seconds)
    attachments = ["- Ảnh 1 — KHUNG CẢNH ĐÃ DUYỆT: khung hình mở đầu; chuẩn về bố cục, ánh sáng, nét vẽ 2D, màu sắc."]
    if has_plate:
        attachments.append("- Ảnh 2 — ẢNH CHUẨN CỦA BỐI CẢNH: nơi này phải giữ đúng kiến trúc, đồ vật cố định, màu sắc.")
    parts = [
        "Làm video cho một cảnh của phần mềm của mình. Tự làm trọn từ đầu tới cuối trong yêu cầu này, không hỏi lại "
        f"giữa chừng. Ngân sách: tối đa {AGENT_MAX_VIDEOS} video và tối đa {AGENT_MAX_IMAGES} ảnh.",
        "",
        "Ảnh đính kèm, theo thứ tự:",
        *attachments,
        "",
        f"Lời kể của cảnh (video cần dài khoảng {target} giây): \"{scene.text.strip()}\"",
        f"Mô tả hình của cảnh: {' '.join((scene.image_prompt or '').split()) or '(xem Ảnh 1)'}",
        *([f"Nơi chốn cố định: {location_line}"] if location_line else []),
        "",
        "Đây là VIDEO, không phải ảnh chuyển động: cảnh này không có nhân vật, nên chuyển động phải đến từ chính vật "
        "trong cảnh và hợp với lời kể (gió lay cây, cỏ, lá ngô; mưa rơi; khói, sương trôi; nước chảy, gợn; đèn chập "
        "chờn; cửa, rèm đung đưa; bụi bay). Chuyển động thấy rõ ở nhiều chỗ trong khung hình.",
        "",
        "Luật bắt buộc:",
        "- Máy quay đứng yên như đặt trên chân máy: không lia, không zoom. Chỉ máy quay lia/zoom trên một khung đứng "
        "im là KHÔNG ĐẠT.",
        "- Không thêm người, không thêm con vật, không thêm chữ, phụ đề, logo.",
        *AI_CLIPS_ONLY,
        "- Giữ đúng nét vẽ 2D, bố cục, màu sắc và ánh sáng của Ảnh 1 suốt video; không đổi sang ảnh thật.",
        "",
        "Các bước:",
        "1. Tự lập danh sách clip (mỗi clip một kiểu chuyển động rõ, dùng Ảnh 1 làm khung đầu). Ghi danh sách vào báo cáo.",
        "2. Làm từng clip. Sau mỗi clip: trích khung mỗi giây và khung cuối, tự so với Ảnh 1. Loại nếu: so các khung "
        "cách nhau một giây mà gần như không có gì chuyển động; chỉ có máy quay lia/zoom; có người, con vật hay chữ "
        "xuất hiện; đổi nét vẽ, đổi màu, đổi nơi chốn. Bị loại thì tạo lại (viết prompt khác, chuyển động rõ hơn), "
        "trong ngân sách.",
        f"3. Ghép các đoạn tốt nhất thành một video khoảng {target} giây.",
        "",
        "GIAO KẾT QUẢ trong tin nhắn cuối (gửi file trong chat để mình tải về):",
        "- Đúng chỉ một video: video cuối đã ghép (16:9, càng nét càng tốt). Không gửi kèm clip nháp trong tin cuối.",
        f"- Ghi một dòng \"{NEW_SCENE_IMAGE_TAG}: không\".",
        "- Báo cáo ngắn: danh sách clip đã lập; tổng số video và ảnh đã tạo; mỗi video đạt hay bị loại ở khung nào, vì "
        "sao; kết quả cuối ĐẠT hay KHÔNG ĐẠT.",
        "",
        f"Dòng cuối cùng của tin nhắn cuối cùng ghi đúng nguyên văn: {done_token}",
    ]
    return "\n".join(parts)


def crowd_brief(project: Project, scene: Scene, seconds: float, done_token: str,
                location_line: Optional[str], has_plate: bool) -> str:
    """Bản giao việc cho cảnh vẽ có người nhưng không ai trong bảng nhân vật (cảnh sát, dân làng, quan toà không tên):
    giữ đúng những người trong ảnh cảnh, đầu tròn, cử động thật; không lưới 9 ô, không bảng diễn viên. Gặp 13/11/2026:
    các cảnh này bị coi là phong cảnh và nhận bản giao việc "không có người, không thêm người" dù ảnh có người."""
    target = target_seconds(seconds)
    attachments = ["- Ảnh 1 — KHUNG CẢNH ĐÃ DUYỆT: khung hình mở đầu; chuẩn về số người, dáng người, quần áo, bố cục, "
                   "ánh sáng, nét vẽ 2D, màu sắc."]
    if has_plate:
        attachments.append("- Ảnh 2 — ẢNH CHUẨN CỦA BỐI CẢNH: nơi này phải giữ đúng kiến trúc, đồ vật cố định, màu sắc.")
    parts = [
        "Làm video cho một cảnh của phần mềm của mình. Tự làm trọn từ đầu tới cuối trong yêu cầu này, không hỏi lại "
        f"giữa chừng. Ngân sách: tối đa {AGENT_MAX_VIDEOS} video và tối đa {AGENT_MAX_IMAGES} ảnh.",
        "",
        "Ảnh đính kèm, theo thứ tự:",
        *attachments,
        "",
        f"Lời kể của cảnh (video cần dài khoảng {target} giây): \"{scene.text.strip()}\"",
        f"Mô tả hình của cảnh: {' '.join((scene.image_prompt or '').split()) or '(xem Ảnh 1)'}",
        *([f"Nơi chốn cố định: {location_line}"] if location_line else []),
        *_female_hair_lines(project),
        "",
        "Những người trong cảnh là những người có trong Ảnh 1: giữ đúng số người, quần áo, màu sắc và dáng của họ như "
        "Ảnh 1 suốt video.",
        ROUND_HEAD_GOAL,
        "",
        "Đây là VIDEO, không phải ảnh chuyển động: người trong cảnh phải làm hành động hợp lời kể bằng cơ thể (đi, bước "
        "tới, quay đầu, cúi xuống, giơ tay, chỉ tay, cầm nắm đồ vật, run rẩy), thấy rõ trong khung hình; vật trong cảnh "
        "cũng có thể chuyển động (gió, mưa, khói, đèn). Chỉ đổi nét mặt, chỉ chớp mắt, hay chỉ máy quay lia/zoom trên một "
        "khung đứng im đều KHÔNG ĐẠT.",
        "",
        "Luật bắt buộc:",
        "- Máy quay đứng yên như đặt trên chân máy: không lia, không zoom.",
        "- Không clip nào để người xoay từ trước ra sau (hoặc từ sau ra trước): sau tóc sẽ mọc một đĩa trắng.",
        "- Không thêm người mới, không thêm con vật, không thêm chữ, phụ đề, logo.",
        *AI_CLIPS_ONLY,
        "- Giữ đúng nét vẽ 2D, bố cục, màu sắc và ánh sáng của Ảnh 1 suốt video; không đổi sang ảnh thật.",
        "",
        "Các bước:",
        "1. Tự lập danh sách clip (mỗi clip MỘT hành động đơn giản 3–6 giây, dùng Ảnh 1 hoặc khung cuối của clip trước "
        "làm khung đầu). Ghi danh sách vào báo cáo.",
        "2. Làm từng clip. Sau mỗi clip: trích khung mỗi giây và khung cuối, tự so với Ảnh 1. Loại nếu có bất kỳ khung "
        "nào: mặt người hay mặt anime, đầu nhỏ lại hoặc méo, đĩa trắng sau tóc, đổi quần áo, thêm người, đổi nét vẽ, cắt "
        "cảnh trong clip; hoặc so các khung cách nhau một giây mà người gần như đứng im. Đầu bắt đầu méo từ giây nào thì "
        "cắt bỏ từ giây đó, giữ phần trước (ít nhất 2 giây). Bị loại thì tạo lại (prompt khác, hành động ngắn hơn), "
        "trong ngân sách; không được sửa bằng cách bớt cử động.",
        f"3. Ghép các đoạn tốt nhất thành một video khoảng {target} giây, chỉnh màu các đoạn cho khớp nhau.",
        "",
        "GIAO KẾT QUẢ trong tin nhắn cuối (gửi file trong chat để mình tải về):",
        "- Đúng chỉ một video: video cuối đã ghép (16:9, càng nét càng tốt). Không gửi kèm clip nháp trong tin cuối.",
        f"- Ghi một dòng \"{NEW_SCENE_IMAGE_TAG}: không\".",
        "- Báo cáo ngắn: danh sách clip đã lập; tổng số video và ảnh đã tạo; mỗi video đạt hay bị loại ở khung nào, vì "
        "sao; kết quả cuối ĐẠT hay KHÔNG ĐẠT.",
        "",
        f"Dòng cuối cùng của tin nhắn cuối cùng ghi đúng nguyên văn: {done_token}",
    ]
    return "\n".join(parts)


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
        ROUND_HEAD_GOAL,
        "",
        # 11/11/2026: câu cũ "nhân vật cử động ít hoặc chạy tại chỗ vẫn đạt" + "bị loại thì giảm cử động" làm 34/38 clip
        # vụ xưởng sắt gần như đứng hình (chủ dự án 10/11: "phải di chuyển bình thường chứ, đây là ảnh chuyển động rồi").
        # Thử 10/11: ép cử động + khoá máy quay vẫn giữ đầu tròn (cảnh 20).
        "Đây là VIDEO, không phải ảnh chuyển động: mỗi clip nhân vật phải làm đúng hành động trong lời kể bằng cơ thể "
        "(đi, bước vào, quay đầu, cúi xuống, ngồi xuống, giơ tay, cầm nắm đồ vật, ôm mặt khóc, run rẩy), thấy rõ trong "
        "khung hình. Chỉ đổi nét mặt, chỉ chớp mắt, hay chỉ máy quay lia/zoom trên một khung đứng im đều KHÔNG ĐẠT.",
        "",
        "Luật bắt buộc (đo thật: video hỏng ở đúng các chỗ này):",
        "- Tuyệt đối không clip nào được để nhân vật xoay người từ trước ra sau (hoặc từ sau ra trước): sau tóc sẽ mọc một đĩa "
        "trắng như vầng hào quang. Chỗ đổi hướng là một cú cắt cảnh giữa hai clip.",
        "- Đoạn nhân vật quay lưng phải bắt đầu từ một ảnh góc sau vẽ riêng (cùng nhân vật, cùng phong cách, chỉ thấy "
        "tóc phủ kín đầu, không chút màu trắng nào của đầu), dùng ảnh đó làm khung đầu của clip.",
        "- Máy quay đứng yên như đặt trên chân máy: không lia, không zoom; chuyển động đến từ nhân vật và vật trong cảnh.",
        *AI_CLIPS_ONLY,
        "- Ảnh 1 khác Ảnh 2 ở dáng đầu hay mái tóc, hoặc có nhân vật nữ đầu trọc (tóc chỉ là một chỏm sau gáy), thì vẽ "
        "lại Ảnh 1 trước (giữ nguyên mọi thứ khác, chỉ sửa dáng đầu, mái tóc cho đúng), rồi dùng ảnh đã sửa làm khung "
        "đầu.",
        "",
        "Các bước:",
        "1. Tự lập danh sách clip từ lời kể và storyboard: ô nào góc trước/nghiêng, ô nào góc sau, mỗi clip làm gì, cắt "
        "cảnh ở đâu. Ghi danh sách clip đó vào báo cáo.",
        "2. Vẽ các ảnh khởi đầu cần thiết (ảnh cảnh đã sửa, ảnh góc sau) và tự kiểm với Ảnh 2.",
        "3. Làm từng clip bằng Muse Video, mỗi clip MỘT hành động đơn giản dài 3–6 giây: đưa ô storyboard của lúc bắt "
        "đầu hành động làm khung ĐẦU và ô của lúc hành động xong làm khung CUỐI (ghi rõ trong prompt: ảnh thứ nhất là "
        "khung đầu, ảnh thứ hai là khung cuối), kèm câu khoá: giữ đầu tròn trắng to, chấm mắt, tóc, quần áo như Ảnh 2; "
        "clip sau nối từ khung cuối của clip trước (dùng resume_from_snapshot_id khi được). Đầu bắt đầu méo từ giây nào "
        "thì cắt bỏ từ giây đó, giữ phần trước (ít nhất 2 giây) rồi làm clip tiếp từ khung cuối của phần giữ. Sau mỗi clip: trích khung mỗi giây và khung cuối, tự so với ảnh khởi "
        "đầu và Ảnh 2. Loại nếu có bất kỳ khung nào: mặt người hay mặt anime, đầu nhỏ lại hoặc méo, nhân vật nữ mất tóc "
        "trên đỉnh đầu, đĩa trắng sau tóc, đổi màu quần áo, thêm người, cắt cảnh trong clip; hoặc so các khung cách "
        "nhau một giây mà nhân vật gần như đứng im. Bị loại thì tạo lại (viết prompt khác, chia hành động thành clip "
        "ngắn hơn, mỗi clip một hành động rõ), trong ngân sách; không được sửa bằng cách bớt cử động.",
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
