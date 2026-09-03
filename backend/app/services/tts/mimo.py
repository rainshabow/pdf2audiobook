"""MiMo-TTS（小米 MiMo API，OpenAI Chat 兼容）适配器。

接口：POST {base}/chat/completions
认证：请求头 `api-key: $MIMO_API_KEY`
参考：https://mimo.mi.com/docs/zh-CN/api/audio/tts
"""

import base64
import io
import wave

import httpx

from app.services.ratelimit import AsyncRateLimiter
from app.services.tts.base import AudioResult, TTSAdapter

MODELS = [
    {"name": "mimo-v2.5-tts", "type": "custom"},
    {"name": "mimo-v2.5-tts-voicedesign", "type": "voice_design"},
    {"name": "mimo-v2.5-tts-voiceclone", "type": "voice_clone"},
]
VOICES = ["mimo_default", "冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"]
_DEFAULT_DESIGN = "自然、平稳、适合有声书的中文普通话朗读"


class MimoTTSAdapter(TTSAdapter):
    """MiMo-TTS 云端 TTS：每次请求合成一段文本，返回 base64 音频。"""

    def __init__(self, base_url: str, model: str, api_key: str,
                 timeout: float = 180.0, rpm: int = 0):
        self._base = base_url.rstrip("/")
        self._model = model or "mimo-v2.5-tts"
        self._api_key = api_key or ""
        self._client = httpx.AsyncClient(timeout=timeout)
        # 云端账号按 RPM 限流：>0 时每个 HTTP 请求先取令牌（不设并发上限也能兜底防 429）
        self._limiter = AsyncRateLimiter(rpm) if rpm > 0 else None

    async def list_models(self) -> list[dict]:
        return list(MODELS)

    async def list_speakers(self) -> list[dict]:
        return [{"name": v} for v in VOICES]

    async def synthesize(self, text: str, *, voice: str | None = None,
                         speed: float = 1.0, language: str | None = None,
                         instruct: str | None = None) -> AudioResult:
        return (await self._synthesize_many([text], model=self._model,
                                            voice=voice, instruct=instruct))[0]

    async def synthesize_clone_batch(self, texts: list[str], *, ref_audio: bytes,
                                      ref_text: str | None = None,
                                      language: str | None = None) -> list[AudioResult]:
        """语音克隆：voiceclone 模型固定，voice 字段传参考音频 base64。"""
        return await self._synthesize_many(
            texts, model="mimo-v2.5-tts-voiceclone",
            voice=base64.b64encode(ref_audio).decode(), instruct=None)

    async def synthesize_clone(self, text: str, *, ref_audio: bytes,
                               ref_text: str | None = None,
                               language: str | None = None) -> AudioResult:
        return (await self.synthesize_clone_batch([text], ref_audio=ref_audio,
                                                  ref_text=ref_text))[0]

    async def _synthesize_many(self, texts: list[str], *, model: str,
                               voice: str | None, instruct: str | None) -> list[AudioResult]:
        if not texts:
            return []
        results: list[AudioResult] = []
        for text in texts:
            body = self._build_body(model, text, voice=voice, instruct=instruct)
            if self._limiter is not None:
                await self._limiter.acquire()
            r = await self._client.post(
                f"{self._base}/chat/completions",
                headers={"api-key": self._api_key, "Content-Type": "application/json"},
                json=body,
            )
            if r.status_code >= 400:
                detail = r.text
                try:
                    err = r.json().get("error", {})
                    detail = err.get("message", r.text) if isinstance(err, dict) else r.text
                except Exception:
                    pass
                raise RuntimeError(f"mimo-tts 错误 {r.status_code}: {detail}")
            data = r.json().get("choices", [{}])[0].get("message", {}).get("audio", {}).get("data")
            if not data:
                raise RuntimeError("mimo-tts 未返回音频")
            wav = base64.b64decode(data)
            results.append(AudioResult(data=wav, duration=_wav_duration(wav), format="wav"))
        return results

    @staticmethod
    def _build_body(model: str, text: str, *, voice: str | None,
                    instruct: str | None) -> dict:
        """按模型语义构造请求体。

        - mimo-v2.5-tts：voice 传预置音色 ID（默认 mimo_default）；user 消息可选
        - mimo-v2.5-tts-voicedesign：不支持 voice；user 消息必填（音色设计描述）
        - mimo-v2.5-tts-voiceclone：voice 必填，传参考音频 base64
        """
        messages = []
        if model == "mimo-v2.5-tts-voicedesign":
            messages.append({"role": "user", "content": instruct or _DEFAULT_DESIGN})
        elif instruct:
            messages.append({"role": "user", "content": instruct})
        messages.append({"role": "assistant", "content": text})
        audio: dict = {"format": "wav"}
        if model == "mimo-v2.5-tts-voicedesign":
            pass  # 不支持 voice 字段
        elif model == "mimo-v2.5-tts-voiceclone":
            if not voice:
                raise ValueError("mimo voiceclone 需要参考音频")
            audio["voice"] = voice  # base64 音频样本
        else:
            audio["voice"] = voice or "mimo_default"
        return {"model": model, "messages": messages, "audio": audio, "stream": False}

    async def interrupt(self) -> None:
        # 云端请求无法中断单次调用；任务取消由 JobManager 在批次间检查
        return None

    async def aclose(self) -> None:
        await self._client.aclose()


def _wav_duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()
