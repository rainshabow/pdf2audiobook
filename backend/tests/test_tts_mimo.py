import base64
import io
import json
import math
import struct
import wave

import httpx
import pytest

from app.services.tts.base import AudioResult
from app.services.tts.mimo import MODELS, VOICES, MimoTTSAdapter


def _wav_bytes(duration: float = 1.5) -> bytes:
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


def _audio_response(wav: bytes) -> httpx.Response:
    payload = {
        "choices": [{"message": {
            "audio": {"data": base64.b64encode(wav).decode()}
        }}]
    }
    return httpx.Response(200, json=payload)


def _make_adapter(handler) -> MimoTTSAdapter:
    adapter = MimoTTSAdapter("https://api.xiaomimimo.com/v1", "mimo-v2.5-tts",
                             api_key="sk-test")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return adapter


@pytest.mark.asyncio
async def test_list_models_and_speakers():
    adapter = _make_adapter(lambda request: httpx.Response(500))
    models = await adapter.list_models()
    speakers = await adapter.list_speakers()
    assert models == MODELS
    assert speakers == [{"name": v} for v in VOICES]
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_synthesize_posts_chat_completions_and_reads_wav():
    wav = _wav_bytes(1.5)
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return _audio_response(wav)

    adapter = _make_adapter(handler)
    result = await adapter.synthesize("测试文本。", voice="冰糖", instruct="平稳朗读")
    assert isinstance(result, AudioResult)
    assert abs(result.duration - 1.5) < 0.02
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["headers"]["api-key"] == "sk-test"
    body = captured["body"]
    assert body["model"] == "mimo-v2.5-tts"
    assert body["stream"] is False
    assert body["audio"] == {"format": "wav", "voice": "冰糖"}
    # user 消息携带朗读指示，assistant 消息携带待合成文本
    assert body["messages"][0] == {"role": "user", "content": "平稳朗读"}
    assert body["messages"][1] == {"role": "assistant", "content": "测试文本。"}
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_synthesize_without_instruct_omits_user_message():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _audio_response(_wav_bytes(0.5))

    adapter = _make_adapter(handler)
    await adapter.synthesize("测试文本。", voice=None, instruct=None)
    body = captured["body"]
    assert body["audio"]["voice"] == "mimo_default"  # 默认预置音色
    assert body["messages"] == [{"role": "assistant", "content": "测试文本。"}]
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_voicedesign_model_requires_user_message_and_no_voice():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _audio_response(_wav_bytes(0.5))

    adapter = MimoTTSAdapter("https://api.xiaomimimo.com/v1",
                             "mimo-v2.5-tts-voicedesign", api_key="sk-test")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await adapter.synthesize("播报文本。", voice="冰糖", instruct="清亮女声")
    body = captured["body"]
    assert body["model"] == "mimo-v2.5-tts-voicedesign"
    assert "voice" not in body["audio"]
    assert body["messages"][0] == {"role": "user", "content": "清亮女声"}
    assert body["messages"][1] == {"role": "assistant", "content": "播报文本。"}
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_voiceclone_posts_base64_ref_audio():
    ref_wav = _wav_bytes(0.5)
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _audio_response(_wav_bytes(0.5))

    adapter = _make_adapter(handler)
    results = await adapter.synthesize_clone_batch(["克隆句。"], ref_audio=ref_wav,
                                                   ref_text="参考文本")
    assert len(results) == 1
    body = captured["body"]
    assert body["model"] == "mimo-v2.5-tts-voiceclone"
    assert body["audio"]["voice"] == base64.b64encode(ref_wav).decode()
    assert body["messages"][-1] == {"role": "assistant", "content": "克隆句。"}
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_error_response_raises_runtime_error_with_message():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    adapter = _make_adapter(handler)
    with pytest.raises(RuntimeError, match="401.*Invalid API key"):
        await adapter.synthesize("测试文本。")
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_missing_audio_raises_runtime_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {}}]})

    adapter = _make_adapter(handler)
    with pytest.raises(RuntimeError, match="未返回音频"):
        await adapter.synthesize("测试文本。")
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_empty_texts_returns_empty():
    adapter = _make_adapter(lambda request: httpx.Response(500))
    assert await adapter.synthesize_clone_batch([], ref_audio=_wav_bytes(0.1)) == []
    await adapter._client.aclose()
