# QA Test Report: Story Studio - Text-to-Speech (TTS) Subsystem

- **Ngày kiểm thử:** 2026-10-16
- **Môi trường:** Windows 11 x64, Python 3.14.6, pytest-9.1.1, uv
- **Tester:** qa-engineer (Agent Team)
- **Kết quả chung:** **PASS (19/19 tests passed - 100%)**
- **Thời gian thực thi:** 54.35s

---

## 1. Mục tiêu kiểm thử
Xác nhận chất lượng, tính chính xác và khả năng chịu lỗi của phân hệ Text-to-Speech (TTS) theo Task-3:
1. Bộ lọc văn bản `normalize_narration_text` loại bỏ triệt để nhãn thoại, chỉ dẫn đạo diễn, cảm xúc trong ngoặc và hiệu ứng âm thanh (SFX).
2. Phát hiện ngôn ngữ (`detect_language`) và định tuyến thông minh (Smart Voice Routing): text tiếng Anh không đưa vào giọng tiếng Việt/VieNeu gây méo tiếng.
3. Sinh giọng đọc thực tế với Edge-TTS (Tiếng Việt & Tiếng Anh) và VieNeu (Tiếng Việt), kiểm tra dung lượng âm thanh (> 0 bytes), thời lượng (duration > 1.0s) và định dạng phụ đề SRT chuẩn SubRip.

---

## 2. Chi tiết các Test Case đã thực thi

| STT | Tên Test Case | Phạm vi kiểm thử | Kết quả | Ghi chú |
|:---:|:---|:---|:---:|:---|
| 1 | `test_normalize_narration_text_emotion_cues` | Lọc bỏ 18 chỉ dẫn cảm xúc trong ngoặc `(thì thầm)`, `(hồi hộp)`, `(gào thét)`, `(la lớn)`, v.v. | **PASS** | Sạch 100% cảm xúc |
| 2 | `test_normalize_narration_text_sfx_and_visual_cues` | Lọc bỏ SFX, âm thanh, visual cue `[SFX: ...]`, `[tiếng nổ]`, `[Prompt: ...]`, `[Visual: ...]` | **PASS** | Không rò rỉ vào kịch bản |
| 3 | `test_normalize_narration_text_emotion_and_sfx_mixed` | Chuỗi phức tạp `(thì thầm) Cứu tôi với! [tiếng sấm]` -> `Cứu tôi với!` | **PASS** | Không còn chữ "thì thầm" hay "tiếng sấm" |
| 4 | `test_normalize_narration_text_speaker_labels` | Lọc nhãn vai `Người dẫn chuyện:`, `Narrator:`, `[Lâm]:`, `Cảnh 1:`, `Scene 1:` | **PASS** | Loại bỏ nhãn ở đầu & xuống dòng |
| 5 | `test_normalize_narration_text_preserves_explanatory_parentheses` | Giữ lại nội dung giải thích bình thường trong ngoặc đơn, unwrap ngoặc | **PASS** | Đúng ngữ nghĩa kịch bản |
| 6 | `test_normalize_narration_text_markdown_and_emojis` | Lọc markdown (`**`, `*`, `~~`, `#`, `>`), emoji (`🔥`, `🚀`), chuẩn hóa dấu câu | **PASS** | Ngăn ngừa TTS hallucination |
| 7 | `test_normalize_narration_text_empty_and_cues_only` | Text rỗng hoặc chỉ toàn cue trả về chuỗi rỗng `""` | **PASS** | Chuẩn hóa an toàn |
| 8 | `test_detect_language` | Phân biệt tiếng Việt (`vi`) và tiếng Anh (`en`) chính xác | **PASS** | 100% chính xác |
| 9 | `test_voice_catalog` | Catalog đầy đủ 14 voices tuyển chọn: Edge-TTS Việt, VieNeu Việt, Edge-TTS Anh | **PASS** | Metadata đầy đủ theo schema |
| 10 | `test_srt_timestamp_formatting` | Format mốc thời gian SRT chuẩn `00:00:00,000` | **PASS** | Độ chính xác mili-giây |
| 11 | `test_fallback_srt_generator` | Sinh cue phụ đề fallback an toàn khi không có word boundary | **PASS** | Hợp lệ chuẩn SubRip |
| 12 | `test_get_audio_duration_accuracy` | Đo độ dài file âm thanh với ffprobe/PyAV/fallback | **PASS** | Chống crash khi thiếu file |
| 13 | `test_tts_empty_text_error` | Bắt lỗi `ValueError` khi text rỗng hoặc chỉ chứa cue sau lọc | **PASS** | Thông báo lỗi minh bạch |
| 14 | `test_english_text_routed_from_vietnamese_voice` | Text tiếng Anh + VieNeu (Thiện Minh, Mai Anh) -> Tự động fallback sang Andrew & Ava Multilingual | **PASS** | `fallback_used == True`, audio > 0 bytes |
| 15 | `test_tts_vietnamese_namminh_with_cleaning` | Sinh âm thanh thực tế giọng Nam Minh (`vi-VN-NamMinhNeural`) + lọc nhãn & cảm xúc | **PASS** | Audio > 1KB, SRT hợp lệ |
| 16 | `test_tts_vietnamese_hoaimy` | Sinh âm thanh thực tế giọng Hoài My (`vi-VN-HoaiMyNeural`) | **PASS** | Audio > 2KB, duration > 1.0s |
| 17 | `test_tts_english_andrew` | Sinh âm thanh thực tế giọng Andrew (`en-US-AndrewMultilingualNeural`) | **PASS** | Audio > 1KB, duration > 1.0s |
| 18 | `test_tts_english_ava` | Sinh âm thanh thực tế giọng Ava (`en-US-AvaMultilingualNeural`) | **PASS** | Audio > 2KB, duration > 1.0s |
| 19 | `test_tts_vietnamese_vieneu_maianh_or_fallback` | Sinh âm thanh với VieNeu Mai Anh (`vieneu-MaiAnh`) hoặc fallback minh bạch sang Hoài My | **PASS** | Audio > 1KB, phụ đề chuẩn |

---

## 3. Tiêu chí nghiệm thu (Acceptance Criteria)

1. **Exit Code:** `$LASTEXITCODE == 0` trên Windows PowerShell.
2. **Artifacts:** Các file âm thanh MP3 và phụ đề SRT được sinh ra thực tế trong thư mục tạm, kích thước > 0 bytes (> 1KB - 2KB), có thể phát bình thường.
3. **Phụ đề SRT:** Khớp 100% với nội dung lời thoại đã làm sạch; tuyệt đối không sót nhãn người nói (`Người dẫn chuyện:`) hay chỉ dẫn cảm xúc (`(thì thầm)`).
4. **Console Cleanliness:** Không có unhandled exception, traceback hoặc lỗi mã hóa `UnicodeEncodeError` trên Windows.
