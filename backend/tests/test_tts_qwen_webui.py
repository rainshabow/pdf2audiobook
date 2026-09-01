import io
import wave

import httpx
import pytest

from app.services.tts.base import AudioResult
from app.services.tts.qwen_webui import QwenWebUIAdapter


def _wav_bytes(duration: float = 1.5) -> bytes:
    import math
    import struct
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        n = int(24000 * duration)
        w.writeframes(b"".join(
            struct.pack("<h", int(1000 * math.sin(2 * math.pi * 440 * i / 24000)))
            for i in range(n)))
    return buf.getvalue()


def _json_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _wav_response(payload: dict, wav: bytes) -> httpx.Response:
    import base64
    payload = {**payload, "audio_files_base64": [base64.b64encode(wav).decode()]}
    return httpx.Response(200, json=payload)


@pytest.mark.asyncio
async def test_list_models_and_speakers():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return _json_response({"models": [{"name": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "type": "custom"}]})
        if request.url.path.endswith("/speakers"):
            return _json_response({"speakers": ["小明"]})
        return _json_response({})

    adapter = QwenWebUIAdapter("http://127.0.0.1:7860", "m1")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    models = await adapter.list_models()
    speakers = await adapter.list_speakers()
    assert models[0]["name"].endswith("CustomVoice")
    assert speakers == ["小明"]
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_synthesize_posts_custom_voice_and_reads_duration():
    wav = _wav_bytes(1.5)
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        return _wav_response({}, wav)

    adapter = QwenWebUIAdapter("http://127.0.0.1:7860", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await adapter.synthesize("测试文本", voice="小明", language="zh", instruct="用温柔的语气说")
    assert isinstance(result, AudioResult)
    assert abs(result.duration - 1.5) < 0.02
    import json
    body = json.loads(captured["body"])
    assert body["model_name"] == "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    assert body["text"] == "测试文本"
    assert body["speaker"] == "小明"
    assert body["language"] == "zh"
    assert body["instruct"] == "用温柔的语气说"
    assert body["segment_gen"] is False
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_interrupt_posts():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = str(request.url.path)
        return _json_response({"message": "ok"})

    adapter = QwenWebUIAdapter("http://127.0.0.1:7860", "m1")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await adapter.interrupt()
    assert captured["path"] == "/qwenapi/v1/interrupt"
    await adapter._client.aclose()
