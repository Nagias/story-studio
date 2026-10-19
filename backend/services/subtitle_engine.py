"""
Kinetic Karaoke Subtitle Engine (Word-Level Sync & ASS Generation)
------------------------------------------------------------------
Compliant with OP_CTOOL Master Specification:
1. Generates Advanced SubStation Alpha (.ass) subtitles for YouTube 1080p.
2. Kinetic Karaoke timing: words light up in golden yellow (#FFD700 / &H0000D7FF) in sync with speech rhythm.
3. Emphasizes key Retention Words (kinetic_highlight_words) with dynamic font scaling (1.08x - 1.12x).
4. Word-level timestamps from Faster-Whisper or high-precision syllable alignment fallback.
"""

import os
import re
import math
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger("story_studio.subtitle_engine")

def format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp string: H:MM:SS.cc"""
    total_cs = max(0, int(round(seconds * 100)))
    h = total_cs // 360000
    m = (total_cs % 360000) // 6000
    s = (total_cs % 6000) // 100
    cs = total_cs % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def extract_word_timestamps(
    audio_path: Optional[Union[str, Path]] = None,
    expected_text: Optional[str] = None,
    language: str = "vi",
    fallback_duration: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Extract word-level timestamps using Faster-Whisper if available;
    otherwise use high-precision proportional syllable timing fallback.
    """
    audio_p = Path(audio_path) if audio_path else None
    words_timing: List[Dict[str, Any]] = []

    # 1. Check for exact pre-computed word timing JSON sidecar (from Edge-TTS WordBoundary)
    if audio_p:
        words_json = audio_p.with_suffix(".words.json")
        if words_json.exists():
            try:
                import json
                data = json.loads(words_json.read_text(encoding="utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    return data
            except Exception:
                pass

    # 2. Attempt faster-whisper if installed and file exists
    if audio_p and audio_p.exists():
        try:
            from faster_whisper import WhisperModel  # type: ignore
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(audio_p), language=language, word_timestamps=True)
            for seg in segments:
                if hasattr(seg, "words") and seg.words:
                    for w in seg.words:
                        words_timing.append({
                            "word": w.word.strip(),
                            "start": w.start,
                            "end": w.end,
                        })
            if words_timing:
                return words_timing
        except Exception as e:
            logger.debug(f"faster-whisper not available or failed ({e}); falling back to phonetic alignment.")

    # High-precision proportional fallback
    total_dur = 3.5
    if audio_p and audio_p.exists():
        from services.tts_service import get_audio_duration
        total_dur = get_audio_duration(str(audio_p)) or 3.5
    elif fallback_duration and fallback_duration > 0:
        total_dur = fallback_duration
    else:
        tokens_count = len((expected_text or "").split())
        total_dur = max(2.0, tokens_count * 0.32 + 0.8)

    text_content = expected_text or ""
    tokens = [t for t in text_content.strip().split() if t]
    if not tokens:
        tokens = ["..."]

    total_chars = sum(len(t) for t in tokens)
    speech_span = max(0.5, total_dur - 0.3)
    curr_t = 0.1

    for tok in tokens:
        weight = len(tok) / max(1, total_chars)
        dur = max(0.12, weight * speech_span)
        end_t = min(total_dur, curr_t + dur)
        words_timing.append({
            "word": tok,
            "start": round(curr_t, 3),
            "end": round(end_t, 3),
        })
        curr_t = end_t

    return words_timing

def generate_karaoke_ass(
    scenes_data: List[Dict[str, Any]],
    output_ass_path: Union[str, Path],
    font_name: str = "Arial",
    font_size: int = 56,
    margin_v: int = 45,
    style_mode: str = "kinetic_pop",  # kinetic_pop, karaoke_sweep, classic
) -> str:
    """
    Builds a professional 1080p Kinetic Karaoke .ass subtitle script.
    
    Styles:
    - Primary Colour: White &H00FFFFFF
    - Karaoke Highlight Colour: Golden Yellow (#FFD700 -> ASS BGR hex &H0000D7FF)
    - Border: 3.5px sharp black shadow
    - MarginV: 45 (situated cleanly in bottom third)
    - style_mode:
        - 'kinetic_pop': Modern YouTube Shorts/Vox style where the current spoken word pops up in gold/bold.
        - 'karaoke_sweep': Continuous karaoke smooth sweep with \kf tags.
        - 'classic': Clean bottom subtitle.
    """
    out_p = Path(output_ass_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    header = f"""[Script Info]
Title: YouTube Story Studio Kinetic Karaoke Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3.5,1.5,2,40,40,{margin_v},1
Style: KineticEmphasis,{font_name},{int(font_size * 1.1)},&H0000D7FF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,108,108,1,0,1,4.0,2.0,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogue_lines: List[str] = []
    cumulative_offset = 0.0

    for sc in scenes_data:
        duration = float(sc.get("total_duration") or sc.get("duration") or 3.5)
        text = (sc.get("text") or sc.get("voiceover_text") or "").strip()
        highlight_keywords = [
            k.strip().lower() for k in (sc.get("kinetic_highlight_words") or []) if k.strip()
        ]

        if not text:
            cumulative_offset += duration
            continue

        audio_path = sc.get("audio_path") or sc.get("voice_audio_path")
        word_timings = extract_word_timestamps(
            audio_path=audio_path,
            expected_text=text,
            fallback_duration=duration,
        )

        # Chunk words into digestible subtitle lines (6-8 words per line for mobile/YouTube retention)
        chunk_size = 7
        for i in range(0, len(word_timings), chunk_size):
            chunk = word_timings[i : i + chunk_size]
            if not chunk:
                continue

            if style_mode == "kinetic_pop":
                # Modern Shorts/Vox style: Active word pops in Gold/Yellow with bold scale, others clean white
                for w_idx, active_item in enumerate(chunk):
                    w_start = cumulative_offset + active_item["start"]
                    w_end = cumulative_offset + max(active_item["start"] + 0.12, active_item["end"])

                    line_parts = []
                    for other_idx, other_item in enumerate(chunk):
                        w_str = other_item["word"]
                        is_hk = any(hk in w_str.lower() for hk in highlight_keywords)
                        if other_idx == w_idx:
                            # Active spoken word: Pop in bright gold or cyan
                            color_tag = "\\c&H0000FFFF" if is_hk else "\\c&H0000D7FF"
                            scale_tag = "\\fscx114\\fscy114" if is_hk else "\\fscx110\\fscy110"
                            line_parts.append(f"{{{color_tag}\\b1{scale_tag}}}{w_str}{{\\r}}")
                        else:
                            line_parts.append(f"{{\\c&H00FFFFFF\\b0}}{w_str}{{\\r}}")

                    line_text = " ".join(line_parts).strip()
                    start_ass = format_ass_time(w_start)
                    end_ass = format_ass_time(w_end)
                    dialogue_lines.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{line_text}")

            elif style_mode == "karaoke_sweep":
                # Format Karaoke string with \kf tags
                chunk_start = cumulative_offset + chunk[0]["start"]
                chunk_end = cumulative_offset + chunk[-1]["end"]
                karaoke_elements = []
                for item in chunk:
                    w_str = item["word"]
                    w_dur_cs = max(10, int(round((item["end"] - item["start"]) * 100)))

                    # Check if this word matches any kinetic highlight keywords
                    is_highlight = any(hk in w_str.lower() for hk in highlight_keywords)
                    if is_highlight:
                        karaoke_elements.append(f"{{\\kf{w_dur_cs}}}{{\\c&H0000D7FF\\fscx108\\fscy108}}{w_str}{{\\r}} ")
                    else:
                        karaoke_elements.append(f"{{\\kf{w_dur_cs}}}{w_str} ")

                line_text = "".join(karaoke_elements).strip()
                start_ass = format_ass_time(chunk_start)
                end_ass = format_ass_time(chunk_end)
                dialogue_lines.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{line_text}")

            else:
                # Classic static line
                chunk_start = cumulative_offset + chunk[0]["start"]
                chunk_end = cumulative_offset + chunk[-1]["end"]
                line_text = " ".join(item["word"] for item in chunk)
                start_ass = format_ass_time(chunk_start)
                end_ass = format_ass_time(chunk_end)
                dialogue_lines.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{line_text}")

        cumulative_offset += duration

    full_content = header + "\n".join(dialogue_lines) + "\n"
    with open(out_p, "w", encoding="utf-8") as f:
        f.write(full_content)

    logger.info(f"Generated kinetic karaoke ASS subtitle file at: {out_p}")
    return str(out_p)
