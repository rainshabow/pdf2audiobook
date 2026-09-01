import io
import math
import struct
import wave

from app.services.tts.base import AudioResult, TTSAdapter

_SAMPLE_RATE = 24000


class MockTTSAdapter(TTSAdapter):
    """开发/测试引擎：按文本长度生成固定时长正弦 WAV。"""

    async def list_models(self) -> list[dict]:
        return [{"name": "mock-voice", "type": "custom"}]

    async def list_speakers(self) -> list[dict]:
        return [{"name": "测试音色"}]

    async def synthesize(self, text: str, *, voice: str | None = None,
                         speed: float = 1.0, language: str | None = None,
                         instruct: str | None = None) -> AudioResult:
        duration = max(1.0, len(text) * 0.08)  # 调速统一由 job_manager 后处理
        data = _sine_wav(duration)
        return AudioResult(data=data, duration=duration, format="wav")

    async def synthesize_clone(self, text: str, *, ref_audio: bytes,
                               ref_text: str | None = None,
                               language: str | None = None) -> AudioResult:
        # 测试引擎：克隆与普通合成等价
        return await self.synthesize(text)


def _sine_wav(duration: float) -> bytes:
    n = int(_SAMPLE_RATE * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SAMPLE_RATE)
        frames = bytearray()
        for i in range(n):
            t = i / _SAMPLE_RATE
            # 440Hz 低音量正弦，避免测试时刺耳
            sample = int(1200 * math.sin(2 * math.pi * 440 * t))
            frames += struct.pack("<h", sample)
        w.writeframes(bytes(frames))
    return buf.getvalue()
