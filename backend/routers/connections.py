"""Trạng thái kết nối cho trang Tài khoản và kết nối.

- GET  /api/connections/status    cổng AI viết lời, model, có khoá hay chưa (chỉ true/false, không bao giờ trả khoá),
  có YOUTUBE_API_KEY chưa, nguồn tạo ảnh mặc định, cổng VieNeu có mở không (nối TCP ngắn, không tốn lượt AI).
- POST /api/connections/llm-ping  một lần gọi AI rất ngắn qua services/case_adaptation_llm.py (tốn 1 lượt AI);
  lỗi thì trả ok=false kèm câu lỗi, vẫn HTTP 200.
"""
import asyncio
import logging
import socket
import time

import config
from fastapi import APIRouter

from services import case_adaptation_llm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/connections", tags=["Connections"])

PING_TIMEOUT_SEC = 20.0
PORT_PROBE_TIMEOUT_SEC = 0.3


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=PORT_PROBE_TIMEOUT_SEC):
            return True
    except OSError as exc:
        logger.info("Cổng %s:%s không mở (%s)", host, port, type(exc).__name__)
        return False


def _has(value) -> bool:
    return bool((value or "").strip())


@router.get("/status")
async def connections_status():
    port_open = await asyncio.to_thread(_port_open, config.VIENEU_HOST, config.VIENEU_PORT)
    return {
        "llm": {
            "base_url": config.NINEROUTER_BASE_URL,
            "has_key": _has(config.NINEROUTER_API_KEY),
            "text_model": config.NINEROUTER_LLM_MODEL,
            "image_model": config.NINEROUTER_IMAGE_MODEL,
        },
        "youtube": {"has_key": _has(config.YOUTUBE_API_KEY)},
        "image_provider_default": config.DEFAULT_IMAGE_PROVIDER,
        "vieneu": {"port_open": port_open},
    }


@router.post("/llm-ping")
async def llm_ping():
    key = (config.NINEROUTER_API_KEY or "").strip()
    started = time.monotonic()
    error = None
    try:
        await case_adaptation_llm.call_llm_json(
            'Trả lời đúng một đối tượng JSON.', 'Trả {"ok": true}',
            temperature=0.0, timeout=PING_TIMEOUT_SEC,
        )
    except case_adaptation_llm.LLMError as exc:
        error = case_adaptation_llm._redact(exc.user_message, key)
    except Exception as exc:  # noqa: BLE001 - nút "Gọi thử" phải báo lỗi chứ không trả 500
        error = case_adaptation_llm._redact(f"Gọi thử thất bại ({type(exc).__name__})", key)
    return {"ok": error is None, "seconds": round(time.monotonic() - started, 2), "error": error}
