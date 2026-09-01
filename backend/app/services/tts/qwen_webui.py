import base64
import io
import wave

import httpx

from app.services.tts.base import AudioResult, TTSAdapter


class QwenWebUIAdapter(TTSAdapter):
    """调用本机 qwen-tts-webui 的 /qwenapi/v1/* HTTP 接口。"""

    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self._base = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=timeout)

    async def list_models(self) -> list[dict]:
        r = await self._client.get(f"{self._base}/qwenapi/v1/models")
        r.raise_for_status()
        return r.json().get("models", [])

    async def list_speakers(self) -> list[dict]:
        r = await self._client.get(f"{self._base}/qwenapi/v1/speakers")
        r.raise_for_status()
        return r.json().get("speakers", [])

    async def synthesize(self, text: str, *, voice: str | None = None,
                         speed: float = 1.0, language: str | None = None,
                         instruct: str | None = None) -> AudioResult:
        body = {
            "model_name": self._model,
            "text": text,
            "speaker": voice,
            "instruct": instruct or "",  # webui 要求字符串，None 会 422
            "language": language,
            "segment_gen": False,
        }
        r = await self._client.post(f"{self._base}/qwenapi/v1/custom-voice", json=body)
        if r.status_code >= 400:
            detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
            raise RuntimeError(f"qwen-tts-webui 错误 {r.status_code}: {detail}")
        data = r.json().get("audio_files_base64", [])
        if not data:
            raise RuntimeError("qwen-tts-webui 未返回音频")
        wav = base64.b64decode(data[0])
        return AudioResult(data=wav, duration=_wav_duration(wav), format="wav")

    async def interrupt(self) -> None:
        try:
            await self._client.post(f"{self._base}/qwenapi/v1/interrupt")
        except httpx.HTTPError:
            pass  # 引擎可能不在线，取消任务本身仍需继续

    async def aclose(self) -> None:
        await self._client.aclose()


def _wav_duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()
