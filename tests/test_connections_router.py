"""Trang Tài khoản và kết nối: /api/connections/status và /llm-ping (không gọi mạng, không gọi AI thật)."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config
from main import app
from routers import connections
from services import case_adaptation_llm

SECRET = "sk-bi-mat-123"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(connections, "_port_open", lambda host, port: False)
    return TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


def test_status_never_returns_secret(client, monkeypatch):
    monkeypatch.setattr(config, "NINEROUTER_API_KEY", SECRET)
    monkeypatch.setattr(config, "YOUTUBE_API_KEY", "yt-bi-mat-456")
    r = client.get("/api/connections/status")
    assert r.status_code == 200
    body = r.json()
    assert body["llm"]["has_key"] is True and body["youtube"]["has_key"] is True
    assert SECRET not in r.text and "yt-bi-mat-456" not in r.text
    assert set(body["llm"]) == {"base_url", "has_key", "text_model", "image_model"}
    assert body["vieneu"] == {"port_open": False}
    assert body["image_provider_default"] == config.DEFAULT_IMAGE_PROVIDER


def test_status_without_keys(client, monkeypatch):
    monkeypatch.setattr(config, "NINEROUTER_API_KEY", "")
    monkeypatch.setattr(config, "YOUTUBE_API_KEY", "  ")
    body = client.get("/api/connections/status").json()
    assert body["llm"]["has_key"] is False and body["youtube"]["has_key"] is False


def test_status_reports_vieneu_port_open(client, monkeypatch):
    monkeypatch.setattr(connections, "_port_open", lambda host, port: (host, port) == (config.VIENEU_HOST, config.VIENEU_PORT))
    assert client.get("/api/connections/status").json()["vieneu"]["port_open"] is True


def test_ping_reports_llm_failure_without_500(client, monkeypatch):
    monkeypatch.setattr(config, "NINEROUTER_API_KEY", SECRET)

    async def boom(*a, **k):
        raise case_adaptation_llm.LLMError("network", f"Không kết nối được 9router, key {SECRET}")
    monkeypatch.setattr(case_adaptation_llm, "call_llm_json", boom)
    r = client.post("/api/connections/llm-ping")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and "9router" in body["error"]
    assert SECRET not in r.text


def test_ping_reports_unexpected_exception_without_500(client, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("hỏng bất ngờ")
    monkeypatch.setattr(case_adaptation_llm, "call_llm_json", boom)
    r = client.post("/api/connections/llm-ping")
    assert r.status_code == 200 and r.json()["ok"] is False and "RuntimeError" in r.json()["error"]


def test_ping_reports_success_time(client, monkeypatch):
    async def fine(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(case_adaptation_llm, "call_llm_json", fine)
    body = client.post("/api/connections/llm-ping").json()
    assert body["ok"] is True and body["error"] is None and body["seconds"] >= 0
