"""Ảnh Gemini qua cổng AI kiểu OpenAI: 9router trả ảnh ở /images/generations, CLI Proxy chỉ trả ở /chat/completions.

Đo thật 09/11/2026: CLI Proxy báo HTTP 400 "Model gemini-3.1-flash-image is not supported on /v1/images/generations"
và trả ảnh trong choices[0].message.images[0].image_url.url dạng data:image/jpeg;base64,...
"""
import asyncio
import base64
import io
import json

import httpx
import pytest
from PIL import Image

import config
from services import image_service


def _jpeg_bytes(w=320, h=180):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 60, 90)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def fake_gateway(monkeypatch):
    """Thay httpx.AsyncClient trong image_service bằng client chạy qua handler giả; trả list các request đã nhận."""
    calls = []
    state = {"handler": None}

    def transport_handler(request: httpx.Request):
        calls.append((request.url.path, json.loads(request.content or b"{}")))
        return state["handler"](request)

    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(transport_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(image_service.httpx, "AsyncClient", make_client)
    # image_service đọc hằng lúc import, client LLM chung đọc config lúc gọi: đổi cả hai
    for mod in (image_service, config):
        monkeypatch.setattr(mod, "NINEROUTER_BASE_URL", "http://gateway.test/v1")
        monkeypatch.setattr(mod, "NINEROUTER_API_KEY", "k")
    return state, calls


def test_cli_proxy_image_comes_from_chat_endpoint(fake_gateway, tmp_path):
    state, calls = fake_gateway
    data_url = "data:image/jpeg;base64," + base64.b64encode(_jpeg_bytes()).decode()

    def handler(request):
        if request.url.path.endswith("/images/generations"):
            return httpx.Response(400, json={"error": {"message": "Model gemini-3.1-flash-image is not supported on /v1/images/generations or /v1/images/edits."}})
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "images": [{"type": "image_url", "image_url": {"url": data_url}}]}}]})

    state["handler"] = handler
    out = tmp_path / "a.jpg"
    path = asyncio.run(image_service.generate_9router_gemini("harbor", str(out), model="gemini-3.1-flash-image"))

    assert [c[0] for c in calls] == ["/v1/images/generations", "/v1/chat/completions"]
    chat_body = calls[1][1]
    assert chat_body["model"] == "gemini-3.1-flash-image"
    assert "harbor" in chat_body["messages"][0]["content"]
    with Image.open(path) as im:
        assert abs(im.size[0] / im.size[1] - 16 / 9) < 0.02


def test_chat_endpoint_without_image_is_an_error_not_success(fake_gateway, tmp_path):
    state, _ = fake_gateway

    def handler(request):
        if request.url.path.endswith("/images/generations"):
            return httpx.Response(400, json={"error": {"message": "Model x is not supported on /v1/images/generations"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Tôi không vẽ được ảnh này."}}]})

    state["handler"] = handler
    out = tmp_path / "a.jpg"
    with pytest.raises(RuntimeError, match="không vẽ được"):
        asyncio.run(image_service.generate_9router_gemini("harbor", str(out)))
    assert not out.exists()


def test_other_http_errors_do_not_switch_endpoint(fake_gateway, tmp_path):
    state, calls = fake_gateway
    state["handler"] = lambda request: httpx.Response(401, json={"error": "Invalid API key"})
    with pytest.raises(RuntimeError, match="401"):
        asyncio.run(image_service.generate_9router_gemini("harbor", str(tmp_path / "a.jpg")))
    assert [c[0] for c in calls] == ["/v1/images/generations"]


def test_9router_images_endpoint_still_works(fake_gateway, tmp_path):
    state, calls = fake_gateway
    b64 = base64.b64encode(_jpeg_bytes(400, 400)).decode()
    state["handler"] = lambda request: httpx.Response(200, json={"data": [{"b64_json": b64}]})
    path = asyncio.run(image_service.generate_9router_gemini("harbor", str(tmp_path / "a.jpg")))
    assert [c[0] for c in calls] == ["/v1/images/generations"]
    with Image.open(path) as im:
        assert abs(im.size[0] / im.size[1] - 16 / 9) < 0.02
