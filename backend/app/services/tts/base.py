from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AudioResult:
    data: bytes
    duration: float
    format: str = "wav"


class TTSAdapter(ABC):
    @abstractmethod
    async def list_models(self) -> list[dict]:
        ...

    @abstractmethod
    async def list_speakers(self) -> list[dict]:
        ...

    @abstractmethod
    async def synthesize(self, text: str, *, voice: str | None = None,
                         speed: float = 1.0, language: str | None = None,
                         instruct: str | None = None) -> AudioResult:
        ...

    async def interrupt(self) -> None:
        """取消当前引擎任务；不支持时 no-op。"""
        return None

    async def warmup(self) -> None:
        """预加载模型/建立连接（默认 no-op，引擎可覆盖）。"""
        return None

    async def synthesize_batch(self, texts: list[str], *, voice: str | None = None,
                               language: str | None = None,
                               instruct: str | None = None) -> list["AudioResult"]:
        """批量合成（默认逐句调用 synthesize，引擎可覆盖为一次请求）。"""
        return [await self.synthesize(t, voice=voice, language=language, instruct=instruct)
                for t in texts]

    async def synthesize_clone(self, text: str, *, ref_audio: bytes,
                               ref_text: str | None = None,
                               language: str | None = None) -> "AudioResult":
        raise NotImplementedError("当前引擎不支持语音克隆")

    async def synthesize_clone_batch(self, texts: list[str], *, ref_audio: bytes,
                                      ref_text: str | None = None,
                                      language: str | None = None) -> list["AudioResult"]:
        return [await self.synthesize_clone(t, ref_audio=ref_audio, ref_text=ref_text,
                                            language=language)
                for t in texts]
