import os
import re
import shutil
import subprocess
import sys
import pytest
from pathlib import Path

# Add backend directory to sys.path
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Ensure UTF-8 console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from services.tts_service import (
    get_available_voices,
    generate_speech,
    get_audio_duration,
    format_srt_timestamp,
    create_fallback_srt,
    normalize_narration_text,
    detect_language,
    AVAILABLE_VOICES,
)


def validate_srt_content(srt_text: str, expected_snippet: str = "") -> bool:
    """Validate that SRT content conforms to SubRip standard format."""
    lines = [l.strip() for l in srt_text.strip().split("\n") if l.strip()]
    if not lines:
        return False

    # Timestamp pattern: 00:00:00,000 --> 00:00:00,000
    ts_pattern = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}$")
    has_valid_timestamp = any(ts_pattern.match(l) for l in lines)
    if not has_valid_timestamp:
        return False

    if expected_snippet and expected_snippet.lower() not in srt_text.lower():
        return False

    return True


# ==============================================================================
# 1. UNIT TESTS: Text Normalization and Cleaning
# ==============================================================================

def test_normalize_narration_text_emotion_cues():
    """Verify emotion, delivery, and acting cues in parentheses/brackets are completely stripped."""
    cues = [
        ("(thì thầm) Xin chào các bạn.", "Xin chào các bạn."),
        ("Anh ấy nhìn quanh (hồi hộp) rồi bước tiếp.", "Anh ấy nhìn quanh rồi bước tiếp."),
        ("Không thể nào! (gào thét)", "Không thể nào!"),
        ("Chạy nhanh lên! (tiếng thở dốc)", "Chạy nhanh lên!"),
        ("(nói nhỏ) Hãy cẩn thận.", "Hãy cẩn thận."),
        ("Haha vui quá (cười lớn) thật tuyệt.", "Haha vui quá thật tuyệt."),
        ("Tôi nhớ mẹ (khóc nức nở) rất nhiều.", "Tôi nhớ mẹ rất nhiều."),
        ("(ngạc nhiên) Cái gì cơ?", "Cái gì cơ?"),
        ("(hoảng sợ) Mau trốn đi!", "Mau trốn đi!"),
        ("Đôi tay anh (run rẩy) cầm lấy thanh kiếm.", "Đôi tay anh cầm lấy thanh kiếm."),
        ("Thôi được rồi (thở dài) chúng ta bắt đầu.", "Thôi được rồi chúng ta bắt đầu."),
        ("(ngậm ngùi) Kỷ niệm xưa ùa về.", "Kỷ niệm xưa ùa về."),
        ("(tức giận) Ngươi dám lừa ta!", "Ngươi dám lừa ta!"),
        ("(la lớn) Cứu tôi với!", "Cứu tôi với!"),
        ("(thì thầm) Cứu tôi với! [tiếng sấm]", "Cứu tôi với!"),
        ("(lo lắng) Không biết chuyện gì sẽ xảy ra.", "Không biết chuyện gì sẽ xảy ra."),
        ("Narrator: Once upon a time (whispering) in the forest.", "Once upon a time in the forest."),
        ("He looked around, (gasps) seeing the monster.", "He looked around, seeing the monster."),
        ("Finally, (sighs) we made it home.", "Finally, we made it home."),
    ]
    for raw, expected in cues:
        cleaned = normalize_narration_text(raw)
        assert cleaned == expected, f"Failed for {raw!r}: got {cleaned!r}, expected {expected!r}"


def test_normalize_narration_text_sfx_and_visual_cues():
    """Verify SFX, audio, music, visual, and prompt cues are completely stripped."""
    sfx_samples = [
        ("[SFX: tiếng sấm rền] Trời bắt đầu đổ mưa to.", "Trời bắt đầu đổ mưa to."),
        ("Bỗng nhiên có tiếng nổ lớn [tiếng nổ lớn] làm rung chuyển mặt đất.", "Bỗng nhiên có tiếng nổ lớn làm rung chuyển mặt đất."),
        ("[nhạc nền kịch tính] Quân địch bắt đầu tấn công.", "Quân địch bắt đầu tấn công."),
        ("[âm thanh mưa rơi] Đêm dần trôi qua trong lạnh giá.", "Đêm dần trôi qua trong lạnh giá."),
        ("[sound: heavy explosion] The fortress fell.", "The fortress fell."),
        ("(Hình ảnh: Lâm đứng nhìn về phía chân trời xa xăm) Gió thổi nhẹ qua làn tóc.", "Gió thổi nhẹ qua làn tóc."),
        ("[Visual: cinematic close-up of dragon eyes] The beast awakened.", "The beast awakened."),
        ("[Prompt: dark mysterious cave, high detail] Hang động tối om và ẩm ướt.", "Hang động tối om và ẩm ướt."),
        ("[Visual Prompt: heroic knight standing] Hiệp sĩ giơ cao thanh gươm.", "Hiệp sĩ giơ cao thanh gươm."),
        ("[Camera: wide panoramic view] Thung lũng trải dài ngút ngàn.", "Thung lũng trải dài ngút ngàn."),
    ]
    for raw, expected in sfx_samples:
        cleaned = normalize_narration_text(raw)
        assert cleaned == expected, f"Failed for {raw!r}: got {cleaned!r}, expected {expected!r}"


def test_normalize_narration_text_emotion_and_sfx_mixed():
    """Verify mixed emotion and sfx cues like '(thì thầm) Cứu tôi với! [tiếng sấm]' -> 'Cứu tôi với!'."""
    raw = "(thì thầm) Cứu tôi với! [tiếng sấm]"
    cleaned = normalize_narration_text(raw)
    assert cleaned == "Cứu tôi với!"
    assert "thì thầm" not in cleaned
    assert "tiếng sấm" not in cleaned


def test_normalize_narration_text_speaker_labels():
    """Verify speaker and scene prefixes at the start or line breaks are cleanly stripped."""
    speakers = [
        ("Người dẫn chuyện: Đêm hôm đó, khu rừng chìm trong tĩnh lặng.", "Đêm hôm đó, khu rừng chìm trong tĩnh lặng."),
        ("Narrator: Long ago in a distant kingdom, peace reigned.", "Long ago in a distant kingdom, peace reigned."),
        ("Dẫn chuyện: Ngày xưa có hai anh em nhà nọ.", "Ngày xưa có hai anh em nhà nọ."),
        ("[Lâm]: Cứu tôi với! (hét lớn)", "Cứu tôi với!"),
        ("[Người dẫn chuyện]: Mặt trời dần lặn sau rặng núi.", "Mặt trời dần lặn sau rặng núi."),
        ("(Người dẫn chuyện): Đêm nay trăng rất sáng.", "Đêm nay trăng rất sáng."),
        ("[Nhân vật 1]: Chúng ta phải xuất phát ngay.", "Chúng ta phải xuất phát ngay."),
        ("[Nhân vật Lâm]: Tôi đã hiểu ra mọi chuyện.", "Tôi đã hiểu ra mọi chuyện."),
        ("Lâm: Tôi không sợ đâu!", "Tôi không sợ đâu!"),
        ("Main: Đây chính là mục tiêu của chúng ta.", "Đây chính là mục tiêu của chúng ta."),
        ("MC: Kính chào quý khán giả đang theo dõi.", "Kính chào quý khán giả đang theo dõi."),
        ("Host: Welcome to today's episode.", "Welcome to today's episode."),
        ("Voiceover: Everything changed after that summer.", "Everything changed after that summer."),
        ("V.O.: Looking back, it was the best decision.", "Looking back, it was the best decision."),
        ("Cảnh 1: Trong căn nhà nhỏ ven suối.", "Trong căn nhà nhỏ ven suối."),
        ("Scene 1: Inside the high-tech laboratory.", "Inside the high-tech laboratory."),
        ("Phân cảnh 2: Ngoài bờ sông lộng gió.", "Ngoài bờ sông lộng gió."),
        # Nested prefixes
        ("Cảnh 1: Người dẫn chuyện: (thì thầm) Trong đêm tối, cậu bé bước đi.", "Trong đêm tối, cậu bé bước đi."),
    ]
    for raw, expected in speakers:
        cleaned = normalize_narration_text(raw)
        assert cleaned == expected, f"Failed for {raw!r}: got {cleaned!r}, expected {expected!r}"


def test_normalize_narration_text_preserves_explanatory_parentheses():
    """Verify legitimate explanatory text in parentheses is preserved while stripping brackets."""
    explanatory = [
        ("Hà Nội (thủ đô của Việt Nam) rất đẹp vào mùa thu.", "Hà Nội thủ đô của Việt Nam rất đẹp vào mùa thu."),
        ("Lâm (người bạn thân nhất của tôi) đã quay trở về.", "Lâm người bạn thân nhất của tôi đã quay trở về."),
        ("Vào năm 1945 (năm Ất Dậu) đã diễn ra nhiều biến cố lớn.", "Vào năm 1945 năm Ất Dậu đã diễn ra nhiều biến cố lớn."),
        ("Chiếc xe (màu đỏ tươi) phóng nhanh qua phố.", "Chiếc xe màu đỏ tươi phóng nhanh qua phố."),
        ("Three hundred warriors (the elite royal guard) stood firm.", "Three hundred warriors the elite royal guard stood firm."),
    ]
    for raw, expected in explanatory:
        cleaned = normalize_narration_text(raw)
        assert cleaned == expected, f"Failed for {raw!r}: got {cleaned!r}, expected {expected!r}"


def test_normalize_narration_text_markdown_and_emojis():
    """Verify markdown markers, hashtags, bullets, emojis, and quotes are normalized."""
    samples = [
        ("**Chào mừng** bạn đến với *Story Studio*! 🔥 🚀", "Chào mừng bạn đến với Story Studio!"),
        ("***Đặc biệt quan trọng*** trong câu chuyện này.", "Đặc biệt quan trọng trong câu chuyện này."),
        ("# Tiêu đề chương một\n> Trích dẫn bài học lịch sử", "Tiêu đề chương một Trích dẫn bài học lịch sử"),
        ("~~Từ bị gạch~~ và `mã lệnh` trong văn bản.", "Từ bị gạch và mã lệnh trong văn bản."),
        ('"Xin chào", cô ấy nói: \'Hãy đi tiếp\'.', "Xin chào, cô ấy nói: Hãy đi tiếp."),
        ("Mưa rơi rất to... sấm chớp đùng đùng!! Thật đáng sợ??", "Mưa rơi rất to. sấm chớp đùng đùng! Thật đáng sợ?"),
        ("Con đường dài — gập ghềnh và khó khăn.", "Con đường dài, gập ghềnh và khó khăn."),
    ]
    for raw, expected in samples:
        cleaned = normalize_narration_text(raw)
        assert cleaned == expected, f"Failed for {raw!r}: got {cleaned!r}, expected {expected!r}"


def test_normalize_narration_text_empty_and_cues_only():
    """Verify empty inputs or cue-only texts return empty string."""
    empty_samples = [
        "",
        "   ",
        "(thì thầm)",
        "[SFX: tiếng sấm rền]",
        "Người dẫn chuyện:",
        "Narrator: ",
        "Cảnh 1: ",
        "[Visual: close-up shot]",
        "(Hình ảnh: cậu bé nhìn xa xăm)",
        "(thì thầm) [SFX: tiếng sấm]",
    ]
    for raw in empty_samples:
        cleaned = normalize_narration_text(raw)
        assert cleaned == "", f"Expected empty string for {raw!r}, got {cleaned!r}"


# ==============================================================================
# 2. UNIT TESTS: Language Detection
# ==============================================================================

def test_detect_language():
    """Verify accurate detection of Vietnamese vs English."""
    vn_samples = [
        "Xin chào tất cả các bạn, tôi là người dẫn chuyện.",
        "Ngày xửa ngày xưa, trong một khu rừng kỳ diệu có chú rồng lửa.",
        "Hôm nay trời nắng đẹp, gió thổi nhè nhẹ bên bờ hồ Tây.",
        "Đêm hôm đó, khu rừng chìm trong tĩnh lặng huyền bí.",
    ]
    for text in vn_samples:
        assert detect_language(text) == "vi", f"Expected 'vi' for: {text}"

    en_samples = [
        "Once upon a time in a peaceful ancient forest.",
        "At the narrow cliffside Gates of Fire, three hundred warriors stood unyielding.",
        "Hello everyone, welcome to Story Studio AI narrative generator.",
        "King Leonidas raised his notched ash-wood spear against the blistering sun.",
        "The dark clouds gathered over the mysterious mountain peak.",
    ]
    for text in en_samples:
        assert detect_language(text) == "en", f"Expected 'en' for: {text}"


# ==============================================================================
# 3. UNIT TESTS: Voice Catalog Metadata
# ==============================================================================

def test_voice_catalog():
    """Verify available voices catalog contains required Vietnamese and English voices."""
    voices = get_available_voices()
    assert isinstance(voices, list)
    assert len(voices) >= 12, f"Expected at least 12 curated voices, found {len(voices)}"

    voice_ids = {v["id"] for v in voices}

    # Vietnamese Edge-TTS
    assert "vi-VN-NamMinhNeural" in voice_ids, "Missing vi-VN-NamMinhNeural"
    assert "vi-VN-HoaiMyNeural" in voice_ids, "Missing vi-VN-HoaiMyNeural"

    # VieNeu voices
    assert "vieneu-MaiAnh" in voice_ids, "Missing vieneu-MaiAnh"
    assert "vieneu-TrucLy" in voice_ids, "Missing vieneu-TrucLy"
    assert "vieneu-MyDuyen" in voice_ids, "Missing vieneu-MyDuyen"
    assert "vieneu-ThienMinh" in voice_ids, "Missing vieneu-ThienMinh"
    assert "vieneu-HaiDang" in voice_ids, "Missing vieneu-HaiDang"

    # English Edge-TTS voices
    assert "en-US-AndrewMultilingualNeural" in voice_ids, "Missing en-US-AndrewMultilingualNeural"
    assert "en-US-BrianMultilingualNeural" in voice_ids, "Missing en-US-BrianMultilingualNeural"
    assert "en-US-AvaMultilingualNeural" in voice_ids, "Missing en-US-AvaMultilingualNeural"
    assert "en-US-EmmaMultilingualNeural" in voice_ids, "Missing en-US-EmmaMultilingualNeural"
    assert "en-US-ChristopherNeural" in voice_ids, "Missing en-US-ChristopherNeural"
    assert "en-US-JennyNeural" in voice_ids, "Missing en-US-JennyNeural"
    assert "en-US-GuyNeural" in voice_ids, "Missing en-US-GuyNeural"

    # Verify schema fields for all voices
    for v in voices:
        assert "id" in v and len(v["id"]) > 0
        assert "name" in v and len(v["name"]) > 0
        assert "gender" in v and v["gender"] in ("Male", "Female")
        assert "locale" in v and v["locale"] in ("vi-VN", "en-US")
        assert "language" in v and len(v["language"]) > 0
        assert "sample" in v and len(v["sample"]) > 10
        assert "recommended" in v and isinstance(v["recommended"], bool)


# ==============================================================================
# 4. UNIT & INTEGRATION TESTS: Error Handling and Fallbacks
# ==============================================================================

def test_srt_timestamp_formatting():
    """Verify format_srt_timestamp converts float seconds to standard SRT timestamps."""
    assert format_srt_timestamp(0.0) == "00:00:00,000"
    assert format_srt_timestamp(1.5) == "00:00:01,500"
    assert format_srt_timestamp(65.123) == "00:01:05,123"
    assert format_srt_timestamp(3661.045) == "01:01:01,045"


def test_fallback_srt_generator():
    """Verify create_fallback_srt generates valid single cue subtitle."""
    cue = create_fallback_srt("Xin chào thế giới", 4.25)
    assert "00:00:00,000 --> 00:00:04,250" in cue
    assert "Xin chào thế giới" in cue


def test_get_audio_duration_fails_loudly_instead_of_guessing(tmp_path):
    """Không đo được thì báo lỗi rõ, không trả số đoán (trước đây trả 3,0 giây như thể đã đo)."""
    from services.tts_service import MediaDurationError
    with pytest.raises(MediaDurationError, match="non_existent.mp3"):
        get_audio_duration(str(tmp_path / "non_existent.mp3"))
    broken = tmp_path / "broken.mp3"
    broken.write_bytes(b"not audio at all")
    with pytest.raises(MediaDurationError):
        get_audio_duration(str(broken))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="cần ffmpeg để tạo file âm thanh mẫu")
def test_get_audio_duration_measures_real_file(tmp_path):
    out = tmp_path / "silence.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "2",
                    "-q:a", "9", str(out)], check=True, timeout=60)
    assert abs(get_audio_duration(str(out)) - 2.0) < 0.15


@pytest.mark.asyncio
async def test_tts_empty_text_error(tmp_path):
    """Verify generate_speech raises ValueError on empty or cue-only text."""
    audio_file = tmp_path / "empty.mp3"
    with pytest.raises(ValueError, match="Cannot generate speech: text is empty"):
        await generate_speech(text="", voice="vi-VN-HoaiMyNeural", output_audio_path=str(audio_file))

    with pytest.raises(ValueError, match="Cannot generate speech: text is empty"):
        await generate_speech(text="   \n\t  ", voice="vi-VN-HoaiMyNeural", output_audio_path=str(audio_file))

    with pytest.raises(ValueError, match="Cannot generate speech: text is empty"):
        await generate_speech(text="(thì thầm)", voice="vi-VN-HoaiMyNeural", output_audio_path=str(audio_file))

    with pytest.raises(ValueError, match="Cannot generate speech: text is empty"):
        await generate_speech(text="[SFX: tiếng nổ lớn]", voice="vi-VN-HoaiMyNeural", output_audio_path=str(audio_file))


# ==============================================================================
# 5. INTEGRATION TESTS: Smart Routing (English Text -> Vietnamese Voice)
# ==============================================================================

@pytest.mark.live  # Edge-TTS thật
@pytest.mark.asyncio
async def test_english_text_routed_from_vietnamese_voice(tmp_path):
    """
    Verify English text selected with a Vietnamese voice (VieNeu or vi-VN) is automatically
    routed to the corresponding English Multilingual voice (Male -> Andrew, Female -> Ava).
    """
    # 1. Male VieNeu voice with English text -> Andrew Multilingual
    mp3_male = str(tmp_path / "en_male_routed.mp3")
    srt_male = str(tmp_path / "en_male_routed.srt")
    res_male = await generate_speech(
        text="King Leonidas raised his spear against the morning sun.",
        voice="vieneu-ThienMinh",  # Male VieNeu voice
        output_audio_path=mp3_male,
        output_srt_path=srt_male,
    )
    assert res_male["fallback_used"] is True, "Expected fallback_used to be True"
    assert res_male["voice"] == "en-US-AndrewMultilingualNeural", f"Expected Andrew, got {res_male['voice']}"
    assert "does not support English text" in res_male["fallback_reason"]
    assert res_male["requested_voice"] == "vieneu-ThienMinh"
    assert res_male["detected_language"] == "en"
    assert os.path.exists(res_male["audio_path"]) and os.path.getsize(res_male["audio_path"]) > 500

    # 2. Female Vietnamese voice with English text -> Ava Multilingual
    mp3_female = str(tmp_path / "en_female_routed.mp3")
    srt_female = str(tmp_path / "en_female_routed.srt")
    res_female = await generate_speech(
        text="Once upon a time in a peaceful village surrounded by gentle green hills.",
        voice="vi-VN-HoaiMyNeural",  # Female Vietnamese voice
        output_audio_path=mp3_female,
        output_srt_path=srt_female,
    )
    assert res_female["fallback_used"] is True
    assert res_female["voice"] == "en-US-AvaMultilingualNeural", f"Expected Ava, got {res_female['voice']}"
    assert "does not support English text" in res_female["fallback_reason"]
    assert res_female["requested_voice"] == "vi-VN-HoaiMyNeural"
    assert res_female["detected_language"] == "en"
    assert os.path.exists(res_female["audio_path"]) and os.path.getsize(res_female["audio_path"]) > 500

    # 3. Female VieNeu voice with English text -> Ava Multilingual (prevents garbled audio)
    mp3_maianh = str(tmp_path / "en_maianh_routed.mp3")
    srt_maianh = str(tmp_path / "en_maianh_routed.srt")
    res_maianh = await generate_speech(
        text="Welcome to the magical adventure in the deep forest.",
        voice="vieneu-MaiAnh",  # Female VieNeu voice
        output_audio_path=mp3_maianh,
        output_srt_path=srt_maianh,
    )
    assert res_maianh["fallback_used"] is True, "Expected fallback_used to be True"
    assert res_maianh["voice"] == "en-US-AvaMultilingualNeural", f"Expected Ava, got {res_maianh['voice']}"
    assert "does not support English text" in res_maianh["fallback_reason"]
    assert res_maianh["requested_voice"] == "vieneu-MaiAnh"
    assert res_maianh["detected_language"] == "en"
    assert os.path.exists(res_maianh["audio_path"]) and os.path.getsize(res_maianh["audio_path"]) > 500


# ==============================================================================
# 6. INTEGRATION TESTS: Real Audio Synthesis with Edge-TTS and VieNeu fallback
# ==============================================================================

@pytest.mark.live  # Edge-TTS thật
@pytest.mark.asyncio
async def test_tts_vietnamese_namminh_with_cleaning(tmp_path):
    """
    Test generating Vietnamese speech with vi-VN-NamMinhNeural,
    verifying stage cues and speaker prefixes are stripped from audio and subtitles.
    """
    audio_file = tmp_path / "voice_namminh.mp3"
    srt_file = tmp_path / "voice_namminh.srt"
    test_text = "Người dẫn chuyện: (thì thầm) Chào các bạn, tôi là Nam Minh, hôm nay chúng ta cùng khám phá câu chuyện mới."

    result = await generate_speech(
        text=test_text,
        voice="vi-VN-NamMinhNeural",
        output_audio_path=str(audio_file),
        output_srt_path=str(srt_file),
    )

    assert result["voice"] == "vi-VN-NamMinhNeural"
    assert result["duration"] > 1.0, f"Duration too short: {result['duration']}"
    assert os.path.exists(result["audio_path"])
    assert os.path.exists(result["srt_path"])
    assert os.path.getsize(result["audio_path"]) > 1000

    with open(result["srt_path"], "r", encoding="utf-8") as f:
        srt_content = f.read()

    assert validate_srt_content(srt_content, "Nam Minh"), "Invalid SRT subtitle format or content"
    assert "thì thầm" not in srt_content, "Stage cue (thì thầm) leaked into subtitles!"
    assert "Người dẫn chuyện" not in srt_content, "Speaker prefix leaked into subtitles!"


@pytest.mark.live  # Edge-TTS thật
@pytest.mark.asyncio
async def test_tts_vietnamese_hoaimy(tmp_path):
    """Test generating Vietnamese speech with vi-VN-HoaiMyNeural."""
    audio_file = tmp_path / "voice_hoaimy.mp3"
    srt_file = tmp_path / "voice_hoaimy.srt"
    test_text = "Xin chào, tôi là Hoài My, người kể chuyện của Story Studio."

    result = await generate_speech(
        text=test_text,
        voice="vi-VN-HoaiMyNeural",
        output_audio_path=str(audio_file),
        output_srt_path=str(srt_file),
    )

    assert result["voice"] == "vi-VN-HoaiMyNeural"
    assert result["duration"] > 1.0, f"Duration too short: {result['duration']}"
    assert os.path.exists(result["audio_path"])
    assert os.path.exists(result["srt_path"])
    assert os.path.getsize(result["audio_path"]) > 2000

    with open(result["srt_path"], "r", encoding="utf-8") as f:
        srt_content = f.read()

    assert validate_srt_content(srt_content, "Hoài My"), "Invalid SRT subtitle format or content"


@pytest.mark.live  # Edge-TTS thật
@pytest.mark.asyncio
async def test_tts_english_andrew(tmp_path):
    """Test generating English speech with en-US-AndrewMultilingualNeural."""
    audio_file = tmp_path / "voice_andrew.mp3"
    srt_file = tmp_path / "voice_andrew.srt"
    test_text = "Welcome to Story Studio. This is Andrew narrating our epic cinematic adventure."

    result = await generate_speech(
        text=test_text,
        voice="en-US-AndrewMultilingualNeural",
        output_audio_path=str(audio_file),
        output_srt_path=str(srt_file),
    )

    assert result["voice"] == "en-US-AndrewMultilingualNeural"
    assert result["duration"] > 1.0, f"Duration too short: {result['duration']}"
    assert os.path.exists(result["audio_path"])
    assert os.path.exists(result["srt_path"])

    with open(result["srt_path"], "r", encoding="utf-8") as f:
        srt_content = f.read()

    assert validate_srt_content(srt_content, "Andrew"), "Invalid SRT subtitle format or content"


@pytest.mark.live  # Edge-TTS thật
@pytest.mark.asyncio
async def test_tts_english_ava(tmp_path):
    """Test generating English speech with en-US-AvaMultilingualNeural."""
    audio_file = tmp_path / "voice_ava.mp3"
    srt_file = tmp_path / "voice_ava.srt"
    test_text = "Hello, I am Ava, bringing your creative stories to life with warmth and emotional expression."

    result = await generate_speech(
        text=test_text,
        voice="en-US-AvaMultilingualNeural",
        output_audio_path=str(audio_file),
        output_srt_path=str(srt_file),
    )

    assert result["voice"] == "en-US-AvaMultilingualNeural"
    assert result["duration"] > 1.0, f"Duration too short: {result['duration']}"
    assert os.path.exists(result["audio_path"])
    assert os.path.exists(result["srt_path"])
    assert os.path.getsize(result["audio_path"]) > 2000

    with open(result["srt_path"], "r", encoding="utf-8") as f:
        srt_content = f.read()

    assert validate_srt_content(srt_content, "Ava"), "Invalid SRT subtitle format or content"


@pytest.mark.live  # bật server VieNeu thật (uv), rơi về Edge-TTS
@pytest.mark.asyncio
async def test_tts_vietnamese_vieneu_maianh_or_fallback(tmp_path):
    """
    Test generating speech with VieNeu Mai Anh.
    If VieNeu engine is running locally, it produces VieNeu audio.
    If VieNeu is unavailable, it transparently falls back to Edge-TTS Hoài My.
    """
    audio_file = tmp_path / "voice_maianh.mp3"
    srt_file = tmp_path / "voice_maianh.srt"
    test_text = "Xin chào các bạn, hôm nay tôi sẽ kể cho các bạn nghe một câu chuyện kỳ bí."

    result = await generate_speech(
        text=test_text,
        voice="vieneu-MaiAnh",
        output_audio_path=str(audio_file),
        output_srt_path=str(srt_file),
    )

    assert result["requested_voice"] == "vieneu-MaiAnh"
    assert result["voice"] in ("vieneu-MaiAnh", "vi-VN-HoaiMyNeural")
    assert result["duration"] > 1.0
    assert os.path.exists(result["audio_path"])
    assert os.path.exists(result["srt_path"])
    assert os.path.getsize(result["audio_path"]) > 1000
