from pydantic import BaseModel, Field


class ChapterInfo(BaseModel):
    id: str
    title: str
    level: int = 1
    page_start: int = 0
    page_end: int = 0
    char_count: int = 0
    status: str = "pending"  # pending|rewritten|synthesized|failed
    audio_duration: float = 0.0


class Book(BaseModel):
    book_id: str
    title: str
    author: str = ""
    page_count: int = 0
    created_at: str = ""
    status: str = "uploaded"  # uploaded|parsed|rewriting|synthesizing|done|failed
    chapter_count: int = 0


class BookDetail(Book):
    chapters: list[ChapterInfo] = Field(default_factory=list)
    toc: list[dict] = Field(default_factory=list)


class JobInfo(BaseModel):
    id: str
    book_id: str
    chapter_id: str | None = None
    type: str
    status: str = "pending"  # pending|running|done|failed|cancelled
    progress: float = 0.0
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""


class SettingsView(BaseModel):
    tts_engine: str = "mock"
    tts_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    tts_speaker: str | None = None
    tts_speed: float = 1.0
    tts_instruct: str | None = None
    llm_model: str = "dsv4-flash"
    chapter_low_chars: int = 5000
    chapter_high_chars: int = 15000


class TTSModelInfo(BaseModel):
    name: str
    type: str = "custom"


class TTSSpeakerInfo(BaseModel):
    name: str
