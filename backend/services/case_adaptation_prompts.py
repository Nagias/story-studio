"""
Prompt LLM cho luồng chuyển thể vụ án thật thành truyện song ngữ Việt/Anh (spec mục 6, 7.1a, 7.2, 7.10).

- SYSTEM_PROMPT dùng chung cho mọi việc nhỏ.
- Mỗi hàm *_prompt trả user prompt cho đúng một việc. Dòng đầu luôn là marker "TASK: <TÊN>" (LLM giả trong test
  đọc dòng này để chọn fixture). Câu chữ tiếng Việt; khoá JSON tiếng Anh, khớp với phần kiểm ở case_adaptation_steps.
- Mỗi prompt nói rõ kích thước đầu ra mong đợi (số sự việc, độ dài tối thiểu), vì model hay lười và tóm gọn.
"""
import math
from typing import Iterable

# Ngưỡng kiểm của bước đọc đoạn (spec 7.2). case_adaptation_steps dùng lại đúng các số này.
EVENT_RULE_MIN_WORDS = 150   # đoạn từ 150 từ trở lên mới bị kiểm số sự việc
WORDS_PER_EVENT = 250        # ít nhất 1 sự việc cho mỗi 250 từ
MIN_EVENT_WORDS = 12         # mỗi tóm tắt sự việc dài ít nhất 12 từ
_EXPECTED_WORDS_PER_EVENT = 70  # mức mong đợi nói với model (chặt hơn ngưỡng loại)

ROLES = ("victim", "suspect", "perpetrator", "witness", "investigator", "family", "other")
RELATION_TYPES = (
    "motive", "alibi_contradiction", "blood_match", "call_log", "witness_seen", "suspect_link", "causal", "timeline",
)

SYSTEM_PROMPT = """\
Bạn là biên kịch chuyên chuyển thể vụ án có thật thành truyện kể và phim tài liệu kể chuyện cho kênh YouTube ở Việt Nam và Mỹ.
Công việc được chia thành nhiều việc nhỏ. Mỗi tin nhắn giao đúng một việc, dòng đầu ghi tên việc ("TASK: ..."). Làm đúng, làm đủ việc đó, không làm thêm việc khác.

NGUYÊN TẮC CHUNG
1. Giữ nguyên sự thật: diễn biến, cách gây án, quá trình điều tra, kết quả và bối cảnh chung (vùng núi, nông thôn, thành thị, thị trấn ven biển...). Không bịa thêm sự kiện, nhân vật có vai trò trong vụ án, động cơ, nghi phạm hay bằng chứng mà bài không nói.
2. Mức kịch tính hoá "như phim": được thêm không khí, cảm xúc, nội tâm và lời thoại dựng lại, nhưng chỉ dựa trên những sự kiện có trong bài. Được có nhân vật phụ không tên (người qua đường, hàng xóm).
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
    return f"""TASK: EXTRACT {index}
Việc: đọc kỹ ĐOẠN {index + 1}/{total} của một bài viết về vụ án có thật và ghi chép đầy đủ mọi thứ có trong đoạn: tên riêng, sự việc, bằng chứng, quan hệ. Đây là bước ghi chép hồ sơ: chép tên thật, ngày giờ và con số đúng nguyên văn như trong bài, chưa đổi tên.

Các tên đã gặp ở những đoạn trước. Nếu đoạn này nhắc lại cùng người, cùng nơi thì trong mục "names" của sự việc, bằng chứng, quan hệ hãy viết đúng như dưới đây; cách gọi mới xuất hiện trong đoạn này thì liệt kê thêm vào "names":
{_bullet_names(known_names)}

YÊU CẦU
1. "names": mọi tên riêng xuất hiện trong đoạn. Mỗi cách viết khác nhau là một mục riêng, chép nguyên văn (ví dụ họ tên đầy đủ, "ông/bà + tên", tên gọi tắt là ba mục khác nhau).
   - "kind": "person" (người), "place" (địa danh: thành phố, huyện, xã, đường, núi, sông, cảng, toà nhà...), "organization" (công ty, trường, bệnh viện hay đơn vị có tên cụ thể), "identifier" (biển số xe, số điện thoại, số giấy tờ, số tài khoản...).
   - "role" (người): {roles}. Nơi chốn, tổ chức, mã số ghi "other".
   - "context": một câu ngắn nói người/nơi đó là ai, ở đâu, liên quan thế nào trong đoạn.
   - KHÔNG liệt kê: tên quốc gia; tên chung của cơ quan ("cảnh sát", "công an", "toà án", "viện kiểm sát", "bệnh viện", "cơ quan điều tra"); danh từ chung ("nạn nhân", "nghi phạm", "pháp y"); tên hãng, mẫu xe.
2. "events": mỗi sự việc riêng biệt là một mục, theo đúng thứ tự trong đoạn. Mỗi hành động, phát hiện, lời khai, kết quả giám định, bước điều tra, lần bắt giữ, phiên toà là một sự việc riêng. KHÔNG gộp nhiều sự việc làm một.
   {size_rule}
   - "summary": viết bằng tiếng Việt, 1–2 câu đầy đủ, ít nhất {MIN_EVENT_WORDS} từ: ai làm gì, ở đâu, bằng cách nào, kết quả ra sao. Giữ tên thật và chi tiết đúng như bài.
   - "time_label": mốc thời gian chép nguyên văn từ bài (ngày, giờ, "ba ngày sau"...); bài không nói thì "".
   - "names": các tên liên quan đến sự việc, viết đúng như trong "names" hoặc danh sách tên đã gặp.
3. "evidence": mọi vật chứng, dấu vết, kết quả giám định, giấy tờ, dữ liệu camera hay điện thoại, lời khai quan trọng có trong đoạn.
   - "label_vi", "label_en": nhãn ngắn 2–6 từ (tiếng Việt / tiếng Anh), không chứa tên riêng.
   - "description_vi", "description_en": một câu mô tả (tiếng Việt / tiếng Anh).
   - "names": các tên liên quan, viết như trong "names".
4. "relations": quan hệ giữa hai đối tượng có tên (nợ nần, làm ăn, vợ chồng, đe doạ, nhìn thấy, gọi điện...).
   - "source_name", "target_name": viết đúng như trong "names" hoặc danh sách tên đã gặp.
   - "relation_type": một trong {relation_types}.
   - "label_vi", "label_en": nhãn ngắn 2–6 từ, không chứa tên riêng.
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
   - Tổ chức: tên hư cấu cùng loại hình (công ty vận tải thì là công ty vận tải).
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
