import base64
import io
import wave

import httpx

from app.services.tts.base import AudioResult, TTSAdapter


class QwenWebUIAdapter(TTSAdapter):
    """调用本机 qwen-tts-webui 的 /qwenapi/v1/* HTTP 接口。"""

    def __init__(self, base_url: str, model: str, timeout: float = 600.0):
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

    async def synthesize_batch(self, texts: list[str], *, voice: str | None = None,
                               language: str | None = None,
                               instruct: str | None = None) -> list[AudioResult]:
        if not texts:
            return []
        body = {
            "model_name": self._model,
            "text": "\n".join(t.replace("\n", " ") for t in texts),
            "speaker": voice,
            "instruct": instruct or "",
            "language": language,
            "segment_gen": True,  # 一次提交多句，减少请求次数并保持语气一致
        }
        wavs = await self._post_audio(f"{self._base}/qwenapi/v1/custom-voice", body,
                                      expected=len(texts))
        return [AudioResult(data=w, duration=_wav_duration(w), format="wav") for w in wavs]

    async def synthesize_clone_batch(self, texts: list[str], *, ref_audio: bytes,
                                      ref_text: str | None = None,
                                      language: str | None = None) -> list[AudioResult]:
        if not texts:
            return []
        model = self._model.replace("CustomVoice", "Base")  # 克隆使用 Base 模型
        body = {
            "model_name": model,
            "text": "\n".join(t.replace("\n", " ") for t in texts),
            "ref_audio_base64": base64.b64encode(ref_audio).decode(),
            "ref_text": ref_text,
            "language": language,
            "segment_gen": True,
        }
        wavs = await self._post_audio(f"{self._base}/qwenapi/v1/voice-clone", body,
                                      expected=len(texts))
        return [AudioResult(data=w, duration=_wav_duration(w), format="wav") for w in wavs]

    async def synthesize_clone(self, text: str, *, ref_audio: bytes,
                               ref_text: str | None = None,
                               language: str | None = None) -> AudioResult:
        results = await self.synthesize_clone_batch([text], ref_audio=ref_audio,
                                                    ref_text=ref_text, language=language)
        return results[0]

    async def _post_audio(self, url: str, body: dict, expected: int) -> list[bytes]:
        r = await self._client.post(url, json=body)
        if r.status_code >= 400:
            detail = (r.json().get("detail", r.text)
                      if r.headers.get("content-type", "").startswith("application/json") else r.text)
            raise RuntimeError(f"qwen-tts-webui 错误 {r.status_code}: {detail}")
        data = r.json().get("audio_files_base64", [])
        if len(data) != expected:
            raise RuntimeError(f"qwen-tts-webui 返回音频数 {len(data)} != 期望 {expected}")
        return [base64.b64decode(x) for x in data]

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
