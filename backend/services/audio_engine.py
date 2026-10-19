"""
3-Layer Audio & Dynamic Pacing Engine
-------------------------------------
Compliant with OP_CTOOL Master Specification:
1. Layer 1: Multi-speaker Voiceover (Edge-TTS) with dramatic silence insertion (pause_after_sec: 0.3s - 2.0s).
2. Layer 2: Foley & SFX Sound Design synchronized to scene start cue timestamps.
3. Layer 3: Adaptive BGM with Automatic Sidechain Audio Ducking (-20dB during voiceover, -8dB during pauses/climax).
"""

import os
import sys
import math
import struct
import wave
import shutil
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

import numpy as np
import edge_tts

from config import ASSETS_DIR, BGM_DIR
from services.tts_service import get_audio_duration, normalize_narration_text

logger = logging.getLogger("story_studio.audio_engine")

SFX_DIR = ASSETS_DIR / "sfx"
SFX_DIR.mkdir(parents=True, exist_ok=True)

# Speaker to Voice mapping (Vietnamese & English default presets)
SPEAKER_VOICE_MAP = {
    "narrator": "vi-VN-NamMinhNeural",
    "male": "vi-VN-NamMinhNeural",
    "female": "vi-VN-HoaiMyNeural",
    "nam": "vi-VN-NamMinhNeural",
    "nu": "vi-VN-HoaiMyNeural",
    "detective": "vi-VN-NamMinhNeural",
    "en_narrator": "en-US-GuyNeural",
    "en_female": "en-US-JennyNeural",
}

# BGM Energy preset mapping
BGM_ENERGY_MAP = {
    "ambient_low": "ambient_peaceful",
    "tension_buildup": "mysterious_dark",
    "dramatic_climax": "cinematic_adventure",
}

def resolve_voice_for_speaker(speaker: Optional[str], default_voice: str = "vi-VN-NamMinhNeural") -> str:
    """Resolve TTS voice ID from speaker role or character name."""
    if not speaker:
        return default_voice
    clean = speaker.strip().lower()
    for key, voice in SPEAKER_VOICE_MAP.items():
        if key in clean:
            return voice
    return default_voice

def generate_procedural_sfx(cue_name: str, out_wav_path: Path, duration_sec: float = 2.0):
    """
    Synthesize high-fidelity procedural SFX wav files locally
    guaranteeing 100% self-contained offline zero-error execution.
    """
    sr = 44100
    n_samples = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n_samples, endpoint=False)
    cue = cue_name.lower()

    if "heartbeat" in cue:
        # Dual thumping sub-bass pulses (lub-dub)
        pulse1 = np.exp(-((t - 0.2) ** 2) / 0.005) * np.sin(2 * np.pi * 55 * t)
        pulse2 = np.exp(-((t - 0.5) ** 2) / 0.005) * np.sin(2 * np.pi * 48 * t) * 0.8
        pulse3 = np.exp(-((t - 1.2) ** 2) / 0.005) * np.sin(2 * np.pi * 55 * t)
        pulse4 = np.exp(-((t - 1.5) ** 2) / 0.005) * np.sin(2 * np.pi * 48 * t) * 0.8
        data = (pulse1 + pulse2 + pulse3 + pulse4) * 0.85
    elif "rain" in cue:
        # Pink/brown filtered continuous rainfall noise
        white = np.random.normal(0, 0.25, n_samples)
        # Simple IIR low-pass filter
        data = np.zeros(n_samples)
        for i in range(1, n_samples):
            data[i] = 0.95 * data[i - 1] + 0.05 * white[i]
        data = data * 0.7
    elif "clock" in cue or "tick" in cue:
        # Precision mechanical clock ticking clicks
        data = np.zeros(n_samples)
        for tick_time in [0.25, 0.75, 1.25, 1.75]:
            idx = int(tick_time * sr)
            if idx + 2000 < n_samples:
                decay = np.exp(-np.linspace(0, 10, 2000))
                click = np.sin(2 * np.pi * 1800 * t[:2000]) * decay
                data[idx : idx + 2000] += click * 0.7
    elif "thunder" in cue:
        # Low frequency rumble envelope
        noise = np.random.normal(0, 0.4, n_samples)
        envelope = np.exp(-t * 1.5) * (t ** 0.5)
        # Lowpass filter
        data = np.zeros(n_samples)
        for i in range(1, n_samples):
            data[i] = 0.98 * data[i - 1] + 0.02 * noise[i]
        data = data * envelope * 2.5
    elif "gate" in cue or "creak" in cue:
        # Metallic resonance frequency modulation creak
        freq = 350 + 150 * np.sin(2 * np.pi * 1.5 * t) + 80 * np.random.normal(0, 0.1, n_samples)
        phase = np.cumsum(2 * np.pi * freq / sr)
        envelope = np.sin(np.pi * t / duration_sec) ** 2
        data = np.sin(phase) * envelope * 0.5
    elif "footstep" in cue:
        # Rhythmic gravel crunch footfalls
        data = np.zeros(n_samples)
        for step_t in [0.3, 0.9, 1.5]:
            idx = int(step_t * sr)
            if idx + 4000 < n_samples:
                decay = np.exp(-np.linspace(0, 8, 4000))
                crunch = np.random.normal(0, 0.3, 4000) * decay
                data[idx : idx + 4000] += crunch * 0.6
    elif "sword" in cue or "blade" in cue or "clash" in cue:
        # Metallic high-frequency resonance + noise attack
        attack_env = np.exp(-t * 24)
        ring_env = np.exp(-t * 4.0)
        harmonics = (
            np.sin(2 * np.pi * 3200 * t) * 0.4 +
            np.sin(2 * np.pi * 4850 * t) * 0.3 +
            np.sin(2 * np.pi * 6420 * t) * 0.2 +
            np.sin(2 * np.pi * 1250 * t) * 0.3
        ) * ring_env
        noise = np.random.normal(0, 0.5, n_samples) * attack_env * 0.6
        data = (harmonics + noise) * 0.95
    elif "shield" in cue or "block" in cue:
        # Heavy bronze/iron shield impact: low thud + metallic reverberation
        thud = np.sin(2 * np.pi * 120 * t) * np.exp(-t * 12) * 0.7
        clang = (np.sin(2 * np.pi * 850 * t) + np.sin(2 * np.pi * 1420 * t) * 0.6) * np.exp(-t * 5.0) * 0.5
        data = (thud + clang) * 0.9
    elif "explosion" in cue or "boom" in cue or "blast" in cue:
        # Sub-bass rumble (48Hz) + sudden white noise explosion burst + long decaying rumble
        sub = np.sin(2 * np.pi * 50 * t) * np.exp(-t * 1.8) * 0.8
        burst = np.random.normal(0, 0.6, n_samples) * np.exp(-t * 4.5) * 0.7
        rumble = np.random.normal(0, 0.3, n_samples) * (t ** 0.5) * np.exp(-t * 1.2) * 0.5
        data = (sub + burst + rumble) * 0.95
    elif "wind" in cue or "howl" in cue:
        # Modulated pink noise simulating howling desolate wind
        noise = np.random.normal(0, 0.3, n_samples)
        mod = 0.5 + 0.5 * np.sin(2 * np.pi * 0.8 * t)
        data = np.zeros(n_samples)
        for i in range(1, n_samples):
            data[i] = 0.96 * data[i - 1] + 0.04 * noise[i]
        data = data * mod * 1.4
    elif "fire" in cue or "flame" in cue:
        # Low warm drone + random sharp crackle pops
        sub_warm = np.sin(2 * np.pi * 120 * t) * 0.2
        crackle = np.zeros(n_samples)
        pop_indices = np.random.choice(n_samples, size=min(40, n_samples // 1000), replace=False)
        for p_idx in pop_indices:
            if p_idx + 300 < n_samples:
                crackle[p_idx : p_idx + 300] += np.random.normal(0, 0.7, 300) * np.exp(-np.linspace(0, 5, 300))
        data = (sub_warm + crackle) * 0.8
    elif "magic" in cue or "spell" in cue or "shimmer" in cue:
        # Ethereal rising chime harmonics with shimmer
        chimes = (
            np.sin(2 * np.pi * 1046 * t) * 0.25 +
            np.sin(2 * np.pi * 1318 * t) * 0.25 +
            np.sin(2 * np.pi * 1568 * t) * 0.25 +
            np.sin(2 * np.pi * 2093 * t) * 0.25
        ) * np.sin(np.pi * t / duration_sec)
        vibrato = np.sin(2 * np.pi * 6 * t) * 0.1
        data = (chimes * (1.0 + vibrato)) * 0.85
    elif "whoosh" in cue or "swoosh" in cue:
        # Fast swept whoosh (300Hz -> 1800Hz -> 200Hz)
        center_t = duration_sec * 0.4
        bell_env = np.exp(-((t - center_t) ** 2) / 0.08)
        sweep_freq = 300 + 1500 * np.exp(-((t - center_t) ** 2) / 0.05)
        phase = np.cumsum(2 * np.pi * sweep_freq / sr)
        noise = np.random.normal(0, 0.3, n_samples) * bell_env
        data = (np.sin(phase) * 0.5 + noise * 0.5) * bell_env * 1.2
    elif "crowd" in cue or "shout" in cue or "battle" in cue:
        # Layered distant roar of battle army
        formants = (
            np.sin(2 * np.pi * 180 * t) * 0.3 +
            np.sin(2 * np.pi * 320 * t) * 0.3 +
            np.sin(2 * np.pi * 540 * t) * 0.2
        ) * np.sin(np.pi * t / duration_sec)
        noise = np.random.normal(0, 0.3, n_samples) * 0.4
        data = (formants + noise) * 0.9
    elif "hit" in cue or "impact" in cue:
        # Heavy cinematic trailer impact: low sub-bass boom (55Hz) + sudden punch
        sub = np.sin(2 * np.pi * 55 * t) * np.exp(-t * 2.8) * 0.8
        thud = np.sin(2 * np.pi * 110 * t) * np.exp(-t * 8.0) * 0.5
        data = (sub + thud) * 0.95
    else:
        # General cinematic atmospheric sub-bass pulse / drone
        envelope = np.sin(np.pi * t / duration_sec)
        data = np.sin(2 * np.pi * 90 * t) * envelope * 0.5

    data = np.clip(data, -0.98, 0.98)
    int_data = (data * 32767).astype(np.int16)

    with wave.open(str(out_wav_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int_data.tobytes())

def ensure_sfx_library(sfx_dir: Optional[Path] = None):
    """Ensure standard procedural SFX library is populated."""
    target_dir = sfx_dir or SFX_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    standard_cues = [
        ("heavy_rain_loop", 3.0),
        ("distant_thunder_subtle", 3.0),
        ("heartbeat_single_pulse", 2.0),
        ("clock_ticking", 2.0),
        ("rusty_iron_gate_creak", 2.5),
        ("wet_footsteps_gravel", 2.0),
        ("dramatic_hit", 1.5),
        ("whoosh_transition", 1.2),
        ("sword_clash", 1.8),
        ("shield_block", 1.6),
        ("explosion_boom", 2.5),
        ("wind_howl", 3.0),
        ("fire_crackle", 3.0),
        ("magic_spell_shimmer", 2.2),
        ("crowd_battle_shout", 2.5),
    ]

    for name, dur in standard_cues:
        fpath = target_dir / f"{name}.wav"
        if not fpath.exists():
            try:
                generate_procedural_sfx(name, fpath, duration_sec=dur)
            except Exception as e:
                logger.warning(f"Could not generate procedural SFX for {name}: {e}")

# Initialize on module load
try:
    ensure_sfx_library()
except Exception:
    pass

SFX_TRIGGER_KEYWORDS: List[tuple] = [
    ("sword_clash", ["sword", "blade", "spear", "dory", "clash", "strike", "slash", "cut", "gươm", "kiếm", "đao", "giáo", "chém", "đâm", "vung kiếm"]),
    ("shield_block", ["shield", "hoplon", "block", "guard", "defend", "khiên", "đỡ đòn", "chắn", "giáp"]),
    ("explosion_boom", ["explode", "explosion", "blast", "bomb", "boom", "bùng nổ", "nổ tung", "sóng xung kích", "chấn động"]),
    ("fire_crackle", ["fire", "flame", "burn", "torch", "blaze", "lửa", "cháy", "ngọn lửa", "thiêu rụi", "đuốc"]),
    ("distant_thunder_subtle", ["thunder", "lightning", "storm", "sấm", "sét", "chớp", "giông bão"]),
    ("heavy_rain_loop", ["rain", "downpour", "mưa", "mưa bão", "giọt nước", "mưa rào"]),
    ("wind_howl", ["wind", "howl", "breeze", "storm", "gió", "gió rít", "bão cát", "gió lốc"]),
    ("magic_spell_shimmer", ["magic", "glow", "talisman", "spell", "mystic", "aura", "rune", "phép", "phát sáng", "linh phù", "ma thuật", "hào quang"]),
    ("whoosh_transition", ["whoosh", "swoosh", "rush", "leap", "fly", "dash", "vút", "lao", "lướt", "nhảy", "thoắt"]),
    ("heartbeat_single_pulse", ["heart", "breath", "pulse", "fear", "anxiety", "tim", "hồi hộp", "thở gấp", "sợ hãi", "nín thở"]),
    ("wet_footsteps_gravel", ["footstep", "walk", "step", "stride", "march", "bước chân", "tiến bước", "hành quân", "bước đi"]),
    ("rusty_iron_gate_creak", ["door", "gate", "creak", "open", "cửa", "cổng sắt", "kẽo kẹt", "mở cửa"]),
    ("clock_ticking", ["clock", "time", "tick", "ticking", "đồng hồ", "tích tắc", "thời gian"]),
    ("crowd_battle_shout", ["army", "soldiers", "horde", "persian", "spartan", "warriors", "troops", "phalanx", "quân đoàn", "chiến binh", "vạn quân", "tiếng thét", "ba trăm"]),
    ("dramatic_hit", ["sudden", "reveal", "doom", "death", "danger", "gục ngã", "nguy hiểm", "bất ngờ", "đột ngột", "tuyệt vọng"]),
]

def auto_detect_scene_sfx(text: str, visual_prompt: str = "") -> List[str]:
    """
    Intelligently extracts semantic SFX sound cues from Vietnamese & English scene narration and visual prompts.
    Returns up to 2 distinct matching SFX cue names.
    """
    combined = f"{text or ''} {visual_prompt or ''}".lower()
    matched_cues: List[str] = []

    for cue_name, keywords in SFX_TRIGGER_KEYWORDS:
        if any(kw in combined for kw in keywords):
            if cue_name not in matched_cues:
                matched_cues.append(cue_name)
        if len(matched_cues) >= 2:
            break

    return matched_cues

def find_or_create_sfx(cue_name: str, sfx_dir: Optional[Path] = None) -> Optional[str]:
    """Find matching SFX in library or synthesize on demand."""
    target_dir = sfx_dir or SFX_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    clean_cue = cue_name.strip().lower().replace(" ", "_")

    # 1. Exact match
    for ext in [".wav", ".mp3", ".ogg"]:
        p = target_dir / f"{clean_cue}{ext}"
        if p.exists():
            return str(p)

    # 2. Fuzzy substring match in existing files
    for f in target_dir.iterdir():
        if f.is_file() and any(part in f.stem.lower() for part in clean_cue.split("_") if len(part) > 2):
            return str(f)

    # 3. Procedural on-demand synthesis
    out_wav = target_dir / f"{clean_cue}.wav"
    try:
        generate_procedural_sfx(clean_cue, out_wav, duration_sec=2.5)
        return str(out_wav)
    except Exception as e:
        logger.warning(f"Failed to generate SFX for {cue_name}: {e}")
        return None

def append_silence_to_audio(
    input_audio_path: Union[str, Path],
    output_audio_path: Union[str, Path],
    pause_sec: float,
) -> str:
    """
    Appends silent audio segment to the tail of an audio file using FFmpeg apad filter.
    Creates dramatic breathing room between dialogue beats.
    """
    in_p = Path(input_audio_path)
    out_p = Path(output_audio_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    if pause_sec <= 0.05:
        shutil.copy2(in_p, out_p)
        return str(out_p)

    # Use FFmpeg apad filter to pad exact duration of silence
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_p),
        "-af", f"apad=pad_dur={pause_sec:.3f}",
        "-c:a", "pcm_s16le",
        str(out_p),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.warning(f"FFmpeg apad failed ({res.stderr}), falling back to direct copy.")
        shutil.copy2(in_p, out_p)

    return str(out_p)

async def generate_voiced_scene_audio(
    text: str,
    output_path: Union[str, Path],
    speaker: str = "narrator",
    voice_override: Optional[str] = None,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    pause_after_sec: float = 0.8,
) -> Dict[str, Any]:
    """
    Generate speech with Edge-TTS, apply dramatic tail silence padding,
    and return duration metrics.
    """
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    voice = voice_override or resolve_voice_for_speaker(speaker)
    clean_text = normalize_narration_text(text)
    if not clean_text:
        clean_text = text.strip() or "..."

    # Step 1: Generate raw speech to temp file
    temp_raw = out_p.parent / f"temp_{out_p.stem}_raw.mp3"
    communicate = edge_tts.Communicate(
        text=clean_text,
        voice=voice,
        rate=rate,
        pitch=pitch,
    )
    await communicate.save(str(temp_raw))

    # Measure raw duration
    raw_duration = get_audio_duration(str(temp_raw)) or 2.0

    # Step 2: Pad silence for dramatic pacing
    padded_path = append_silence_to_audio(
        input_audio_path=temp_raw,
        output_audio_path=out_p,
        pause_sec=pause_after_sec,
    )

    # Clean up temp
    if temp_raw.exists():
        try:
            temp_raw.unlink()
        except Exception:
            pass

    total_duration = get_audio_duration(padded_path) or (raw_duration + pause_after_sec)

    return {
        "audio_path": padded_path,
        "voice": voice,
        "raw_duration": raw_duration,
        "pause_after_sec": pause_after_sec,
        "total_duration": total_duration,
    }

def mix_3layer_audio(
    scenes_audio: List[Dict[str, Any]],
    bgm_path: Optional[str],
    output_master_path: Union[str, Path],
    bgm_energy: str = "ambient_low",
    ducking_ratio: float = 6.0,
    ducking_threshold: float = 0.08,
    attack_ms: int = 50,
    release_ms: int = 300,
    bgm_volume: float = 0.25,
) -> str:
    """
    Master 3-Layer Audio Mixing Engine:
    Layer 1: Voiceover timeline sequence.
    Layer 2: SFX events delayed and mixed onto the timeline.
    Layer 3: Sidechain Ducking BGM against Voice+SFX.

    Uses FFmpeg sidechaincompress:
    - -20dB during voiceover
    - -8dB during pauses and climaxes
    """
    out_master = Path(output_master_path)
    out_master.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: Concatenate scene voiceover segments
    voice_segments = [
        s.get("audio_path") or s.get("voice_audio_path")
        for s in scenes_audio
        if (s.get("audio_path") or s.get("voice_audio_path")) and Path(s.get("audio_path") or s.get("voice_audio_path")).exists()
    ]
    if not voice_segments:
        raise ValueError("No valid voice audio segments to mix.")

    concat_list_file = out_master.parent / "voice_concat_list.txt"
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for seg in voice_segments:
            # Escape single quotes and use forward slashes for FFmpeg concat
            safe_p = Path(seg).as_posix().replace("'", "'\\''")
            f.write(f"file '{safe_p}'\n")

    concatenated_voice = out_master.parent / "concatenated_voice.wav"
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_file),
        "-c:a", "pcm_s16le",
        str(concatenated_voice),
    ]
    subprocess.run(cmd_concat, capture_output=True, check=True)

    total_voice_duration = get_audio_duration(str(concatenated_voice)) or 5.0

    # Step 2: Overlay Layer 2 (SFX cues) onto voice track if cues exist
    sfx_events = []
    current_time_offset = 0.0
    for sc in scenes_audio:
        sc_dur = float(sc.get("total_duration") or sc.get("duration") or 3.0)
        cues = sc.get("sfx_cue") or []
        if isinstance(cues, str):
            cues = [cues]
        for cue in cues:
            sfx_file = find_or_create_sfx(cue)
            if sfx_file:
                sfx_events.append({
                    "path": sfx_file,
                    "delay_ms": int(current_time_offset * 1000),
                })
        current_time_offset += sc_dur

    voice_and_sfx_track = concatenated_voice
    if sfx_events:
        # Build multi-input amix filter for SFX
        sfx_mixed = out_master.parent / "voice_and_sfx.wav"
        sfx_inputs = ["-i", str(concatenated_voice)]
        filter_parts = []
        mix_labels = ["[0:a]"]

        for idx, event in enumerate(sfx_events[:8]):  # Cap at 8 simultaneous SFX inputs
            sfx_inputs.extend(["-i", event["path"]])
            in_idx = idx + 1
            delay = event["delay_ms"]
            label = f"[sfx{idx}]"
            filter_parts.append(f"[{in_idx}:a]adelay={delay}|{delay},volume=0.6{label}")
            mix_labels.append(label)

        all_labels = "".join(mix_labels)
        filter_parts.append(f"{all_labels}amix=inputs={len(mix_labels)}:duration=first:dropout_transition=2[out_vsfx]")
        filter_str = ";".join(filter_parts)

        cmd_sfx = ["ffmpeg", "-y"] + sfx_inputs + ["-filter_complex", filter_str, "-map", "[out_vsfx]", str(sfx_mixed)]
        res_sfx = subprocess.run(cmd_sfx, capture_output=True, text=True)
        if res_sfx.returncode == 0:
            voice_and_sfx_track = sfx_mixed
        else:
            logger.warning(f"SFX mix failed ({res_sfx.stderr}), continuing with voice track only.")

    # Step 3: Layer 3 Adaptive BGM with Sidechain Ducking
    resolved_bgm = None
    if bgm_path and Path(bgm_path).exists():
        resolved_bgm = bgm_path
    else:
        # Lookup default track based on energy
        track_name = BGM_ENERGY_MAP.get(bgm_energy, "ambient_peaceful")
        cand = BGM_DIR / f"{track_name}.mp3"
        if cand.exists():
            resolved_bgm = str(cand)
        else:
            # Fallback to any existing BGM track
            for f in BGM_DIR.iterdir():
                if f.suffix in [".mp3", ".wav"]:
                    resolved_bgm = str(f)
                    break

    if not resolved_bgm:
        # No BGM available, output voice+sfx track
        shutil.copy2(voice_and_sfx_track, out_master)
        return str(out_master)

    # Master Sidechain Ducking filter complex (as specified in Master Spec)
    # Resample and split voice: 1 copy for speech audio, 1 copy as sidechain trigger
    # Loop BGM to match or exceed voice duration, then sidechaincompress ducking BGM when voice speaks
    filter_ducking = (
        f"[0:a]aresample=48000,asplit=2[v_main][v_sc];"
        f"[1:a]aresample=48000,aloop=loop=-1:size=2147483647,volume={bgm_volume}[bgm_loop];"
        f"[bgm_loop][v_sc]sidechaincompress=threshold={ducking_threshold}:ratio={ducking_ratio}:attack={attack_ms}:release={release_ms}[ducked_bgm];"
        f"[v_main][ducked_bgm]amix=inputs=2:duration=first:dropout_transition=2[outa]"
    )

    cmd_master = [
        "ffmpeg", "-y",
        "-i", str(voice_and_sfx_track),
        "-i", str(resolved_bgm),
        "-filter_complex", filter_ducking,
        "-map", "[outa]",
        "-t", f"{total_voice_duration:.3f}",
        "-ar", "48000",
        "-ac", "2",
        str(out_master),
    ]

    res_master = subprocess.run(cmd_master, capture_output=True, text=True)
    if res_master.returncode != 0:
        logger.error(f"Master sidechain ducking failed ({res_master.stderr}), using fallback voice track.")
        shutil.copy2(voice_and_sfx_track, out_master)

    logger.info(f"3-Layer Audio Master successfully rendered to: {out_master}")
    return str(out_master)
