"""VieNeu-TTS chạy thường trực: giữ model trong RAM để mỗi cảnh chỉ mất thời gian đọc, không phải nạp lại model.

Dựa trên douyin-movie-studio/backend/services/vieneu_server.py (API tương thích OpenAI /v1/audio/speech).
tts_service.ensure_vieneu_server() tự bật server này khi cần, với cache trên ổ D:
    uv run --with vieneu --python 3.11 backend/services/vieneu_server.py
Cổng mặc định 127.0.0.1:5005 (đổi bằng VIENEU_HOST / VIENEU_PORT).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

# Dùng lại bộ lọc chỉ dẫn sân khấu / nhãn vai của worker CLI để hai đường đọc giống nhau
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vieneu_worker import clean_vietnamese_text  # noqa: E402

app = FastAPI(title="VieNeu-TTS Local Server (Story Studio)", version="1.0")
tts_engine = None
# FastAPI chạy endpoint đồng bộ trên nhiều luồng; model chỉ cho một lượt đọc mỗi lúc
_infer_lock = threading.Lock()


def get_tts():
    global tts_engine
    if tts_engine is None:
        from vieneu import Vieneu
        print("[*] Đang nạp mô hình VieNeu-TTS vào RAM...", flush=True)
        tts_engine = Vieneu()
        print("[✓] Mô hình VieNeu-TTS đã sẵn sàng.", flush=True)
    return tts_engine


class SpeechRequest(BaseModel):
    input: str = Field(..., description="Văn bản cần đọc")
    voice: str = Field(default="Mai Anh", description="Tên giọng VieNeu (vd Mai Anh, Trúc Ly)")
    response_format: Optional[str] = "mp3"
    speed: Optional[float] = 1.0
    temperature: Optional[float] = 0.8


@app.get("/health")
def health_check():
    return {"status": "online", "engine": "VieNeu-TTS", "model_loaded": tts_engine is not None}


@app.get("/voices")
def list_voices():
    import json
    import vieneu
    for name in ("voices_v3_turbo.json", "voices.json"):
        p = Path(vieneu.__file__).parent / "assets" / name
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return {"default_voice": data.get("default_voice"), "voices": sorted(data.get("presets", {}).keys())}
    return {"voices": []}


@app.post("/v1/audio/speech")
def synthesize_speech(req: SpeechRequest):
    clean_text = clean_vietnamese_text(req.input)
    if not clean_text:
        raise HTTPException(status_code=400, detail="Văn bản trống sau khi lọc chỉ dẫn.")

    tts = get_tts()
    try:
        with _infer_lock:
            audio = tts.infer(
                text=clean_text,
                voice=req.voice or "Mai Anh",
                temperature=req.temperature or 0.8,
                apply_watermark=False,
            )
    except Exception as e:
        print(f"[!] VieNeu synthesis error: {e}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=str(e))
    if audio is None or len(audio) == 0:
        raise HTTPException(status_code=500, detail="VieNeu không tạo được âm thanh.")

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "out.wav"
        tts.save(audio, str(wav_path))
        if (req.response_format or "mp3").lower() != "mp3":
            return Response(content=wav_path.read_bytes(), media_type="audio/wav")

        mp3_path = Path(tmp) / "out.mp3"
        cmd = [shutil.which("ffmpeg") or "ffmpeg", "-y", "-i", str(wav_path)]
        if req.speed and abs(req.speed - 1.0) > 0.05:
            cmd += ["-af", f"atempo={req.speed}"]
        cmd += ["-c:a", "libmp3lame", "-b:a", "192k", str(mp3_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not mp3_path.exists() or mp3_path.stat().st_size == 0:
            raise HTTPException(status_code=500, detail="Lỗi chuyển WAV sang MP3 bằng ffmpeg.")
        return Response(content=mp3_path.read_bytes(), media_type="audio/mpeg")


def main():
    host = os.environ.get("VIENEU_HOST", "127.0.0.1")
    port = int(os.environ.get("VIENEU_PORT", "5005"))
    get_tts()  # nạp model trước: /health chỉ trả lời khi đã sẵn sàng
    print(f"[*] VieNeu server: http://{host}:{port}", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
