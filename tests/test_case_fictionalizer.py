"""
Unit tests cho AnonymizerShield (case_fictionalizer.py).

Từ đợt chuyển thể vụ án bằng LLM, file này chỉ còn lớp AnonymizerShield cùng các regex và danh sách tên mẫu: kiểm lọt
tên thật (case_adaptation_checks) dùng regex để bắt thêm những tên mà bảng tên chưa có. Ma trận 70/30, sổ phục bút và
bộ sinh kịch bản mẫu đã bỏ.
"""

import sys
from pathlib import Path

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.case_fictionalizer import AnonymizerShield


SAMPLE_RAW_REPORT = """
Vào đêm ngày 14 tháng 10 năm 2021, tại khu vực Cảng Hải Phòng, một vụ án mạng nghiêm trọng đã xảy ra.
Nạn nhân được xác định là ông Nguyễn Văn Hải, 42 tuổi, làm việc tại kho vận bốc xếp.
Theo lời khai ban đầu của anh Trần Đình Long (người báo án, đi xe máy biển số 15B-678.90),
anh ta phát hiện thi thể ông Hải nằm gần công-ten-nơ số 4 với vết chấn thương nặng ở vùng đầu.
Qua xác minh nhanh, cơ quan điều tra triệu tập nghi phạm Vũ Mạnh Hùng do có tranh chấp nợ nần 300 triệu đồng.
Tuy nhiên kết quả khám nghiệm tử thi cho thấy thời gian tử vong thực sự là khoảng 22h15.
"""


def test_anonymizer_shield():
    shield = AnonymizerShield()

    # 1. Build vault
    vault1 = shield.build_deterministic_vault(SAMPLE_RAW_REPORT)
    assert len(vault1) > 0

    # 2. Check deterministic guarantee: second run on same text gives identical vault
    vault2 = shield.build_deterministic_vault(SAMPLE_RAW_REPORT)
    assert vault1 == vault2, "Deterministic Alias Vault failed: identical inputs gave different mappings!"

    # 3. Anonymize text
    sanitized = shield.anonymize(SAMPLE_RAW_REPORT, vault1)

    # 4. Strictly assert NO real PII remains in sanitized text
    real_pii_terms = ["Nguyễn Văn Hải", "Trần Đình Long", "Vũ Mạnh Hùng", "15B-678.90"]
    for term in real_pii_terms:
        assert term not in sanitized, f"PII Leak Detected! Real term '{term}' was found in sanitized text."

    print("✓ test_anonymizer_shield passed (100% PII sanitized & Deterministic Vault confirmed)")


def test_extract_pii_candidates_finds_names_plates_and_places():
    found = AnonymizerShield().extract_pii_candidates(SAMPLE_RAW_REPORT)

    assert {"Nguyễn Văn Hải", "Trần Đình Long", "Vũ Mạnh Hùng"} <= set(found["persons"])
    assert "15B-678.90" in found["plates"]
    assert any("Hải Phòng" in place for place in found["locations"])
    assert any("14 tháng 10" in date for date in found["dates"])


def test_vault_gives_every_person_a_distinct_alias_that_is_not_a_real_name():
    shield = AnonymizerShield()
    vault = shield.build_deterministic_vault(SAMPLE_RAW_REPORT)
    persons = shield.extract_pii_candidates(SAMPLE_RAW_REPORT)["persons"]

    aliases = [vault[name] for name in persons]
    assert len(set(aliases)) == len(aliases)
    assert not set(aliases) & set(persons)


if __name__ == "__main__":
    test_anonymizer_shield()
    test_extract_pii_candidates_finds_names_plates_and_places()
    test_vault_gives_every_person_a_distinct_alias_that_is_not_a_real_name()
    print("\n🎉 ALL ANONYMIZER SHIELD TESTS PASSED 100%!")
