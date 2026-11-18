"""Hàm SRT tự viết cũ (backend/services/video_service.py, tts_service.py), thay bằng pysubs2 ngày 18/11/2026."""
# flake8: noqa

def parse_srt_time(ts_str: str) -> float:
    """Parse SRT timestamp '00:00:01,234' into seconds."""
    ts_str = ts_str.strip().replace(",", ".")
    parts = ts_str.split(":")
    hours = float(parts[0])
    minutes = float(parts[1])
    seconds = float(parts[2])
    return hours * 3600.0 + minutes * 60.0 + seconds

def format_srt_time(sec: float) -> str:
    """Format seconds into SRT timestamp '00:00:01,234'."""
    total_ms = max(0, int(round(sec * 1000)))
    hours = total_ms // 3600000
    minutes = (total_ms % 3600000) // 60000
    secs = (total_ms % 60000) // 1000
    ms = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

def merge_srt_files(scenes_srt_list: List[Dict[str, Any]], output_srt_path: str) -> str:
    """
    Merge multiple SRT files sequentially by applying cumulative duration offsets.
    scenes_srt_list: [{"srt_path": "...", "duration": 3.5}, ...]
    """
    merged_cues: List[str] = []
    cue_index = 1
    current_offset = 0.0

    for item in scenes_srt_list:
        srt_file = item.get("srt_path")
        duration = float(item.get("duration", 3.0))

        if srt_file and os.path.exists(srt_file):
            with open(srt_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()

            blocks = content.split("\n\n")
            for block in blocks:
                lines = [line.strip() for line in block.split("\n") if line.strip()]
                time_line_idx = -1
                for idx, l in enumerate(lines):
                    if "-->" in l:
                        time_line_idx = idx
                        break

                if time_line_idx != -1:
                    time_parts = lines[time_line_idx].split("-->")
                    try:
                        start_t = parse_srt_time(time_parts[0]) + current_offset
                        end_t = parse_srt_time(time_parts[1]) + current_offset
                        text_lines = "\n".join(lines[time_line_idx + 1:])
                        if text_lines.strip():
                            merged_cues.append(
                                f"{cue_index}\n{format_srt_time(start_t)} --> {format_srt_time(end_t)}\n{text_lines}\n"
                            )
                            cue_index += 1
                    except Exception:
                        pass

        current_offset += duration

    out_p = Path(output_srt_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        f.write("\n".join(merged_cues) + "\n")

    return str(out_p)



def format_srt_timestamp(seconds: float) -> str:
    """Format float seconds to SRT timestamp 00:00:00,000."""
    total_ms = int(max(0.0, seconds) * 1000)
    hours = total_ms // 3600000
    minutes = (total_ms % 3600000) // 60000
    secs = (total_ms % 60000) // 1000
    ms = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

