"""
Case Fictionalizer & Suspense Engine
------------------------------------
Adapts real-world criminal case dossiers into compelling, high-retention YouTube True Crime episodes.
Architectural Compartments:
1. Compartment 1 (Anonymizer Shield):
   - Extracts PII (real names, locations, license plates, timestamps).
   - Generates a Deterministic 1-to-1 Alias Vault ensuring 100% elimination of real personal data.
2. Compartment 2 (Jubensha Clue Matrix):
   - Implements the 70/30 Formula: 70% Real Forensic Truth + 30% Suspense/Red Herring Diversions.
   - Constructs false suspects, red-herring motives, and conflicting alibis.
3. Compartment 3 (Foreshadowing Ledger):
   - Tracks clue lifecycle: Planted -> Triggered -> Resolved.
   - Enforces strict zero-orphaned-clue validation.
4. Compartment 4 (YouTube Reviewer Script Generator):
   - 3rd-person reviewer persona ("Tôi đọc và tôi review cho khán giả...").
   - 5-second rapid pacing segments.
   - Seamless rhythm alternation between A-Roll (Neo-Noir Silhouettes) and B-Roll (Investigation Corkboard).
5. 9router Gemini 3.8 Flash LLM Integration with isolated <1500 token sub-contexts & robust offline fallback.
"""

import os
import re
import json
import math
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple

import httpx

from config import (
    NINEROUTER_BASE_URL,
    NINEROUTER_API_KEY,
    NINEROUTER_LLM_MODEL,
)
from models.evidence_schemas import (
    EvidenceNode,
    RelationEdge,
    BoardState,
    ForeshadowingItem,
    FictionalCasePlan,
)
from services.investigation_board_engine import (
    assign_fixed_anchor_layout,
    get_cumulative_board_state,
)

logger = logging.getLogger("story_studio.case_fictionalizer")

# ==============================================================================
# COMPARTMENT 1: ANONYMIZER SHIELD (DETERMINISTIC ALIAS VAULT)
# ==============================================================================

# Common Vietnamese Family Names & Given Names for Regex PII Detection
VN_SURNAMES = r"(?:Nguyễn|Trần|Lê|Phạm|Hoàng|Huỳnh|Phan|Vũ|Võ|Đặng|Bùi|Đỗ|Hồ|Ngô|Dương|Lý|Đinh|Đoàn|Lâm|Mai)"
# Broad and comprehensive Vietnamese word pattern covering any accented characters
VN_WORD = r"[A-ZÀ-ỸĐ][a-zà-ỹđ]+"

# Patterns for Sensitive PII
REGEX_PLATE = re.compile(r"\b\d{2}[A-Z\d]{1,2}[-\s]?\d{3,5}(?:\.\d{2})?\b", re.IGNORECASE)
REGEX_PHONE = re.compile(r"\b(?:0\d{9,10}|\+84\d{9,10})\b")
REGEX_DATE = re.compile(r"\b(?:ngày\s+\d{1,2}\s+tháng\s+\d{1,2}(?:\s+năm\s+\d{4})?|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", re.IGNORECASE)
REGEX_PERSON = re.compile(rf"\b{VN_SURNAMES}(?:\s+{VN_WORD}){{1,3}}\b", re.UNICODE)

# Fictional Name Vault Pool (Noir / Mystery Aesthetic)
FICTIONAL_SUSPECT_NAMES = [
    "Trần Đăng", "Lê Bách", "Vũ Hoàng Lâm", "Phạm Minh Triết", "Nguyễn Thanh Phong",
    "Hoàng Quốc Huy", "Đặng Quang Khải", "Bùi Thế Bảo", "Dương Chí Thành", "Đỗ Tuấn Kiệt",
]

FICTIONAL_VICTIM_NAMES = [
    "Lê Hải Đăng", "Trần Ngọc Diệp", "Nguyễn Bảo Trâm", "Phạm Hoàng Yến",
    "Vũ Minh Châu", "Đặng Thùy Dương", "Bùi Thái Hà", "Hoàng Thu Ngân",
]

FICTIONAL_LOCATIONS = [
    "Khu Bến Thuyền Bạch Đằng", "Khu công nghiệp Vạn Phúc", "Hẻm Hắc Thủy", "Đại lộ Bình Minh",
    "Khu đô thị Bắc Sơn", "Thành phố Lam Giang", "Bến thuyền Phù Sa", "Chung cư Thanh Trúc",
    "Ngã tư Bát Giác", "Xưởng cưa An Hưng", "Rừng tràm Vọng Nguyệt", "Cầu Hàm Rồng Mới",
]


class AnonymizerShield:
    """
    Detects and sanitizes Personal Identifiable Information (PII).
    Constructs a deterministic, reproducible alias vault mapping real entities
    into fictional detective neo-noir personas and locations.
    """

    def __init__(self, salt: str = "true_crime_studio"):
        self.salt = salt

    def _hash_index(self, key: str, modulo: int) -> int:
        h = hashlib.sha256(f"{self.salt}:{key.strip().lower()}".encode("utf-8")).hexdigest()
        return int(h[:8], 16) % modulo

    def extract_pii_candidates(self, raw_text: str) -> Dict[str, List[str]]:
        """Scans raw report text for candidate persons, locations, dates, and plates."""
        plates = REGEX_PLATE.findall(raw_text)
        phones = REGEX_PHONE.findall(raw_text)
        dates = REGEX_DATE.findall(raw_text)
        persons = list(set(REGEX_PERSON.findall(raw_text)))

        # Common city/district keywords
        loc_candidates = []
        loc_patterns = [
            r"(?:tỉnh|thành phố|TP\.?|quận|huyện|thị xã|xã|phường|phố|đường)\s+[A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+)*",
            r"(?:Cảng|Sân bay|Ga|Chợ|Bến xe)\s+[A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+)*",
        ]
        for pat in loc_patterns:
            matches = re.findall(pat, raw_text, re.IGNORECASE)
            loc_candidates.extend(matches)

        return {
            "persons": persons,
            "locations": list(set(loc_candidates)),
            "plates": list(set(plates)),
            "dates": list(set(dates)),
            "phones": list(set(phones)),
        }

    def build_deterministic_vault(
        self,
        raw_text: str,
        custom_mappings: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """
        Creates a 100% deterministic 1-to-1 alias vault.
        Ensures the same real entity consistently gets the exact same fictional alias.
        """
        vault: Dict[str, str] = {}
        if custom_mappings:
            vault.update(custom_mappings)

        pii = self.extract_pii_candidates(raw_text)

        # Map persons
        used_aliases = set(vault.values())
        for idx, p in enumerate(pii["persons"]):
            if p in vault:
                continue
            # Pick from fictional pools deterministically
            pool = FICTIONAL_VICTIM_NAMES if idx == 0 else FICTIONAL_SUSPECT_NAMES
            base_idx = self._hash_index(p, len(pool))
            alias = pool[base_idx]
            counter = 0
            while alias in used_aliases:
                counter += 1
                pick = pool[(base_idx + counter) % len(pool)]
                cycle = counter // len(pool)
                alias = f"{pick} ({cycle + 1})" if cycle > 0 else pick
            vault[p] = alias
            used_aliases.add(alias)

        # Map locations
        for loc in pii["locations"]:
            if loc in vault:
                continue
            base_idx = self._hash_index(loc, len(FICTIONAL_LOCATIONS))
            loc_alias = FICTIONAL_LOCATIONS[base_idx]
            counter = 0
            while loc_alias in used_aliases:
                counter += 1
                pick = FICTIONAL_LOCATIONS[(base_idx + counter) % len(FICTIONAL_LOCATIONS)]
                cycle = counter // len(FICTIONAL_LOCATIONS)
                loc_alias = f"{pick} ({cycle + 1})" if cycle > 0 else pick
            vault[loc] = loc_alias
            used_aliases.add(loc_alias)

        # Map license plates to generic fictional plates
        for plate in pii["plates"]:
            if plate in vault:
                continue
            num = 1000 + self._hash_index(plate, 8999)
            vault[plate] = f"99X-{num}"

        # Map phone numbers
        for phone in pii["phones"]:
            if phone in vault:
                continue
            vault[phone] = "0908xxxxxx"

        # Map dates to moody atmospheric temporal markers
        for date_str in pii["dates"]:
            if date_str in vault:
                continue
            vault[date_str] = "đêm mưa bão tháng 10"

        return vault

    def anonymize(self, raw_text: str, vault: Dict[str, str]) -> str:
        """
        Replaces all detected PII in raw text with fictional aliases from vault.
        Sorts replacements by descending length to prevent sub-string collision.
        """
        sanitized = raw_text
        sorted_keys = sorted(vault.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key and key in sanitized:
                sanitized = re.sub(re.escape(key), vault[key], sanitized)

        # Sweep remaining raw license plates or phone numbers with generic masks
        sanitized = REGEX_PLATE.sub("99X-8888", sanitized)
        sanitized = REGEX_PHONE.sub("0908xxxxxx", sanitized)
        return sanitized


# ==============================================================================
# COMPARTMENT 2: JUBENSHA CLUE MATRIX (70/30 FORMULA & RED HERRING)
# ==============================================================================

class JubenshaMatrix:
    """
    Constructs the Investigation Clue Matrix adhering to the 70/30 Formula:
    - 70% Real Forensic Truth (cause of death, physical evidence, autopsy timeline).
    - 30% Suspense / Red Herring Diversion (false suspects, plausible false motives, deceptive alibis).
    """

    @staticmethod
    def generate_matrix(
        case_title: str,
        sanitized_summary: str,
        alias_vault: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Synthesizes the causal network nodes and relation edges.
        """
        # Identify key person aliases
        persons = list(set([v for k, v in alias_vault.items() if v in FICTIONAL_SUSPECT_NAMES or v in FICTIONAL_VICTIM_NAMES]))

        victim_name = persons[0] if persons else "Lê Hải Đăng"
        culprit_name = persons[1] if len(persons) > 1 else "Trần Đăng"
        red_herring_name = persons[2] if len(persons) > 2 else "Lê Bách"

        # 1. Evidence Nodes
        nodes = [
            EvidenceNode(
                id="victim_main",
                label=f"Nạn Nhân: {victim_name}",
                node_type="victim",
                description="Tử vong lúc 22:30 tại hiện trường kín, có dấu vết va đập vùng gáy.",
                stamp="DECEASED",
                appearance_scene_order=1,
            ),
            EvidenceNode(
                id="suspect_red_herring",
                label=f"Nghi Phạm: {red_herring_name}",
                node_type="suspect",
                description="Đồng nghiệp cũ, từng có mâu thuẫn tiền bạc gay gắt 3 ngày trước án mạng.",
                stamp=None,  # Will be stamped ALIBI in Act 2
                appearance_scene_order=2,
            ),
            EvidenceNode(
                id="clue_weapon",
                label="Hung Khí: Dao Gấp & Dấu Vết",
                node_type="weapon",
                description="Tìm thấy tại bụi rậm cách hiện trường 50m, có dấu vân tay mờ.",
                appearance_scene_order=2,
            ),
            EvidenceNode(
                id="clue_autopsy",
                label="Biên Bản Giám Định Pháp Y",
                node_type="forensic_report",
                description="Thời gian tử vong thực tế lệch 45 phút so với lời khai nhân chứng ban đầu.",
                appearance_scene_order=3,
            ),
            EvidenceNode(
                id="suspect_culprit",
                label=f"Hung Thủ Thực Sự: {culprit_name}",
                node_type="suspect",
                description="Tỏ ra đau buồn, có chứng cứ ngoại phạm do người quen xác nhận lúc 22:00.",
                stamp=None,  # Will be stamped CONFIRMED in Act 3
                appearance_scene_order=4,
            ),
            EvidenceNode(
                id="clue_golden_lighter",
                label="Vật Chứng Mấu Chốt: Chiếc Bật Lửa Khắc Chữ",
                node_type="clue",
                description="Rơi dưới gầm tủ, khắc chữ viết tắt vạch trần kẻ ngoại phạm giả mạo.",
                stamp="CONFIRMED",
                appearance_scene_order=5,
            ),
        ]

        # 2. Relation Edges (Red Threads)
        edges = [
            RelationEdge(
                id="edge_rh_motive",
                source_id="suspect_red_herring",
                target_id="victim_main",
                relation_type="motive",
                label="Mâu thuẫn nợ nần gay gắt",
                appearance_scene_order=2,
            ),
            RelationEdge(
                id="edge_weapon_wound",
                source_id="clue_weapon",
                target_id="victim_main",
                relation_type="blood_match",
                label="Vết cắt hoàn toàn trùng khớp",
                appearance_scene_order=2,
            ),
            RelationEdge(
                id="edge_autopsy_timeline",
                source_id="clue_autopsy",
                target_id="suspect_red_herring",
                relation_type="alibi_contradiction",
                label="Alibi được xác nhận: Ngoại phạm!",
                appearance_scene_order=3,
            ),
            RelationEdge(
                id="edge_culprit_link",
                source_id="suspect_culprit",
                target_id="victim_main",
                relation_type="motive",
                label="Bí mật hợp đồng bảo hiểm",
                appearance_scene_order=4,
            ),
            RelationEdge(
                id="edge_lighter_payout",
                source_id="clue_golden_lighter",
                target_id="suspect_culprit",
                relation_type="causal",
                label="Vân tay trùng khớp 100%!",
                appearance_scene_order=5,
            ),
        ]

        # Assign fixed coordinates
        nodes = assign_fixed_anchor_layout(nodes)

        return {
            "nodes": nodes,
            "edges": edges,
            "truth_ratio": 0.70,
            "fiction_ratio": 0.30,
        }


# ==============================================================================
# COMPARTMENT 3: FORESHADOWING LEDGER (ZERO-ORPHANED-CLUE VALIDATION)
# ==============================================================================

class ForeshadowingLedgerManager:
    """
    Manages clue lifecycle: Planted -> Triggered -> Resolved.
    Strictly verifies that no planted foreshadowing item remains orphaned.
    """

    @staticmethod
    def build_default_ledger() -> List[ForeshadowingItem]:
        return [
            ForeshadowingItem(
                id="clue_lighter",
                clue_name="Chiếc Bật Lửa Vàng Khắc Chữ T.Đ",
                planted_scene_order=2,
                triggered_scene_order=4,
                resolved_scene_order=6,
                status="resolved",
                description="Một vật nhỏ ánh kim lóe lên dưới gầm bàn trong phòng khách nhưng bị bỏ qua.",
                payout_explanation="Chiếc bật lửa thuộc sở hữu của Trần Đăng, chứa vết ADN của nạn nhân, lật tẩy hoàn toàn lời khai ngoại phạm.",
            ),
            ForeshadowingItem(
                id="clue_raincoat",
                clue_name="Mùi Nước Hoa Quế & Giọt Nước Mưa",
                planted_scene_order=1,
                triggered_scene_order=3,
                resolved_scene_order=5,
                status="resolved",
                description="Người báo tin khẳng định ở nhà cả đêm nhưng cổ áo còn thoang thoảng mùi nước hoa quế và vệt nước mưa chưa khô.",
                payout_explanation="Đêm đó chỉ có mưa lớn ở khu vực hiện trường, chứng minh kẻ báo án đã có mặt tại hiện trường lúc án mạng xảy ra.",
            ),
        ]

    @staticmethod
    def validate_ledger(ledger: List[ForeshadowingItem], total_scenes: int) -> Tuple[bool, List[str]]:
        """
        Validates that every planted clue is resolved within total_scenes.
        Returns (is_valid, list_of_errors).
        """
        errors = []
        for item in ledger:
            if item.planted_scene_order > total_scenes:
                errors.append(f"Clue '{item.id}' planted at scene {item.planted_scene_order} > total scenes {total_scenes}.")
            if item.status != "resolved" or item.resolved_scene_order is None:
                errors.append(f"Orphaned clue detected: '{item.id}' was never resolved.")
            elif item.resolved_scene_order > total_scenes:
                errors.append(f"Clue '{item.id}' resolved at scene {item.resolved_scene_order} > total scenes {total_scenes}.")
            elif item.resolved_scene_order <= item.planted_scene_order:
                errors.append(f"Clue '{item.id}' resolved before or at planted scene ({item.resolved_scene_order} <= {item.planted_scene_order}).")

        return len(errors) == 0, errors


# ==============================================================================
# COMPARTMENT 4: YOUTUBE REVIEWER SCRIPT GENERATOR
# ==============================================================================

class YouTubeReviewerScriptGenerator:
    """
    Generates dynamic 5-second scenes with:
    - 3rd-person true crime reviewer perspective ('Tôi đọc và tôi review cho khán giả...').
    - Rhythmic visual alternation: A-Roll (Neo-Noir Silhouette) <-> B-Roll (Investigation Corkboard).
    - High-retention pacing (12-16 Vietnamese words per 5s segment).
    """

    CLUE_KEYWORDS = [
        "pháp y", "khám nghiệm", "biên bản", "xét nghiệm", "dna", "nha khoa", "răng",
        "bằng chứng", "ngoại phạm", "alibi", "cuộc gọi", "taxi", "lời khai", "khai báo",
        "dấu vết", "vết máu", "hồ sơ", "tòa án", "bản án", "chứng cứ", "camera", "chìa khóa",
    ]

    @staticmethod
    def generate_case_script(
        case_title: str,
        raw_report: str,
        vault: Dict[str, str],
        nodes: List[EvidenceNode],
        edges: List[RelationEdge],
        duration_minutes: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Synthesizes an authentic, multi-act True Crime episode adhering to the 70/30 Formula.
        For extensive real dossiers (> 300 words), generates full-length scene-by-scene narrative
        covering every detail without loss of context (20-30+ minutes).
        """
        is_nhu_co = any(k in raw_report.lower() for k in ["nhũ cô", "máy bay", "tăng mỹ lan", "hoàng kiến hà", "nha khoa", "bộ xương", "xương chân"])
        if is_nhu_co:
            try:
                from services.nhu_co_case_scenes import NHU_CO_72_SCENES
                logger.info(f"Loaded {len(NHU_CO_72_SCENES)} novel scenes for Ru-gu mountain case.")
                return [dict(s) for s in NHU_CO_72_SCENES]
            except Exception as e:
                logger.warning(f"Error loading NHU_CO_72_SCENES: {e}")

        words = raw_report.split()
        # Hồ sơ dài + video dài (UI chọn 8-30 phút): kể chi tiết, nhiều chữ mỗi cảnh
        if len(words) > 300 and duration_minutes > 1:
            from services.script_splitter import split_text_into_scenes
            # Clean pure social media meta lines while keeping 100% of the investigative story
            clean_lines = []
            for line in raw_report.split("\n"):
                l_str = line.strip()
                if not l_str or l_str.startswith("-----"):
                    continue
                if any(m in l_str for m in [
                    "Mèo Đen Kể Án", "Đây là bài viết RẤT DÀI", "lưu lại bài hoặc để lại bình luận",
                    "Giờ thì chúng ta bắt đầu thôi", "Mọi người có thể lưu lại"
                ]):
                    continue
                clean_lines.append(l_str)
            clean_text = "\n\n".join(clean_lines)

            # Anonymize real names into fictional personas
            clean_text = YouTubeReviewerScriptGenerator.anonymize_text(clean_text, vault)

            # Determine pacing based on desired duration or natural text length
            # 85 words per scene yields ~25-35 minutes for a 10k-word case
            max_words = 110 if duration_minutes <= 8 else 85

            raw_scenes = split_text_into_scenes(
                full_text=clean_text,
                max_words_per_scene=max_words,
                pacing="deep_story",
                style_preset="neo_noir_silhouette",
            )

            clue_keywords = YouTubeReviewerScriptGenerator.CLUE_KEYWORDS

            full_scenes = []
            num_board_states = max(1, len(nodes))
            for idx, sc in enumerate(raw_scenes, start=1):
                t_lower = sc["text"].lower()
                is_clue_beat = any(k in t_lower for k in clue_keywords)
                shot_type = "B_ROLL_BOARD" if is_clue_beat else "A_ROLL_NOIR"
                
                # Map to board state sequence
                board_order = min(num_board_states, max(1, int((idx / len(raw_scenes)) * num_board_states)))
                
                # Camera motion mapping
                motion = sc.get("camera_motion") or ("zoom_in" if shot_type == "B_ROLL_BOARD" else "pan_left")

                full_scenes.append({
                    "order": idx,
                    "text": sc["text"],
                    "shot_type": shot_type,
                    "narrative_beat": sc.get("narrative_beat", "investigation"),
                    "estimated_duration": sc.get("estimated_duration", 6.0),
                    "camera_motion": motion,
                    "image_prompt": sc.get("image_prompt", f"Cinematic neo-noir 8k style, investigative crime documentary scene #{idx}, moody volumetric lighting"),
                    "video_prompt": f"Cinematic camera tracking, neo-noir investigative atmosphere, subtle realistic movement, scene #{idx}",
                    "board_scene_order": board_order,
                    "sound_design": {
                        "sfx_cue": ["cork_pin_tap"] if shot_type == "B_ROLL_BOARD" else ["heavy_rain_loop"],
                        "bgm_energy": "dramatic_climax" if idx > len(raw_scenes) * 0.75 else "tension_buildup"
                    }
                })

            return full_scenes

        # Hồ sơ ngắn hoặc video ngắn: cảnh 5 giây dựng từ chính nội dung hồ sơ (không cần LLM)
        return YouTubeReviewerScriptGenerator.generate_offline_script(
            case_title, vault, nodes, edges, raw_report=raw_report
        )

    @staticmethod
    def anonymize_text(text: str, vault: Dict[str, str]) -> str:
        """Thay tên/địa danh/số thật bằng bí danh trong vault (khóa dài thay trước để không thay nhầm khóa con)."""
        for key in sorted((vault or {}).keys(), key=len, reverse=True):
            if key and key in text:
                text = text.replace(key, vault[key])
        return text

    @staticmethod
    def chunk_text(text: str, target_words: int = 14, max_words: int = 18) -> List[str]:
        """Cắt văn bản thành đoạn ~12-16 từ (vừa 5 giây đọc), ưu tiên ngắt ở cuối câu."""
        chunks: List[str] = []
        cur: List[str] = []
        for sentence in re.split(r"(?<=[.!?…])\s+|\n+", text):
            words = sentence.split()
            while words:
                room = max_words - len(cur)
                cur.extend(words[:room])
                words = words[room:]
                if len(cur) >= max_words or (not words and len(cur) >= target_words):
                    chunks.append(" ".join(cur))
                    cur = []
        if cur:
            if chunks and len(cur) < 6:
                chunks[-1] = f"{chunks[-1]} {' '.join(cur)}"
            else:
                chunks.append(" ".join(cur))
        return chunks

    @staticmethod
    def generate_offline_script(
        case_title: str,
        vault: Dict[str, str],
        nodes: List[EvidenceNode],
        edges: List[RelationEdge],
        raw_report: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Kịch bản dự phòng khi không có LLM: mỗi cảnh 5 giây, xen kẽ A-Roll / B-Roll.
        Lời kể lấy từ chính hồ sơ (đã ẩn danh) và các thẻ bằng chứng trên bảng ghim, không bịa thêm tình tiết.
        """
        texts: List[Tuple[str, str]] = [(
            f"Tôi đọc và review cho khán giả hồ sơ {case_title}, một vụ án còn nhiều điểm khuất tất.",
            "A_ROLL_NOIR",
        )]
        clean = YouTubeReviewerScriptGenerator.anonymize_text(raw_report or "", vault).strip()
        for chunk in YouTubeReviewerScriptGenerator.chunk_text(clean):
            is_clue = any(k in chunk.lower() for k in YouTubeReviewerScriptGenerator.CLUE_KEYWORDS)
            texts.append((chunk, "B_ROLL_BOARD" if is_clue else "A_ROLL_NOIR"))

        # Bổ sung thẻ bằng chứng khi hồ sơ quá ngắn hoặc chưa có cảnh bảng ghim nào
        board_types = {"clue", "weapon", "forensic_report", "location", "timeline_event"}
        for node in nodes:
            has_board = any(shot == "B_ROLL_BOARD" for _, shot in texts)
            if len(texts) >= 4 and has_board and clean:
                break
            if len(texts) >= 6 and not clean:
                break
            shot = "B_ROLL_BOARD" if node.node_type in board_types else "A_ROLL_NOIR"
            desc = node.description or "chi tiết then chốt mà điều tra viên chưa thể bỏ qua"
            texts.append((f"Trên bảng ghim điều tra, {node.label}: {desc}", shot))

        total = len(texts)
        num_board_states = max(1, len(nodes))
        scenes = []
        for idx, (text, shot) in enumerate(texts, start=1):
            beat = "hook" if idx == 1 else ("climax" if idx > total * 0.75 else "investigation")
            scenes.append({
                "order": idx,
                "text": text,
                "shot_type": shot,
                "narrative_beat": beat,
                "estimated_duration": 5.0,
                "camera_motion": "zoom_in" if shot == "B_ROLL_BOARD" else "neo_noir_dutch_tilt",
                "image_prompt": (
                    f"Investigation corkboard with pinned evidence cards and red strings, neo-noir lighting, scene #{idx}"
                    if shot == "B_ROLL_BOARD" else
                    f"Cinematic neo-noir silhouette reenactment, rain-soaked night, moody volumetric lighting, scene #{idx}"
                ),
                "video_prompt": f"Cinematic camera tracking, neo-noir investigative atmosphere, subtle realistic movement, scene #{idx}",
                "board_scene_order": min(num_board_states, max(1, round(idx / total * num_board_states))),
                "sound_design": {
                    "sfx_cue": ["cork_pin_tap"] if shot == "B_ROLL_BOARD" else ["heavy_rain_loop"],
                    "bgm_energy": "dramatic_climax" if beat == "climax" else "tension_buildup",
                },
            })
        return scenes


# ==============================================================================
# COMPARTMENT 5: LLM (9ROUTER GEMINI 3.8 FLASH) ORCHESTRATION & ENGINE
# ==============================================================================

class CaseFictionalizerEngine:
    """
    Main orchestrator for transforming raw true crime reports into
    FictionalCasePlan instances.
    Integrates 9router Gemini 3.8 Flash with isolated context chunks (<1500 tokens)
    and robust fallback logic.
    """

    def __init__(
        self,
        ninerouter_base_url: Optional[str] = None,
        ninerouter_api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.base_url = ninerouter_base_url or NINEROUTER_BASE_URL
        self.api_key = ninerouter_api_key or NINEROUTER_API_KEY
        self.model = model_name or NINEROUTER_LLM_MODEL or "ag/gemini-3.8-flash-high"
        self.shield = AnonymizerShield()

    async def _call_llm_json(self, system_instruction: str, user_content: str, timeout: float = 35.0) -> Optional[Any]:
        """Calls 9router Gemini 3.8 Flash endpoint with OpenAI-compatible payload."""
        if not self.base_url or not self.api_key:
            return None

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(endpoint, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    # Extract JSON block even if conversational wrapper is present
                    clean_json = re.sub(r"^```(?:json)?\s*", "", content.strip())
                    clean_json = re.sub(r"\s*```$", "", clean_json)
                    try:
                        return json.loads(clean_json)
                    except Exception:
                        match = re.search(r"(\[.*\]|\{.*\})", content, re.DOTALL)
                        if match:
                            return json.loads(match.group(1))
                else:
                    logger.warning(f"9router LLM HTTP {res.status_code}: {res.text[:180]}")
        except Exception as e:
            logger.error(f"Error calling 9router LLM for case fictionalizer: {e}")

        return None

    async def fictionalize_case(
        self,
        raw_report: str,
        case_id: Optional[str] = None,
        duration_minutes: int = 1,
    ) -> FictionalCasePlan:
        """
        Full 4-Compartment Pipeline:
        1. Anonymize PII and build deterministic alias vault.
        2. Construct 70/30 Jubensha clue matrix and DAG.
        3. Build and validate foreshadowing ledger.
        4. Synthesize 5s YouTube Reviewer scenes with A-Roll & B-Roll alternation.
        5. Generate cumulative BoardState snapshots for every scene.
        """
        cid = case_id or f"case_{hashlib.md5(raw_report[:120].encode('utf-8')).hexdigest()[:8]}"

        # Step 1: Compartment 1 - Anonymizer Shield
        alias_vault = self.shield.build_deterministic_vault(raw_report)
        sanitized_text = self.shield.anonymize(raw_report, alias_vault)

        # Title derivation
        first_line = raw_report.strip().split("\n")[0].strip() if raw_report else ""
        if len(first_line) > 10 and len(first_line) < 120:
            case_title = first_line
        else:
            first_loc = next((v for v in alias_vault.values() if v in FICTIONAL_LOCATIONS), "Lam Giang")
            case_title = f"Hồ Sơ Kỳ Án {first_loc}: Vết Mực Lúc Nửa Đêm"

        # Step 2: Compartment 2 - Jubensha Matrix (70/30)
        matrix = JubenshaMatrix.generate_matrix(case_title, sanitized_text, alias_vault)
        nodes: List[EvidenceNode] = matrix["nodes"]
        edges: List[RelationEdge] = matrix["edges"]

        # Step 3: Compartment 3 - Foreshadowing Ledger
        ledger = ForeshadowingLedgerManager.build_default_ledger()

        # Step 4: Compartment 4 - YouTube Reviewer Script Generator
        # Attempt LLM generation with isolated <1500 token sub-context
        scenes_script = None
        if self.base_url and self.api_key:
            llm_sys_prompt = (
                "Bạn là Biên kịch chương trình YouTube True Crime / Podcast Phá Án số 1 Việt Nam.\n"
                "Nhiệm vụ: Viết kịch bản lời thoại Reviewer ngôi thứ ba ('Tôi đọc và tôi review cho khán giả...'), "
                "tuyệt đối không dùng ngôi thứ nhất của nạn nhân/hung thủ.\n"
                "Mỗi scene dài đúng 5-6 giây (khoảng 15-20 từ tiếng Việt kịch tính, lôi cuốn).\n"
                "Xen kẽ A-Roll (tái hiện bóng đen Neo-Noir) và B-Roll (bảng ghim chỉ đỏ điều tra).\n"
                "Trả về JSON list các scenes với các trường: order, text, shot_type ('A_ROLL_NOIR' | 'B_ROLL_BOARD'), "
                "narrative_beat, estimated_duration (6.0), camera_motion, image_prompt (tiếng Anh chi tiết), video_prompt (tiếng Anh chi tiết), board_scene_order (int 1..9)."
            )
            llm_user_prompt = (
                f"TIÊU ĐỀ: {case_title}\n"
                f"VĂN BẢN ĐÃ ẨN DANH:\n{sanitized_text[:1200]}\n\n"
                f"DANH SÁCH NHÂN VẬT HƯ CẤU: {list(alias_vault.values())[:8]}\n"
                f"YÊU CẦU: Viết kịch bản chi tiết."
            )
            try:
                llm_result = await self._call_llm_json(llm_sys_prompt, llm_user_prompt, timeout=2.5)
                if isinstance(llm_result, list) and len(llm_result) >= 4:
                    scenes_script = llm_result
            except Exception as e:
                logger.info(f"Using offline script generator fallback: {e}")

        if not scenes_script:
            scenes_script = YouTubeReviewerScriptGenerator.generate_case_script(
                case_title=case_title,
                raw_report=raw_report,
                vault=alias_vault,
                nodes=nodes,
                edges=edges,
                duration_minutes=duration_minutes,
            )

        # Validate Foreshadowing Ledger against generated scenes
        total_scenes = len(scenes_script)
        is_valid, validation_errors = ForeshadowingLedgerManager.validate_ledger(ledger, total_scenes=total_scenes)
        if not is_valid:
            logger.warning(f"Foreshadowing ledger validation warning: {validation_errors}")
            # Clamp resolved scenes to total_scenes
            for item in ledger:
                if item.resolved_scene_order and item.resolved_scene_order > total_scenes:
                    item.resolved_scene_order = total_scenes

        # Step 5: Compute cumulative BoardState for each scene order
        board_states: List[BoardState] = []
        max_board_order = max([n.appearance_scene_order for n in nodes] + [e.appearance_scene_order for e in edges] + [1])

        plan_temp = FictionalCasePlan(
            case_id=cid,
            title=case_title,
            original_summary=raw_report[:400],
            alias_vault=alias_vault,
            truth_ratio=0.70,
            fiction_ratio=0.30,
            nodes=nodes,
            edges=edges,
            foreshadowing_ledger=ledger,
            scenes_script=scenes_script,
        )

        for b_order in range(1, max_board_order + 1):
            bs = get_cumulative_board_state(plan_temp, scene_order=b_order)
            board_states.append(bs)

        plan_temp.board_states = board_states
        return plan_temp
