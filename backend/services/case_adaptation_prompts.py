"""
Prompt LLM cho luồng chuyển thể vụ án thật thành truyện song ngữ Việt/Anh (spec mục 6, 7.1a–7.4, 7.10).

- SYSTEM_PROMPT dùng chung cho mọi việc nhỏ.
- Mỗi hàm *_prompt trả user prompt cho đúng một việc. Dòng đầu luôn là marker "TASK: <TÊN>" (LLM giả trong test
  đọc dòng này để chọn fixture). Câu chữ tiếng Việt; khoá JSON tiếng Anh, khớp với phần kiểm ở case_adaptation_steps.
- Mỗi prompt nói rõ kích thước đầu ra mong đợi (số sự việc, số cảnh, số từ), vì model hay lười và tóm gọn.
- G5–G6 (dàn ý, viết cảnh): tóm tắt sự việc và mô tả bằng chứng đã được thay sang tên hư cấu trước khi gửi;
  riêng đoạn gốc giữ nguyên văn (có tên thật) để model bám đúng sự thật, kèm bảng tên thật → tên hư cấu.
- Lời Việt của một nhịp thấy cả câu chuyện: logline, dàn ý mọi nhịp (đánh dấu nhịp đang viết) và nhân vật đã xuất hiện
  ở các nhịp trước, để cài cắm, trả lời và không giới thiệu lại nhân vật.
"""
import math
import re
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from models.case_adaptation_schemas import (
    MAX_BOARD_RATIO,
    QUESTION_EVERY_PARTS,
    CaseBible,
    CaseEntity,
    StoryPart,
    TimelineEvent,
)
from services.case_adaptation_checks import (
    EN_WORDS_PER_MINUTE,
    GENERIC_TERMS,
    VI_WORDS_PER_MINUTE,
    apply_aliases,
    build_forbidden_names,
)
from services.video_service import CAMERA_MOTIONS

# Ngưỡng kiểm của bước đọc đoạn (spec 7.2). case_adaptation_steps dùng lại đúng các số này.
EVENT_RULE_MIN_WORDS = 150   # đoạn từ 150 từ trở lên mới bị kiểm số sự việc
WORDS_PER_EVENT = 250        # ít nhất 1 sự việc cho mỗi 250 từ
MIN_EVENT_WORDS = 12         # mỗi tóm tắt sự việc dài ít nhất 12 từ
_EXPECTED_WORDS_PER_EVENT = 70  # mức mong đợi nói với model (chặt hơn ngưỡng loại)

ROLES = ("victim", "suspect", "perpetrator", "witness", "investigator", "family", "other")
RELATION_TYPES = (
    "motive", "alibi_contradiction", "blood_match", "call_log", "witness_seen", "suspect_link", "causal", "timeline",
)

# Ngưỡng kiểm của dàn ý và các việc viết cảnh (spec 7.3, 7.4). case_adaptation_steps dùng lại đúng các số này.
SCENES_PER_PART = (2, 6)        # số cảnh mỗi nhịp
MAX_SCENE_OVERSHOOT = 1.2       # tổng số cảnh (kể cả cảnh miễn trừ) không vượt mục tiêu tối đa quá 20%
MAX_EVENTS_PER_SCENE = 3        # mỗi cảnh kể tối đa 3 sự việc (nhiều hơn là tóm gọn)
MAX_SCENES_PER_EVENT = 2        # một sự việc đủ cho tối đa 2 cảnh (nhiều hơn là kéo dài cho đủ)
SCENES_PER_MINUTE = 4           # trung bình khoảng 15 giây mỗi cảnh
MAX_DROPPED_SHARE = 1 / 3       # dàn ý bỏ tối đa 1/3 số sự việc (chi tiết vụn) để kể gọn và cuốn
MAX_DEDUPE_SHARE = 0.5          # bước lọc trùng gộp tối đa một nửa số sự việc (nhiều hơn là gộp nhầm)
# Số chữ mỗi cảnh tính từ số giây mỗi cảnh của thời lượng đã chọn (word_budget, theo VI_WORDS_PER_MINUTE /
# EN_WORDS_PER_MINUTE đo thật, khai báo ở case_adaptation_checks), để video ra đúng số phút: trước đây giới hạn cố định
# 80 chữ nên model viết trung bình 72 chữ Việt mỗi cảnh, video 8 phút ra 13–14,5 phút.
MIN_IMAGE_PROMPT_WORDS = 20
MIN_VIDEO_PROMPT_WORDS = 8
PART_KINDS = ("hook", "setup", "discovery", "investigation", "twist", "resolution", "open_questions", "epilogue")
VISUAL_KINDS = ("image", "video", "board")
NARRATIVE_BEATS = ("hook", "setting", "escalation", "climax", "resolution")
BGM_ENERGIES = ("ambient_low", "tension_buildup", "dramatic_climax")
DEFAULT_SCENE_SECONDS = 60 / SCENES_PER_MINUTE   # 15 giây, khi không biết thời lượng video (viết lại lời Anh lẻ)


@dataclass(frozen=True)
class WordBudget:
    """Số từ lời kể của một cảnh. `*_aim`: khoảng nói với model (cảnh thường / cảnh video); `*_limit`: khoảng nhận,
    ngoài khoảng này thì bị loại. Số phút người dùng chọn là MỨC TỐI THIỂU (CLAUDE.md mục 1: "Mức tối thiểu là 15 phút"):
    model được dặn viết 100–110% số từ đúng thời lượng. Trước 26/10/2026 dặn 75–95% để không vượt: chọn 20 phút ra 18:27."""
    seconds: float
    vi_aim: tuple[int, int]
    vi_video_aim: tuple[int, int]
    vi_limit: tuple[int, int]
    en_aim: tuple[int, int]
    en_video_aim: tuple[int, int]
    en_limit: tuple[int, int]


def word_budget(seconds_per_scene: float = DEFAULT_SCENE_SECONDS) -> WordBudget:
    """Số từ mỗi cảnh để lời đọc dài khoảng `seconds_per_scene` giây (theo tốc độ đọc đã đo của từng ngôn ngữ)."""
    def ranges(words_per_minute: int) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
        mid = seconds_per_scene * words_per_minute / 60
        return ((math.ceil(mid), round(mid * 1.1)), (round(mid * 0.6), round(mid * 0.7)),  # ceil: không nhắm ngắn hơn
                (round(mid * 0.45), round(mid * 1.25)))

    vi_aim, vi_video_aim, vi_limit = ranges(VI_WORDS_PER_MINUTE)
    en_aim, en_video_aim, en_limit = ranges(EN_WORDS_PER_MINUTE)
    return WordBudget(seconds_per_scene, vi_aim, vi_video_aim, vi_limit, en_aim, en_video_aim, en_limit)


def max_boards_in_part(scene_count: int) -> int:
    """Số cảnh bảng ghim tối đa của một nhịp có `scene_count` cảnh."""
    return max(1, round(scene_count * MAX_BOARD_RATIO))


def asks_question(part: StoryPart, outline_parts: Sequence[StoryPart]) -> bool:
    """Nhịp này kết bằng câu hỏi bỏ ngỏ: nhịp đầu và nhịp thứ QUESTION_EVERY_PARTS, 2×..., trừ nhịp cuối video."""
    ids = [p.id for p in outline_parts]
    if part.id not in ids or next_part_of(part, outline_parts) is None:
        return False
    position = ids.index(part.id) + 1
    return position == 1 or position % QUESTION_EVERY_PARTS == 0


def _span(pair: tuple[int, int]) -> str:
    return f"{pair[0]}–{pair[1]}"

_KIND_HINTS = {
    "hook": "mở đầu gây tò mò: hé lộ khoảnh khắc bí ẩn hoặc đáng sợ nhất; không tiết lộ hung thủ hay kết cục",
    "setup": "bối cảnh: nơi chốn, con người, cuộc sống và các mối quan hệ trước khi vụ án xảy ra",
    "discovery": "phát hiện vụ án: ai phát hiện, phát hiện ra sao, hiện trường lúc đó thế nào",
    "investigation": "điều tra: từng bước điều tra, lời khai, giám định, manh mối, nghi vấn",
    "twist": "bước ngoặt: phát hiện làm đổi hướng điều tra",
    "resolution": "phá án: hung thủ bị xác định, bắt giữ, xét xử, đúng như bài viết",
    "open_questions": "những câu hỏi còn bỏ ngỏ: vụ án chưa có lời giải, các giả thuyết và điều còn bí ẩn, đúng như bài viết",
    "epilogue": "kết và dư âm: hệ quả, những người ở lại, điều vụ án để lại",
}
_TEASER_MARK = ("[CHỈ GỢI: sự việc của nhịp sau; chỉ hé lộ bằng một câu hỏi, một hình ảnh hoặc một chi tiết chưa "
                "có lời giải, không kể trọn]")
_TEASED_MARK = "[đã được hé lộ ở đoạn mở đầu: giờ kể đầy đủ, không lặp lại câu mở đầu]"
_TONE_RULE_VI = ("Giọng tôn trọng nạn nhân, điện ảnh, không kiểu báo lá cải: không dùng từ giật gân hay ghê rợn "
                 "(ví dụ \"ghê rợn\", \"rùng rợn\", \"máu me\", \"man rợ\", \"dã man\"), không tả máu hay vết thương chi tiết.")
_TONE_RULE_EN = ("Giọng tôn trọng nạn nhân, điện ảnh, không kiểu báo lá cải: không dùng từ giật gân hay ghê rợn "
                 "(ví dụ \"gruesome\", \"grisly\", \"horrific\", \"bloody\", \"brutal slaying\"), không tả máu hay vết thương chi tiết.")
_ID_NUMBER_RULE_VI = ("Không giữ con số nhận dạng của bài: số nhà, biển số xe, số điện thoại, số giấy tờ, số hồ sơ, số phòng, "
                      "số hiệu container... Nói chung chung (\"số 88 đường ...\" → \"một căn nhà trên con phố gần cảng\"; "
                      "\"gọi đến số ...\" → \"gọi điện báo cảnh sát\"). Mã số giả trong bảng tên chỉ dùng khi chính con số "
                      "là bằng chứng (ví dụ biển số bị camera ghi lại). Giờ trong ngày và tuổi thì giữ.")
_ID_NUMBER_RULE_EN = ("Không giữ con số nhận dạng của bài: số nhà, biển số xe, số điện thoại, số giấy tờ, số hồ sơ, số phòng... "
                      "Nói chung chung (\"88 ... Street\" → \"a house on a street near the port\"; \"dialed 09...\" → "
                      "\"called the police\"). Mã số giả trong bảng tên chỉ dùng khi chính con số là bằng chứng. "
                      "Giờ trong ngày và tuổi thì giữ.")
_KIND_LABELS = {
    "person": "người", "place": "địa danh", "organization": "tổ chức", "identifier": "mã số",
}
_ROLE_LABELS = {
    "victim": "nạn nhân", "suspect": "nghi phạm", "perpetrator": "hung thủ", "witness": "nhân chứng",
    "investigator": "điều tra viên", "family": "người nhà", "other": "khác",
}

SYSTEM_PROMPT = """\
Bạn là biên kịch chuyên chuyển thể vụ án có thật thành truyện kể và phim tài liệu kể chuyện cho kênh YouTube ở Việt Nam và Mỹ.
Công việc được chia thành nhiều việc nhỏ. Mỗi tin nhắn giao đúng một việc, dòng đầu ghi tên việc ("TASK: ..."). Làm đúng, làm đủ việc đó, không làm thêm việc khác.

NGUYÊN TẮC CHUNG
1. Giữ nguyên sự thật: diễn biến, cách gây án, quá trình điều tra, kết quả và bối cảnh chung (vùng núi, nông thôn, thành thị, thị trấn ven biển...). Không bịa thêm sự kiện, nhân vật có vai trò trong vụ án, động cơ, nghi phạm hay bằng chứng mà bài không nói.
2. Mức kịch tính hoá "như phim": được thêm không khí, ánh sáng, âm thanh, cảnh vật và cảm xúc người ngoài nhìn thấy được, nhưng chỉ dựa trên những sự kiện có trong bài. Không bịa lời nói: lời trích trực tiếp chỉ dùng khi bài có đúng câu đó, còn lại kể gián tiếp; không kể suy nghĩ thầm kín của người thật mà bài không nói. Được có nhân vật phụ không tên (người qua đường, hàng xóm).
3. Tên riêng: chỉ đổi tên người và địa danh riêng từ cấp thành phố, huyện trở xuống (đường, xã, phường, núi, sông, cảng, trường, công ty, bệnh viện hay đơn vị công an có tên cụ thể), theo đúng bảng tên hư cấu được giao. Giữ nguyên tên quốc gia ("Việt Nam", "Đài Loan", "Mỹ") và tên chung của cơ quan ("cảnh sát", "công an", "toà án", "viện kiểm sát", "bệnh viện").
   Tên hư cấu theo phong cách văn hoá gốc của vụ án, không chuyển bối cảnh sang nước khác: vụ ở Việt Nam dùng tên Việt; vụ của người Hoa dùng tên Hán-Việt trong bản tiếng Việt (ví dụ "Lưu Vinh Phú") và pinyin của cùng tên đó trong bản tiếng Anh (ví dụ "Liu Rongfu"); vụ ở Mỹ dùng tên kiểu Mỹ.
4. Ngày giờ: bỏ ngày và tháng cụ thể; năm đổi thành thời kỳ ("giữa thập niên 2010", "đầu những năm 2020"). Giữ mùa, các mốc tương đối ("ba ngày sau", "mười năm sau") và giờ trong ngày (ví dụ cuộc gọi lúc 02:21), vì giờ có thể là bằng chứng. Tuổi để xấp xỉ ("khoảng năm mươi tuổi").
5. Lời kể ở ngôi thứ ba, giọng người kể chuyện điện ảnh. Bản tiếng Anh viết lại tự nhiên cho khán giả Mỹ, không dịch sát từng chữ, nhưng giữ đúng nội dung từng cảnh.
6. Tôn trọng nạn nhân, không giật gân hoá. Không tả máu me; bạo lực chỉ được gợi qua bóng tối, hậu cảnh hoặc đồ vật.
7. Ngoại lệ cho việc đọc bài (TASK: EXTRACT) và gộp tên (TASK: CLUSTER): đây là bước ghi chép hồ sơ, nên chép tên thật, ngày giờ và con số đúng nguyên văn như trong bài, chưa đổi gì. Quy tắc 3 và 4 áp dụng cho những gì sẽ hiện ra với khán giả: tên tập, lời kể, prompt hình, nhãn bằng chứng.
8. Làm đầy đủ, không tóm gọn: liệt kê hết những gì được yêu cầu, không bỏ sót, không gộp nhiều mục làm một cho ngắn. Đầu ra được kiểm bằng máy; đầu ra mỏng hoặc thiếu sẽ bị trả lại.
9. Chỉ trả về đúng một JSON hợp lệ theo mẫu của việc được giao. Khoá JSON giữ nguyên tiếng Anh như mẫu. Không bọc trong ```, không kèm lời giải thích trước hay sau."""


def _quote(text: str) -> str:
    """Đặt tên trong ngoặc kép, đổi ngoặc kép bên trong thành ngoặc đơn để không lẫn ranh giới."""
    return '"' + str(text).replace('"', "'").strip() + '"'


def _one_line(text: str, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def word_count(text: str) -> int:
    return len(str(text or "").split())


def max_events_per_scene(n_events: int, n_scenes: int) -> int:
    """Số sự việc tối đa một cảnh được kể: 3, hoặc nhiều hơn nếu số sự việc buộc phải dồn (bài rất dày)."""
    return max(MAX_EVENTS_PER_SCENE, math.ceil(n_events / max(n_scenes, 1)))


def video_scene_cap(target_max: int) -> int:
    """Số cảnh tối đa của cả video (kể cả cảnh miễn trừ): mục tiêu tối đa + 20%."""
    return math.floor(target_max * MAX_SCENE_OVERSHOOT)


def supported_scene_cap(supported_minutes: int) -> int:
    """Số cảnh dàn ý tối đa khi bài chỉ đủ tư liệu cho `supported_minutes` phút (khoảng 4 cảnh/phút, + 20%)."""
    return math.floor(supported_minutes * SCENES_PER_MINUTE * MAX_SCENE_OVERSHOOT)


def max_dropped(n_events: int) -> int:
    """Số sự việc tối đa dàn ý được bỏ khỏi video."""
    return math.floor(n_events * MAX_DROPPED_SHARE + 1e-9)


def max_deduped(n_events: int) -> int:
    """Số sự việc tối đa bước lọc trùng được gộp vào sự việc khác."""
    return math.floor(n_events * MAX_DEDUPE_SHARE + 1e-9)


def min_events_for(words: int) -> int:
    """Số sự việc tối thiểu để không bị loại (spec 7.2): đoạn ≥ 150 từ cần ít nhất 1 sự việc mỗi 250 từ."""
    return math.ceil(words / WORDS_PER_EVENT) if words >= EVENT_RULE_MIN_WORDS else 0


def _bullet_names(names: Iterable[str]) -> str:
    lines = [f"- {_quote(n)}" for n in names if str(n).strip()]
    return "\n".join(lines) if lines else "(chưa có: đây là đoạn đầu tiên)"


# ---------------------------------------------------------------- G2: đọc một đoạn

def extract_prompt(chunk: str, index: int, total: int, known_names: list[str]) -> str:
    words = word_count(chunk)
    minimum = min_events_for(words)
    expected = max(minimum, round(words / _EXPECTED_WORDS_PER_EVENT), 1)
    if minimum:
        size_rule = (f"Đoạn này dài khoảng {words} từ, nên thường có từ {expected} sự việc trở lên. "
                     f"Bắt buộc có ít nhất {minimum} sự việc; ít hơn là chắc chắn bị thiếu và sẽ bị trả lại.")
    else:
        size_rule = (f"Đoạn này ngắn (khoảng {words} từ): liệt kê mọi sự việc có trong đoạn; "
                     "đoạn chỉ là tiêu đề hay lời dẫn thì để mảng rỗng.")
    roles = " | ".join(ROLES)
    relation_types = " | ".join(RELATION_TYPES)
    generic_terms = ", ".join(_quote(t) for t in GENERIC_TERMS)
    return f"""TASK: EXTRACT {index}
Việc: đọc kỹ ĐOẠN {index + 1}/{total} của một bài viết về vụ án có thật và ghi chép đầy đủ mọi thứ có trong đoạn: tên riêng, sự việc, bằng chứng, quan hệ. Đây là bước ghi chép hồ sơ: chép tên thật, ngày giờ và con số đúng nguyên văn như trong bài, chưa đổi tên.

Các tên đã gặp ở những đoạn trước. Nếu đoạn này nhắc lại cùng người, cùng nơi thì trong mục "names" của sự việc, bằng chứng, quan hệ hãy viết đúng như dưới đây; cách gọi mới xuất hiện trong đoạn này thì liệt kê thêm vào "names":
{_bullet_names(known_names)}

YÊU CẦU
1. "names": mọi tên riêng xuất hiện trong đoạn. Mỗi cách viết khác nhau là một mục riêng, chép nguyên văn (ví dụ họ tên đầy đủ, "ông/bà + tên", tên gọi tắt là ba mục khác nhau).
   - MỌI người được gọi bằng tên trong đoạn đều phải có trong "names", kể cả biệt danh (ví dụ "Hùng sẹo", "Sáu lùn"), tên gọi ở nhà và người chỉ được nhắc một lần.
   - Nghệ danh, bút danh, tên vai diễn hay nhân vật mà một người thật từng đóng hoặc gắn với họ: cũng là tên cần đổi, "kind" "person". Tên tác phẩm gắn với người trong vụ (phim, phim truyền hình, sách, bài hát, chương trình, kênh, ban nhạc): "kind" "organization", "context" ghi rõ "tác phẩm" hay "ban nhạc". Chỉ cần tra những tên này là tìm ra người thật, nên không được bỏ sót.
   - "kind": "person" (người), "place" (địa danh: thành phố, huyện, xã, đường, núi, sông, cảng, toà nhà...), "organization" (công ty, trường, bệnh viện hay đơn vị có tên cụ thể; tác phẩm, ban nhạc), "identifier" (biển số xe, số điện thoại, số giấy tờ, số tài khoản...).
   - "role" (người): {roles}. Nơi chốn, tổ chức, mã số ghi "other".
   - "context": một câu ngắn nói người/nơi đó là ai, ở đâu, liên quan thế nào trong đoạn.
   - KHÔNG đưa vào "names" (và không cần ghi vào "names" của sự việc, bằng chứng, quan hệ): tên quốc gia; tên hãng, mẫu xe; danh từ chung chỉ cơ quan, vai trò, nghề nghiệp, ví dụ {generic_terms}.
2. "events": mỗi sự việc riêng biệt là một mục, theo đúng thứ tự trong đoạn. Mỗi hành động, phát hiện, lời khai, kết quả giám định, bước điều tra, lần bắt giữ, phiên toà là một sự việc riêng. KHÔNG gộp nhiều sự việc làm một.
   {size_rule}
   - "summary": viết bằng tiếng Việt, 1–2 câu đầy đủ, ít nhất {MIN_EVENT_WORDS} từ: ai làm gì, ở đâu, bằng cách nào, kết quả ra sao. Giữ tên thật và chi tiết đúng như bài.
   - "time_label": mốc thời gian chép nguyên văn từ bài (ngày, giờ, "ba ngày sau"...); bài không nói thì "".
   - "names": các tên liên quan đến sự việc, viết đúng như trong "names" hoặc danh sách tên đã gặp.
3. "evidence": mọi vật chứng, dấu vết, kết quả giám định, giấy tờ, dữ liệu camera hay điện thoại, lời khai quan trọng có trong đoạn.
   - "label_vi", "label_en": nhãn ngắn 2–6 từ (tiếng Việt / tiếng Anh), không chứa tên riêng, không ghi ngày, tháng hay năm (nhãn hiện lên bảng ghim trong video).
   - "description_vi", "description_en": một câu mô tả (tiếng Việt / tiếng Anh).
   - "names": các tên liên quan, viết như trong "names".
4. "relations": quan hệ giữa hai đối tượng có tên (nợ nần, làm ăn, vợ chồng, đe doạ, nhìn thấy, gọi điện...).
   - "source_name", "target_name": viết đúng như trong "names" hoặc danh sách tên đã gặp.
   - "relation_type": một trong {relation_types}.
   - "label_vi", "label_en": nhãn ngắn 2–6 từ, không chứa tên riêng, không ghi ngày, tháng hay năm.
5. Mục nào trong đoạn không có thì để mảng rỗng. Không thêm điều bài không nói.

Trả về đúng một JSON object theo mẫu:
{{"names": [{{"name": "...", "kind": "person", "role": "victim", "context": "..."}}],
 "events": [{{"summary": "...", "time_label": "...", "names": ["..."]}}],
 "evidence": [{{"label_vi": "...", "label_en": "...", "description_vi": "...", "description_en": "...", "names": ["..."]}}],
 "relations": [{{"source_name": "...", "target_name": "...", "relation_type": "motive", "label_vi": "...", "label_en": "..."}}]}}

ĐOẠN {index + 1}/{total}:
<<<
{chunk.strip()}
>>>"""


# ---------------------------------------------------------------- G3: gộp tên

def cluster_prompt(names: list[dict]) -> str:
    lines = []
    for i, item in enumerate(names, start=1):
        kind = item.get("kind") or "?"
        role = item.get("role") or "other"
        context = _one_line(item.get("context", ""), 220)
        lines.append(f"{i}. {_quote(item.get('name', ''))} | {kind} | {role} | {context}")
    roles = " | ".join(ROLES)
    return f"""TASK: CLUSTER
Việc: dưới đây là mọi tên riêng đọc được trong một bài viết về vụ án có thật, chép nguyên văn, kèm loại, vai và ngữ cảnh. Nhiều tên là các cách gọi khác nhau của cùng một người, một nơi hay một tổ chức (họ tên đầy đủ, "ông/bà + tên", tên gọi tắt, tên viết hoa hoặc không dấu, "TP X" và "X"...). Hãy gộp chúng thành các nhóm: mỗi nhóm là đúng một người, một nơi, một tổ chức hoặc một mã số.

QUY TẮC
1. Mỗi tên trong danh sách nằm trong ĐÚNG MỘT nhóm: không bỏ sót tên nào, không đặt một tên vào hai nhóm. Danh sách có {len(names)} tên, nên các nhóm cộng lại phải có đúng {len(names)} tên.
2. "real_names": chép tên đúng nguyên văn như trong danh sách (giữ dấu, hoa thường). Không thêm tên không có trong danh sách.
3. Chỉ gộp khi ngữ cảnh cho thấy chắc chắn là cùng một đối tượng. Hai người khác nhau thì để hai nhóm, kể cả khi trùng tên gọi. Một nơi và một tổ chức mang tên nơi đó (ví dụ một cảng và công ty khai thác cảng) là hai nhóm khác nhau.
4. "kind": "person" | "place" | "organization" | "identifier".
5. "role": với người, chọn một trong {roles} theo ngữ cảnh ("perpetrator" khi bài đã xác định là hung thủ, "suspect" khi chỉ bị tình nghi). Nơi chốn, tổ chức, mã số ghi "other".
6. "id": ngắn, chữ thường không dấu, chữ số và dấu gạch dưới, không trùng nhau (ví dụ "person_1", "place_1", "organization_1", "identifier_1").

DANH SÁCH TÊN (số thứ tự. "tên" | loại | vai | ngữ cảnh):
{chr(10).join(lines)}

Trả về đúng một JSON object theo mẫu:
{{"groups": [{{"id": "person_1", "kind": "person", "role": "victim", "real_names": ["...", "..."]}}]}}"""


# ---------------------------------------------------------------- G4: đặt tên hư cấu

def aliases_prompt(groups: list[dict], opening_excerpt: str) -> str:
    lines = []
    for group in groups:
        real = ", ".join(_quote(n) for n in group.get("real_names", []))
        lines.append(f"- {group.get('id')} | {group.get('kind')} | {group.get('role') or 'other'} | {real}")
    group_list = "\n".join(lines) if lines else "(không có nhóm nào)"
    return f"""TASK: ALIASES
Việc: lập bảng tên hư cấu cho bản chuyển thể. Xác định văn hoá của vụ án, đặt tên hư cấu cho TỪNG nhóm dưới đây, đặt tên tập, viết logline, tả bối cảnh và ngoại hình nhân vật.

ĐOẠN ĐẦU BÀI (để nhận ra nước, văn hoá và thời đại của vụ án):
<<<
{opening_excerpt.strip()}
>>>

CÁC NHÓM (id | loại | vai | các tên thật):
{group_list}

YÊU CẦU
1. "culture": văn hoá gốc của vụ án, chữ thường, ví dụ "vietnamese", "chinese_taiwan", "chinese_mainland", "chinese_hongkong", "american", "japanese", "korean".
2. "solved": true nếu bài cho thấy vụ án đã được phá (đã xác định hung thủ), false nếu chưa.
3. "entities": mỗi nhóm có đúng một mục, cùng "id", gồm "alias_vi" và "alias_en" (không được để trống):
   - Người: họ tên hư cấu đầy đủ, cùng giới tính, hợp văn hoá và thời đại. Không dùng lại tên (chữ cuối) của tên thật; ví dụ người thật tên "... Văn Hùng" thì tên hư cấu không được kết thúc bằng "Hùng".
     * Vụ ở Việt Nam: "alias_vi" là tên Việt có dấu, "alias_en" là đúng tên đó viết không dấu (ví dụ "Trịnh Quang Vũ" / "Trinh Quang Vu").
     * Vụ của người Hoa (Đài Loan, Trung Quốc, Hồng Kông...): "alias_vi" là tên Hán-Việt, "alias_en" là pinyin của cùng tên đó (ví dụ "Lưu Vinh Phú" / "Liu Rongfu").
     * Vụ ở Mỹ hoặc nước nói tiếng Anh: tên kiểu Mỹ, giống nhau ở hai bản.
   - Địa danh: tên hư cấu cùng loại (đường thì là đường, cảng thì là cảng, thành phố thì là thành phố), cùng phong cách văn hoá, không dùng lại chữ riêng của tên thật; "alias_en" viết theo cách tự nhiên trong tiếng Anh (ví dụ "Cảng Hải Yến" / "Hai Yen Port").
   - Tổ chức: tên hư cấu cùng loại hình (công ty vận tải thì là công ty vận tải). Tác phẩm (phim, sách, bài hát, chương trình): tựa hư cấu cùng thể loại, không giữ chữ nào đặc trưng của tựa thật; "alias_en" là tựa tiếng Anh tự nhiên của tựa hư cấu đó (ví dụ "Hoa Nở Sau Giông" / "Blossoms After the Storm").
   - Tên vai diễn, nhân vật: tên hư cấu cùng kiểu (vai cổ trang thì tên cổ trang).
   - Mã số (biển số, số điện thoại...): giá trị giả cùng định dạng, giống nhau ở hai bản.
   - Mọi tên hư cấu phải khác nhau giữa các nhóm, và không được trùng hay chỉ khác dấu, khác hoa thường so với bất kỳ tên thật nào trong danh sách.
   - "gender": "male" hoặc "female" với người; "" với nhóm khác.
   - "age_range": ví dụ "late 40s", "mid-30s" (theo bài; bài không nói thì ước theo vai); "" với nhóm khác.
   - "appearance_en": với người, 1–2 câu tiếng Anh, ít nhất 12 từ, tả ngoại hình cố định để vẽ hình nhất quán: dân tộc, tuổi, vóc dáng, tóc, khuôn mặt, trang phục thường mặc (bài không nói thì tự đặt cho hợp vai và thời đại). Không ghi tên. Nhóm khác để "".
4. "title_vi", "title_en": tên tập hư cấu, gợi tò mò, không tiết lộ hung thủ. Không chứa tên thật nào (cần tên thì dùng tên hư cấu), không có ngày tháng hay năm cụ thể.
5. "logline_vi", "logline_en": 1–2 câu nói vụ án xoay quanh điều gì, không chứa tên thật, không có ngày tháng hay năm cụ thể.
6. "setting_notes_en": tiếng Anh, 2–4 câu, ít nhất 30 từ, tả bối cảnh để vẽ hình: thời kỳ (thập niên, không ghi năm), khí hậu và thời tiết, kiến trúc, trang phục, kiểu địa điểm. Không chứa tên riêng của người hay địa danh.

Trả về đúng một JSON object theo mẫu:
{{"culture": "...", "solved": true, "title_vi": "...", "title_en": "...", "logline_vi": "...", "logline_en": "...", "setting_notes_en": "...",
 "entities": [{{"id": "...", "alias_vi": "...", "alias_en": "...", "gender": "male", "age_range": "...", "appearance_en": "..."}}]}}"""


# ---------------------------------------------------------------- G5–G6: phần dùng chung

def _aliased(text: str, bible: CaseBible, lang: str = "vi") -> str:
    """Thay tên thật (real_names của entity) bằng tên hư cấu của `lang` trước khi đưa vào prompt."""
    fixed, _replaced = apply_aliases(text or "", build_forbidden_names(bible, ""), lang)
    return fixed


def _entity_kind(ent: CaseEntity) -> str:
    label = _KIND_LABELS.get(ent.kind, ent.kind)
    if ent.kind == "person":
        extras = [_ROLE_LABELS.get(ent.role, ent.role)] + [v for v in (ent.gender, ent.age_range) if v]
        label += " (" + ", ".join(extras) + ")"
    return label


def _name_table_vi(bible: CaseBible) -> str:
    lines = [f"- {_entity_kind(e)}: {', '.join(_quote(n) for n in e.real_names)} → {_quote(e.alias_vi)}"
             for e in bible.entities]
    return "\n".join(lines) if lines else "(không có tên riêng nào)"


def _name_table_en(bible: CaseBible) -> str:
    lines = []
    for e in bible.entities:
        real = ", ".join(_quote(n) for n in e.real_names)
        lines.append(f"- {_entity_kind(e)}: tên thật {real}; tên trong lời Việt {_quote(e.alias_vi)} → "
                     f"lời Anh dùng {_quote(e.alias_en)}")
    return "\n".join(lines) if lines else "(không có tên riêng nào)"


def _alias_vi_of(bible: CaseBible, entity_id: str) -> str:
    ent = next((e for e in bible.entities if e.id == entity_id), None)
    return ent.alias_vi if ent is not None else entity_id


def _event_lines(events: Iterable[TimelineEvent], bible: CaseBible, indent: str = "",
                 marks: Optional[dict[str, str]] = None, summary_chars: int = 400) -> str:
    lines = []
    for ev in events:
        when = f' | mốc trong bài: "{_one_line(ev.time_label, 80)}"' if ev.time_label.strip() else ""
        mark = f" {marks[ev.id]}" if marks and ev.id in marks else ""
        lines.append(f"{indent}- {ev.id}{mark}{when} | {_one_line(_aliased(ev.summary, bible), summary_chars)}")
    return "\n".join(lines) if lines else f"{indent}(không có sự việc nào)"


def _board_lines(bible: CaseBible, revealed: Iterable[str] = ()) -> str:
    shown = set(revealed)
    lines = []
    for ev in bible.evidence:
        mark = " (đã hiện ở nhịp trước)" if ev.id in shown else ""
        desc = _one_line(_aliased(ev.description_vi or ev.description_en, bible), 200)
        lines.append(f"- {ev.id}{mark}: bằng chứng \"{_aliased(ev.label_vi or ev.label_en, bible)}\" — {desc}")
    for rel in bible.relations:
        mark = " (đã hiện ở nhịp trước)" if rel.id in shown else ""
        label = _aliased(rel.label_vi or rel.label_en, bible)
        lines.append(f"- {rel.id}{mark}: quan hệ {_alias_vi_of(bible, rel.source_id)} → "
                     f"{_alias_vi_of(bible, rel.target_id)}: \"{label}\"")
    return "\n".join(lines) if lines else "(hồ sơ không có bằng chứng hay quan hệ nào)"


def _chunks_block(chunks: list[str]) -> str:
    return "\n\n".join(f"<<<\n{c.strip()}\n>>>" for c in chunks) if chunks else "(không có)"


def _solved_rule(bible: CaseBible) -> str:
    if bible.solved:
        return "Vụ án này ĐÃ được phá: chỉ kể hung thủ, cách phá án và bản án đúng như bài viết."
    return ("Vụ án này CHƯA được phá: không được nói ai là hung thủ, không kể bắt giữ, nhận tội hay xét xử nào "
            "mà bài không có; chỉ kể các nghi vấn và giả thuyết đúng như bài.")


def _where(part: StoryPart, part_position: Optional[tuple[int, int]]) -> str:
    return f"nhịp {part_position[0]}/{part_position[1]}" if part_position else f"nhịp {part.id}"


def _scene_list(scenes: list[dict], fields: tuple[tuple[str, str], ...]) -> str:
    blocks = []
    for n, scene in enumerate(scenes, start=1):
        head = f"Cảnh {n}/{len(scenes)} (visual_kind: {scene.get('visual_kind', 'image')})"
        body = [f"  {label}: {scene.get(key, '')}" for key, label in fields if scene.get(key)]
        blocks.append("\n".join([head, *body]))
    return "\n".join(blocks)


# ---------------------------------------------------------------- G5: dàn ý

def outline_prompt(bible: CaseBible, target_minutes: int, target_scenes: tuple[int, int]) -> str:
    lo, hi = target_scenes
    cap = video_scene_cap(hi)
    min_part, max_part = SCENES_PER_PART
    example_minutes = 3
    kinds = " | ".join(PART_KINDS)
    ending = ('"resolution" (phá án)' if bible.solved
              else '"open_questions" (những câu hỏi còn bỏ ngỏ); KHÔNG dùng "resolution" vì vụ chưa phá được')
    n_events = len(bible.timeline)
    most_dropped = max_dropped(n_events)
    if most_dropped:
        drop_rule = (f'"dropped": chi tiết vụn bỏ khỏi video để câu chuyện gọn và cuốn (thủ tục hành chính, thông tin lặp '
                     f'lại, chi tiết phụ không làm câu chuyện tiến lên), mỗi mục {{"event_id": "...", "reason": "lý do ngắn"}}. '
                     f"Tối đa {most_dropped} sự việc; không bỏ gì thì để []. KHÔNG được bỏ sự việc then chốt: lúc phát hiện "
                     "vụ án, bằng chứng hay lời khai làm đổi hướng điều tra, bước ngoặt, việc xác định, bắt giữ, xét xử hung "
                     "thủ hoặc kết luận cuối cùng của vụ.")
    else:
        drop_rule = '"dropped": dòng thời gian ngắn nên không bỏ sự việc nào, để [].'
    return f"""TASK: OUTLINE
Việc: lập dàn ý cho một video kể chuyện khoảng {target_minutes} phút, chuyển thể từ một vụ án có thật. Chia câu chuyện thành các nhịp (phần) theo cấu trúc phim; mỗi nhịp có từ {min_part} đến {max_part} cảnh, mỗi cảnh khoảng 15 giây lời kể. Mục tiêu là kể cuốn, giữ người xem tới cuối, nhưng không bịa. Chỉ lập dàn ý, chưa viết lời kể.

HỒ SƠ (tên đã đổi sang tên hư cấu)
- Tên tập: {_quote(bible.title_vi)}
- Logline: {_one_line(bible.logline_vi, 400) or "(không có)"}
- {_solved_rule(bible)}
- Cảnh đầu tiên của video là câu miễn trừ do hệ thống tự thêm: KHÔNG lập nhịp hay cảnh cho nó.

DÒNG THỜI GIAN: {n_events} sự việc, theo thứ tự trong bài (id | mốc thời gian | nội dung):
{_event_lines(bible.timeline, bible)}

BẰNG CHỨNG VÀ QUAN HỆ TRONG HỒ SƠ:
{_board_lines(bible)}

THỜI LƯỢNG VÀ SỐ CẢNH
1. "supported_minutes": số phút (số nguyên, ít nhất 1) mà bài này đủ chất liệu để kể hấp dẫn mà không phải bịa thêm; tính khoảng {SCENES_PER_MINUTE} cảnh cho mỗi phút, mỗi sự việc đủ cho 1–{MAX_SCENES_PER_EVENT} cảnh. Ước trung thực theo lượng sự việc giữ lại (không tính sự việc trong "dropped"), không theo thời lượng người dùng chọn: không nâng lên cho bằng {target_minutes} phút, không hạ xuống để viết ít.
2. Video luôn có thêm 1 cảnh miễn trừ ở đầu, đã tính vào các mức dưới đây. Tổng số cảnh của dàn ý (cộng "scene_count" của mọi nhịp):
   - nếu "supported_minutes" ≥ {target_minutes}: từ {lo - 1} đến {hi - 1} cảnh (video có {lo}–{hi} cảnh, kể cả cảnh miễn trừ); ít hơn {lo - 1} cảnh là thiếu và sẽ bị trả lại;
   - nếu "supported_minutes" < {target_minutes}: vừa với chất liệu, khoảng "supported_minutes" × {SCENES_PER_MINUTE} cảnh và không quá "supported_minutes" × {SCENES_PER_MINUTE * MAX_SCENE_OVERSHOOT:g} cảnh (làm tròn xuống; ví dụ {example_minutes} phút: khoảng {example_minutes * SCENES_PER_MINUTE} cảnh, tối đa {supported_scene_cap(example_minutes)} cảnh). Không kéo dài cho đủ số cảnh;
   - trong mọi trường hợp không quá {cap - 1} cảnh (video tối đa {cap} cảnh, kể cả cảnh miễn trừ).

QUY TẮC NHỊP
1. Thứ tự kể để giữ người xem, không bắt buộc theo thời gian: mở bằng hook (khoảnh khắc gây tò mò nhất, không tiết lộ kết); sau đó được kể ngay lúc phát hiện vụ án (discovery) rồi mới quay ngược về bối cảnh, con người (setup), hoặc kể setup trước nếu như vậy cuốn hơn; tiếp theo là investigation (điều tra), twist (bước ngoặt), kết thúc và epilogue (kết và dư âm). Bước ngoặt và kết luôn ở cuối, không tiết lộ sớm. Kết thúc của vụ này là {ending}. Không bắt buộc đủ mọi loại; một loại có thể có nhiều nhịp liền nhau (ví dụ ba nhịp investigation).
2. "kind": một trong {kinds}.
3. "event_ids": id các sự việc nhịp này kể, theo thứ tự kể. Mỗi sự việc trong dòng thời gian (đủ {n_events} id) phải nằm trong ĐÚNG MỘT nhịp hoặc trong "dropped": không bỏ sót id nào, và không kể lại cùng một sự việc ở hai nhịp. Chỉ dùng id có trong danh sách trên. Ngoại lệ duy nhất: nhịp hook được mượn trước tối đa 1 sự việc của một nhịp sau, nhưng chỉ để gợi tò mò (một câu hỏi, một hình ảnh, một chi tiết chưa có lời giải), không kể lại trọn sự việc; sự việc đó vẫn nằm trong nhịp của nó, và chính nhịp đó mới kể đầy đủ.
4. {drop_rule}
5. "scene_count": số nguyên từ {min_part} đến {max_part}; không ít hơn số sự việc của nhịp chia {MAX_EVENTS_PER_SCENE} (mỗi cảnh kể tối đa {MAX_EVENTS_PER_SCENE} sự việc), và không nhiều hơn {MAX_SCENES_PER_EVENT} × số sự việc của nhịp (mỗi sự việc đủ cho tối đa {MAX_SCENES_PER_EVENT} cảnh; nhịp 1 sự việc thì đúng {min_part} cảnh). Nhịp có nhiều sự việc thì tách thành nhiều nhịp.
6. "summary_vi": 1–2 câu tiếng Việt nói nhịp này kể gì; chỉ dùng tên hư cấu như trong hồ sơ trên; không ghi ngày, tháng hay năm cụ thể. Riêng nhịp hook: "summary_vi" là lời gợi tò mò (câu hỏi hay hình ảnh mở đầu), không tóm tắt diễn biến hay kết quả.
7. "id": "p1", "p2", "p3"... theo thứ tự.

Trả về đúng một JSON object theo mẫu (thay phần trong <...> bằng số nguyên):
{{"supported_minutes": <số phút tư liệu đủ để kể mà không bịa>, "parts": [{{"id": "p1", "kind": "hook", "summary_vi": "...", "event_ids": ["..."], "scene_count": 3}}], "dropped": []}}"""


# ---------------------------------------------------------------- G4b: lọc sự việc trùng

def dedupe_prompt(bible: CaseBible) -> str:
    n = len(bible.timeline)
    return f"""TASK: DEDUPE
Việc: dưới đây là {n} sự việc ghi chép lần lượt từ các đoạn của một bài viết về vụ án có thật (tên đã đổi sang tên hư cấu). Bài báo hay kể một chuyện hai lần (đoạn mở đầu tóm tắt rồi phần sau kể chi tiết, hoặc nhắc lại khi tổng kết), nên có thể có sự việc trùng nhau. Hãy tìm các nhóm sự việc kể về CÙNG MỘT việc đã xảy ra.

QUY TẮC
1. Chỉ gộp khi chắc chắn là cùng một hành động của cùng người, ở cùng lúc (ví dụ "người vợ báo cảnh sát chồng mất tích" ở đoạn đầu và "chiều hôm đó, người vợ đến đồn trình báo chồng không về nhà" ở đoạn sau). Hai việc giống nhau nhưng xảy ra ở hai lúc khác nhau (hai lần thẩm vấn, hai cuộc gọi) là hai sự việc riêng: không gộp.
2. "keep": id của sự việc ghi đầy đủ chi tiết nhất trong nhóm; "drop": các id còn lại của nhóm (ít nhất 1). Mỗi id chỉ nằm trong tối đa một nhóm, và không vừa là "keep" vừa là "drop".
3. "reason": một câu ngắn nói vì sao là cùng một việc.
4. Không có sự việc nào trùng thì trả "duplicates": []. Không gộp cho gọn: sự việc khác nhau thì giữ riêng.

DÒNG THỜI GIAN: {n} sự việc, theo thứ tự trong bài (id | mốc thời gian | nội dung tóm tắt):
{_event_lines(bible.timeline, bible, summary_chars=220)}

Trả về đúng một JSON object theo mẫu:
{{"duplicates":[{{"keep": "...", "drop": ["..."], "reason": "..."}}]}}"""


# ---------------------------------------------------------------- G6: lời Việt

def _story_block(bible: CaseBible, part: StoryPart, outline_parts: Sequence[StoryPart]) -> str:
    """Logline và dàn ý tóm tắt của mọi nhịp, đánh dấu nhịp đang viết."""
    lines = [f"- Logline: {_one_line(_aliased(bible.logline_vi, bible), 400) or '(không có)'}"]
    if outline_parts:
        lines.append(f"- Dàn ý cả video ({len(outline_parts)} nhịp, theo thứ tự kể):")
        for n, p in enumerate(outline_parts, start=1):
            current = p.id == part.id
            mark = "►" if current else " "
            note = "  ◄ NHỊP ĐANG VIẾT" if current else ""
            summary = _one_line(_aliased(p.summary_vi, bible), 300) or "(không có tóm tắt)"
            lines.append(f"  {mark} {n}. {p.kind} ({p.scene_count} cảnh): {summary}{note}")
    return "\n".join(lines)


def next_part_of(part: StoryPart, outline_parts: Sequence[StoryPart]) -> Optional[StoryPart]:
    """Nhịp kể ngay sau `part` trong dàn ý; None nếu `part` là nhịp cuối (hoặc không có dàn ý)."""
    ids = [p.id for p in outline_parts]
    if part.id not in ids:
        return None
    index = ids.index(part.id)
    return outline_parts[index + 1] if index + 1 < len(outline_parts) else None


_LAST_QUESTION = re.compile(r"[^.!?…。！？]*[?？][\"'”’»)\]]*\s*$")


def _last_question(text: str) -> str:
    """Câu hỏi kết thúc `text` (câu cuối, nếu là câu hỏi), để nhịp sau không hỏi lặp kiểu."""
    match = _LAST_QUESTION.search(text or "")
    return " ".join(match.group(0).split()) if match else ""


def _ending_rule(part: StoryPart, outline_parts: Sequence[StoryPart], bible: CaseBible,
                 prev_question: str = "") -> str:
    """Cảnh cuối của nhịp: câu hỏi bỏ ngỏ kéo sang nhịp sau (khác kiểu câu hỏi của nhịp trước), hoặc câu khép lại
    video ở nhịp cuối."""
    nxt = next_part_of(part, outline_parts)
    if nxt is None:
        if outline_parts:
            return ("Đây là nhịp cuối của video: cảnh cuối khép lại câu chuyện bằng một câu đọng lại về những gì vụ án để "
                    "lại, không mở thêm tình tiết mới.")
        return "Cảnh cuối của nhịp kết bằng một câu gợi tò mò về điều sẽ kể tiếp, không trả lời trước."
    summary = _one_line(_aliased(nxt.summary_vi, bible), 300) or "(không có tóm tắt)"
    if not asks_question(part, outline_parts):
        return (f"Cảnh cuối của nhịp này dẫn sang nhịp sau ({nxt.kind}: {summary}) bằng một chi tiết, một hình ảnh hoặc "
                "một câu khẳng định nặng ký gợi điều sắp kể, không trả lời trước. KHÔNG kết bằng câu hỏi, và cả nhịp "
                "không có câu hỏi nào: người xem đã được hỏi đủ ở các nhịp khác.")
    vary = ("Đổi cách hỏi qua từng nhịp: hỏi thẳng vào điều nhịp sau tiết lộ (\"Ai...\", \"Điều gì...\", \"Vì sao...\", "
            "\"Bằng cách nào...\", \"... sẽ dẫn tới đâu?\"), không mở đầu câu hỏi bằng \"Liệu\".")
    if prev_question:
        vary += (f" Câu hỏi cuối nhịp trước là {_quote(_one_line(prev_question, 200))}: câu hỏi của nhịp này phải khác "
                 "hẳn, không mở đầu bằng cùng từ, không cùng kiểu câu.")
    return (f"Câu cuối của cảnh cuối nhịp này PHẢI là một câu hỏi bỏ ngỏ (kết bằng dấu ?) kéo người xem sang nhịp sau "
            f"({nxt.kind}: {summary}). Câu hỏi gợi đúng điều nhịp sau sẽ kể, không trả lời trước, không hỏi chung chung "
            f"kiểu \"chuyện gì sẽ xảy ra tiếp theo?\". {vary}")


def write_vi_prompt(bible: CaseBible, part: StoryPart, events: list[TimelineEvent], source_chunks: list[str],
                    prev_scenes: list[dict], *, part_position: Optional[tuple[int, int]] = None,
                    revealed_ids: Iterable[str] = (), teaser_ids: Iterable[str] = (),
                    teased_ids: Iterable[str] = (), outline_parts: Sequence[StoryPart] = (),
                    introduced_names: Iterable[str] = (), budget: Optional[WordBudget] = None) -> str:
    """- `revealed_ids`: id bằng chứng/quan hệ đã hiện ở các nhịp trước (đánh dấu trong danh sách).
    - `teaser_ids`: sự việc nhịp hook mượn của nhịp sau: chỉ được gợi, không kể trọn.
    - `teased_ids`: sự việc của nhịp này đã được hook hé lộ: giờ mới kể đầy đủ.
    - `outline_parts`: mọi nhịp của dàn ý (để viết có cài cắm và trả lời); nhịp `part` được đánh dấu.
    - `introduced_names`: tên hư cấu (tiếng Việt) của nhân vật đã xuất hiện ở các nhịp trước: không giới thiệu lại.
    - `budget`: số từ mỗi cảnh theo thời lượng video (mặc định 15 giây mỗi cảnh)."""
    n = part.scene_count
    budget = budget or word_budget()
    lo, hi = budget.vi_limit
    per_scene = max_events_per_scene(len(events), n)
    event_ids = ", ".join(ev.id for ev in events) or "(không có)"
    marks = {e: _TEASER_MARK for e in teaser_ids}
    marks.update({e: _TEASED_MARK for e in teased_ids})
    if prev_scenes:
        prev = "\n".join(f"- {s.get('narration_vi', '')}" for s in prev_scenes)
        prev_rule = "Nối tiếp mạch kể từ hai cảnh này, không lặp lại nội dung của chúng."
    else:
        prev = "(đây là nhịp đầu tiên, ngay sau câu miễn trừ ở đầu video)"
        prev_rule = "Câu đầu tiên mở màn câu chuyện, không nhắc lại câu miễn trừ."
    met = list(dict.fromkeys(name for name in introduced_names if name))
    if met:
        introduced = (", ".join(_quote(name) for name in met) + "\nNhững người này khán giả đã biết: không giới thiệu "
                      "lại (không nhắc lại tuổi, nghề, quan hệ như lần đầu), gọi thẳng bằng tên hoặc cách gọi ngắn. Chỉ "
                      "giới thiệu ngắn gọn người lần đầu xuất hiện trong nhịp này.")
    elif outline_parts and outline_parts[0].id == part.id:
        introduced = "(đây là nhịp đầu tiên: nhân vật nào xuất hiện lần đầu thì giới thiệu ngắn gọn)"
    else:
        introduced = "(chưa có nhân vật nào được kể ở các nhịp trước)"
    return f"""TASK: WRITE_VI {part.id}
Việc: viết lời kể tiếng Việt cho ĐÚNG {n} cảnh của {_where(part, part_position)} ("{part.kind}") trong video chuyển thể vụ án có thật {_quote(bible.title_vi)}. Chỉ viết nhịp này, không viết các nhịp khác.

TOÀN BỘ CÂU CHUYỆN (để nhịp này ăn khớp với cả video; chỉ viết nhịp đang viết):
{_story_block(bible, part, outline_parts)}

NHÂN VẬT ĐÃ XUẤT HIỆN Ở CÁC NHỊP TRƯỚC:
{introduced}

NHỊP NÀY
- Loại nhịp: {part.kind}: {_KIND_HINTS.get(part.kind, part.kind)}.
- Nội dung: {_one_line(_aliased(part.summary_vi, bible), 400) or "(không có)"}
- Số cảnh: đúng {n} cảnh.
- {_solved_rule(bible)}
- Sự việc phải kể, theo thứ tự (mỗi sự việc phải được kể ít nhất trong một cảnh):
{_event_lines(events, bible, indent="  ", marks=marks)}

BẢNG TÊN: đoạn gốc dưới đây dùng tên thật; lời kể CHỈ được dùng tên hư cấu ở bên phải mũi tên (gọi tắt theo tên hư cấu cũng được, ví dụ "ông" + tên):
{_name_table_vi(bible)}
Tên riêng nào trong đoạn gốc không có trong bảng (tên đường, tên người chỉ nhắc qua...): không viết ra, thay bằng cách gọi chung ("một con phố gần cảng", "một người hàng xóm").

BẰNG CHỨNG VÀ QUAN HỆ (id dùng cho "board_reveal"):
{_board_lines(bible, revealed_ids)}

HAI CẢNH CUỐI CỦA NHỊP TRƯỚC:
{prev}
{prev_rule}

ĐOẠN GỐC CHỨA CÁC SỰ VIỆC TRÊN (nguồn sự thật duy nhất; có tên thật, chỉ để đọc):
{_chunks_block(source_chunks)}

CÁCH VIẾT
1. Mỗi cảnh có "narration_vi" dài khoảng {_span(budget.vi_aim)} từ (khoảng {round(budget.seconds)} giây đọc; video phải đạt ít nhất thời lượng đã chọn, nên đừng viết ngắn hơn); bắt buộc từ {lo} đến {hi} từ, ngoài khoảng này sẽ bị trả lại. Câu gọn, mỗi câu một ý, không kể lan man. Lời kể ngôi thứ ba, giọng người kể chuyện điện ảnh, câu trọn vẹn, liền mạch từ cảnh này sang cảnh sau.
   Viết để đọc chậm, có nhịp ngừng tạo căng thẳng: nhiều câu ngắn; dấu phẩy ở chỗ cần ngắt hơi; ở khoảnh khắc nặng nề nhất của cảnh có thể dùng một dấu ba chấm (…) để người đọc dừng lại (tối đa một lần mỗi cảnh).
   Không dùng câu hỏi tu từ trong lời kể; câu hỏi chỉ được có ở chỗ quy tắc 11 cho phép.
2. Kể đúng thứ tự sự việc. Mỗi cảnh kể 1–{per_scene} sự việc; sự việc quan trọng có thể kéo dài 2 cảnh. Kể cụ thể (ai, làm gì, ở đâu, bằng cách nào, thấy gì), không tóm gọn kiểu "sau đó cảnh sát vào cuộc điều tra".
3. "Như phim" nhưng không bịa: được thêm không khí, ánh sáng, âm thanh, cảnh vật và cảm xúc người ngoài nhìn thấy được, chỉ từ những gì đoạn gốc có. KHÔNG đặt lời vào miệng nhân vật: lời nói trực tiếp trong ngoặc kép chỉ dùng khi đoạn gốc có đúng câu đó (chép lại nguyên văn, hoặc dịch sang tiếng Việt nếu bài viết bằng tiếng khác); đoạn gốc không có thì kể gián tiếp (bà báo cảnh sát rằng chồng mình không về nhà). Không kể suy nghĩ thầm kín của người thật mà đoạn gốc không nói. Không thêm sự kiện, nhân vật có vai trò trong vụ án, động cơ, nghi phạm hay bằng chứng mới; nhân vật phụ không tên (người qua đường, hàng xóm) thì được.
4. Ngày giờ: không viết ngày, tháng, năm cụ thể (không "15 tháng 10", không "15/10", không "năm 2021"); năm đổi thành thời kỳ ("đầu những năm 2020"). Giữ giờ trong ngày ("khoảng 23 giờ 30"), mùa và các mốc tương đối ("chiều hôm đó", "hơn một giờ sau"). Tuổi để xấp xỉ hoặc viết bằng chữ.
5. {_ID_NUMBER_RULE_VI}
6. Giữ tên quốc gia và tên chung của cơ quan ("cảnh sát", "công an", "toà án"). {_TONE_RULE_VI}
7. Sự việc ghi [CHỈ GỢI] (nhịp mở đầu mượn của nhịp sau): chỉ hé lộ bằng một câu hỏi, một hình ảnh hoặc một chi tiết chưa có lời giải, trong một hai câu; không kể trọn diễn biến, không nói kết quả. Sự việc ghi [đã được hé lộ ở đoạn mở đầu]: giờ mới kể đầy đủ, không lặp lại câu mở đầu.
8. "visual_kind" của từng cảnh:
   - "board": cảnh nói về chính các bằng chứng hoặc mối quan hệ hiện lên bảng điều tra ở cảnh đó. "board_reveal" PHẢI có ít nhất 1 id (chỉ dùng id trong danh sách trên, ưu tiên những cái chưa hiện), và lời kể của cảnh nói rõ nội dung của đúng những bằng chứng/quan hệ ấy. Không dùng "board" cho lời kể chung chung (ví dụ "lời khai được ghi vào hồ sơ"); không có gì để hiện thì dùng "image". Nhịp này có TỐI ĐA {max_boards_in_part(n)} cảnh "board" (người xem cần hình ảnh câu chuyện hơn bảng ghim); chỉ dùng khi bằng chứng là trọng tâm của cảnh.
   - "video": một khoảnh khắc hành động ngắn (chạy, bỏ trốn, xe lao đi...). Tối đa 1 cảnh video trong nhịp này; lời cảnh video ngắn hơn, khoảng {_span(budget.vi_video_aim)} từ.
   - "image": mọi cảnh còn lại.
   Cảnh không phải "board" thì "board_reveal" là [].
9. "covers_event_ids": id các sự việc (của nhịp này) mà lời kể của cảnh đó thật sự kể ra: mỗi cảnh có từ 1 đến {per_scene} id, chia đều cho các cảnh theo thứ tự. Gộp mọi cảnh lại phải có đủ: {event_ids}.
10. Cài cắm và trả lời theo dàn ý cả video ở trên: chi tiết mà nhịp sau sẽ giải thích (một đồ vật, một câu nói, một điều bất thường có trong sự việc của nhịp này) thì gieo nhẹ để khán giả để ý, không nói trước lời giải hay diễn biến của nhịp sau; câu hỏi hay chi tiết các nhịp trước đã gieo thì khi tới sự việc liên quan, nhắc lại đúng chi tiết ấy và trả lời. Không giới thiệu lại nhân vật đã xuất hiện ở nhịp trước.
11. {_ending_rule(part, outline_parts, bible, _last_question(prev_scenes[-1].get("narration_vi", "")) if prev_scenes else "")}

Trả về đúng một JSON object, "scenes" có đúng {n} phần tử theo thứ tự kể:
{{"scenes": [{{"narration_vi": "...", "visual_kind": "image", "board_reveal": [], "covers_event_ids": ["..."]}}]}}"""


# ---------------------------------------------------------------- G6: lời Anh

def _en_writing_rules(count_rule: str, budget: Optional[WordBudget] = None) -> str:
    budget = budget or word_budget()
    lo, hi = budget.en_limit
    return f"""CÁCH VIẾT
1. Mỗi cảnh có "narration_en" dài khoảng {_span(budget.en_aim)} từ tiếng Anh (khoảng {round(budget.seconds)} giây đọc, để video ra đúng thời lượng đã chọn); bắt buộc từ {lo} đến {hi} từ, dài hơn {hi} từ sẽ bị trả lại: viết gọn hơn bản Việt, giữ ý chính và chi tiết then chốt. Cảnh "video" ngắn hơn, khoảng {_span(budget.en_video_aim)} từ.
2. {count_rule}
3. Văn phong người dẫn chuyện phim tài liệu true-crime Mỹ: câu rõ, nhịp tự nhiên khi đọc to; viết lại cho tự nhiên chứ không dịch sát từng chữ. Lời trích trong ngoặc kép chỉ có khi bản Việt có (dịch đúng câu đó); không thêm lời thoại hay suy nghĩ của nhân vật. Cảnh tiếng Việt kết bằng câu hỏi thì cảnh tiếng Anh tương ứng cũng kết bằng câu hỏi đó.
4. Tên: chỉ dùng tên ở phần "lời Anh dùng" trong bảng tên; không dùng tên thật, không dùng dạng tên tiếng Việt khi hai dạng khác nhau. Bỏ danh xưng tiếng Việt ("ông", "bà", "anh", "chị"); gọi bằng tên hoặc "he", "she".
5. Ngày giờ: không ngày, tháng, năm cụ thể ("October 15", "2021"); dùng thời kỳ ("in the early 2020s"), mùa và mốc tương đối ("one autumn night", "three days later"). Giữ giờ trong ngày ("around 11:30 p.m.").
6. {_ID_NUMBER_RULE_EN}
7. Giữ tên quốc gia và tên chung của cơ quan bằng tiếng Anh ("Vietnam", "Taiwan", "the police", "the court"). {_TONE_RULE_EN}"""


def write_en_prompt(bible: CaseBible, part: StoryPart, vi_scenes: list[dict], source_chunks: list[str], *,
                    part_position: Optional[tuple[int, int]] = None, budget: Optional[WordBudget] = None) -> str:
    n = len(vi_scenes)
    rules = _en_writing_rules(
        "Cảnh tiếng Anh số k kể đúng nội dung cảnh tiếng Việt số k (hình ảnh dùng chung): không gộp hai cảnh, "
        "không tách một cảnh, không đảo thứ tự, không thêm chi tiết mà cảnh Việt và đoạn gốc không có.", budget)
    return f"""TASK: WRITE_EN {part.id}
Việc: viết lời kể tiếng Anh cho ĐÚNG {n} cảnh của {_where(part, part_position)} trong video chuyển thể vụ án có thật {_quote(bible.title_en)}, cho khán giả Mỹ nghe qua giọng đọc. Lời tiếng Việt của các cảnh đã có ở dưới; viết đúng {n} cảnh tiếng Anh tương ứng.

BẢNG TÊN:
{_name_table_en(bible)}

CÁC CẢNH TIẾNG VIỆT:
{_scene_list(vi_scenes, (("narration_vi", "VI"),))}

ĐOẠN GỐC (để hiểu đúng sự thật; có tên thật, chỉ để đọc):
{_chunks_block(source_chunks)}

{rules}

Trả về đúng một JSON object, "scenes" có đúng {n} phần tử theo thứ tự cảnh:
{{"scenes": [{{"narration_en": "..."}}]}}"""


# ---------------------------------------------------------------- G6: prompt hình

def prompts_prompt(bible: CaseBible, part: StoryPart, scenes: list[dict], visual_style: str, *,
                   part_position: Optional[tuple[int, int]] = None) -> str:
    """`scenes`: mỗi cảnh có narration_vi, narration_en, visual_kind."""
    n = len(scenes)
    people = [f"- {_quote(e.alias_en)} / {_quote(e.alias_vi)} — {_entity_kind(e)}: "
              f"{e.appearance_en or '(chưa có mô tả; tả cho hợp vai và thời đại)'}"
              for e in bible.entities if e.kind == "person"]
    places = [f"- {_quote(e.alias_en)} / {_quote(e.alias_vi)} — {_entity_kind(e)}"
              for e in bible.entities if e.kind in ("place", "organization")]
    motions = " | ".join(CAMERA_MOTIONS)
    beats = " | ".join(NARRATIVE_BEATS)
    energies = " | ".join(BGM_ENERGIES)
    return f"""TASK: PROMPTS {part.id}
Việc: viết prompt tạo hình bằng tiếng Anh (ảnh tĩnh, và clip 5 giây cho cảnh video) cho ĐÚNG {n} cảnh của {_where(part, part_position)}. Mỗi hình được tạo riêng bằng AI, không biết các cảnh khác, nên mỗi prompt phải đọc riêng vẫn hiểu.

PHONG CÁCH HÌNH: {visual_style}
BỐI CẢNH CHUNG: {bible.setting_notes_en or "(không có)"}

NHÂN VẬT (lời kể gọi bằng tên; prompt KHÔNG được ghi tên, chỉ tả bằng ngoại hình dưới đây, chép đủ các đặc điểm chính mỗi lần nhân vật xuất hiện để các cảnh giống nhau):
{chr(10).join(people) or "(không có)"}
NƠI CHỐN, TỔ CHỨC (prompt tả kiểu nơi chốn, không ghi tên):
{chr(10).join(places) or "(không có)"}

CÁC CẢNH:
{_scene_list(scenes, (("narration_vi", "VI"), ("narration_en", "EN")))}

YÊU CẦU CHO TỪNG CẢNH
1. "image_prompt": tiếng Anh, khoảng 40–80 từ, ít nhất {MIN_IMAGE_PROMPT_WORDS} từ (ngắn hơn sẽ bị trả lại). Gồm: khung hình (wide shot, medium shot, close-up...), chủ thể (tả bằng ngoại hình ở trên), hành động, bối cảnh lấy từ bối cảnh chung, ánh sáng, và phong cách "{visual_style}". Không ghi tên người hay tên địa danh; không có chữ, logo, biển số đọc được trong hình.
   - Cảnh "board": tả một bảng điều tra (corkboard) với ảnh, ghi chú, vật chứng và sợi chỉ đỏ nối các manh mối mà cảnh đó nói tới.
2. "video_prompt": tiếng Anh, 15–40 từ, tả chuyển động của máy quay và của chủ thể trong 5 giây. Bắt buộc với cảnh "video" (ít nhất {MIN_VIDEO_PROMPT_WORDS} từ); cảnh khác để "".
3. "camera_motion": một trong {motions}.
4. "narrative_beat": một trong {beats}.
5. "sfx_cue": 0–2 tiếng động ngắn, tiếng Anh, viết kiểu snake_case (ví dụ "heavy_rain_loop", "footsteps", "distant_thunder_subtle", "clock_ticking", "heartbeat_single_pulse", "rusty_iron_gate_creak"); không cần thì [].
6. "bgm_energy": một trong {energies}.
7. An toàn cho YouTube: không máu, không vết thương, không thi thể lộ rõ, không vũ khí đang gây thương tích; bạo lực chỉ được gợi qua bóng tối, hậu cảnh hoặc đồ vật (tấm bạt che, dây phong toả, đèn pin, bóng người).

Trả về đúng một JSON object, "scenes" có đúng {n} phần tử theo thứ tự cảnh:
{{"scenes": [{{"image_prompt": "...", "video_prompt": "", "camera_motion": "zoom_in", "narrative_beat": "setting", "sfx_cue": [], "bgm_energy": "tension_buildup"}}]}}"""


# ---------------------------------------------------------------- viết lại lời Anh cho cảnh đã sửa

def rewrite_en_prompt(bible: CaseBible, items: list[tuple[int, str]], budget: Optional[WordBudget] = None) -> str:
    orders = ", ".join(str(order) for order, _text in items)
    scenes = "\n".join(f"- order {order}: {_one_line(text, 1200)}" for order, text in items)
    rules = _en_writing_rules(
        "Mỗi cảnh tiếng Anh kể đúng nội dung cảnh tiếng Việt cùng order; không gộp, không tách, không bỏ cảnh nào, "
        "không thêm chi tiết mà lời Việt không có.", budget)
    example_order = items[0][0] if items else 1
    return f"""TASK: REWRITE_EN
Việc: lời tiếng Việt của {len(items)} cảnh dưới đây vừa được thêm hoặc sửa trong bản chuyển thể vụ án có thật {_quote(bible.title_en)}. Hãy viết lại lời kể tiếng Anh cho ĐÚNG các cảnh này (order: {orders}), cho khán giả Mỹ nghe qua giọng đọc.

BẢNG TÊN:
{_name_table_en(bible)}

CÁC CẢNH TIẾNG VIỆT:
{scenes}

{rules}

Trả về đúng một JSON object, "scenes" có đúng {len(items)} phần tử, mỗi phần tử ghi đúng "order" của cảnh:
{{"scenes": [{{"order": {example_order}, "narration_en": "..."}}]}}"""
