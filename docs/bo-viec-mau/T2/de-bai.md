# Việc: đo thời lượng âm thanh không được thì đừng đoán 3 giây

Lỗi "thành công giả" (đường cấm 3 trong `CLAUDE.md`): `get_audio_duration()` trong `backend/services/tts_service.py` không đo được thời lượng (thiếu ffprobe, file không có, file hỏng) thì trả 3,0 giây như thể đã đo. Video bị cắt hoặc kéo sai độ dài mà không ai biết.

Kết quả mong đợi:

1. Không đo được thì báo lỗi `MediaDurationError` (lớp lỗi mới, đặt trong `services/tts_service.py`). Thông báo lỗi có tên file và lý do không đo được.
2. Đo được thì trả số giây thật như cũ (file im lặng 2 giây đo ra sai số dưới 0,15 giây).
3. Phụ đề karaoke (`extract_word_timestamps()` trong `services/subtitle_engine.py`) không được sập vì lỗi mới. Không đo được thì ghi log rồi ước lượng như khi không có file âm thanh: dùng `fallback_duration` nếu có, không thì theo số chữ.
4. Những chỗ gọi khác giữ nguyên, để lỗi nổi lên (không bắt lỗi rồi đoán một con số khác).
5. Test cũ nào đang đạt nhờ con số đoán 3 giây thì sửa test cho đúng (cho thời lượng giả rõ ràng ngay trong test), không giữ số đoán trong code.

Phạm vi được sửa: `backend/services/tts_service.py`, `backend/services/subtitle_engine.py`, thư mục `tests/`; cập nhật `CLAUDE.md`, `FEATURE_MAP.md`, `TASKS.md` khi quy tắc dự án yêu cầu; `tools/ruff_baseline.json` chỉ được hạ mốc. Không sửa file khác.
