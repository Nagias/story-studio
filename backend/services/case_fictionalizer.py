"""
Anonymizer Shield (regex bắt tên thật) cho chuyển thể vụ án
-----------------------------------------------------------
Còn lại sau khi bỏ luồng cũ (ma trận 70/30, sổ phục bút, bộ sinh kịch bản mẫu, CaseFictionalizerEngine): việc chuyển thể
nay do LLM làm qua hàng việc (services/case_worker, case_adaptation_steps).

Giữ lại vì kiểm lọt tên thật (services/case_adaptation_checks) dùng AnonymizerShield.extract_pii_candidates để bắt thêm
những tên mà bảng tên của LLM chưa có:
- các regex REGEX_PERSON / REGEX_PLATE / REGEX_PHONE / REGEX_DATE và họ Việt VN_SURNAMES;
- danh sách tên mẫu FICTIONAL_* của AnonymizerShield.build_deterministic_vault (vault tên giả cố định, 1-1).
"""

import re
import hashlib
from typing import List, Dict, Optional

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
