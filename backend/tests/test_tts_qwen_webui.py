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
    # instruct=None 时应发送空字符串（webui 要求 str，不允许 null）
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


@pytest.mark.asyncio
async def test_synthesize_none_instruct_sent_as_empty_string():
    import base64
    import io
    import math
    import struct
    import wave

    wav = _wav_bytes(1.0)
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured["body"] = json.loads(request.content)
        payload = {"audio_files_base64": [base64.b64encode(wav).decode()]}
        return httpx.Response(200, json=payload)

    adapter = QwenWebUIAdapter("http://127.0.0.1:7860", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await adapter.synthesize("测试文本", voice=None, language=None, instruct=None)
    assert captured["body"]["instruct"] == ""
    assert "speaker" in captured["body"] and captured["body"]["speaker"] is None
    assert "language" in captured["body"] and captured["body"]["language"] is None
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_synthesize_batch_uses_segment_gen():
    import base64
    import io
    import math
    import struct
    import wave

    def wav(dur=0.5):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            n = int(24000 * dur)
            w.writeframes(b"".join(struct.pack("<h", int(500 * math.sin(2 * math.pi * 440 * i / 24000))) for i in range(n)))
        return buf.getvalue()

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured["body"] = json.loads(request.content)
        payload = {"audio_files_base64": [base64.b64encode(wav()).decode() for _ in range(2)]}
        return httpx.Response(200, json=payload)

    adapter = QwenWebUIAdapter("http://127.0.0.1:7860", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    results = await adapter.synthesize_batch(
        ["第一句。\n第二句。", "第三句。"], voice="serena", instruct="平稳")
    assert len(results) == 2
    assert captured["body"]["segment_gen"] is True
    assert captured["body"]["text"] == "第一句。 第二句。\n第三句。"  # 内部换行替换
    assert captured["body"]["speaker"] == "serena"
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_synthesize_clone_batch_posts_voice_clone():
    import base64
    import io
    import math
    import struct
    import wave

    def wav(dur=0.5):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            n = int(24000 * dur)
            w.writeframes(b"".join(struct.pack("<h", int(500 * math.sin(2 * math.pi * 440 * i / 24000))) for i in range(n)))
        return buf.getvalue()

    ref_wav = wav()
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured["body"] = json.loads(request.content)
        payload = {"audio_files_base64": [base64.b64encode(wav()).decode()]}
        return httpx.Response(200, json=payload)

    adapter = QwenWebUIAdapter("http://127.0.0.1:7860", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    results = await adapter.synthesize_clone_batch(
        ["克隆测试。"], ref_audio=ref_wav, ref_text="参考文本")
    assert len(results) == 1
    assert captured["body"]["model_name"] == "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    assert captured["body"]["segment_gen"] is True
    assert captured["body"]["ref_audio_base64"] == base64.b64encode(ref_wav).decode()
    assert captured["body"]["ref_text"] == "参考文本"
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_list_endpoints_degrade_on_500_or_offline():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "模型未加载"})

    adapter = QwenWebUIAdapter("http://127.0.0.1:7860", "m1")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await adapter.list_models() == []
    assert await adapter.list_speakers() == []

    async def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    adapter2 = QwenWebUIAdapter("http://127.0.0.1:7860", "m1")
    adapter2._client = httpx.AsyncClient(transport=httpx.MockTransport(offline))
    assert await adapter2.list_models() == []
    assert await adapter2.list_speakers() == []
    await adapter._client.aclose()
    await adapter2._client.aclose()
