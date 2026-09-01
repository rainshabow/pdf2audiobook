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
