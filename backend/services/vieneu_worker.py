"""VieNeu-TTS Standalone CLI Generator Worker for Story Studio.
Invoked directly via:
    uv run --with vieneu --python 3.11 backend/services/vieneu_worker.py --text "..." --voice "Mai Anh" --output "output.mp3"
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Safe console re-encoding on Windows
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


# Regex for detecting stage directions, SFX, audio/visual cues and emotion markers
CUE_INDICATORS_REGEX = re.compile(
    r'(?:'
    r'sfx|sound(?:s)?|nhạc(?: nền)?|tiếng(?: động| súng| mưa| sấm| gió| chim| cười| khóc| bước chân| thở| thở dốc| nổ| xe| còi| chuông)?|'
    r'âm\s+thanh|bgm|foley|fx|vfx|'
    r'hình\s+ảnh|visual(?: prompt)?|image(?: prompt)?|prompt|camera|cảnh\s+quay|góc\s+quay|cận\s+cảnh|toàn\s+cảnh|bối\s+cảnh|phân\s+cảnh|scene|'
    r'thì\s+thầm|thì\s+thào|hồi\s+hộp|la\s+lớn|la\s+hét|hét\s+lớn|hét\s+lên|gào\s+thét|gào\s+lên|gầm\s+lên|kêu\s+lên|'
    r'ngạc\s+nhiên|hoảng\s+sợ|hoảng\s+hốt|kinh\s+hãi|sợ\s+hãi|'
    r'cười\s+lớn|cười\s+khúc\s+khích|cười\s+mỉm|cười\s+khẩy|cười\s+rộ|cười|'
    r'khóc\s+nấc|khóc\s+nức\s+nở|khóc\s+thút\s+thít|khóc|'
    r'thở\s+dài|thở\s+dốc|thở\s+mạnh|thở\s+hắt|thở\s+phào|hít\s+sâu|hít\s+một\s+hơi|'
    r'ngậm\s+ngùi|tức\s+giận|giận\s+dữ|phẫn\s+nộ|bực\s+tức|run\s+rẩy|run\s+run|run\s+sợ|'
    r'nói\s+nhỏ|nói\s+lớn|nói\s+to|nói\s+thầm|nói\s+khẽ|'
    r'trầm\s+ngâm|ngập\s+ngừng|do\s+dự|lo\s+lắng|bồn\s+chồn|phấn\s+khích|hào\s+hứng|hân\s+hoan|vui\s+mừng|'
    r'bí\s+hiểm|thất\s+vọng|bất\s+ngờ|dõng\s+dạc|nghiêm\s+giọng|nghiêm\s+nghị|căng\s+thẳng|chậm\s+rãi|chậm\s+lại|nhanh|nhanh\s+giọng|'
    r'vang\s+vọng|dồn\s+dập|nghẹn\s+ngào|nghẹn\s+lời|vui\s+vẻ|buồn\s+bã|buồn\s+rầu|hoài\s+niệm|lạnh\s+lùng|lạnh\s+tanh|'
    r'đau\s+đớn|thảng\s+thốt|châm\s+biếm|mỉa\s+mai|nghiêm\s+túc|hăng\s+hái|mệt\s+mỏi|yếu\s+ớt|kiên\s+quyết|dứt\s+khoát|'
    r'im\s+lặng|khoảng\s+lặng|ngừng\s+lại|dừng\s+lại|tạm\s+dừng|im\s+bặt|'
    r'gật\s+đầu|lắc\s+đầu|nhìn\s+quanh|quay\s+lại|bước\s+tới|tiến\s+lại|đứng\s+dậy|ngồi\s+xuống|'
    r'whisper(?:ing)?|gasp(?:s|ing)?|sigh(?:s|ing)?|scream(?:s|ing)?|shout(?:s|ing)?|laugh(?:s|ing|ter)?|'
    r'cry(?:ing)?|cries|angry|angrily|nervous(?:ly)?|excited(?:ly)?|pause|sobbing|giggle|giggling|'
    r'chuckle|chuckling|terrified|panicked|scared|trembling|slowly|quickly|loudly|softly|cheerfully|sadly|'
    r'narration|narrator|voiceover|vo|v\.o\.|sound\s*effects?'
    r')',
    re.IGNORECASE | re.UNICODE
)


def clean_vietnamese_text(text: str) -> str:
    """
    Clean text for TTS inference, stripping stage directions, emotional cues,
    speaker prefixes, markdown, emojis, while preserving legitimate explanatory text.
    """
    if not text:
        return ""
    cleaned = text

    # 1. Strip HTML/XML tags
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)

    # 2. Iteratively strip leading character / narrator / scene labels at start or line breaks
    while True:
        prev = cleaned
        # Bracketed labels: [Lâm]:, [Người dẫn chuyện]:, (Narrator):, [Nhân vật 1]:
        cleaned = re.sub(
            r'(?m)^\s*[\[\(]\s*(?:người\s+dẫn\s+chuyện|narrator|dẫn\s+chuyện|nhân\s+vật(?:\s+\w+)?|lâm|main|mc|host|speaker|voiceover|v\.o\.?|cảnh\s*\d+|scene\s*\d+|[\w\s]{1,25})\s*[\]\)]\s*[:：\.-]?\s*',
            '',
            cleaned,
            flags=re.IGNORECASE
        )
        # Plain role prefixes: Người dẫn chuyện:, Narrator:, Dẫn chuyện:, Lâm:, Main:, Cảnh 1:
        cleaned = re.sub(
            r'(?m)^\s*(?:người\s+dẫn\s+chuyện|narrator|dẫn\s+chuyện|nhân\s+vật(?:\s+\w+)?|lâm|main|mc|host|speaker|voiceover|v\.o\.?|cảnh\s*\d+|phân\s+cảnh\s*\d+|scene\s*\d+)\s*[:：\.-]\s*',
            '',
            cleaned,
            flags=re.IGNORECASE
        )
        if cleaned == prev:
            break

    # 3. Process brackets & parentheses: remove if cue, unwrap if normal explanatory
    def _process_brackets(match: re.Match) -> str:
        inner = match.group(2).strip()
        if not inner:
            return ' '
        # Check if contains cue keywords or is prompt / visual / colon cue
        if CUE_INDICATORS_REGEX.search(inner) or re.match(r'^(?:sfx|sound|visual|prompt|camera|image|action|ghi chú|note|lưu ý)\s*[:：]', inner, re.I):
            return ' '
        # If it is only punctuation or symbols, discard
        if not re.search(r'[\w\d]', inner, re.UNICODE):
            return ' '
        # Normal explanatory content: keep text inside without brackets
        return f' {inner} '

    # Handle all bracket types iteratively for nested brackets
    bracket_pat = re.compile(r'([\(\[\{（【「『])([^\)\]\}）】」』]*)([\)\]\}）】」』])')
    for _ in range(5):
        if not bracket_pat.search(cleaned):
            break
        cleaned = bracket_pat.sub(_process_brackets, cleaned)

    # 4. Strip markdown formatting
    cleaned = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', cleaned)
    cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)
    cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)
    cleaned = re.sub(r'___([^_]+)___', r'\1', cleaned)
    cleaned = re.sub(r'__([^_]+)__', r'\1', cleaned)
    cleaned = re.sub(r'_([^_]+)_', r'\1', cleaned)
    cleaned = re.sub(r'~~([^~]+)~~', r'\1', cleaned)
    cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
    cleaned = re.sub(r'(?m)^\s*#{1,6}\s*', '', cleaned)
    cleaned = re.sub(r'(?m)^\s*>\s*', '', cleaned)
    cleaned = re.sub(r'(?m)^\s*[-*+]\s+', '', cleaned)
    cleaned = re.sub(r'[*#_`~|\\^/+=@$%&]', ' ', cleaned)

    # 5. Remove CJK characters
    cleaned = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffef]', ' ', cleaned)

    # 6. Remove emojis and unusual symbols
    cleaned = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27bf\ufe00-\ufe0f]', ' ', cleaned)

    # 7. Normalize quotes and dashes
    cleaned = re.sub(r'[\—\–]', ', ', cleaned)
    cleaned = re.sub(r'["“”«»]', '', cleaned)
    # Remove quotation single quotes while preserving apostrophes inside words (e.g. today's, don't, it's)
    cleaned = re.sub(r'(?<![a-zA-Z0-9])[\'‘’]|[\'‘’](?![a-zA-Z0-9])', '', cleaned)

    # 8. Normalize punctuation and spacing
    cleaned = re.sub(r'\.{2,}', '.', cleaned)
    cleaned = re.sub(r'!{2,}', '!', cleaned)
    cleaned = re.sub(r'\?{2,}', '?', cleaned)
    cleaned = re.sub(r'\s+([,.:;?!])', r'\1', cleaned)
    cleaned = re.sub(r'([,.:;?!])(?=[^\s\d])', r'\1 ', cleaned)
    cleaned = re.sub(r'^[\s,.:;?!-]+', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def main():
    parser = argparse.ArgumentParser(description="VieNeu-TTS Standalone Audio Generator for Story Studio")
    parser.add_argument("--text", type=str, required=True, help="Text to synthesize")
    parser.add_argument("--voice", type=str, default="Mai Anh", help="Preset voice name")
    parser.add_argument("--output", type=str, required=True, help="Destination audio path (.mp3 or .wav)")
    parser.add_argument("--temperature", type=float, default=0.8, help="Sampling temperature")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier")

    args = parser.parse_args()

    cleaned_text = clean_vietnamese_text(args.text)
    if not cleaned_text or not cleaned_text.strip():
        print(f"[!] Text is empty after filtering stage directions (original: '{args.text}')", file=sys.stderr)
        sys.exit(1)

    dest_path = Path(args.output).resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    from vieneu import Vieneu

    # Initialize VieNeu engine (v3 Turbo ONNX, CPU torch-free)
    tts = Vieneu()

    # Inference without watermark for studio master quality
    audio = tts.infer(
        text=cleaned_text,
        voice=args.voice,
        temperature=args.temperature,
        apply_watermark=False,
    )

    if audio is None or len(audio) == 0:
        print("[!] Synthesis produced empty audio.", file=sys.stderr)
        sys.exit(1)

    # Save to intermediate temporary WAV file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        tmp_wav_path = Path(tmp_wav.name)

    try:
        tts.save(audio, str(tmp_wav_path))

        # Check if destination is MP3 or requires conversion
        if dest_path.suffix.lower() == ".mp3":
            filter_chain = []
            if abs(args.speed - 1.0) > 0.05:
                filter_chain.append(f"atempo={args.speed}")
            
            cmd = ["ffmpeg", "-y", "-i", str(tmp_wav_path)]
            if filter_chain:
                cmd.extend(["-af", ",".join(filter_chain)])
            cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k", str(dest_path)])

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 or not dest_path.exists() or dest_path.stat().st_size == 0:
                print(f"[!] FFmpeg conversion failed: {res.stderr}", file=sys.stderr)
                sys.exit(1)
        else:
            if dest_path.exists():
                dest_path.unlink()
            tmp_wav_path.replace(dest_path)

        print(f"[SUCCESS] Audio written to {dest_path} (size: {dest_path.stat().st_size} bytes)")
        sys.exit(0)
    finally:
        if tmp_wav_path.exists():
            try:
                tmp_wav_path.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    main()
