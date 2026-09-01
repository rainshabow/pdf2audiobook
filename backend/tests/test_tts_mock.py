import io
import wave

import pytest

from app.services.tts import base
from app.services.tts.mock import MockTTSAdapter


@pytest.mark.asyncio
async def test_mock_synthesize_returns_wav_with_duration():
    adapter = MockTTSAdapter()
    result = await adapter.synthesize("你好，这是一个测试。", voice="测试音色")
    assert isinstance(result, base.AudioResult)
    assert result.format == "wav"
    assert len(result.data) > 100
    with wave.open(io.BytesIO(result.data)) as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 24000
        assert w.getsampwidth() == 2
        frames = w.getnframes()
    assert abs(frames / 24000 - result.duration) < 0.01
    assert result.duration >= 1.0


@pytest.mark.asyncio
async def test_mock_lists():
    adapter = MockTTSAdapter()
    assert await adapter.list_models() == [{"name": "mock-voice", "type": "custom"}]
    assert await adapter.list_speakers() == [{"name": "测试音色"}]

@pytest.mark.asyncio
async def test_mock_synthesize_ignores_speed():
    adapter = MockTTSAdapter()
    base = await adapter.synthesize("测试文本", speed=1.0)
    faster = await adapter.synthesize("测试文本", speed=2.0)
    # 调速统一由 job_manager 后处理，mock 引擎必须忽略 speed（Task 5 parked 项收尾）
    assert faster.duration == base.duration
    assert faster.data == base.data
