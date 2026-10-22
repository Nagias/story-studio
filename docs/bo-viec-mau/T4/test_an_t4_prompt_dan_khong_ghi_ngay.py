"""Test ẩn bổ sung của bộ việc mẫu T4 (docs/bo-viec-mau): chỉ chép vào tests/ của bản chấm, không thuộc bộ test dự án.

Yêu cầu 6 của đề: prompt bước đọc bài dặn LLM không ghi ngày, tháng, năm trong nhãn bằng chứng và nhãn quan hệ.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "backend" / "services" / "case_adaptation_prompts.py"
_DATE_WORDS = re.compile(r"ngày|tháng|năm|date", re.IGNORECASE)


def test_prompt_doc_bai_dan_khong_ghi_ngay_trong_nhan():
    lines = SRC.read_text(encoding="utf-8").splitlines()
    label_lines = [i for i, line in enumerate(lines) if '"label_vi", "label_en":' in line]
    assert len(label_lines) >= 2, "không thấy dòng mô tả nhãn bằng chứng/quan hệ trong prompt đọc bài"
    missing = [lines[i].strip() for i in label_lines if not _DATE_WORDS.search(" ".join(lines[i:i + 3]))]
    assert not missing, "Dòng mô tả nhãn chưa dặn không ghi ngày tháng:\n" + "\n".join(missing)
