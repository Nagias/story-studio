"""Test ẩn bổ sung của bộ việc mẫu T2 (docs/bo-viec-mau): chỉ chép vào tests/ của bản chấm, không thuộc bộ test dự án.

Yêu cầu 3 của đề: phụ đề karaoke không đo được thời lượng file âm thanh thì không sập, ước lượng theo fallback_duration
(không dùng con số đoán 3 giây).
"""
import sys


def test_phu_de_karaoke_khong_do_duoc_thi_dung_thoi_luong_du_phong(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)   # không thử tải model nhận giọng
    from services.subtitle_engine import extract_word_timestamps
    broken = tmp_path / "hong.mp3"
    broken.write_bytes(b"khong phai am thanh")
    words = extract_word_timestamps(str(broken), expected_text="Một hai ba bốn năm sáu bảy tám",
                                    language="vi", fallback_duration=7.0)
    assert len(words) == 8
    assert abs(words[-1]["end"] - 7.0) < 0.6, f"chữ cuối kết thúc ở {words[-1]['end']} giây, mong đợi gần 7 giây"
