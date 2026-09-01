import json

from dataclasses import asdict, dataclass, field
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_file_path() -> Path:
    """仓库根 `.env` 的绝对路径（`backend/app/config.py` → parents[2] 即仓库根）。

    后端从 `backend/` 目录启动，`env_file` 若用相对路径会按 cwd 解析而读不到
    仓库根 `.env`，导致 OPENAI_API_KEY 被静默忽略。
    """
    return Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """从 .env 读取的敏感/固定配置。"""
    openai_base_url: str = "https://opencode.ai/zen/go/v1"
    openai_api_key: str = ""
    llm_model: str = "dsv4-flash"
    tts_engine: str = "mock"
    tts_api_url: str = "http://127.0.0.1:7860"
    tts_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    tts_speaker: str | None = None
    tts_speed: float = 1.0
    tts_instruct: str | None = None
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    data_dir: Path = Path("data")

    model_config = SettingsConfigDict(
        env_file=_env_file_path(), env_file_encoding="utf-8", extra="ignore"
    )


@dataclass
class RuntimeSettings:
    """可通过 UI 读写的运行设置（存 data/settings.json，无密钥）。"""
    tts_engine: str = "mock"
    tts_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    tts_speaker: str | None = None
    tts_speed: float = 1.0
    tts_instruct: str | None = None
    llm_model: str = "dsv4-flash"
    chapter_low_chars: int = 5000
    chapter_high_chars: int = 15000


class SettingsStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "settings.json"

    def load(self) -> RuntimeSettings:
        if not self.path.exists():
            return RuntimeSettings()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeSettings(**{k: v for k, v in data.items()
                                  if k in RuntimeSettings.__dataclass_fields__})

    def save(self, rs: RuntimeSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(asdict(rs), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
