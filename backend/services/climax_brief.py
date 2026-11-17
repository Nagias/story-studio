"""Bản giao việc nhiều bước cho Muse làm video một cảnh cao trào (khuôn trong code, không gọi LLM).

Đo thật 28/10/2026: gửi Muse từng prompt clip rồi lấy video đầu tiên thì 14/14 clip vẽ lại đầu tròn sau ~1 giây;
giao một việc nhiều bước (Muse tự tạo, tự trích khung kiểm, tự làm lại) với ảnh góc sau vẽ riêng cho đoạn quay lưng
thì đạt suốt 12 giây (`.cache/thu-muse-28-lan2/`). Thiết kế: docs/superpowers/specs/2026-10-28-video-cao-trao-giao-viec-muse-design.md.

Chia phần (chủ dự án chốt 18/11/2026): mỗi việc giao Muse tối đa AGENT_MAX_VIDEOS video. Mỗi clip 3–6 giây, cảnh dài
tới 24 giây cần khoảng 5 clip, không còn lượt làm lại: vụ Khang Cúc Hoa và Vương Nghĩa Tường có 18 báo cáo Muse "KHÔNG
ĐẠT" vì hết ngân sách. Nay lời kể dài hơn AGENT_PART_MAX_SEC chia thành các phần liền nhau theo ranh giới câu, mỗi phần
một việc (còn 2–3 lượt làm lại), phần sau nối từ khung cuối phần trước, cùng tài khoản và cùng chat.

Luật vẽ và luật chuyển động lấy từ services/prompt_rules.py (một nơi), không viết lại ở đây.
"""
from __future__ import annotations

import math
from typing import Optional

from models.schemas import Project, Scene
from services.character_sheets import CharacterSheet, hair_rule_for, hair_rule_line, look_text
from services.character_sheets import prompt_design as cs_prompt_design
from services.prompt_rules import FEMALE_HAIR_RULE_EN, is_round_head, video_rules_vi

AGENT_MAX_VIDEOS = 6        # giới hạn của Muse cho một yêu cầu (Muse tự khai 28/10/2026)
AGENT_MAX_IMAGES = 4
AGENT_PART_MAX_SEC = 15     # một việc giao Muse phủ tối đa chừng này giây lời kể (3–4 clip, còn 2–3 lượt làm lại)
AGENT_MIN_SECONDS = 5
PANEL_SECONDS = 5           # một ô storyboard ứng với ~5 giây lời kể (như climax_video.CLIP_SECONDS)
NEW_SCENE_IMAGE_TAG = "ANH_CANH_MOI"
AGENT_VIDEO_MODE = "agent-video"   # chế độ việc giao nhiều bước (Fleet Runner nhận ra theo tên này)
AGENT_REPLY_MAX_CHARS = 8000        # báo cáo của Muse giữ lại tối đa chừng này ký tự
BRIEF_MAX_CHARS = 7000      # bản giao việc dài hơn thì Muse dễ bỏ qua phần cuối (test chặn)


def target_seconds(narration_sec: float) -> int:
    """Độ dài video xin Muse cho MỘT phần: bằng lời kể của phần (làm tròn lên), ít nhất AGENT_MIN_SECONDS."""
    return max(AGENT_MIN_SECONDS, math.ceil(narration_sec - 1e-9))


def agent_parts(scene: Scene, seconds: float) -> list[dict]:
    """Các phần lời kể của cảnh, mỗi phần một việc Muse: [{index, text, start, end, seconds}]."""
    from services.dialogue_video import plan_segments   # nạp muộn: dialogue_video nạp location_sheets
    return plan_segments(scene.text or "", seconds, max_sec=AGENT_PART_MAX_SEC)


def part_panels(part: dict) -> tuple[int, int]:
    """(ô đầu, ô cuối) của storyboard ứng với phần lời kể, đánh số liền qua các lưới (lưới 2 bắt đầu ở ô 10)."""
    first = int(part["start"] // PANEL_SECONDS) + 1
    last = max(first, math.ceil(part["end"] / PANEL_SECONDS - 1e-9))
    return first, last


# ------------------------------------------------------------------------------------------------------------ khối chung
def _header() -> list[str]:
    return ["Làm video cho một cảnh của phần mềm của mình. Tự làm trọn từ đầu tới cuối trong yêu cầu này, không hỏi lại "
            f"giữa chừng. Ngân sách: tối đa {AGENT_MAX_VIDEOS} video và tối đa {AGENT_MAX_IMAGES} ảnh."]


def _narration_lines(scene: Scene, part: Optional[dict], n_parts: int, target: int) -> list[str]:
    whole = " ".join((scene.text or "").split())
    if not part or n_parts <= 1:
        return [f"Lời kể của cảnh (video cần dài khoảng {target} giây): \"{whole}\""]
    lines = [f"Cảnh này chia {n_parts} phần, mỗi phần một yêu cầu riêng nối tiếp nhau. Đây là PHẦN {part['index']}/{n_parts}.",
             f"Lời kể của ĐÚNG PHẦN NÀY (video cần dài khoảng {target} giây): \"{part['text']}\"",
             f"Toàn bộ lời kể của cảnh, để hiểu mạch (phần khác làm ở yêu cầu khác, đừng làm trước): \"{whole}\""]
    return lines


def _start_frame_line(part: Optional[dict], what: str) -> str:
    if part and part["index"] > 1:
        return ("- Ảnh 1 — KHUNG CUỐI CỦA PHẦN TRƯỚC (đã làm trong chat này): khung mở đầu của phần này, hành động tiếp "
                f"diễn từ đó; chuẩn về {what}.")
    return f"- Ảnh 1 — KHUNG CẢNH ĐÃ DUYỆT: khung mở đầu; chuẩn về {what}."


def _female_hair_lines(project: Project) -> list[str]:
    """Phong cách đầu tròn: quy tắc tóc cho MỌI nhân vật nữ trong cảnh, kể cả người chưa có bảng nhân vật (cảnh 41,
    29/10/2026: cô gái không có bảng nên ảnh cảnh vẫn đầu trọc mà bản giao việc không nhắc)."""
    if not is_round_head(project):
        return []
    return ["Quy tắc tóc trên áp cho mọi nhân vật nữ trong cảnh, kể cả người không có trong bảng diễn viên."]


def _cast_lines(project: Project, people: list[CharacterSheet]) -> list[str]:
    """Mỗi người một dòng: chỉ phần ngoại hình đã duyệt (không chép lại nét vẽ, luật đã có ở phần Luật), không cắt.
    Trước 18/11/2026 thiết kế chép cả đoạn phong cách cho từng người rồi cắt ở 1.500 ký tự: luật tóc mọi góc bị cắt cụt."""
    lines = []
    for p in people:
        lines.append(f"- {p.name_vi}: {look_text(cs_prompt_design(project, p.design_en))}")
        # look_text bỏ dòng nét vẽ (có câu quy tắc tóc của thiết kế mặc định): luôn ghi dòng "thắng" cho người nữ
        if hair_rule_for(project, p.entity_id):
            lines.append("  " + hair_rule_line("", FEMALE_HAIR_RULE_EN).replace(FEMALE_HAIR_RULE_EN,
                                                                                "the female hair rule below."))
    return lines


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
REJECT_RULE = ("Sau mỗi clip: trích khung mỗi giây và khung cuối, tự so với ảnh khởi đầu{board}. Loại nếu có bất kỳ khung "
               "nào: mặt người hay mặt anime, đầu nhỏ lại hoặc méo, nhân vật nữ mất tóc trên đỉnh đầu, đĩa trắng sau tóc, "
               "đổi quần áo, thêm người, đổi nét vẽ, cắt cảnh trong clip, máy quay lia hoặc zoom; hoặc so các khung cách "
               "nhau một giây mà người gần như đứng im. Đầu bắt đầu méo từ giây nào thì cắt bỏ từ giây đó, giữ phần trước "
               "(ít nhất 2 giây). Bị loại thì tạo lại (viết prompt khác, hành động ngắn hơn, góc trung hoặc xa khi cử động "
               "mạnh), trong ngân sách; không được sửa bằng cách bớt cử động.")


def _delivery(done_token: str, may_redraw: bool, target: int) -> list[str]:
    redraw = (f"- Nếu đã vẽ lại Ảnh 1: gửi kèm đúng một ảnh đó (cùng khung với Ảnh 1) và ghi một dòng "
              f"\"{NEW_SCENE_IMAGE_TAG}: có\"; không vẽ lại thì ghi \"{NEW_SCENE_IMAGE_TAG}: không\"." if may_redraw
              else f"- Ghi một dòng \"{NEW_SCENE_IMAGE_TAG}: không\".")
    return [
        f"Ghép các đoạn tốt nhất thành một video khoảng {target} giây, chỉnh màu các đoạn cho khớp nhau.",
        "",
        "GIAO KẾT QUẢ trong tin nhắn cuối (gửi file trong chat để mình tải về):",
        "- Đúng chỉ một video: video cuối đã ghép (16:9, càng nét càng tốt). Không gửi kèm clip nháp trong tin cuối.",
        redraw,
        "- Báo cáo ngắn: danh sách clip đã lập; tổng số video và ảnh đã tạo; mỗi video đạt hay bị loại ở khung nào, vì "
        "sao; kết quả cuối ĐẠT hay KHÔNG ĐẠT.",
        "",
        f"Dòng cuối cùng của tin nhắn cuối cùng ghi đúng nguyên văn: {done_token}",
    ]


# ------------------------------------------------------------------------------------------------------- ba loại cảnh
def landscape_brief(project: Project, scene: Scene, seconds: float, done_token: str, location_line: Optional[str],
                    has_plate: bool, part: Optional[dict] = None, n_parts: int = 1) -> str:
    """Cảnh vẽ không có nhân vật (phong cảnh, căn phòng, đồ vật): chuyển động đến từ vật trong cảnh, máy quay đứng yên,
    không thêm người. Chủ dự án 11/11/2026: cảnh phong cảnh được làm video và được tính vào tỉ lệ video Muse.
    Đính kèm: khung mở đầu, rồi ảnh chuẩn bối cảnh nếu nơi đó đã khoá."""
    target = target_seconds(part["seconds"] if part else seconds)
    attachments = [_start_frame_line(part, "bố cục, ánh sáng, nét vẽ 2D, màu sắc")]
    if has_plate:
        attachments.append("- Ảnh 2 — ẢNH CHUẨN CỦA BỐI CẢNH: nơi này phải giữ đúng kiến trúc, đồ vật cố định, màu sắc.")
    parts = [
        *_header(), "", "Ảnh đính kèm, theo thứ tự:", *attachments, "",
        *_narration_lines(scene, part, n_parts, target),
        f"Mô tả hình của cảnh: {' '.join((scene.image_prompt or '').split()) or '(xem Ảnh 1)'}",
        *([f"Nơi chốn cố định: {location_line}"] if location_line else []),
        "",
        "Cảnh này không có nhân vật.",
        "Luật bắt buộc:",
        *video_rules_vi(project, people=False),
        *AI_CLIPS_ONLY,
        "- Giữ đúng nét vẽ 2D, bố cục, màu sắc và ánh sáng của Ảnh 1 suốt video; không đổi sang ảnh thật.",
        "",
        "Các bước:",
        "1. Tự lập danh sách clip (mỗi clip một kiểu chuyển động rõ, dùng Ảnh 1 làm khung đầu). Ghi danh sách vào báo cáo.",
        "2. Làm từng clip. " + REJECT_RULE.format(board=""),
        "3. " + _delivery(done_token, False, target)[0],
        *_delivery(done_token, False, target)[1:],
    ]
    return "\n".join(parts)


def crowd_brief(project: Project, scene: Scene, seconds: float, done_token: str, location_line: Optional[str],
                has_plate: bool, part: Optional[dict] = None, n_parts: int = 1) -> str:
    """Cảnh vẽ có người nhưng không ai trong bảng nhân vật (cảnh sát, dân làng, quan toà không tên): giữ đúng những người
    trong ảnh cảnh, cử động thật; không lưới 9 ô, không bảng diễn viên. Gặp 13/11/2026: các cảnh này bị coi là phong cảnh
    và nhận bản giao việc "không có người" dù ảnh có người."""
    target = target_seconds(part["seconds"] if part else seconds)
    attachments = [_start_frame_line(part, "số người, dáng người, quần áo, bố cục, ánh sáng, nét vẽ 2D, màu sắc")]
    if has_plate:
        attachments.append("- Ảnh 2 — ẢNH CHUẨN CỦA BỐI CẢNH: nơi này phải giữ đúng kiến trúc, đồ vật cố định, màu sắc.")
    parts = [
        *_header(), "", "Ảnh đính kèm, theo thứ tự:", *attachments, "",
        *_narration_lines(scene, part, n_parts, target),
        f"Mô tả hình của cảnh: {' '.join((scene.image_prompt or '').split()) or '(xem Ảnh 1)'}",
        *([f"Nơi chốn cố định: {location_line}"] if location_line else []),
        "",
        "Những người trong cảnh là những người có trong Ảnh 1: giữ đúng số người, quần áo, màu sắc và dáng của họ như "
        "Ảnh 1 suốt video.",
        *_female_hair_lines(project),
        "",
        "Luật bắt buộc:",
        *video_rules_vi(project, people=True),
        *AI_CLIPS_ONLY,
        "- Không thêm người mới, không thêm con vật. Giữ đúng nét vẽ 2D, bố cục, màu sắc và ánh sáng của Ảnh 1; không "
        "đổi sang ảnh thật.",
        "",
        "Các bước:",
        "1. Tự lập danh sách clip (mỗi clip MỘT hành động đơn giản 3–6 giây, dùng Ảnh 1 hoặc khung cuối của clip trước "
        "làm khung đầu). Ghi danh sách vào báo cáo.",
        "2. Làm từng clip. " + REJECT_RULE.format(board=""),
        "3. " + _delivery(done_token, False, target)[0],
        *_delivery(done_token, False, target)[1:],
    ]
    return "\n".join(parts)


def scene_brief(project: Project, scene: Scene, people: list[CharacterSheet], grid_count: int, seconds: float,
                done_token: str, part: Optional[dict] = None, n_parts: int = 1,
                panels: Optional[tuple[int, int]] = None) -> str:
    """Bản giao việc tiếng Việt gửi nguyên văn cho Muse; đính kèm theo thứ tự: khung mở đầu (ảnh cảnh, hoặc khung cuối
    phần trước), bảng diễn viên, các lưới storyboard của phần này."""
    target = target_seconds(part["seconds"] if part else seconds)
    first_part = not part or part["index"] == 1
    attachments = [
        _start_frame_line(part, "bố cục, bối cảnh, ánh sáng, nét vẽ 2D, quần áo của cảnh"),
        "- Ảnh 2 — BẢNG DIỄN VIÊN: mỗi nhân vật của cảnh đủ các góc (trước, nghiêng, sau, đỉnh đầu). Đây là chuẩn của "
        "dáng đầu, mái tóc và quần áo ở mọi góc.",
    ]
    for g in range(1, grid_count + 1):
        attachments.append(f"- Ảnh {g + 2} — STORYBOARD 3x3 đã duyệt" + (f" (lưới {g}/{grid_count})" if grid_count > 1
                                                                         else "") + ", đọc trái sang phải, trên xuống dưới.")
    if panels:
        attachments.append(f"Phần này ứng với các ô storyboard {panels[0]}–{panels[1]} (đếm liền qua các lưới, lưới 2 bắt "
                           "đầu ở ô 10).")
    redraw = ("- Ảnh 1 khác Ảnh 2 ở dáng đầu hay mái tóc, hoặc có nhân vật nữ đầu trọc (tóc chỉ là một chỏm sau gáy), "
              "thì vẽ lại Ảnh 1 trước (giữ nguyên mọi thứ khác, chỉ sửa dáng đầu, mái tóc cho đúng), rồi dùng ảnh đã "
              "sửa làm khung đầu.")
    parts = [
        *_header(), "", "Ảnh đính kèm, theo thứ tự:", *attachments, "",
        *_narration_lines(scene, part, n_parts, target),
        "",
        "Nhân vật của cảnh (thiết kế đã duyệt, chỉ ngoại hình; nét vẽ theo Ảnh 1 và luật dưới):",
        *_cast_lines(project, people),
        "",
        "Luật bắt buộc (đo thật: video hỏng ở đúng các chỗ này):",
        *video_rules_vi(project, people=True),
        *_female_hair_lines(project),
        "- Đoạn nhân vật quay lưng phải bắt đầu từ một ảnh góc sau vẽ riêng (cùng nhân vật, cùng phong cách, chỉ thấy "
        "tóc phủ kín đầu, không chút màu trắng nào của đầu), dùng ảnh đó làm khung đầu của clip.",
        *AI_CLIPS_ONLY,
        *([redraw] if first_part else []),
        "",
        "Các bước:",
        "1. Tự lập danh sách clip từ lời kể và storyboard: ô nào góc trước/nghiêng, ô nào góc sau, mỗi clip làm gì, cắt "
        "giữa clip nào. Ghi danh sách clip đó vào báo cáo.",
        "2. Vẽ các ảnh khởi đầu cần thiết (ảnh góc sau" + (", ảnh cảnh đã sửa" if first_part else "") +
        ") và tự kiểm với Ảnh 2.",
        "3. Làm từng clip bằng Muse Video, mỗi clip MỘT hành động đơn giản dài 3–6 giây: đưa ô storyboard của lúc bắt "
        "đầu hành động làm khung ĐẦU và ô của lúc hành động xong làm khung CUỐI (ghi rõ trong prompt: ảnh thứ nhất là "
        "khung đầu, ảnh thứ hai là khung cuối), kèm câu khoá: giữ đầu, tóc, quần áo như Ảnh 2; clip sau nối từ khung "
        "cuối của clip trước (dùng resume_from_snapshot_id khi được). " + REJECT_RULE.format(board=" và Ảnh 2"),
        "4. " + _delivery(done_token, first_part, target)[0],
        *_delivery(done_token, first_part, target)[1:],
    ]
    return "\n".join(parts)
