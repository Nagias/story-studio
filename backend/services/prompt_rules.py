"""Luật vẽ và luật chuyển động gửi Muse: mỗi luật viết ĐÚNG MỘT LẦN ở đây. Ảnh cảnh, bảng nhân vật, lưới 9 khung, video
theo lời thoại và bản giao việc cao trào đều lấy luật từ file này, không tự viết lại câu của mình.

Vì sao (rà soát 17–18/11/2026, dựng lại prompt thật của vụ Khang Cúc Hoa): luật đầu tròn có bốn bản khác chữ, cùng một
prompt video vừa bảo "máy quay đứng yên" vừa bảo "đổi góc máy", lưới 9 khung dặn "cử động nhẹ, không cắt cảnh" trong khi
bản giao việc đòi "cử động mạnh, cắt giữa hai clip", video thoại tính "đổi nét mặt" là cử động còn video cao trào thì
không. Muse phải tự chọn nghe câu nào, nên mỗi lần sửa một lỗi lại sinh lỗi khác. Test `tests/test_prompt_rules.py` dựng
prompt cuối của các đường và chặn cặp luật cãi nhau.

Chủ dự án chốt 18/11/2026: khi nhân vật cử động mạnh thì quay góc trung hoặc xa (mặt nhỏ trong khung, Muse ít vẽ lệch
mặt); cận mặt chỉ cho biểu cảm, cử động nhẹ. Vẫn giữ mục tiêu 50% video có cử động.
"""
from typing import Optional

# Phong cách nhân vật đầu tròn (kiểu kênh "Thế Giới Kì Quái", chủ dự án 26/10/2026)
ROUND_HEAD_STYLES = ("horror_cartoon_2d",)

# Chủ dự án 29/10/2026 (câu 12 mục 1.2): được biểu cảm như video mẫu. Đo 13/11/2026: mặt ông già hay bị vẽ nhăn chi tiết
# đúng lúc khóc, nên tuổi chỉ thể hiện bằng tóc, dáng, quần áo.
ROUND_HEAD_RULE_EN = (
    "Round-head characters: the head is always a big flat round white ball with two dot eyes and a line mouth, never "
    "a realistic human face and never an anime face (no nose, no irises, no eyelashes, no detailed lips, no wrinkles, "
    "no hollow cheeks). Expressions use simple flat lines: short line eyebrows that frown or rise, tears, sweat drops, "
    "an open or trembling mouth, and half of the round white face shaded grey when afraid. Age is shown only by hair "
    "colour, body shape and clothes, even when crying."
)
# Chủ dự án 28/10/2026: tóc nhân vật nữ "phủ nhiều trên đầu thay vì chỉ có chút tóc ở phần gáy"
FEMALE_HAIR_RULE_EN = (
    "Female characters always have thick, full hair covering most of the top of the head: a generous mass of hair on "
    "the crown that frames the white face, then falls to the length given in the design; never a bald round head with "
    "only a little hair at the nape."
)
# Bảng nhân vật: thiết kế giữ nguyên ở mọi góc (tóc lúc phủ lúc trọc giữa các góc là lỗi hay gặp nhất)
ANGLE_RULE_EN = (
    "The head shape, face, hairstyle, clothes, shoes and colours described above are FIXED: draw them identically in "
    "every view. Decide once exactly where the hair grows on the head (hairline, top of the head, parting, length) and "
    "keep that exactly the same from the front, the sides, the back and the top: the hair must never cover the head in "
    "one view and leave it bare in another."
)
NO_TEXT_EN = "No text, no subtitles, no captions, no logo, no watermark."
NO_TEXT_VI = "- Không chữ, không phụ đề, không logo, không máu, không vết thương."

# Gặp 10/11/2026 (vụ xưởng sắt): 48 clip chỉ có máy quay lia/zoom ảnh tĩnh. Máy quay đứng yên trong mỗi clip; đổi nơi
# hay đổi góc nhìn là một cú cắt sang clip/video sau, không bao giờ bằng chuyển động máy quay.
LOCKED_CAMERA_EN = ("locked-off static camera on a tripod: no pan, no zoom, no dolly, no camera shake; all motion comes "
                    "from the characters and things inside the scene")
CAMERA_VI = ("- MÁY QUAY ĐỨNG YÊN suốt mỗi clip: không lia, không zoom, không trượt máy; đổi nơi hay đổi góc nhìn là một "
             "cú cắt sang clip sau. Clip chỉ có máy quay lia hoặc zoom trên khung đứng im là KHÔNG ĐẠT.")
MOTION_VI = ("- CHUYỂN ĐỘNG THẬT: người trong cảnh làm đúng hành động của lời kể bằng cơ thể (đi, quay đầu, cúi xuống, "
             "ngồi, giơ tay, cầm nắm đồ vật, ôm mặt khóc, run rẩy), thấy rõ trong khung. Chỉ đổi nét mặt hay chỉ chớp mắt "
             "là KHÔNG ĐẠT.")
SCENERY_MOTION_VI = ("- CHUYỂN ĐỘNG THẬT: cảnh không có người nên chuyển động đến từ chính vật trong cảnh và hợp với lời "
                     "kể (gió lay cây, cỏ, lá; mưa rơi; khói, sương trôi; nước chảy; đèn chập chờn; cửa, rèm đung đưa; "
                     "bụi bay), thấy rõ ở nhiều chỗ trong khung hình. Không thêm người, không thêm con vật.")
SHOT_SIZE_VI = ("- GÓC MÁY THEO CỬ ĐỘNG: hành động lớn (đi, chạy, cúi, ngồi, giơ tay) quay góc trung hoặc xa, thấy cả "
                "người, mặt nhỏ trong khung; cận mặt chỉ cho biểu cảm, khi đó người chỉ cử động nhẹ.")
NO_TURN_VI = ("- Không clip nào để người xoay từ trước ra sau hoặc ngược lại (sau tóc sẽ mọc đĩa trắng): đổi hướng là "
              "một cú cắt giữa hai clip.")
# Cùng ý cho prompt tiếng Anh (lưới 9 khung)
MOTION_EN = ("The characters' body action follows the narration and progresses clearly from panel to panel (walking, "
             "turning the head, bending down, sitting, raising or pointing a hand, holding objects, trembling); "
             "expressions go with the action. Big body actions are shown in medium or wide shots with the whole body "
             "visible; close-ups only for expressions with small movement.")


def is_round_head(project_or_style) -> bool:
    style = getattr(project_or_style, "style_preset", project_or_style)
    return style in ROUND_HEAD_STYLES


def round_head_rules_en(project_or_style) -> list[str]:
    """Luật đầu tròn và tóc nữ (tiếng Anh) nếu dự án dùng phong cách đầu tròn; không thì rỗng."""
    return [ROUND_HEAD_RULE_EN, FEMALE_HAIR_RULE_EN] if is_round_head(project_or_style) else []


def reject_faults_vi(project_or_style) -> str:
    """Lỗi hình làm một clip bị loại, theo phong cách. Rà soát 18/11/2026: bản giao việc cao trào ghi cứng lỗi của kiểu
    đầu tròn ("mặt người hay mặt anime", "đĩa trắng sau tóc") cho MỌI phong cách: với phong cách ảnh thật, Muse sẽ loại
    mọi clip vì nhân vật nào cũng có mặt người."""
    if is_round_head(project_or_style):
        return ("mặt người hay mặt anime, đầu nhỏ lại hoặc méo, nhân vật nữ mất tóc trên đỉnh đầu, đĩa trắng sau tóc, "
                "đổi quần áo")
    return "gương mặt, kiểu tóc, vóc dáng hay quần áo của nhân vật khác ảnh chuẩn, mặt hoặc tay méo, đổi phong cách vẽ"


def back_view_rule_vi(project_or_style) -> list[str]:
    """Đoạn quay lưng: chỉ kiểu đầu tròn cần ảnh góc sau vẽ riêng (đầu trắng lộ ra sau tóc thành đĩa trắng)."""
    if not is_round_head(project_or_style):
        return []
    return ["- Đoạn nhân vật quay lưng phải bắt đầu từ một ảnh góc sau vẽ riêng (cùng nhân vật, cùng phong cách, chỉ thấy "
            "tóc phủ kín đầu, không chút màu trắng nào của đầu), dùng ảnh đó làm khung đầu của clip."]


def video_rules_vi(project_or_style, people: bool = True) -> list[str]:
    """Luật của mọi việc làm video gửi Muse (video theo lời thoại, bản giao việc cao trào), theo đúng thứ tự này."""
    rules = [MOTION_VI, SHOT_SIZE_VI] if people else [SCENERY_MOTION_VI]
    rules.append(CAMERA_VI)
    if people and is_round_head(project_or_style):
        rules.append(NO_TURN_VI)
    rules += [f"- {r}" for r in round_head_rules_en(project_or_style) if people]
    rules.append(NO_TEXT_VI)
    return rules


def negative_for(style_id: Optional[str]) -> str:
    """Danh sách cấm của phong cách (trước đây viết sẵn trong STYLE_PRESETS mà không bao giờ gửi đi)."""
    from services.image_service import STYLE_PRESETS   # nạp muộn: image_service nặng
    return str((STYLE_PRESETS.get(style_id or "") or {}).get("negative_prompt") or "")
