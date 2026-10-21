import asyncio
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import edge_tts

logger = logging.getLogger("story_studio.tts_service")

# ----------------- VieNeu (giọng Việt offline) -----------------
# Mọi thứ nặng của VieNeu (uv cache, Python do uv tải, model HuggingFace) nằm trong thư mục
# dự án (ổ D), không rơi về ổ C. Thư mục này nằm trong .gitignore và bị chặn khi đóng gói.
VIENEU_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
VIENEU_URL = f"http://{os.getenv('VIENEU_HOST', '127.0.0.1')}:{os.getenv('VIENEU_PORT', '5005')}"
VIENEU_UV_CMD = ["uv", "run", "--with", "vieneu", "--python", "3.11"]
VIENEU_SERVER_START_TIMEOUT = 240.0  # nạp model khi đã có cache ~20 s; lần cài đầu tiên lâu hơn nhiều
VIENEU_SERVER_RETRY_AFTER = 600.0    # server vừa chết thì 10 phút sau mới thử bật lại
VIENEU_CLI_TIMEOUT = 90.0            # CLI nạp lại model mỗi lần (~26 s khi đã có cache)

_vieneu_lock: Optional[asyncio.Lock] = None
_vieneu_proc: Optional[subprocess.Popen] = None
_vieneu_started_at = 0.0
_vieneu_failed_at = 0.0


def vieneu_env() -> Dict[str, str]:
    """Biến môi trường khi gọi VieNeu: ép cache của uv/Python/HuggingFace vào thư mục .cache của dự án."""
    env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", **os.environ}
    env["UV_CACHE_DIR"] = str(VIENEU_CACHE_DIR / "uv")
    env["UV_PYTHON_INSTALL_DIR"] = str(VIENEU_CACHE_DIR / "uv-python")
    env["HF_HOME"] = str(VIENEU_CACHE_DIR / "huggingface")
    env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    return env


async def _vieneu_server_ready(timeout: float = 2.0) -> bool:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{VIENEU_URL}/health")
        return resp.status_code == 200
    except Exception:
        return False


async def ensure_vieneu_server() -> bool:
    """
    Đảm bảo server VieNeu (giữ model trong RAM, xem vieneu_server.py) đang chạy ở VIENEU_URL.
    Chưa chạy thì tự bật nền bằng uv với cache trên ổ D rồi chờ model nạp xong. Trả True khi dùng được.
    """
    global _vieneu_lock, _vieneu_proc, _vieneu_started_at, _vieneu_failed_at
    if await _vieneu_server_ready():
        return True
    if os.getenv("STORY_STUDIO_DISABLE_VIENEU_AUTOSTART") == "1":
        return False
    if _vieneu_lock is None:
        _vieneu_lock = asyncio.Lock()

    async with _vieneu_lock:
        if await _vieneu_server_ready():
            return True
        if _vieneu_proc is None or _vieneu_proc.poll() is not None:
            if time.time() - _vieneu_failed_at < VIENEU_SERVER_RETRY_AFTER:
                return False
            server_script = Path(__file__).resolve().parent / "vieneu_server.py"
            VIENEU_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
            try:
                with open(VIENEU_CACHE_DIR / "vieneu_server.log", "ab") as log:
                    _vieneu_proc = subprocess.Popen(
                        [*VIENEU_UV_CMD, str(server_script)],
                        env=vieneu_env(),
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        cwd=str(VIENEU_CACHE_DIR.parent),
                        creationflags=flags,
                    )
            except Exception as e:
                _vieneu_failed_at = time.time()
                logger.warning(f"Không bật được server VieNeu: {e}")
                return False
            _vieneu_started_at = time.time()
            logger.info(f"Đang bật server VieNeu (pid {_vieneu_proc.pid}), chờ nạp model...")

        while time.time() - _vieneu_started_at < VIENEU_SERVER_START_TIMEOUT:
            if _vieneu_proc.poll() is not None:
                _vieneu_failed_at = time.time()
                logger.warning(f"Server VieNeu đã thoát (mã {_vieneu_proc.returncode}), xem {VIENEU_CACHE_DIR / 'vieneu_server.log'}")
                return False
            if await _vieneu_server_ready():
                logger.info(f"Server VieNeu sẵn sàng sau {time.time() - _vieneu_started_at:.0f}s")
                return True
            await asyncio.sleep(1.0)
        logger.warning(f"Server VieNeu chưa sẵn sàng sau {VIENEU_SERVER_START_TIMEOUT:.0f}s")
        return False

AVAILABLE_VOICES: List[Dict[str, Any]] = [
    # --- TIẾNG VIỆT (VIETNAMESE) ---
    {
        "id": "vi-VN-NamMinhNeural",
        "name": "Nam Minh (Nam - Hào Hùng, Trầm Ấm, Đọc Chuẩn Tiếng Việt)",
        "gender": "Male",
        "locale": "vi-VN",
        "language": "Tiếng Việt",
        "sample": "Xin chào, tôi là Nam Minh, giọng đọc nam trầm ấm và hào hùng chuẩn phòng thu.",
        "recommended": True,
    },
    {
        "id": "vi-VN-HoaiMyNeural",
        "name": "Hoài My (Nữ - Truyền Cảm, Nhẹ Nhàng, Đọc Chuẩn Tiếng Việt)",
        "gender": "Female",
        "locale": "vi-VN",
        "language": "Tiếng Việt",
        "sample": "Xin chào, tôi là Hoài My, giọng đọc nữ nhẹ nhàng, truyền cảm và sâu lắng.",
        "recommended": True,
    },
    {
        "id": "vieneu-MaiAnh",
        "name": "VieNeu Mai Anh (Nữ Bắc - AI Offline Thế Hệ Mới)",
        "gender": "Female",
        "locale": "vi-VN",
        "language": "Tiếng Việt",
        "sample": "Xin chào, tôi là Mai Anh, giọng đọc truyền cảm AI thế hệ mới.",
        "recommended": False,
    },
    {
        "id": "vieneu-TrucLy",
        "name": "VieNeu Trúc Ly (Nữ Bắc - Kể Chuyện)",
        "gender": "Female",
        "locale": "vi-VN",
        "language": "Tiếng Việt",
        "sample": "Xin chào, tôi là Trúc Ly, giọng đọc nhẹ nhàng sâu lắng.",
        "recommended": False,
    },
    {
        "id": "vieneu-MyDuyen",
        "name": "VieNeu Mỹ Duyên (Nữ Nam - Cảm Xúc Miền Nam)",
        "gender": "Female",
        "locale": "vi-VN",
        "language": "Tiếng Việt",
        "sample": "Xin chào, tôi là Mỹ Duyên, giọng nữ miền Nam ngọt ngào.",
        "recommended": False,
    },
    {
        "id": "vieneu-ThienMinh",
        "name": "VieNeu Thiện Minh (Nam Bắc - Trầm Ấm)",
        "gender": "Male",
        "locale": "vi-VN",
        "language": "Tiếng Việt",
        "sample": "Xin chào, tôi là Thiện Minh, giọng nam truyền cảm kể chuyện.",
        "recommended": False,
    },
    {
        "id": "vieneu-HaiDang",
        "name": "VieNeu Hải Đăng (Nam Bắc - Hải Đăng, Trầm Ấm Kể Chuyện)",
        "gender": "Male",
        "locale": "vi-VN",
        "language": "Tiếng Việt",
        "sample": "Xin chào, tôi là Hải Đăng, giọng đọc nam tự nhiên và truyền cảm.",
        "recommended": False,
    },

    # --- ENGLISH (US PODCAST & CINEMATIC NARRATION) ---
    {
        "id": "en-US-AndrewMultilingualNeural",
        "name": "Andrew Multilingual (Nam - Cinematic Epic & Documentary)",
        "gender": "Male",
        "locale": "en-US",
        "language": "English (US)",
        "sample": "At the narrow cliffside Gates of Fire, three hundred Spartan warriors stood unyielding.",
        "recommended": True,
    },
    {
        "id": "en-US-BrianMultilingualNeural",
        "name": "Brian Multilingual (Nam - Deep Heroic Narrator)",
        "gender": "Male",
        "locale": "en-US",
        "language": "English (US)",
        "sample": "King Leonidas raised his notched ash-wood spear against the blistering sun.",
        "recommended": True,
    },
    {
        "id": "en-US-AvaMultilingualNeural",
        "name": "Ava Multilingual (Nữ - Natural Emotional Storyteller)",
        "gender": "Female",
        "locale": "en-US",
        "language": "English (US)",
        "sample": "Hello, I am Ava, bringing stories to life with depth and warmth.",
        "recommended": True,
    },
    {
        "id": "en-US-EmmaMultilingualNeural",
        "name": "Emma Multilingual (Nữ - Gentle & Expressive)",
        "gender": "Female",
        "locale": "en-US",
        "language": "English (US)",
        "sample": "Hello, I am Emma, an expressive and eloquent narrator voice.",
        "recommended": True,
    },
    {
        "id": "en-US-ChristopherNeural",
        "name": "Christopher (Nam - Authoritative Historic)",
        "gender": "Male",
        "locale": "en-US",
        "language": "English (US)",
        "sample": "Hello, I am Christopher, an authoritative narrative voice.",
        "recommended": True,
    },
    {
        "id": "en-US-GuyNeural",
        "name": "Guy (Nam - US Podcast Narrator)",
        "gender": "Male",
        "locale": "en-US",
        "language": "English (US)",
        "sample": "Hello, I am Guy, a deep narrative male voice.",
        "recommended": False,
    },
    {
        "id": "en-US-JennyNeural",
        "name": "Jenny (Nữ - US Storyteller)",
        "gender": "Female",
        "locale": "en-US",
        "language": "English (US)",
        "sample": "Hello, I am Jenny, a natural and warm storyteller voice.",
        "recommended": False,
    },
    {
        "id": "en-US-AriaNeural",
        "name": "Aria (Nữ - Expressive)",
        "gender": "Female",
        "locale": "en-US",
        "language": "English (US)",
        "sample": "Hello, I am Aria, a clear and expressive voice.",
        "recommended": False,
    },
]

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


def detect_language(text: str) -> str:
    """Detect whether input text is Vietnamese ('vi') or English ('en')."""
    if not text or not text.strip():
        return "vi"
    # Vietnamese diacritic characters
    vn_regex = re.compile(r'[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]', re.IGNORECASE)
    if vn_regex.search(text):
        return "vi"
    # Check common English words
    en_words = {
        "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not", "on", "with",
        "he", "as", "you", "do", "at", "this", "but", "his", "by", "from", "they", "we", "say", "her",
        "she", "or", "an", "will", "my", "one", "all", "would", "there", "their", "what", "so", "up",
        "out", "if", "about", "who", "get", "which", "go", "me", "when", "make", "can", "like", "time",
        "no", "just", "him", "know", "take", "people", "into", "year", "your", "good", "some", "could",
        "them", "see", "other", "than", "then", "now", "look", "only", "come", "its", "over", "think",
        "also", "back", "after", "use", "two", "how", "our", "work", "first", "well", "way", "even",
        "new", "want", "because", "any", "these", "give", "day", "most", "us", "hello", "hi", "world",
        "story", "ancient", "warrior", "fire", "sword", "king", "dragon", "forest", "dark", "light",
        "night", "sun", "moon", "star", "mountain", "river", "once", "upon", "spartan", "hero"
    }
    words = {w.lower() for w in re.findall(r'[a-zA-Z]+', text)}
    if not words:
        return "vi"
    if len(words.intersection(en_words)) >= 1:
        return "en"
    return "en" if len(words) >= 3 else "vi"


def get_available_voices() -> List[Dict[str, Any]]:
    """Return catalog of curated voices for Story Studio."""
    return AVAILABLE_VOICES


def get_audio_duration(file_path: str) -> float:
    """Get accurate audio duration in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        val = result.stdout.strip()
        if val:
            return round(float(val), 3)
    except Exception as e:
        # Fallback to PyAV if available
        try:
            import av
            with av.open(file_path) as container:
                duration = float(container.duration) / 1000000.0
                return round(duration, 3)
        except Exception:
            pass
    # Worst case approximation based on file size or default 3.0s
    return 3.0


def normalize_narration_text(text: str) -> str:
    """
    Clean and normalize script text for TTS voice synthesis:
    - Strips stage directions, emotion cues, and SFX in brackets/parentheses: (thì thầm), [SFX: ...], (tiếng thở dốc)
    - Strips speaker/character/scene labels at start or line breaks: 'Người dẫn chuyện:', 'Narrator:', '[Lâm]:', 'Cảnh 1:'
    - Preserves legitimate explanatory text inside parentheses by unwrapping them without deleting inner words
    - Strips markdown formatting (**, *, __, _, ~~, `, #, >, bullets)
    - Strips emojis and CJK foreign script causing TTS hallucination
    - Cleans quotation marks so TTS does not speak 'nháy kép' or stutter
    - Normalizes spacing, dashes, and punctuation rhythm
    - Returns clean string, or empty string if input contains only stage directions/labels
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

def format_srt_timestamp(seconds: float) -> str:
    """Format float seconds to SRT timestamp 00:00:00,000."""
    total_ms = int(max(0.0, seconds) * 1000)
    hours = total_ms // 3600000
    minutes = (total_ms % 3600000) // 60000
    secs = (total_ms % 60000) // 1000
    ms = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

def create_fallback_srt(text: str, duration: float) -> str:
    """Generate a single-cue SRT subtitle spanning the whole duration."""
    start_ts = "00:00:00,000"
    end_ts = format_srt_timestamp(max(duration, 0.5))
    clean_text = text.strip()
    return f"1\n{start_ts} --> {end_ts}\n{clean_text}\n\n"

def generate_readable_srt(word_timings: List[Dict[str, Any]], fallback_text: str, duration: float) -> str:
    """
    Generate natural, readable SRT subtitle cues grouped into coherent phrases (4-8 words per cue)
    instead of jarring single-word flashes.
    """
    if not word_timings:
        return create_fallback_srt(fallback_text, duration)

    cues = []
    current_phrase: List[Dict[str, Any]] = []

    for item in word_timings:
        current_phrase.append(item)
        word = item.get("word", "").strip()
        has_stop = any(word.endswith(p) for p in ('.', '!', '?', ';', ':'))
        has_pause = any(word.endswith(p) for p in (',', '—', '-'))
        if has_stop or (has_pause and len(current_phrase) >= 4) or len(current_phrase) >= 7:
            start_s = current_phrase[0]["start"]
            end_s = current_phrase[-1]["end"]
            text_str = " ".join(w["word"] for w in current_phrase)
            cues.append((start_s, end_s, text_str))
            current_phrase = []

    if current_phrase:
        start_s = current_phrase[0]["start"]
        end_s = current_phrase[-1]["end"]
        text_str = " ".join(w["word"] for w in current_phrase)
        cues.append((start_s, end_s, text_str))

    if not cues:
        return create_fallback_srt(fallback_text, duration)

    srt_lines = []
    for idx, (st, en, txt) in enumerate(cues, start=1):
        st_str = format_srt_timestamp(st)
        en_str = format_srt_timestamp(max(en, st + 0.4))
        srt_lines.append(f"{idx}\n{st_str} --> {en_str}\n{txt.strip()}\n")

    return "\n".join(srt_lines) + "\n"

def _nudge_rate(rate: str, delta: int) -> str:
    """Cộng `delta` % vào tốc độ đọc dạng Edge-TTS ("+0%", "-10%"); giá trị lạ thì coi là +0%."""
    m = re.fullmatch(r"\s*([+-]?\d+)\s*%\s*", rate or "")
    base = int(m.group(1)) if m else 0
    return f"{base + delta:+d}%"


async def generate_speech(
    text: str,
    voice: str = "vi-VN-NamMinhNeural",
    output_audio_path: Optional[str] = None,
    output_srt_path: Optional[str] = None,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> Dict[str, Any]:
    """
    Generate speech and synchronized subtitles using Edge-TTS or VieNeu.
    Handles exceptions transparently and produces studio-grade output.
    Returns:
        {
            "audio_path": str,
            "srt_path": str,
            "duration": float,
            "voice": str,
            "srt_content": str,
            "word_timings": List[Dict[str, Any]],
            "fallback_used": bool,
            "fallback_reason": Optional[str],
            "requested_voice": str,
            "detected_language": str,
        }
    """
    clean_text = normalize_narration_text(text)
    if not clean_text or not clean_text.strip():
        raise ValueError(f"Cannot generate speech: text is empty after filtering stage directions and labels (original: '{text}').")

    if not output_audio_path:
        raise ValueError("output_audio_path must be provided.")

    audio_path = Path(output_audio_path)
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    if not output_srt_path:
        output_srt_path = str(audio_path.with_suffix(".srt"))
    srt_path = Path(output_srt_path)
    srt_path.parent.mkdir(parents=True, exist_ok=True)

    detected_lang = detect_language(clean_text)
    requested_voice = voice
    fallback_used = False
    fallback_reason: Optional[str] = None

    # Check for language mismatch: English text with Vietnamese voice
    is_vn_voice = (
        voice.lower().startswith("vieneu") or
        voice.lower().startswith("vi-vn") or
        any(v.get("id", "").lower() == voice.lower() and v.get("locale") == "vi-VN" for v in AVAILABLE_VOICES)
    )

    if detected_lang == "en" and is_vn_voice:
        # Determine gender of requested voice
        voice_meta = next((v for v in AVAILABLE_VOICES if v.get("id", "").lower() == voice.lower()), None)
        is_male = False
        if voice_meta:
            is_male = voice_meta.get("gender") == "Male"
        else:
            is_male = any(m in voice.lower() for m in ("nam", "male", "thienminh", "haidang"))

        fallback_voice = "en-US-AndrewMultilingualNeural" if is_male else "en-US-AvaMultilingualNeural"
        fallback_reason = "Voice VieNeu/Vietnamese does not support English text. Automatically routed to English voice"
        logger.warning(
            f"{fallback_reason}. (Requested: '{requested_voice}', Routed to: '{fallback_voice}', Text preview: '{clean_text[:40]}...')"
        )
        voice = fallback_voice
        fallback_used = True

    # 1. Handle VieNeu-TTS voices (only for Vietnamese text)
    if voice.lower().startswith("vieneu"):
        vieneu_map = {
            "vieneu-maianh": "Mai Anh",
            "vieneu-trucly": "Trúc Ly",
            "vieneu-myduyen": "Mỹ Duyên",
            "vieneu-thienminh": "Thiện Minh",
            "vieneu-haidang": "Hải Đăng",
        }
        target_vieneu_voice = vieneu_map.get(voice.lower(), "Mai Anh")
        worker_script = Path(__file__).resolve().parent / "vieneu_worker.py"

        vieneu_success = False
        vieneu_errors: List[str] = []

        # 1a. Server VieNeu giữ model trong RAM (tự bật nếu chưa chạy): mỗi cảnh chỉ tốn thời gian đọc
        if await ensure_vieneu_server():
            try:
                import httpx
                # CPU đọc ~1 giây cho mỗi vài từ: câu dài cần timeout dài hơn
                async with httpx.AsyncClient(timeout=max(60.0, len(clean_text) / 4)) as client:
                    resp = await client.post(
                        f"{VIENEU_URL}/v1/audio/speech",
                        json={"input": clean_text, "voice": target_vieneu_voice, "response_format": "mp3"},
                    )
                if resp.status_code == 200 and len(resp.content) > 500:
                    audio_path.write_bytes(resp.content)
                    vieneu_success = True
                else:
                    vieneu_errors.append(f"server HTTP {resp.status_code}: {resp.text[:150]}")
            except Exception as e:
                vieneu_errors.append(f"server: {e}")
        else:
            vieneu_errors.append("server VieNeu không bật được")

        # 1b. Dự phòng: CLI nạp lại model mỗi lần (~26 s), cache vẫn trên ổ D
        if not vieneu_success and worker_script.exists():
            try:
                cmd = [
                    *VIENEU_UV_CMD,
                    str(worker_script),
                    "--text", clean_text,
                    "--voice", target_vieneu_voice,
                    "--output", str(audio_path),
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=vieneu_env(),
                )
                try:
                    stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=VIENEU_CLI_TIMEOUT)
                    if proc.returncode == 0 and audio_path.exists() and audio_path.stat().st_size > 500:
                        vieneu_success = True
                    else:
                        err_str = stderr_b.decode("utf-8", errors="replace") if stderr_b else "Unknown error"
                        logger.warning(f"VieNeu CLI synthesis exited with code {proc.returncode}: {err_str}")
                        vieneu_errors.append(f"CLI mã {proc.returncode}: {err_str.strip()[-150:]}")
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    logger.warning(f"VieNeu CLI synthesis timed out after {VIENEU_CLI_TIMEOUT:.0f}s for text: {clean_text[:40]}...")
                    vieneu_errors.append(f"CLI quá {VIENEU_CLI_TIMEOUT:.0f}s")
            except Exception as e:
                logger.warning(f"VieNeu CLI launch failed: {e}")
                vieneu_errors.append(f"CLI không chạy được: {e}")

        if vieneu_success:
            # VieNeu không có mốc thời gian từng từ: xoá file .words.json cũ (nếu cảnh từng đọc bằng Edge)
            # để phụ đề karaoke không dùng mốc của bản thu trước
            audio_path.with_suffix(".words.json").unlink(missing_ok=True)
            duration = get_audio_duration(str(audio_path))
            srt_content = create_fallback_srt(clean_text, duration)
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            return {
                "audio_path": str(audio_path),
                "srt_path": str(srt_path),
                "duration": duration,
                "voice": voice,
                "srt_content": srt_content,
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "requested_voice": requested_voice,
                "detected_language": detected_lang,
            }
        else:
            # Transparent fallback to Microsoft Edge-TTS Neural
            voice_meta = next((v for v in AVAILABLE_VOICES if v.get("id", "").lower() == voice.lower()), None)
            is_male = voice_meta.get("gender") == "Male" if voice_meta else any(m in voice.lower() for m in ("thienminh", "haidang", "nam"))
            fallback_voice = "vi-VN-NamMinhNeural" if is_male else "vi-VN-HoaiMyNeural"
            fallback_reason = (
                f"VieNeu voice '{requested_voice}' unavailable, fell back to Edge-TTS '{fallback_voice}'"
                + (f" ({'; '.join(vieneu_errors)})" if vieneu_errors else "")
            )
            logger.info(fallback_reason)
            voice = fallback_voice
            fallback_used = True

    # 2. Microsoft Edge-TTS Engine
    audio_bytes = bytearray()
    word_timings: List[Dict[str, Any]] = []
    last_err = None

    # Edge-TTS trả "No audio was received" theo hai kiểu (đo 21/10/2026):
    # - từng đợt vài giây tới ~1 phút với mọi câu -> chờ 1-2-4-8-15 giây giữa các lần thử;
    # - cố định với đúng một yêu cầu (vd "Ánh mắt kiên định của chàng không hề nao núng." lỗi 5/5 lần) trong khi
    #   chỉ cần nhích tốc độ đọc 1-2% là đọc được 5/5 -> từ lần thử thứ hai đổi nhẹ tốc độ (tai không nhận ra).
    retry_delays = (1, 2, 4, 8, 15)
    rate_nudges = (0, 1, 2, -1, 3, 0)
    max_attempts = len(retry_delays) + 1
    for attempt in range(max_attempts):
        attempt_rate = _nudge_rate(rate, rate_nudges[attempt])
        try:
            communicate = edge_tts.Communicate(
                text=clean_text,
                voice=voice,
                rate=attempt_rate,
                pitch=pitch,
                boundary="WordBoundary",
            )
            audio_bytes = bytearray()
            word_timings = []

            async for chunk in communicate.stream():
                chunk_type = chunk.get("type")
                if chunk_type == "audio":
                    audio_bytes.extend(chunk.get("data", b""))
                elif chunk_type == "WordBoundary":
                    off = (chunk.get("offset") or 0) / 10_000_000.0
                    dur = (chunk.get("duration") or 0) / 10_000_000.0
                    w_text = chunk.get("text", "")
                    word_timings.append({
                        "word": w_text,
                        "start": round(off, 3),
                        "end": round(off + dur, 3),
                    })

            if len(audio_bytes) > 0:
                break
            last_err = RuntimeError("0 bytes audio")
        except Exception as e:
            last_err = e
        if attempt < max_attempts - 1:
            logger.warning(f"Edge-TTS attempt {attempt + 1}/{max_attempts} failed ({last_err}), retrying...")
            await asyncio.sleep(retry_delays[attempt])
        else:
            raise RuntimeError(f"Edge-TTS audio synthesis failed for voice '{voice}' after {max_attempts} attempts: {last_err}") from last_err

    if len(audio_bytes) == 0:
        err_msg = f"Edge-TTS synthesis returned 0 bytes for voice '{voice}'"
        if last_err:
            err_msg += f": {last_err}"
        raise RuntimeError(err_msg)

    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    duration = get_audio_duration(str(audio_path))

    # Generate professional grouped phrase-level subtitles
    srt_content = generate_readable_srt(word_timings, clean_text, duration)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    # Save word-level timestamps sidecar for Kinetic ASS subtitles
    words_json_path = audio_path.with_suffix(".words.json")
    try:
        import json
        with open(words_json_path, "w", encoding="utf-8") as f:
            json.dump(word_timings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return {
        "audio_path": str(audio_path),
        "srt_path": str(srt_path),
        "duration": duration,
        "voice": voice,
        "srt_content": srt_content,
        "word_timings": word_timings,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "requested_voice": requested_voice,
        "detected_language": detected_lang,
    }
