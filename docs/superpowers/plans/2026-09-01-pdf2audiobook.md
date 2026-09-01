# PDF 转语音应用 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个前后端分离的本地 Web 应用：上传 PDF 书籍 → 解析并按大章节切分 → 用 dsv4-flash 改写为口语化 Markdown → 用 Qwen3-TTS（qwen-tts-webui）按章节合成音频与字幕，支持换源、调速、单章重建。

**Architecture:** FastAPI 单进程后端（pymupdf 解析、OpenAI 兼容 LLM 改写、TTS 适配层、进程内串行任务队列、SQLite 任务库），Vue 3 + Vite + TS 前端（REST + 轮询）。所有产物为 `data/books/<book_id>/chapters/<chapter_id>/` 下的普通文件（speech.md / audio.wav / chapter.srt / chapter.vtt / segments.json / parts/），可人工维护、单章重建。

**Tech Stack:** Python 3.13 + FastAPI + pymupdf + openai + httpx + imageio-ffmpeg + SQLite；Vue 3 + Vite + TS + Pinia + Vue Router + axios + CodeMirror 6 + marked；pytest / Vitest。

**Spec:** `docs/superpowers/specs/2026-09-01-pdf2audiobook-design.md`

## Global Constraints

- 后端 Python 3.13，前端 Node 24（npm 11）。
- LLM：OpenAI 兼容接口 `https://opencode.ai/zen/go/v1`，模型 `dsv4-flash`，密钥只存 `.env`（已 gitignore），`.env.example` 提供占位。
- TTS 默认引擎 `mock`（开发）；正式引擎 `qwen_webui` 指向 `http://127.0.0.1:7860`（qwen-tts-webui API），模型 `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`。
- 数据根目录 `data/`（gitignore），书籍目录 `data/books/<book_id>/`，任务库 `data/jobs.db`。
- 章节自适应阈值：低 5000 字、高 15000 字（每章约 10–30 分钟音频），可配置。
- 每章产物必须包含：`speech.md`、`segments.json`、`audio.wav`、`chapter.srt`、`chapter.vtt`、`parts/`。
- 字幕时间轴来自合成实际时长累计（非语音识别）；固化语速时按倍率换算。
- TTS 合成任务全局串行；取消时调用引擎 interrupt（qwen: `POST /qwenapi/v1/interrupt`）。
- `.env` 不得出现在任何提交中；示例 PDF 位于 `data/samples/agentic-ai-guide-zh-v1.1.0.pdf`（不入库）。
- 提交信息用 conventional commits（feat:/fix:/test:/docs:/chore:）。

## File Structure

```
backend/
  requirements.txt
  app/
    __init__.py
    config.py            # .env 配置 + data/settings.json 运行时设置
    models.py            # Pydantic 响应模型（Book/Chapter/Job/SettingsView…）
    store.py             # 文件布局 + SQLite JobDB
    main.py              # FastAPI 应用工厂、CORS、路由挂载
    api/
      __init__.py
      books.py           # 上传/列表/详情/删除/启动任务
      chapters.py        # speech.md 读写、重建、音频/字幕流
      jobs.py            # 任务列表/取消
      settings.py        # 设置读写、TTS 模型/声音列表
    services/
      __init__.py
      pdf_extractor.py   # pymupdf 元数据/TOC/块抽取
      segmenter.py       # TOC/字号 → 大章节，自适应合并
      rewriter.py        # dsv4-flash 口语化改写（断点续跑）
      audio.py           # WAV 拼接/变速/字幕生成/文本分句
      job_manager.py     # 任务队列、parse/rewrite/synthesize/rebuild
      tts/
        __init__.py
        base.py          # TTSAdapter ABC
        mock.py          # 测试引擎（静音/提示音 WAV）
        qwen_webui.py    # qwen-tts-webui HTTP 适配器
  tests/
    conftest.py          # tmp data dir fixture
    test_pdf_extractor.py
    test_segmenter.py
    test_rewriter.py
    test_audio.py
    test_tts_mock.py
    test_tts_qwen_webui.py
    test_job_manager.py
    test_api.py
frontend/
  package.json
  vite.config.ts         # /api 代理到 127.0.0.1:8000
  tsconfig.json
  index.html
  src/
    main.ts
    App.vue
    router.ts
    api/client.ts        # axios 封装 + 全部 API 函数
    stores/books.ts      # Pinia：书籍/章节状态
    stores/jobs.ts       # Pinia：任务轮询
    stores/settings.ts   # Pinia：设置
    views/
      BooksView.vue      # 书架（上传/列表/删除）
      BookDetailView.vue # 章节树 + 解析/改写/合成
      ChapterView.vue    # Markdown 编辑 + 播放器 + 字幕
      JobsView.vue       # 任务中心
      SettingsView.vue   # 设置
    components/
      UploadCard.vue
      ChapterTree.vue
      ChapterEditor.vue  # CodeMirror 6 + marked 预览
      AudioPlayer.vue    # <audio> + VTT 字幕 + 倍速
      JobList.vue
```

---

### Task 1: 后端骨架（依赖、配置、存储层、模型）

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/store.py`
- Create: `backend/app/models.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Produces: `config.Settings`（读 `.env`）、`config.RuntimeSettings`、`config.SettingsStore(data_dir).load()/.save(rs)`、`store.init_store(data_dir)`、`store.book_dir(data_dir, book_id)`、`store.chapter_dir(data_dir, book_id, chapter_id)`、`store.save_json(path, obj)`、`store.load_json(path, default)`、`store.new_book_id()`、`store.JobDB(db_path)`。
- Produces: `models.Book`、`models.ChapterInfo`、`models.BookDetail`、`models.JobInfo`、`models.SettingsView`。

- [ ] **Step 1: 写失败测试**

创建 `backend/requirements.txt`：

```
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
python-multipart>=0.0.9,<1
pydantic>=2.7,<3
pydantic-settings>=2.3,<3
pymupdf>=1.24,<2
openai>=1.40,<2
httpx>=0.27,<1
pytest>=8,<9
pytest-asyncio>=0.23,<1
imageio-ffmpeg>=0.5,<1
```

创建 `backend/tests/test_store.py`：

```python
import json
from pathlib import Path
from app import store


def test_init_and_dirs(tmp_path: Path):
    store.init_store(tmp_path)
    assert (tmp_path / "books").is_dir()
    book = store.book_dir(tmp_path, "abc")
    assert book == tmp_path / "books" / "abc"
    ch = store.chapter_dir(tmp_path, "abc", "ch-001")
    assert ch == tmp_path / "books" / "abc" / "chapters" / "ch-001"


def test_json_roundtrip(tmp_path: Path):
    store.init_store(tmp_path)
    p = tmp_path / "meta.json"
    store.save_json(p, {"a": 1})
    assert store.load_json(p, {}) == {"a": 1}
    assert store.load_json(tmp_path / "missing.json", {"x": 2}) == {"x": 2}


def test_new_book_id_unique():
    assert store.new_book_id() != store.new_book_id()


def test_jobdb_crud(tmp_path: Path):
    db = store.JobDB(tmp_path / "jobs.db")
    db.create_job(job_id="j1", book_id="b1", chapter_id=None,
                  job_type="parse", settings_snapshot="{}")
    job = db.get_job("j1")
    assert job["status"] == "pending"
    db.update_job("j1", status="running", progress=0.5)
    assert db.get_job("j1")["progress"] == 0.5
    assert len(db.list_jobs()) == 1
    db.delete_job("j1")
    assert db.get_job("j1") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_store.py -v`
Expected: FAIL（`app` 模块不存在）

- [ ] **Step 3: 实现 config.py**

```python
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
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
        import json
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeSettings(**{k: v for k, v in data.items()
                                  if k in RuntimeSettings.__dataclass_fields__})

    def save(self, rs: RuntimeSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(asdict(rs), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

- [ ] **Step 4: 实现 store.py**

```python
import json
import sqlite3
import threading
import uuid
from pathlib import Path

_DATA_DIR_NAME = "books"


def init_store(data_dir: Path) -> None:
    (data_dir / _DATA_DIR_NAME).mkdir(parents=True, exist_ok=True)
    (data_dir / "tmp").mkdir(parents=True, exist_ok=True)


def book_dir(data_dir: Path, book_id: str) -> Path:
    return data_dir / _DATA_DIR_NAME / book_id


def chapter_dir(data_dir: Path, book_id: str, chapter_id: str) -> Path:
    return book_dir(data_dir, book_id) / "chapters" / chapter_id


def save_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def new_book_id() -> str:
    return uuid.uuid4().hex[:12]


class JobDB:
    """SQLite 任务库（同步 + 锁，本地单进程足够）。"""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                chapter_id TEXT,
                type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                progress REAL NOT NULL DEFAULT 0,
                error TEXT,
                settings_snapshot TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def create_job(self, job_id: str, book_id: str, chapter_id: str | None,
                   job_type: str, settings_snapshot: str) -> None:
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (id, book_id, chapter_id, type, settings_snapshot, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (job_id, book_id, chapter_id, job_type, settings_snapshot, now, now),
            )
            self._conn.commit()

    def update_job(self, job_id: str, **fields: object) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = [fields[k] for k in fields] + [job_id, _now()]
        with self._lock:
            self._conn.execute(
                f"UPDATE jobs SET {cols}, updated_at = ? WHERE id = ?", values
            )
            self._conn.commit()

    def get_job(self, job_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return _row_to_dict(row)

    def list_jobs(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def delete_job(self, job_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            self._conn.commit()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


_COLUMNS = ["id", "book_id", "chapter_id", "type", "status",
            "progress", "error", "settings_snapshot", "created_at", "updated_at"]


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    return {name: row[i] for i, name in enumerate(_COLUMNS)}
```

- [ ] **Step 5: 实现 models.py**

```python
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
```

- [ ] **Step 6: 实现 conftest.py**

```python
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app import store  # noqa: E402


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    store.init_store(tmp_path)
    return tmp_path
```

- [ ] **Step 7: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_store.py -v`
Expected: PASS（5 个测试）

- [ ] **Step 8: 提交**

```bash
git add backend
git commit -m "feat: backend scaffold with config, store and models"
```

---

### Task 2: PDF 解析器（pymupdf）

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/pdf_extractor.py`
- Test: `backend/tests/test_pdf_extractor.py`

**Interfaces:**
- Consumes: `store`（数据目录约定）
- Produces: `ExtractedBlock` dataclass（`page:int, kind:str, text:str, font_size:float, bold:bool`）；`extract_meta(pdf_path) -> dict`；`extract_toc(pdf_path) -> list[dict]`；`extract_blocks(pdf_path, page_start, page_end) -> list[ExtractedBlock]`；`blocks_to_markdown(blocks) -> str`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_pdf_extractor.py`：

```python
from pathlib import Path

import pytest

from app.services.pdf_extractor import (
    ExtractedBlock,
    blocks_to_markdown,
    extract_blocks,
    extract_meta,
    extract_toc,
)

SAMPLE = Path(__file__).resolve().parents[1].parent / "data" / "samples" / "agentic-ai-guide-zh-v1.1.0.pdf"


@pytest.mark.skipif(not SAMPLE.exists(), reason="示例 PDF 未提供")
def test_extract_meta_sample():
    meta = extract_meta(SAMPLE)
    assert meta["page_count"] >= 590
    assert meta["title"]


@pytest.mark.skipif(not SAMPLE.exists(), reason="示例 PDF 未提供")
def test_extract_toc_sample():
    toc = extract_toc(SAMPLE)
    assert len(toc) > 50
    assert toc[0]["level"] >= 1
    assert toc[0]["page"] >= 1


@pytest.mark.skipif(not SAMPLE.exists(), reason="示例 PDF 未提供")
def test_extract_blocks_page3():
    # 第 3 页是目录页，包含多个 heading/text 块
    blocks = extract_blocks(SAMPLE, 3, 3)
    assert len(blocks) > 0
    assert all(isinstance(b, ExtractedBlock) for b in blocks)
    assert any(b.text for b in blocks)


def test_blocks_to_markdown_marks_headings():
    blocks = [
        ExtractedBlock(page=1, kind="heading", text="第一章 开始", font_size=18, bold=True),
        ExtractedBlock(page=1, kind="text", text="这是正文。", font_size=12, bold=False),
        ExtractedBlock(page=1, kind="table", text="a|b\n1|2", font_size=10, bold=False),
    ]
    md = blocks_to_markdown(blocks)
    assert md.startswith("# 第一章 开始")
    assert "这是正文。" in md
    assert "a|b" in md


def test_blocks_to_markdown_skips_empty():
    assert blocks_to_markdown([]) == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_pdf_extractor.py -v`
Expected: FAIL（`pdf_extractor` 不存在）

- [ ] **Step 3: 实现 pdf_extractor.py**

```python
import re
from dataclasses import dataclass
from pathlib import Path

import fitz  # pymupdf


@dataclass
class ExtractedBlock:
    page: int
    kind: str  # heading | text | list | table | code | image | formula
    text: str
    font_size: float = 0.0
    bold: bool = False


_HEADING_RE = re.compile(r"^(\d+(\.\d+)*[\.\s、．]|第[一二三四五六七八九十百千0-9]+[章节部篇]|[A-Z]\.\s)")


def extract_meta(pdf_path: Path) -> dict:
    doc = fitz.open(str(pdf_path))
    try:
        md = doc.metadata or {}
        return {
            "title": (md.get("title") or "").strip() or pdf_path.stem,
            "author": (md.get("author") or "").strip(),
            "page_count": doc.page_count,
        }
    finally:
        doc.close()


def extract_toc(pdf_path: Path) -> list[dict]:
    doc = fitz.open(str(pdf_path))
    try:
        return [{"level": lv, "title": title, "page": page}
                for lv, title, page in doc.get_toc()]
    finally:
        doc.close()


def extract_blocks(pdf_path: Path, page_start: int, page_end: int) -> list[ExtractedBlock]:
    """抽取页范围内的文本/表格块。页号从 1 开始，闭区间。"""
    doc = fitz.open(str(pdf_path))
    try:
        blocks: list[ExtractedBlock] = []
        for pno in range(max(1, page_start), min(page_end, doc.page_count) + 1):
            page = doc[pno - 1]
            # 表格优先（find_tables 可用时）
            try:
                tables = page.find_tables()
                table_texts = [t.extract() for t in tables.tables]
            except Exception:
                table_texts = []
            dict_blocks = page.get_text("dict").get("blocks", [])
            for block in dict_blocks:
                if block.get("type") == 1:  # 图片
                    blocks.append(ExtractedBlock(page=pno, kind="image",
                                                 text="[图片]", font_size=0, bold=False))
                    continue
                spans = [s for line in block.get("lines", []) for s in line.get("spans", [])]
                if not spans:
                    continue
                text = "".join(s["text"] for s in spans).strip()
                if not text or _is_noise(text):
                    continue
                size = max(s["size"] for s in spans)
                bold = any(s["flags"] & 16 for s in spans)  # bit 4 = bold
                kind = _classify(text, size, bold)
                if kind == "table" and table_texts:
                    # 用表格提取结果替换该块文本（近似：按页合并表格文本）
                    text = "\n".join("|".join(str(c or "") for c in row)
                                     for t in table_texts for row in t)
                blocks.append(ExtractedBlock(page=pno, kind=kind, text=text,
                                             font_size=size, bold=bold))
        return blocks
    finally:
        doc.close()


def blocks_to_markdown(blocks: list[ExtractedBlock]) -> str:
    lines: list[str] = []
    for b in blocks:
        text = b.text.strip()
        if not text:
            continue
        if b.kind == "heading":
            lines.append(f"# {text}")
        elif b.kind == "image":
            lines.append(f"（图注位置：{text}）")
        else:
            lines.append(text)
        lines.append("")
    return "\n".join(lines).strip()


def _is_noise(text: str) -> bool:
    # 页眉/页脚/页码特征：纯数字、短横线包围、"— N —"、书名重复行
    if re.fullmatch(r"[\d\s\-—|]+", text):
        return True
    if re.fullmatch(r"—?\s*\d{1,4}\s*—?", text):
        return True
    return False


def _classify(text: str, size: float, bold: bool) -> str:
    if size >= 14 and bold:
        return "heading"
    if size >= 12 and bold and _HEADING_RE.match(text):
        return "heading"
    if "|" in text:
        return "table"
    if text.startswith(("```", "def ", "class ", "import ", "const ", "function")):
        return "code"
    return "text"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_pdf_extractor.py -v`
Expected: PASS（含示例 PDF 的真实断言）

- [ ] **Step 5: 提交**

```bash
git add backend
git commit -m "feat: pdf extractor with pymupdf"
```

---

### Task 3: 章节切分器（TOC + 自适应合并）

**Files:**
- Create: `backend/app/services/segmenter.py`
- Test: `backend/tests/test_segmenter.py`

**Interfaces:**
- Consumes: `pdf_extractor.extract_toc`、`extract_blocks`、`blocks_to_markdown`
- Produces: `segment_from_toc(toc) -> list[dict]`（候选章节：`id/title/level/page_start/page_end`）；`detect_headings(blocks) -> list[(page, title)]`；`adaptive_merge(chapters, char_counts, low, high) -> list[dict]`；`build_candidates(pdf_path, meta) -> list[dict]`（TOC 优先，无 TOC 走字号检测）。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_segmenter.py`：

```python
from app.services import segmenter


def test_segment_from_toc_top_level():
    toc = [
        {"level": 1, "title": "I 基础", "page": 38},
        {"level": 2, "title": "1 LLM 架构与优化方法", "page": 39},
        {"level": 2, "title": "2 分词", "page": 60},
        {"level": 1, "title": "II 进阶", "page": 90},
        {"level": 2, "title": "3 注意力机制", "page": 91},
    ]
    chapters = segmenter.segment_from_toc(toc)
    # 顶层 chapter 为基本单元：I 基础(38-89)、II 进阶(90-末)
    assert len(chapters) == 2
    assert chapters[0]["title"] == "I 基础"
    assert chapters[0]["page_start"] == 38
    assert chapters[0]["page_end"] == 89
    assert chapters[1]["page_start"] == 90


def test_adaptive_merge_small_adjacent():
    chapters = [
        {"id": "c1", "title": "A", "page_start": 1, "page_end": 5},
        {"id": "c2", "title": "B", "page_start": 6, "page_end": 10},
        {"id": "c3", "title": "C", "page_start": 11, "page_end": 30},
    ]
    counts = {"c1": 1000, "c2": 2000, "c3": 8000}
    merged = segmenter.adaptive_merge(chapters, counts, low=5000, high=15000)
    # 三个小节合计 11000 字：贪心合并直到达到下限
    assert len(merged) == 1
    assert merged[0]["title"] == "A + B + C"
    assert merged[0]["char_count"] == 11000
    assert merged[0]["page_end"] == 30


def test_adaptive_merge_no_split_when_under_high():
    chapters = [{"id": "c1", "title": "A", "page_start": 1, "page_end": 20}]
    merged = segmenter.adaptive_merge(chapters, {"c1": 12000}, low=5000, high=15000)
    assert len(merged) == 1


def test_detect_headings():
    from app.services.pdf_extractor import ExtractedBlock
    blocks = [
        ExtractedBlock(page=1, kind="heading", text="第1章 开始", font_size=16, bold=True),
        ExtractedBlock(page=1, kind="text", text="正文", font_size=12, bold=False),
        ExtractedBlock(page=2, kind="heading", text="1.1 子节", font_size=14, bold=True),
    ]
    heads = segmenter.detect_headings(blocks)
    assert heads == [(1, "第1章 开始"), (2, "1.1 子节")]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_segmenter.py -v`
Expected: FAIL（`segmenter` 不存在）

- [ ] **Step 3: 实现 segmenter.py**

```python
import re
from pathlib import Path

from app.services import pdf_extractor
from app.store import new_book_id

_CHAPTER_PREFIX_RE = re.compile(r"^(第[一二三四五六七八九十百千0-9]+[章节部篇]|\d+(\.\d+)*\s)")


def segment_from_toc(toc: list[dict]) -> list[dict]:
    """以顶层章节为基本单元；顶层之间自动补页范围。"""
    if not toc:
        return []
    top_level = min(e["level"] for e in toc)
    top = [e for e in toc if e["level"] == top_level]
    chapters: list[dict] = []
    for i, entry in enumerate(top):
        page_end = (top[i + 1]["page"] - 1) if i + 1 < len(top) else 10**6
        chapters.append({
            "id": _chapter_id(i + 1),
            "title": entry["title"].strip(),
            "level": entry["level"],
            "page_start": entry["page"],
            "page_end": page_end,
            "char_count": 0,
        })
    return chapters


def detect_headings(blocks: list[pdf_extractor.ExtractedBlock]) -> list[tuple[int, str]]:
    heads = []
    for b in blocks:
        if b.kind == "heading" and _CHAPTER_PREFIX_RE.match(b.text.strip()):
            heads.append((b.page, b.text.strip()))
    return heads


def adaptive_merge(chapters: list[dict], char_counts: dict[str, int],
                   low: int, high: int) -> list[dict]:
    """合并过小相邻章节；超过 high 的章节暂不拆分（由 UI 手动调整兜底）。"""
    merged: list[dict] = []
    for ch in chapters:
        ch["char_count"] = int(char_counts.get(ch["id"], 0))
        if merged and merged[-1]["char_count"] < low and \
                merged[-1]["char_count"] + ch["char_count"] <= high:
            prev = merged[-1]
            prev["title"] = f"{prev['title']} + {ch['title']}"
            prev["page_end"] = ch["page_end"]
            prev["char_count"] += ch["char_count"]
            prev["id"] = f"{prev['id']}+{ch['id']}"
        else:
            merged.append(ch)
    return merged


def build_candidates(pdf_path: Path, meta: dict) -> list[dict]:
    """TOC 优先；无 TOC 时用字号检测兜底（返回单一大章节）。"""
    toc = pdf_extractor.extract_toc(pdf_path)
    if toc:
        return segment_from_toc(toc)
    blocks = pdf_extractor.extract_blocks(pdf_path, 1, meta["page_count"])
    heads = detect_headings(blocks)
    if not heads:
        return [{"id": "ch-001", "title": "全书", "level": 1,
                 "page_start": 1, "page_end": meta["page_count"], "char_count": 0}]
    chapters = []
    for i, (page, title) in enumerate(heads):
        page_end = heads[i + 1][0] - 1 if i + 1 < len(heads) else meta["page_count"]
        chapters.append({"id": _chapter_id(i + 1), "title": title, "level": 1,
                         "page_start": page, "page_end": page_end, "char_count": 0})
    return chapters


def _chapter_id(idx: int) -> str:
    return f"ch-{idx:03d}"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_segmenter.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend
git commit -m "feat: chapter segmenter with adaptive merge"
```

---

### Task 4: 口语化改写（dsv4-flash，断点续跑）

**Files:**
- Create: `backend/app/services/rewriter.py`
- Test: `backend/tests/test_rewriter.py`

**Interfaces:**
- Consumes: `store.chapter_dir`、`store.save_json/load_json`、`config.Settings`（openai_base_url/openai_api_key/llm_model）
- Produces: `SYSTEM_PROMPT`（常量）；`Rewriter(client: AsyncOpenAI, model: str, data_dir: Path)`；`Rewriter.split_sections(text, max_chars=2500) -> list[str]`；`Rewriter.rewrite_chapter(book_id, chapter, on_progress) -> None`（写 `speech.md` + `rewrite_checkpoint.json`）。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_rewriter.py`：

```python
import pytest
from openai import AsyncOpenAI

from app.services import rewriter


def test_split_sections_respects_max_chars():
    text = "第一节。\n" + "长" * 3000 + "。\n第二节内容。"
    sections = rewriter.Rewriter.split_sections(text, max_chars=1000)
    assert len(sections) >= 2
    assert all(len(s) <= 1200 for s in sections)  # 允许少量溢出


def test_split_sections_keeps_all_content():
    text = "A。" * 50
    joined = "".join(rewriter.Rewriter.split_sections(text, max_chars=100))
    assert joined.replace("。", "") == "A" * 50


def test_system_prompt_contains_fidelity_rules():
    assert "高保真" in rewriter.SYSTEM_PROMPT
    assert "表格" in rewriter.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_rewrite_chapter_uses_client_and_writes_files(data_dir, monkeypatch):
    from app import store
    ch_dir = store.chapter_dir(data_dir, "b1", "ch-001")
    ch_dir.mkdir(parents=True)
    (ch_dir / "source.md").write_text("表格：A|B\n1|2\n", encoding="utf-8")
    chapter = {"id": "ch-001", "title": "测试章", "page_start": 1, "page_end": 2}

    class FakeCompletions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return type("R", (), {"choices": [type("C", (), {"message": type(
                "M", (), {"content": "口语化结果"})()})()]})()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    rw = rewriter.Rewriter(FakeClient(), "dsv4-flash", data_dir)  # type: ignore[arg-type]
    progress = []

    async def on_progress(p):
        progress.append(p)

    await rw.rewrite_chapter("b1", chapter, on_progress)
    assert (ch_dir / "speech.md").exists()
    assert "口语化结果" in (ch_dir / "speech.md").read_text(encoding="utf-8")
    cp = store.load_json(ch_dir / "rewrite_checkpoint.json", {})
    assert cp["done"]  # 非空
    assert progress[-1] == 1.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_rewriter.py -v`
Expected: FAIL（`rewriter` 不存在）

- [ ] **Step 3: 实现 rewriter.py**

```python
import hashlib
from pathlib import Path
from typing import Awaitable, Callable

from openai import AsyncOpenAI

from app import store

SYSTEM_PROMPT = """你是一名有声书口语化改写专家。任务：把书籍章节原文改写成适合语音朗读的口语化文本，保留全部信息。
规则：
1. 高保真：数字、日期、术语、专有名词、代码标识符、英文原词必须原样保留，不得省略、概括或编造。
2. 表格：改为流畅的陈述句，逐行说明。
3. 列表：用“第一/第二/首先/其次/最后”等口语衔接词。
4. 图注：改写为“如图 X 所示，……”。
5. 公式：改为可朗读的表述，例如“f 对 x 的导数等于……”。
6. 交叉引用：改为“如第 X 章所述”。
7. 输出为 Markdown，标题层级与原文章节结构一致；不要在文首添加标题或前言。
8. 只输出改写后的正文，不要解释。"""

ProgressCb = Callable[[float], Awaitable[None]]


class Rewriter:
    def __init__(self, client: AsyncOpenAI, model: str, data_dir: Path):
        self._client = client
        self._model = model
        self._data_dir = data_dir

    @staticmethod
    def split_sections(text: str, max_chars: int = 2500) -> list[str]:
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        sections: list[str] = []
        buf = ""
        for part in parts:
            if not buf:
                buf = part
            elif len(buf) + len(part) + 2 <= max_chars:
                buf += "\n\n" + part
            else:
                sections.append(buf)
                buf = part
        if buf:
            sections.append(buf)
        # 单段超长时按句切
        out: list[str] = []
        for s in sections:
            if len(s) <= max_chars:
                out.append(s)
                continue
            cur = ""
            for sent in s.replace("。", "。\n").replace("！", "！\n").splitlines():
                if len(cur) + len(sent) <= max_chars:
                    cur += sent
                    continue
                if cur:
                    out.append(cur)
                    cur = ""
                for j in range(0, len(sent), max_chars):
                    chunk = sent[j:j + max_chars]
                    if len(cur) + len(chunk) <= max_chars:
                        cur += chunk
                    else:
                        if cur:
                            out.append(cur)
                        cur = chunk
            if cur:
                out.append(cur)
        return out

    async def rewrite_chapter(self, book_id: str, chapter: dict,
                              on_progress: ProgressCb) -> None:
        ch_dir = store.chapter_dir(self._data_dir, book_id, chapter["id"])
        source_path = ch_dir / "source.md"
        if not source_path.exists():
            raise FileNotFoundError(f"缺少 source.md: {source_path}")
        source = source_path.read_text(encoding="utf-8")
        sections = self.split_sections(source)
        checkpoint_path = ch_dir / "rewrite_checkpoint.json"
        cp = store.load_json(checkpoint_path, {"done": []})
        done: set[str] = set(cp.get("done", []))
        outputs: list[str] = []
        total = len(sections)
        for i, sec in enumerate(sections):
            h = _hash(sec)
            if h in done:
                outputs.append(_load_done(ch_dir, h))
                await on_progress((i + 1) / total)
                continue
            result = await self._call_llm(sec)
            _save_done(ch_dir, h, result)
            done.add(h)
            outputs.append(result)
            store.save_json(checkpoint_path, {"done": sorted(done)})
            await on_progress((i + 1) / total)
        (ch_dir / "speech.md").write_text(_join(outputs), encoding="utf-8")

    async def _call_llm(self, section: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"原文：\n```text\n{section}\n```"},
            ],
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _save_done(ch_dir: Path, h: str, text: str) -> None:
    ch_dir.mkdir(parents=True, exist_ok=True)
    (ch_dir / f".rewrite_{h}.md").write_text(text, encoding="utf-8")


def _load_done(ch_dir: Path, h: str) -> str:
    return (ch_dir / f".rewrite_{h}.md").read_text(encoding="utf-8")


def _join(parts: list[str]) -> str:
    return "\n\n".join(p.strip() for p in parts if p.strip())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_rewriter.py -v`
Expected: PASS（FakeClient 验证调用与文件写入）

- [ ] **Step 5: 提交**

```bash
git add backend
git commit -m "feat: LLM rewriter with checkpoint resume"
```

---

### Task 5: TTS 适配层基类 + 测试引擎（mock）

**Files:**
- Create: `backend/app/services/tts/__init__.py`
- Create: `backend/app/services/tts/base.py`
- Create: `backend/app/services/tts/mock.py`
- Test: `backend/tests/test_tts_mock.py`

**Interfaces:**
- Produces: `AudioResult` dataclass（`data:bytes, duration:float, format:str="wav"`）；`TTSAdapter` ABC（`list_models() -> list[dict]`、`list_speakers() -> list[dict]`、`synthesize(text, *, voice, speed, language, instruct) -> AudioResult`、`interrupt()` 默认 no-op）；`MockTTSAdapter.synthesize` 返回 24kHz mono 16-bit 正弦 WAV，`duration = max(1.0, len(text) * 0.08)`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_tts_mock.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_tts_mock.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 base.py**

```python
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
```

- [ ] **Step 4: 实现 mock.py**

```python
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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_tts_mock.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend
git commit -m "feat: TTS adapter base and mock engine"
```

---

### Task 6: qwen-tts-webui 适配器

**Files:**
- Create: `backend/app/services/tts/qwen_webui.py`
- Test: `backend/tests/test_tts_qwen_webui.py`

**Interfaces:**
- Consumes: `base.AudioResult`、`base.TTSAdapter`
- Produces: `QwenWebUIAdapter(base_url: str, model: str, timeout: float = 120)`；HTTP 端点：`GET /qwenapi/v1/models`、`GET /qwenapi/v1/speakers`、`POST /qwenapi/v1/custom-voice`（body: `model_name/text/speaker/instruct/language/segment_gen:false`，响应 `audio_files_base64`）、`POST /qwenapi/v1/interrupt`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_tts_qwen_webui.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_tts_qwen_webui.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 qwen_webui.py**

```python
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
            "instruct": instruct,
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_tts_qwen_webui.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend
git commit -m "feat: qwen-tts-webui HTTP adapter"
```

---

### Task 7: 音频拼接 / 变速 / 字幕 / 文本分句

**Files:**
- Create: `backend/app/services/audio.py`
- Test: `backend/tests/test_audio.py`

**Interfaces:**
- Consumes: `store.save_json/load_json`
- Produces: `wav_duration(data: bytes) -> float`；`concat_wavs(parts: list[bytes], tmp_dir: Path) -> bytes`（统一 24kHz/mono/16bit 后拼接）；`speed_wav(data: bytes, factor: float, tmp_dir: Path) -> bytes`（ffmpeg atempo）；`build_subtitles(segments: list[dict]) -> tuple[str, str]`（返回 `(srt, vtt)`）；`split_speech_text(text: str, max_chars: int = 500) -> list[str]`；`text_hash(text: str) -> str`（sha256 前 16 位）。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_audio.py`：

```python
import io
import wave
from pathlib import Path

import pytest

from app.services import audio


def _wav(duration: float, rate: int = 24000) -> bytes:
    import math
    import struct
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(rate * duration)
        w.writeframes(b"".join(
            struct.pack("<h", int(500 * math.sin(2 * math.pi * 440 * i / rate)))
            for i in range(n)))
    return buf.getvalue()


def test_wav_duration():
    assert abs(audio.wav_duration(_wav(2.0)) - 2.0) < 0.01


def test_concat_wavs_duration_and_format(tmp_path):
    parts = [_wav(1.0), _wav(0.5), _wav(0.25)]
    out = audio.concat_wavs(parts, tmp_path)
    with wave.open(io.BytesIO(out)) as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1
        assert abs(w.getnframes() / 24000 - 1.75) < 0.02


def test_speed_wav_doubles(tmp_path):
    out = audio.speed_wav(_wav(2.0), 2.0, tmp_path)
    assert abs(audio.wav_duration(out) - 1.0) < 0.05


def test_build_subtitles():
    segments = [
        {"index": 1, "text": "第一句。", "start": 0.0, "end": 2.5},
        {"index": 2, "text": "第二句。", "start": 2.5, "end": 5.0},
    ]
    srt, vtt = audio.build_subtitles(segments)
    assert "00:00:00,000 --> 00:00:02,500" in srt
    assert "第一句。" in srt
    assert "00:00:02.500 --> 00:00:05.000" in vtt
    assert "WEBVTT" in vtt


def test_split_speech_text_groups_paragraphs_and_caps():
    text = "第一段句子。\n\n第二段" + "很长的内容。" * 200
    parts = audio.split_speech_text(text, max_chars=200)
    assert len(parts) >= 2
    assert all(len(p) <= 250 for p in parts)
    assert "第一段句子。" in parts[0]


def test_text_hash_stable():
    assert audio.text_hash("abc") == audio.text_hash("abc")
    assert audio.text_hash("abc") != audio.text_hash("abd")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_audio.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 audio.py**

```python
import hashlib
import io
import re
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg

_RATE = 24000


def wav_duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def concat_wavs(parts: list[bytes], tmp_dir: Path) -> bytes:
    """把多个 WAV 统一为 24kHz/mono/16bit 后拼接（用 ffmpeg）。"""
    if not parts:
        raise ValueError("parts 为空")
    if len(parts) == 1:
        return _normalize(parts[0], tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    norm_paths = []
    for i, p in enumerate(parts):
        path = tmp_dir / f"part_{i:04d}.wav"
        path.write_bytes(_normalize(p, tmp_dir))
        norm_paths.append(path)
    list_path = tmp_dir / "concat.txt"
    list_path.write_text("".join(f"file '{p.name}'\n" for p in norm_paths), encoding="utf-8")
    out_path = tmp_dir / "concat_out.wav"
    _ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
             "-c", "copy", str(out_path)])
    data = out_path.read_bytes()
    return data


def speed_wav(data: bytes, factor: float, tmp_dir: Path) -> bytes:
    """用 ffmpeg atempo 变速（factor > 1 变快）。"""
    if factor <= 0:
        raise ValueError("factor 必须为正数")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_dir / "speed_src.wav"
    dst = tmp_dir / "speed_dst.wav"
    src.write_bytes(_normalize(data, tmp_dir))
    # atempo 支持 0.5–2.0，超范围时链式调用
    filters = []
    remaining = factor
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.6f}")
    _ffmpeg(["-y", "-i", str(src), "-filter:a", ",".join(filters),
             "-ar", str(_RATE), "-ac", "1", str(dst)])
    return dst.read_bytes()


def build_subtitles(segments: list[dict]) -> tuple[str, str]:
    srt_lines = []
    vtt_lines = ["WEBVTT", ""]
    for seg in segments:
        idx = seg["index"]
        text = seg["text"]
        srt_lines.append(f"{idx}\n{_fmt_srt(seg['start'])} --> {_fmt_srt(seg['end'])}\n{text}\n")
        vtt_lines.append(f"{idx}\n{_fmt_vtt(seg['start'])} --> {_fmt_vtt(seg['end'])}\n{text}\n")
    return "\n\n".join(srt_lines).strip(), "\n\n".join(vtt_lines).strip()


def split_speech_text(text: str, max_chars: int = 500) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    out: list[str] = []
    for block in blocks:
        if len(block) <= max_chars:
            out.append(block)
            continue
        # 超长块按句切
        sentences = re.split(r"(?<=[。！？；])", block)
        cur = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(cur) + len(s) <= max_chars:
                cur += s
            else:
                if cur:
                    out.append(cur)
                cur = s
        if cur:
            out.append(cur)
    return out


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _normalize(data: bytes, tmp_dir: Path) -> bytes:
    src = tmp_dir / "norm_src.wav"
    dst = tmp_dir / "norm_dst.wav"
    src.write_bytes(data)
    _ffmpeg(["-y", "-i", str(src), "-ar", str(_RATE), "-ac", "1",
             "-c:a", "pcm_s16le", str(dst)])
    return dst.read_bytes()


def _ffmpeg(args: list[str]) -> None:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([exe, *args], check=True, capture_output=True)


def _fmt_srt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_audio.py -v`
Expected: PASS（imageio-ffmpeg 自动提供 ffmpeg 二进制）

- [ ] **Step 5: 提交**

```bash
git add backend
git commit -m "feat: audio concat, speed, subtitles and text splitting"
```

---

### Task 8: 任务管理器（parse / rewrite / synthesize / rebuild）

**Files:**
- Create: `backend/app/services/job_manager.py`
- Test: `backend/tests/test_job_manager.py`

**Interfaces:**
- Consumes: `config.SettingsStore/RuntimeSettings`、`store.JobDB/book_dir/chapter_dir/save_json/load_json/new_book_id`、`pdf_extractor.*`、`segmenter.*`、`rewriter.Rewriter`、`tts.base.TTSAdapter`、`audio.*`
- Produces: `JobManager(data_dir, settings_store, tts_factory=None, rewriter_factory=None)`；`start(job_type, book_id, chapter_id=None) -> str`；`list_jobs() -> list[dict]`；`get_job(job_id) -> dict|None`；`cancel(job_id) -> None`；`start_worker()` / `shutdown()`。内部处理 `parse/rewrite/synthesize/rebuild`，进度 0–1，状态 `pending|running|done|failed|cancelled`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_job_manager.py`：

```python
import asyncio
from pathlib import Path

import fitz
import pytest

from app import store
from app.config import RuntimeSettings, SettingsStore
from app.services import audio, job_manager
from app.services.tts.base import AudioResult, TTSAdapter


def _make_pdf(path: Path) -> None:
    doc = fitz.open()
    for pno, text in enumerate(["第一章 开始", "这是第一页正文。", "第二章 进阶"], start=1):
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=18)
    doc.set_toc([[1, "第一章 开始", 1], [1, "第二章 进阶", 3]])
    doc.save(str(path))
    doc.close()


def _make_book(data_dir: Path, book_id: str, with_speech: bool = True) -> None:
    bdir = store.book_dir(data_dir, book_id)
    (bdir / "chapters" / "ch-001").mkdir(parents=True)
    store.save_json(bdir / "meta.json", {
        "book_id": book_id, "title": "测试书", "author": "", "page_count": 3,
        "status": "parsed", "toc": [{"level": 1, "title": "第一章 开始", "page": 1}],
    })
    store.save_json(bdir / "chapters.json", {"chapters": [
        {"id": "ch-001", "title": "第一章 开始", "level": 1,
         "page_start": 1, "page_end": 3, "char_count": 30, "status": "pending"},
    ]})
    if with_speech:
        (bdir / "chapters" / "ch-001" / "speech.md").write_text(
            "第一句。\n\n第二句。", encoding="utf-8")


@pytest.mark.asyncio
async def test_parse_job_builds_chapters(data_dir):
    pdf = data_dir / "book.pdf"
    _make_pdf(pdf)
    bdir = store.book_dir(data_dir, "b1")
    bdir.mkdir(parents=True)
    (bdir / "source.pdf").write_bytes(pdf.read_bytes())

    ss = SettingsStore(data_dir)
    ss.save(RuntimeSettings(chapter_low_chars=1, chapter_high_chars=10**9))
    jm = job_manager.JobManager(data_dir, ss)
    jm.start_worker()
    try:
        jid = jm.start("parse", "b1")
        await _wait_done(jm, jid)
        job = jm.get_job(jid)
        assert job["status"] == "done"
        chapters = store.load_json(bdir / "chapters.json", {})["chapters"]
        assert len(chapters) == 2
        assert (bdir / "chapters" / chapters[0]["id"] / "source.md").exists()
        meta = store.load_json(bdir / "meta.json", {})
        assert meta["status"] == "parsed"
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_synthesize_job_writes_audio_and_subtitles(data_dir):
    _make_book(data_dir, "b2")
    jm = job_manager.JobManager(data_dir, SettingsStore(data_dir))
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b2")
        await _wait_done(jm, jid)
        ch = store.chapter_dir(data_dir, "b2", "ch-001")
        assert (ch / "audio.wav").exists()
        assert (ch / "chapter.srt").exists()
        assert (ch / "chapter.vtt").exists()
        segs = store.load_json(ch / "segments.json", [])
        assert len(segs) == 2
        assert segs[1]["start"] >= segs[0]["end"]
        assert audio.wav_duration((ch / "audio.wav").read_bytes()) > 0
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_cancel_pending_job(data_dir):
    _make_book(data_dir, "b3")
    jm = job_manager.JobManager(data_dir, SettingsStore(data_dir))
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b3")
        jm.cancel(jid)
        await _wait_done(jm, jid)
        assert jm.get_job(jid)["status"] == "cancelled"
    finally:
        await jm.shutdown()


async def _wait_done(jm: job_manager.JobManager, jid: str, timeout: float = 30.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = jm.get_job(jid)
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(f"任务未在 {timeout}s 内结束: {jm.get_job(jid)}")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_job_manager.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 job_manager.py**

```python
import asyncio
import json
import shutil
from pathlib import Path
from typing import Awaitable, Callable

from app import audio, store
from app.config import RuntimeSettings, SettingsStore, Settings
from app.services import pdf_extractor, rewriter, segmenter
from app.services.tts.base import TTSAdapter
from app.services.tts.mock import MockTTSAdapter
from app.services.tts.qwen_webui import QwenWebUIAdapter

JobType = str  # parse | rewrite | synthesize | rebuild
ProgressCb = Callable[[float], Awaitable[None]]


class JobManager:
    def __init__(self, data_dir: Path, settings_store: SettingsStore,
                 tts_factory: Callable[[RuntimeSettings, Settings], TTSAdapter] | None = None,
                 rewriter_factory: Callable[[RuntimeSettings, Settings], rewriter.Rewriter] | None = None,
                 settings: Settings | None = None):
        self._data_dir = data_dir
        self._settings_store = settings_store
        self._settings = settings or Settings()
        self._db = store.JobDB(data_dir / "jobs.db")
        self._queue: asyncio.Queue[tuple[str, JobType, str, str | None]] = asyncio.Queue()
        self._cancel_flags: set[str] = set()
        self._worker_task: asyncio.Task | None = None
        self._current_job_id: str | None = None
        self._current_adapter: TTSAdapter | None = None
        self._tts_factory = tts_factory or _default_tts_factory
        self._rewriter_factory = rewriter_factory or _default_rewriter_factory

    def start_worker(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())

    async def shutdown(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    def start(self, job_type: JobType, book_id: str, chapter_id: str | None = None) -> str:
        jid = store.new_book_id()
        rs = self._settings_store.load()
        self._db.create_job(jid, book_id, chapter_id, job_type,
                            json.dumps(_rs_to_dict(rs), ensure_ascii=False))
        self._queue.put_nowait((jid, job_type, book_id, chapter_id))
        return jid

    def get_job(self, job_id: str) -> dict | None:
        return self._db.get_job(job_id)

    def list_jobs(self) -> list[dict]:
        return self._db.list_jobs()

    def cancel(self, job_id: str) -> None:
        self._cancel_flags.add(job_id)
        if self._current_job_id == job_id and self._current_adapter is not None:
            asyncio.create_task(self._current_adapter.interrupt())

    async def _worker(self) -> None:
        while True:
            jid, job_type, book_id, chapter_id = await self._queue.get()
            self._current_job_id = jid
            self._db.update_job(jid, status="running", error=None)
            try:
                if job_type == "parse":
                    await self._run_parse(book_id)
                elif job_type == "rewrite":
                    await self._run_rewrite(book_id, chapter_id)
                elif job_type in ("synthesize", "rebuild"):
                    await self._run_synthesize(book_id, chapter_id)
                else:
                    raise ValueError(f"未知任务类型: {job_type}")
                if jid in self._cancel_flags:
                    self._db.update_job(jid, status="cancelled")
                else:
                    self._db.update_job(jid, status="done", progress=1.0)
            except _JobCancelled:
                self._db.update_job(jid, status="cancelled")
            except Exception as exc:  # noqa: BLE001
                self._db.update_job(jid, status="failed", error=str(exc))
            finally:
                self._cancel_flags.discard(jid)
                self._current_job_id = None
                self._current_adapter = None

    # ---------- parse ----------
    async def _run_parse(self, book_id: str) -> None:
        bdir = store.book_dir(self._data_dir, book_id)
        pdf_path = bdir / "source.pdf"
        meta = pdf_extractor.extract_meta(pdf_path)
        meta.update({"book_id": book_id, "status": "parsed",
                     "toc": pdf_extractor.extract_toc(pdf_path)})
        candidates = segmenter.build_candidates(pdf_path, meta)
        rs = self._settings_store.load()
        counts: dict[str, int] = {}
        for ch in candidates:
            blocks = pdf_extractor.extract_blocks(pdf_path, ch["page_start"], ch["page_end"])
            counts[ch["id"]] = len(pdf_extractor.blocks_to_markdown(blocks))
            await self._maybe_cancel(book_id)
        chapters = segmenter.adaptive_merge(candidates, counts,
                                            rs.chapter_low_chars, rs.chapter_high_chars)
        for ch in chapters:
            blocks = pdf_extractor.extract_blocks(pdf_path, ch["page_start"], ch["page_end"])
            md = pdf_extractor.blocks_to_markdown(blocks)
            ch["char_count"] = len(md)
            ch["status"] = "pending"
            ch_dir = store.chapter_dir(self._data_dir, book_id, ch["id"])
            ch_dir.mkdir(parents=True, exist_ok=True)
            (ch_dir / "source.md").write_text(md, encoding="utf-8")
        store.save_json(bdir / "chapters.json", {"chapters": chapters})
        store.save_json(bdir / "meta.json", meta)
        # 清理旧章节目录
        for old in (bdir / "chapters").iterdir():
            if old.is_dir() and old.name not in {c["id"] for c in chapters}:
                shutil.rmtree(old)

    # ---------- rewrite ----------
    async def _run_rewrite(self, book_id: str, chapter_id: str | None = None) -> None:
        chapters = self._chapters(book_id, chapter_id)
        rs = self._settings_store.load()
        rw = self._rewriter_factory(rs, self._settings)
        for i, ch in enumerate(chapters):
            async def on_progress(p: float) -> None:
                overall = (i + p) / len(chapters)
                await self._maybe_cancel(book_id)
                self._db.update_job(self._current_job_id or "", progress=overall)
            await rw.rewrite_chapter(book_id, ch, on_progress)
            ch_dir = store.chapter_dir(self._data_dir, book_id, ch["id"])
            ch["status"] = "rewritten"
            store.save_json(ch_dir / "status.json", ch)
            self._save_chapters(book_id, chapters)

    # ---------- synthesize / rebuild ----------
    async def _run_synthesize(self, book_id: str, chapter_id: str | None = None) -> None:
        chapters = self._chapters(book_id, chapter_id)
        rs = self._settings_store.load()
        adapter = self._tts_factory(rs, self._settings)
        self._current_adapter = adapter
        for i, ch in enumerate(chapters):
            ch_dir = store.chapter_dir(self._data_dir, book_id, ch["id"])
            speech_path = ch_dir / "speech.md"
            if not speech_path.exists():
                raise FileNotFoundError(f"缺少 speech.md: {speech_path}")
            segments = await self._synthesize_chapter(adapter, ch_dir, speech_path, rs, i, len(chapters))
            ch["status"] = "synthesized"
            ch["audio_duration"] = round(sum(s["end"] - s["start"] for s in segments), 3)
            store.save_json(ch_dir / "status.json", ch)
            self._save_chapters(book_id, chapters)

    async def _synthesize_chapter(self, adapter: TTSAdapter, ch_dir: Path,
                                  speech_path: Path, rs: RuntimeSettings,
                                  ch_idx: int, total: int) -> list[dict]:
        text = speech_path.read_text(encoding="utf-8")
        parts = audio.split_speech_text(text, max_chars=500)
        parts_dir = ch_dir / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        segments: list[dict] = []
        cursor = 0.0
        for idx, seg_text in enumerate(parts):
            await self._maybe_cancel(ch_dir.parents[1].name)
            h = audio.text_hash(seg_text)
            part_path = parts_dir / f"{idx:04d}_{h}.wav"
            if part_path.exists():
                duration = audio.wav_duration(part_path.read_bytes())
            else:
                res = await adapter.synthesize(seg_text, voice=rs.tts_speaker,
                                               speed=1.0, instruct=rs.tts_instruct)
                part_path.write_bytes(res.data)
                duration = res.duration
            segments.append({"index": idx + 1, "text": seg_text, "hash": h,
                             "start": round(cursor, 3), "end": round(cursor + duration, 3)})
            cursor += duration
            self._db.update_job(self._current_job_id or "",
                                progress=(ch_idx + (idx + 1) / len(parts)) / total)
        part_bytes = [p.read_bytes() for p in sorted(parts_dir.glob("*.wav"))]
        wav = audio.concat_wavs(part_bytes, self._data_dir / "tmp")
        if abs(rs.tts_speed - 1.0) > 1e-6:
            wav = audio.speed_wav(wav, rs.tts_speed, self._data_dir / "tmp")
            for s in segments:
                s["start"] = round(s["start"] / rs.tts_speed, 3)
                s["end"] = round(s["end"] / rs.tts_speed, 3)
        (ch_dir / "audio.wav").write_bytes(wav)
        store.save_json(ch_dir / "segments.json", segments)
        srt, vtt = audio.build_subtitles(segments)
        (ch_dir / "chapter.srt").write_text(srt, encoding="utf-8")
        (ch_dir / "chapter.vtt").write_text(vtt, encoding="utf-8")
        return segments

    # ---------- helpers ----------
    def _chapters(self, book_id: str, chapter_id: str | None) -> list[dict]:
        bdir = store.book_dir(self._data_dir, book_id)
        data = store.load_json(bdir / "chapters.json", {"chapters": []})
        chapters = data["chapters"]
        if chapter_id:
            chapters = [c for c in chapters if c["id"] == chapter_id]
            if not chapters:
                raise KeyError(f"章节不存在: {chapter_id}")
        return chapters

    def _save_chapters(self, book_id: str, chapters: list[dict]) -> None:
        store.save_json(store.book_dir(self._data_dir, book_id) / "chapters.json",
                        {"chapters": chapters})

    async def _maybe_cancel(self, book_id: str) -> None:
        jid = self._current_job_id or ""
        if jid in self._cancel_flags:
            raise _JobCancelled()


class _JobCancelled(Exception):
    pass


def _rs_to_dict(rs: RuntimeSettings) -> dict:
    return {k: v for k, v in rs.__dict__.items()}


def _default_tts_factory(rs: RuntimeSettings, settings: Settings) -> TTSAdapter:
    if rs.tts_engine == "qwen_webui":
        return QwenWebUIAdapter(settings.tts_api_url, rs.tts_model)
    return MockTTSAdapter()


def _default_rewriter_factory(rs: RuntimeSettings, settings: Settings) -> rewriter.Rewriter:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=settings.openai_base_url,
                         api_key=settings.openai_api_key)
    return rewriter.Rewriter(client, rs.llm_model, settings.data_dir)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_job_manager.py -v`
Expected: PASS（含取消、音频/字幕产物断言）

- [ ] **Step 5: 提交**

```bash
git add backend
git commit -m "feat: job manager with parse/rewrite/synthesize/rebuild"
```

---

### Task 9: FastAPI 应用与 API 路由

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/books.py`
- Create: `backend/app/api/chapters.py`
- Create: `backend/app/api/jobs.py`
- Create: `backend/app/api/settings.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: 全部 service 层 + `store` + `config`
- Produces: `main.create_app(settings: Settings | None = None) -> FastAPI`；路由：`POST/GET/DELETE /api/books`、`GET /api/books/{id}`、`POST /api/books/{id}/parse|rewrite|synthesize`、`GET/PUT /api/books/{id}/chapters/{ch}/speech.md`、`POST /api/books/{id}/chapters/{ch}/rebuild`、`GET /api/books/{id}/chapters/{ch}/audio`、`GET /api/books/{id}/chapters/{ch}/chapter.vtt`、`GET /api/jobs`、`POST /api/jobs/{id}/cancel`、`GET/PUT /api/settings`、`GET /api/tts/models`、`GET /api/tts/speakers`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_api.py`：

```python
import io
from pathlib import Path

import fitz
import httpx
import pytest

from app import store
from app.config import Settings
from app.main import create_app


def _tiny_pdf_bytes() -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "第一章 开始", fontsize=18)
    doc.set_toc([[1, "第一章 开始", 1]])
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


@pytest.fixture()
async def client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_upload_list_detail(client):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    assert r.status_code == 200
    book = r.json()
    assert book["book_id"]
    assert book["status"] == "uploaded"
    r = await client.get("/api/books")
    assert len(r.json()) == 1
    r = await client.get(f"/api/books/{book['book_id']}")
    assert r.json()["title"] == "book"


@pytest.mark.asyncio
async def test_parse_then_edit_then_rebuild(client, tmp_path):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    r = await client.post(f"/api/books/{book['book_id']}/parse")
    assert r.status_code == 200
    job_id = r.json()["id"]
    await _wait(client, job_id)
    detail = (await client.get(f"/api/books/{book['book_id']}")).json()
    assert detail["status"] == "parsed"
    assert len(detail["chapters"]) == 1
    ch = detail["chapters"][0]["id"]
    # 编辑 speech.md
    r = await client.put(
        f"/api/books/{book['book_id']}/chapters/{ch}/speech.md",
        content="第一句。\n\n第二句。", headers={"Content-Type": "text/plain"})
    assert r.status_code == 200
    got = await client.get(f"/api/books/{book['book_id']}/chapters/{ch}/speech.md")
    assert "第一句" in got.text
    # 重建（mock 引擎）
    r = await client.post(f"/api/books/{book['book_id']}/chapters/{ch}/rebuild")
    job_id = r.json()["id"]
    await _wait(client, job_id)
    ch_dir = store.chapter_dir(tmp_path, book["book_id"], ch)
    assert (ch_dir / "audio.wav").exists()
    assert (ch_dir / "chapter.vtt").exists()
    r = await client.get(f"/api/books/{book['book_id']}/chapters/{ch}/audio")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")


@pytest.mark.asyncio
async def test_settings_and_tts_lists(client):
    r = await client.get("/api/settings")
    assert r.json()["tts_engine"] == "mock"
    r = await client.put("/api/settings", json={"tts_engine": "mock",
                                                "tts_model": "m", "tts_speed": 1.5})
    assert r.status_code == 200
    r = await client.get("/api/tts/models")
    assert r.json()[0]["name"] == "mock-voice"
    r = await client.get("/api/tts/speakers")
    assert r.json()[0]["name"] == "测试音色"


@pytest.mark.asyncio
async def test_delete_book(client, tmp_path):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    r = await client.delete(f"/api/books/{book['book_id']}")
    assert r.status_code == 200
    assert not store.book_dir(tmp_path, book["book_id"]).exists()


async def _wait(client, job_id: str, timeout: float = 30.0):
    import asyncio
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get("/api/jobs")
        job = next((j for j in r.json() if j["id"] == job_id), None)
        if job and job["status"] in ("done", "failed", "cancelled"):
            assert job["status"] == "done", job
            return
        await asyncio.sleep(0.05)
    raise AssertionError("任务超时")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_api.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现路由与 main.py**

`backend/app/api/books.py`：

```python
import shutil

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app import store
from app.models import Book, BookDetail, JobInfo

router = APIRouter()


def _ctx(request: Request):
    s = request.app.state
    return s.data_dir, s.job_manager


def _book_kwargs(meta: dict) -> dict:
    return {k: v for k, v in meta.items() if k in Book.model_fields}


@router.post("", response_model=Book)
async def upload_book(request: Request, file: UploadFile):
    data_dir, _ = _ctx(request)
    book_id = store.new_book_id()
    bdir = store.book_dir(data_dir, book_id)
    bdir.mkdir(parents=True)
    dest = bdir / "source.pdf"
    dest.write_bytes(await file.read())
    from app.services.pdf_extractor import extract_meta
    meta = extract_meta(dest)
    meta.update({"book_id": book_id, "status": "uploaded", "toc": []})
    store.save_json(bdir / "meta.json", meta)
    return Book(**_book_kwargs(meta), chapter_count=0)


@router.get("", response_model=list[Book])
async def list_books(request: Request):
    data_dir, _ = _ctx(request)
    books = []
    for bdir in sorted((data_dir / "books").iterdir()):
        if not bdir.is_dir():
            continue
        meta = store.load_json(bdir / "meta.json", {})
        chapters = store.load_json(bdir / "chapters.json", {"chapters": []})["chapters"]
        books.append(Book(**_book_kwargs(meta), chapter_count=len(chapters)))
    return books


@router.get("/{book_id}", response_model=BookDetail)
async def get_book(request: Request, book_id: str):
    data_dir, _ = _ctx(request)
    bdir = store.book_dir(data_dir, book_id)
    if not bdir.exists():
        raise HTTPException(404, "书籍不存在")
    meta = store.load_json(bdir / "meta.json", {})
    chapters = store.load_json(bdir / "chapters.json", {"chapters": []})["chapters"]
    for ch in chapters:
        status = store.load_json(bdir / "chapters" / ch["id"] / "status.json", {})
        ch["status"] = status.get("status", "pending")
        ch["audio_duration"] = status.get("audio_duration", 0.0)
    return BookDetail(**meta, chapters=chapters)


@router.delete("/{book_id}")
async def delete_book(request: Request, book_id: str):
    data_dir, _ = _ctx(request)
    bdir = store.book_dir(data_dir, book_id).resolve()
    root = (data_dir / "books").resolve()
    if not bdir.is_relative_to(root):
        raise HTTPException(400, "非法路径")
    if bdir.exists():
        shutil.rmtree(bdir)
    return {"ok": True}


@router.post("/{book_id}/parse", response_model=JobInfo)
async def start_parse(request: Request, book_id: str):
    return await _start(request, "parse", book_id)


@router.post("/{book_id}/rewrite", response_model=JobInfo)
async def start_rewrite(request: Request, book_id: str):
    return await _start(request, "rewrite", book_id)


@router.post("/{book_id}/synthesize", response_model=JobInfo)
async def start_synthesize(request: Request, book_id: str):
    return await _start(request, "synthesize", book_id)


async def _start(request: Request, job_type: str, book_id: str):
    data_dir, jm = _ctx(request)
    bdir = store.book_dir(data_dir, book_id)
    if not bdir.exists():
        raise HTTPException(404, "书籍不存在")
    jid = jm.start(job_type, book_id)
    return JobInfo(**jm.get_job(jid))
```

`backend/app/api/chapters.py`：

```python
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from app import store
from app.models import JobInfo

router = APIRouter()


@router.get("/{chapter_id}/speech.md")
async def get_speech(request: Request, book_id: str, chapter_id: str):
    path = store.chapter_dir(_data_dir(request), book_id, chapter_id) / "speech.md"
    if not path.exists():
        return PlainTextResponse("", media_type="text/markdown")
    return PlainTextResponse(path.read_text(encoding="utf-8"),
                             media_type="text/markdown; charset=utf-8")


@router.put("/{chapter_id}/speech.md")
async def save_speech(request: Request, book_id: str, chapter_id: str):
    body = (await request.body()).decode("utf-8")
    ch_dir = store.chapter_dir(_data_dir(request), book_id, chapter_id)
    ch_dir.mkdir(parents=True, exist_ok=True)
    (ch_dir / "speech.md").write_text(body, encoding="utf-8")
    return {"ok": True}


@router.post("/{chapter_id}/rebuild", response_model=JobInfo)
async def rebuild_chapter(request: Request, book_id: str, chapter_id: str):
    jm = request.app.state.job_manager
    jid = jm.start("rebuild", book_id, chapter_id)
    return JobInfo(**jm.get_job(jid))


@router.get("/{chapter_id}/audio")
async def get_audio(request: Request, book_id: str, chapter_id: str):
    path = store.chapter_dir(_data_dir(request), book_id, chapter_id) / "audio.wav"
    if not path.exists():
        raise HTTPException(404, "音频不存在，请先合成")
    return FileResponse(path, media_type="audio/wav")


@router.get("/{chapter_id}/chapter.vtt")
async def get_vtt(request: Request, book_id: str, chapter_id: str):
    path = store.chapter_dir(_data_dir(request), book_id, chapter_id) / "chapter.vtt"
    if not path.exists():
        raise HTTPException(404, "字幕不存在")
    return FileResponse(path, media_type="text/vtt; charset=utf-8")


def _data_dir(request: Request):
    return request.app.state.data_dir
```

`backend/app/api/jobs.py`：

```python
from fastapi import APIRouter, HTTPException, Request

from app.models import JobInfo

router = APIRouter()


@router.get("", response_model=list[JobInfo])
async def list_jobs(request: Request):
    return [JobInfo(**j) for j in request.app.state.job_manager.list_jobs()]


@router.post("/{job_id}/cancel")
async def cancel_job(request: Request, job_id: str):
    jm = request.app.state.job_manager
    job = jm.get_job(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    jm.cancel(job_id)
    return {"ok": True}
```

`backend/app/api/settings.py`：

```python
from fastapi import APIRouter, Request

from app.config import RuntimeSettings
from app.models import SettingsView, TTSModelInfo, TTSSpeakerInfo

router = APIRouter()


def _rs(request: Request) -> RuntimeSettings:
    return request.app.state.settings_store.load()


@router.get("/settings", response_model=SettingsView)
async def get_settings(request: Request):
    rs = _rs(request)
    return SettingsView(**rs.__dict__)


@router.put("/settings", response_model=SettingsView)
async def put_settings(request: Request, view: SettingsView):
    rs = RuntimeSettings(**view.model_dump())
    request.app.state.settings_store.save(rs)
    return SettingsView(**rs.__dict__)


@router.get("/tts/models", response_model=list[TTSModelInfo])
async def list_tts_models(request: Request):
    adapter = request.app.state.build_tts_adapter()
    return [TTSModelInfo(**m) for m in await adapter.list_models()]


@router.get("/tts/speakers", response_model=list[TTSSpeakerInfo])
async def list_tts_speakers(request: Request):
    adapter = request.app.state.build_tts_adapter()
    speakers = await adapter.list_speakers()
    if speakers and isinstance(speakers[0], str):
        return [TTSSpeakerInfo(name=s) for s in speakers]
    return [TTSSpeakerInfo(**s) for s in speakers]
```

`backend/app/main.py`：

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import store
from app.api import books, chapters, jobs, settings as settings_api
from app.config import Settings, SettingsStore
from app.services.job_manager import JobManager


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    store.init_store(settings.data_dir)
    settings_store = SettingsStore(settings.data_dir)
    jm = JobManager(settings.data_dir, settings_store, settings=settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        jm.start_worker()
        yield
        await jm.shutdown()

    app = FastAPI(title="PDF 转语音", lifespan=lifespan)
    app.state.data_dir = settings.data_dir
    app.state.settings = settings
    app.state.settings_store = settings_store
    app.state.job_manager = jm

    from app.services.job_manager import _default_tts_factory
    app.state.build_tts_adapter = lambda: _default_tts_factory(
        settings_store.load(), settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(books.router, prefix="/api/books", tags=["books"])
    app.include_router(chapters.router, prefix="/api/books/{book_id}/chapters", tags=["chapters"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(settings_api.router, prefix="/api", tags=["settings"])
    return app
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_api.py -v`
Expected: PASS（4 个集成测试）

- [ ] **Step 5: 提交**

```bash
git add backend
git commit -m "feat: FastAPI app and API routers"
```

---

### Task 10: 前端骨架（Vite + Vue3 + TS + API 客户端 + Pinia）

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/router.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/stores/books.ts`
- Create: `frontend/src/stores/jobs.ts`
- Create: `frontend/src/stores/settings.ts`
- Test: `frontend/src/api/client.test.ts`（Vitest）

**Interfaces:**
- Produces: `src/api/client.ts` 全部类型与函数（`Book/ChapterInfo/BookDetail/JobInfo/SettingsView`、`listBooks/uploadBook/getBook/deleteBook/startJob/getSpeechMd/saveSpeechMd/rebuildChapter/audioUrl/vttUrl/listJobs/cancelJob/getSettings/saveSettings/listTTSModels/listTTSSpeakers`）；Pinia stores：`useBooksStore`、`useJobsStore`、`useSettingsStore`。

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/api/client.test.ts`（用 Vitest + vi.mock axios）：

```ts
import { describe, expect, it, vi } from "vitest";

vi.mock("axios", () => {
  const data = { data: [{ book_id: "b1", title: "测试", chapter_count: 0 }] };
  return { default: { create: () => ({ get: vi.fn(async () => data), post: vi.fn(async () => data), put: vi.fn(async () => data), delete: vi.fn(async () => ({ data: {} })) }) } };
});

import * as api from "./client";

describe("api client", () => {
  it("listBooks returns books", async () => {
    const books = await api.listBooks();
    expect(books).toEqual([{ book_id: "b1", title: "测试", chapter_count: 0 }]);
  });
  it("audioUrl/vttUrl build paths", () => {
    expect(api.audioUrl("b1", "ch-001")).toBe("/api/books/b1/chapters/ch-001/audio");
    expect(api.vttUrl("b1", "ch-001")).toBe("/api/books/b1/chapters/ch-001/chapter.vtt");
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm install && npx vitest run src/api/client.test.ts`
Expected: FAIL（文件不存在）

- [ ] **Step 3: 创建脚手架文件**

`frontend/package.json`：

```json
{
  "name": "pdf2audiobook-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "@codemirror/lang-markdown": "^6.3.0",
    "@codemirror/state": "^6.4.1",
    "@codemirror/view": "^6.34.0",
    "axios": "^1.7.7",
    "codemirror": "^6.0.1",
    "marked": "^14.1.0",
    "pinia": "^2.2.4",
    "vue": "^3.5.11",
    "vue-router": "^4.4.5"
  },
  "devDependencies": {
    "@types/node": "^22.7.5",
    "@vitejs/plugin-vue": "^5.1.4",
    "typescript": "~5.6.2",
    "vite": "^5.4.8",
    "vitest": "^2.1.2",
    "vue-tsc": "^2.1.6"
  }
}
```

`frontend/vite.config.ts`：

```ts
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: { environment: "node" },
});
```

`frontend/tsconfig.json`：

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "jsx": "preserve",
    "resolveJsonModule": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "types": ["vite/client", "vitest/globals"],
    "lib": ["ES2022", "DOM", "DOM.Iterable"]
  },
  "include": ["src/**/*.ts", "src/**/*.vue", "vite.config.ts"]
}
```

`frontend/index.html`：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>PDF 转语音</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`frontend/src/main.ts`：

```ts
import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";

createApp(App).use(createPinia()).use(router).mount("#app");
```

`frontend/src/App.vue`：

```vue
<script setup lang="ts">
import { onMounted } from "vue";
import { useJobsStore } from "./stores/jobs";

const jobs = useJobsStore();
onMounted(() => jobs.startPolling());
</script>

<template>
  <div class="app">
    <header>
      <router-link to="/">📚 书架</router-link>
      <router-link to="/jobs">⚙️ 任务中心</router-link>
      <router-link to="/settings">🛠 设置</router-link>
      <span v-if="jobs.active" class="dot">●</span>
    </header>
    <main><router-view /></main>
  </div>
</template>

<style>
body { margin: 0; font-family: system-ui, sans-serif; background: #f5f6fa; }
.app { max-width: 1100px; margin: 0 auto; padding: 16px; }
header { display: flex; gap: 16px; align-items: center; padding: 12px 0; border-bottom: 1px solid #ddd; margin-bottom: 16px; }
header a { text-decoration: none; color: #333; font-weight: 600; }
.dot { color: #e11; font-size: 12px; }
</style>
```

`frontend/src/router.ts`：

```ts
import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: () => import("./views/BooksView.vue") },
    { path: "/books/:bookId", component: () => import("./views/BookDetailView.vue") },
    { path: "/books/:bookId/chapters/:chapterId", component: () => import("./views/ChapterView.vue") },
    { path: "/jobs", component: () => import("./views/JobsView.vue") },
    { path: "/settings", component: () => import("./views/SettingsView.vue") },
  ],
});

export default router;
```

`frontend/src/api/client.ts`（见上面 Interfaces 的完整实现）：

```ts
import axios from "axios";

export interface Book {
  book_id: string; title: string; author: string; page_count: number;
  created_at: string; status: string; chapter_count: number;
}
export interface ChapterInfo {
  id: string; title: string; level: number; page_start: number; page_end: number;
  char_count: number; status: string; audio_duration: number;
}
export interface BookDetail extends Book {
  chapters: ChapterInfo[];
  toc: Array<{ level: number; title: string; page: number }>;
}
export interface JobInfo {
  id: string; book_id: string; chapter_id: string | null; type: string;
  status: string; progress: number; error: string | null;
  created_at: string; updated_at: string;
}
export interface SettingsView {
  tts_engine: string; tts_model: string; tts_speaker: string | null;
  tts_speed: number; tts_instruct: string | null; llm_model: string;
  chapter_low_chars: number; chapter_high_chars: number;
}

const api = axios.create({ baseURL: "/api" });

export async function listBooks(): Promise<Book[]> {
  return (await api.get("/books")).data;
}
export async function uploadBook(file: File): Promise<Book> {
  const fd = new FormData();
  fd.append("file", file);
  return (await api.post("/books", fd)).data;
}
export async function getBook(id: string): Promise<BookDetail> {
  return (await api.get(`/books/${id}`)).data;
}
export async function deleteBook(id: string): Promise<void> {
  await api.delete(`/books/${id}`);
}
export async function startJob(
  bookId: string, type: "parse" | "rewrite" | "synthesize",
): Promise<JobInfo> {
  return (await api.post(`/books/${bookId}/${type}`)).data;
}
export async function getSpeechMd(bookId: string, ch: string): Promise<string> {
  return (await api.get(`/books/${bookId}/chapters/${ch}/speech.md`)).data;
}
export async function saveSpeechMd(bookId: string, ch: string, text: string): Promise<void> {
  await api.put(`/books/${bookId}/chapters/${ch}/speech.md`, text,
    { headers: { "Content-Type": "text/plain" } });
}
export async function rebuildChapter(bookId: string, ch: string): Promise<JobInfo> {
  return (await api.post(`/books/${bookId}/chapters/${ch}/rebuild`)).data;
}
export const audioUrl = (bookId: string, ch: string) =>
  `/api/books/${bookId}/chapters/${ch}/audio`;
export const vttUrl = (bookId: string, ch: string) =>
  `/api/books/${bookId}/chapters/${ch}/chapter.vtt`;
export async function listJobs(): Promise<JobInfo[]> {
  return (await api.get("/jobs")).data;
}
export async function cancelJob(id: string): Promise<void> {
  await api.post(`/jobs/${id}/cancel`);
}
export async function getSettings(): Promise<SettingsView> {
  return (await api.get("/settings")).data;
}
export async function saveSettings(s: SettingsView): Promise<SettingsView> {
  return (await api.put("/settings", s)).data;
}
export async function listTTSModels(): Promise<Array<{ name: string; type: string }>> {
  return (await api.get("/tts/models")).data;
}
export async function listTTSSpeakers(): Promise<Array<{ name: string }>> {
  return (await api.get("/tts/speakers")).data;
}
```

`frontend/src/stores/books.ts`：

```ts
import { defineStore } from "pinia";
import { ref } from "vue";
import * as api from "../api/client";

export const useBooksStore = defineStore("books", () => {
  const books = ref<api.Book[]>([]);
  const detail = ref<api.BookDetail | null>(null);

  async function refreshBooks() {
    books.value = await api.listBooks();
  }
  async function loadBook(id: string) {
    detail.value = await api.getBook(id);
  }
  async function upload(file: File) {
    const b = await api.uploadBook(file);
    await refreshBooks();
    return b;
  }
  async function remove(id: string) {
    await api.deleteBook(id);
    if (detail.value?.book_id === id) detail.value = null;
    await refreshBooks();
  }
  return { books, detail, refreshBooks, loadBook, upload, remove };
});
```

`frontend/src/stores/jobs.ts`：

```ts
import { defineStore } from "pinia";
import { ref } from "vue";
import * as api from "../api/client";

export const useJobsStore = defineStore("jobs", () => {
  const jobs = ref<api.JobInfo[]>([]);
  const active = ref(false);
  let timer: number | undefined;

  async function refresh() {
    jobs.value = await api.listJobs();
    active.value = jobs.value.some(
      (j) => j.status === "pending" || j.status === "running",
    );
    if (!active.value && timer !== undefined) {
      window.clearInterval(timer);
      timer = undefined;
    }
  }
  function startPolling() {
    if (timer !== undefined) return;
    void refresh();
    timer = window.setInterval(refresh, 2000);
  }
  async function cancel(id: string) {
    await api.cancelJob(id);
    await refresh();
  }
  return { jobs, active, refresh, startPolling, cancel };
});
```

`frontend/src/stores/settings.ts`：

```ts
import { defineStore } from "pinia";
import { ref } from "vue";
import * as api from "../api/client";

export const useSettingsStore = defineStore("settings", () => {
  const settings = ref<api.SettingsView | null>(null);
  async function load() {
    settings.value = await api.getSettings();
  }
  async function save(s: api.SettingsView) {
    settings.value = await api.saveSettings(s);
  }
  return { settings, load, save };
});
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/api/client.test.ts`
Expected: PASS（2 个测试）

- [ ] **Step 5: 提交**

```bash
git add frontend
git commit -m "feat: frontend scaffold, api client and pinia stores"
```

---

### Task 11: 前端页面与组件

**Files:**
- Create: `frontend/src/components/UploadCard.vue`
- Create: `frontend/src/components/ChapterTree.vue`
- Create: `frontend/src/components/ChapterEditor.vue`
- Create: `frontend/src/components/AudioPlayer.vue`
- Create: `frontend/src/components/JobList.vue`
- Create: `frontend/src/views/BooksView.vue`
- Create: `frontend/src/views/BookDetailView.vue`
- Create: `frontend/src/views/ChapterView.vue`
- Create: `frontend/src/views/JobsView.vue`
- Create: `frontend/src/views/SettingsView.vue`

**Interfaces:**
- Consumes: `api/client.ts`、三个 Pinia stores
- Produces: 可运行页面（书架/书籍详情/章节编辑播放/任务中心/设置）。

- [ ] **Step 1: 实现 UploadCard.vue**

```vue
<script setup lang="ts">
import { ref } from "vue";
import { useBooksStore } from "../stores/books";

const books = useBooksStore();
const uploading = ref(false);
const error = ref("");

async function onFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  uploading.value = true;
  error.value = "";
  try {
    await books.upload(file);
  } catch (err: any) {
    error.value = err?.response?.data?.detail ?? String(err);
  } finally {
    uploading.value = false;
    input.value = "";
  }
}
</script>

<template>
  <div class="upload-card">
    <h2>上传 PDF 书籍</h2>
    <input type="file" accept="application/pdf" @change="onFile" :disabled="uploading" />
    <span v-if="uploading">上传中…</span>
    <p v-if="error" class="err">{{ error }}</p>
  </div>
</template>

<style scoped>
.upload-card { border: 1px dashed #aaa; padding: 20px; border-radius: 8px; background: #fff; }
.err { color: #c00; }
</style>
```

- [ ] **Step 2: 实现 ChapterTree.vue**

```vue
<script setup lang="ts">
import type { BookDetail, ChapterInfo } from "../api/client";

defineProps<{ detail: BookDetail }>();
const emit = defineEmits<{ (e: "open", ch: ChapterInfo): void }>();

const statusText: Record<string, string> = {
  pending: "待改写", rewritten: "待合成", synthesized: "已完成", edited: "已编辑", failed: "失败",
};
</script>

<template>
  <ul class="tree">
    <li v-for="ch in detail.chapters" :key="ch.id">
      <span class="title">{{ ch.title }}</span>
      <span class="pages">p{{ ch.page_start }}–{{ ch.page_end }} · {{ ch.char_count }} 字</span>
      <span class="status" :data-status="ch.status">{{ statusText[ch.status] ?? ch.status }}</span>
      <span v-if="ch.audio_duration" class="dur">{{ Math.round(ch.audio_duration) }}s</span>
      <button @click="emit('open', ch)">编辑/播放</button>
    </li>
  </ul>
</template>

<style scoped>
.tree { list-style: none; padding: 0; }
.tree li { display: flex; gap: 12px; align-items: center; padding: 8px; background: #fff; margin-bottom: 6px; border-radius: 6px; }
.title { flex: 1; font-weight: 600; }
.pages { color: #888; font-size: 12px; }
.status { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: #eee; }
.status[data-status="synthesized"] { background: #cfe8cf; }
.status[data-status="failed"] { background: #f3c6c6; }
.dur { color: #666; font-size: 12px; }
</style>
```

- [ ] **Step 3: 实现 ChapterEditor.vue（CodeMirror 6 + marked 预览）**

```vue
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from "vue";
import { EditorView, basicSetup } from "codemirror";
import { markdown } from "@codemirror/lang-markdown";
import { marked } from "marked";

const props = defineProps<{ modelValue: string }>();
const html = computed(() => marked.parse(props.modelValue) as string);
const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();
const host = ref<HTMLElement | null>(null);
const preview = ref(false);
const view = shallowRef<EditorView | null>(null);

onMounted(() => {
  if (!host.value) return;
  view.value = new EditorView({
    doc: props.modelValue,
    extensions: [basicSetup, markdown(),
      EditorView.updateListener.of((u) => {
        if (u.docChanged) emit("update:modelValue", u.state.doc.toString());
      })],
    parent: host.value,
  });
});
onBeforeUnmount(() => view.value?.destroy());
</script>

<template>
  <div class="editor">
    <label><input type="checkbox" v-model="preview" /> 预览</label>
    <div v-show="!preview" ref="host" class="cm"></div>
    <div v-show="preview" class="preview" v-html="html"></div>
  </div>
</template>

<style scoped>
.cm { border: 1px solid #ddd; height: 60vh; overflow: auto; }
.preview { border: 1px solid #ddd; padding: 16px; height: 60vh; overflow: auto; background: #fff; }
</style>
```

- [ ] **Step 4: 实现 AudioPlayer.vue（音频 + VTT 字幕 + 倍速）**

```vue
<script setup lang="ts">
import { ref } from "vue";
import { audioUrl, vttUrl } from "../api/client";

const props = defineProps<{ bookId: string; chapterId: string }>();
const rate = ref(1);
const cueText = ref("");
const audioEl = ref<HTMLAudioElement | null>(null);

function onRate(e: Event) {
  rate.value = Number((e.target as HTMLSelectElement).value);
  if (audioEl.value) audioEl.value.playbackRate = rate.value;
}
function onTime() {
  const el = audioEl.value;
  if (!el || !el.textTracks?.length) return;
  const track = el.textTracks[0];
  for (const c of track.activeCues ?? []) {
    cueText.value = (c as VTTCue).text;
    return;
  }
  cueText.value = "";
}
</script>

<template>
  <div class="player">
    <audio ref="audioEl" :src="audioUrl(bookId, chapterId)" controls
           @timeupdate="onTime">
      <track kind="subtitles" :src="vttUrl(bookId, chapterId)" default />
    </audio>
    <label>倍速
      <select :value="rate" @change="onRate">
        <option v-for="r in [0.5, 0.75, 1, 1.25, 1.5, 2]" :key="r" :value="r">{{ r }}×</option>
      </select>
    </label>
    <p v-if="cueText" class="cue">{{ cueText }}</p>
  </div>
</template>

<style scoped>
.player { display: flex; flex-direction: column; gap: 8px; }
.cue { background: #222; color: #fff; padding: 8px; border-radius: 6px; min-height: 1.2em; }
</style>
```

- [ ] **Step 5: 实现 JobList.vue**

```vue
<script setup lang="ts">
import { useJobsStore } from "../stores/jobs";

const jobs = useJobsStore();

const typeText: Record<string, string> = {
  parse: "解析", rewrite: "改写", synthesize: "合成", rebuild: "重建",
};
const statusText: Record<string, string> = {
  pending: "排队中", running: "进行中", done: "完成", failed: "失败", cancelled: "已取消",
};
</script>

<template>
  <div>
    <table>
      <thead><tr><th>任务</th><th>书籍</th><th>状态</th><th>进度</th><th>错误</th><th></th></tr></thead>
      <tbody>
        <tr v-for="j in jobs.jobs" :key="j.id">
          <td>{{ typeText[j.type] ?? j.type }}</td>
          <td>{{ j.book_id.slice(0, 8) }}<span v-if="j.chapter_id"> / {{ j.chapter_id }}</span></td>
          <td>{{ statusText[j.status] ?? j.status }}</td>
          <td>
            <progress :value="j.progress" max="1"></progress>
            {{ Math.round(j.progress * 100) }}%
          </td>
          <td class="err">{{ j.error }}</td>
          <td><button v-if="['pending', 'running'].includes(j.status)" @click="jobs.cancel(j.id)">取消</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
table { width: 100%; border-collapse: collapse; background: #fff; }
td, th { border: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 13px; }
.err { color: #c00; max-width: 260px; }
</style>
```

- [ ] **Step 6: 实现 BooksView.vue**

```vue
<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useBooksStore } from "../stores/books";
import UploadCard from "../components/UploadCard.vue";

const books = useBooksStore();
const router = useRouter();
onMounted(() => books.refreshBooks());
</script>

<template>
  <div>
    <UploadCard />
    <h2>书架（{{ books.books.length }}）</h2>
    <ul class="books">
      <li v-for="b in books.books" :key="b.book_id">
        <button class="link" @click="router.push(`/books/${b.book_id}`)">{{ b.title }}</button>
        <span>{{ b.page_count }} 页 · {{ b.chapter_count }} 章 · {{ b.status }}</span>
        <button @click="books.remove(b.book_id)">删除</button>
      </li>
    </ul>
    <p v-if="!books.books.length" class="empty">还没有书籍，先上传一本 PDF 吧。</p>
  </div>
</template>

<style scoped>
.books { list-style: none; padding: 0; }
.books li { display: flex; gap: 12px; align-items: center; padding: 8px; background: #fff; margin-bottom: 6px; border-radius: 6px; }
.link { background: none; border: none; color: #06c; font-size: 15px; font-weight: 600; cursor: pointer; flex: 1; text-align: left; }
.empty { color: #888; }
</style>
```

- [ ] **Step 7: 实现 BookDetailView.vue**

```vue
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { ChapterInfo } from "../api/client";
import { useBooksStore } from "../stores/books";
import ChapterTree from "../components/ChapterTree.vue";

const route = useRoute();
const router = useRouter();
const books = useBooksStore();
const busy = ref(false);
const error = ref("");

onMounted(async () => {
  await books.loadBook(route.params.bookId as string);
  if (books.detail) books.refreshBooks();
});

async function run(type: "parse" | "rewrite" | "synthesize") {
  busy.value = true;
  error.value = "";
  try {
    await startAndPoll(type);
    await books.loadBook(route.params.bookId as string);
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  } finally {
    busy.value = false;
  }
}

async function startAndPoll(type: "parse" | "rewrite" | "synthesize") {
  const api = await import("../api/client");
  const job = await api.startJob(route.params.bookId as string, type);
  while (true) {
    await new Promise((r) => setTimeout(r, 1500));
    const jobs = await api.listJobs();
    const cur = jobs.find((j) => j.id === job.id);
    if (!cur) break;
    if (cur.status === "done") break;
    if (cur.status === "failed" || cur.status === "cancelled") throw new Error(cur.error ?? cur.status);
  }
}

function open(ch: ChapterInfo) {
  router.push(`/books/${route.params.bookId}/chapters/${ch.id}`);
}
</script>

<template>
  <div v-if="books.detail">
    <h2>{{ books.detail.title }}</h2>
    <p>共 {{ books.detail.page_count }} 页，{{ books.detail.chapters.length }} 章</p>
    <div class="actions">
      <button :disabled="busy" @click="run('parse')">① 解析章节</button>
      <button :disabled="busy" @click="run('rewrite')">② 口语化改写</button>
      <button :disabled="busy" @click="run('synthesize')">③ 合成语音</button>
      <span v-if="error" class="err">{{ error }}</span>
    </div>
    <ChapterTree :detail="books.detail" @open="open" />
  </div>
</template>

<style scoped>
.actions { display: flex; gap: 12px; margin-bottom: 16px; }
.err { color: #c00; }
</style>
```

- [ ] **Step 8: 实现 ChapterView.vue**

```vue
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import * as api from "../api/client";
import ChapterEditor from "../components/ChapterEditor.vue";
import AudioPlayer from "../components/AudioPlayer.vue";

const route = useRoute();
const bookId = route.params.bookId as string;
const chapterId = route.params.chapterId as string;
const md = ref("");
const saved = ref(false);
const rebuilding = ref(false);
const error = ref("");

onMounted(async () => {
  md.value = await api.getSpeechMd(bookId, chapterId);
});

async function save() {
  await api.saveSpeechMd(bookId, chapterId, md.value);
  saved.value = true;
  setTimeout(() => (saved.value = false), 2000);
}
async function rebuild() {
  rebuilding.value = true;
  error.value = "";
  try {
    const job = await api.rebuildChapter(bookId, chapterId);
    while (true) {
      await new Promise((r) => setTimeout(r, 1500));
      const jobs = await api.listJobs();
      const cur = jobs.find((j) => j.id === job.id);
      if (!cur || cur.status === "done") break;
      if (cur.status === "failed" || cur.status === "cancelled") throw new Error(cur.error ?? cur.status);
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? String(e);
  } finally {
    rebuilding.value = false;
  }
}
</script>

<template>
  <div>
    <h3>{{ chapterId }}</h3>
    <ChapterEditor v-model="md" />
    <div class="bar">
      <button @click="save">保存文本</button>
      <button :disabled="rebuilding" @click="rebuild">重建本章音频</button>
      <span v-if="saved" class="ok">已保存</span>
      <span v-if="error" class="err">{{ error }}</span>
    </div>
    <AudioPlayer :book-id="bookId" :chapter-id="chapterId" />
  </div>
</template>

<style scoped>
.bar { display: flex; gap: 12px; align-items: center; margin: 12px 0; }
.ok { color: #080; }
.err { color: #c00; }
</style>
```

- [ ] **Step 9: 实现 JobsView.vue / SettingsView.vue**

`frontend/src/views/JobsView.vue`：

```vue
<script setup lang="ts">
import { useJobsStore } from "../stores/jobs";
import JobList from "../components/JobList.vue";
const jobs = useJobsStore();
</script>

<template>
  <div>
    <h2>任务中心</h2>
    <button @click="jobs.refresh()">刷新</button>
    <JobList />
  </div>
</template>
```

`frontend/src/views/SettingsView.vue`：

```vue
<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import * as api from "../api/client";
import { useSettingsStore } from "../stores/settings";

const store = useSettingsStore();
const form = reactive<api.SettingsView>({
  tts_engine: "mock", tts_model: "", tts_speaker: null, tts_speed: 1,
  tts_instruct: null, llm_model: "dsv4-flash",
  chapter_low_chars: 5000, chapter_high_chars: 15000,
});
const models = ref<Array<{ name: string; type: string }>>([]);
const speakers = ref<Array<{ name: string }>>([]);
const saved = ref(false);

onMounted(async () => {
  await store.load();
  if (store.settings) Object.assign(form, store.settings);
  await refreshLists();
});
async function refreshLists() {
  try {
    models.value = await api.listTTSModels();
    speakers.value = await api.listTTSSpeakers();
  } catch { /* 引擎未启动时忽略 */ }
}
async function save() {
  await store.save({ ...form });
  saved.value = true;
  setTimeout(() => (saved.value = false), 2000);
}
</script>

<template>
  <div>
    <h2>设置</h2>
    <label>TTS 引擎
      <select v-model="form.tts_engine" @change="refreshLists">
        <option value="mock">mock（测试）</option>
        <option value="qwen_webui">qwen_webui（本机 Qwen3-TTS）</option>
      </select>
    </label>
    <label>模型
      <select v-model="form.tts_model">
        <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}</option>
      </select>
    </label>
    <label>声音
      <select v-model="form.tts_speaker">
        <option :value="null">默认</option>
        <option v-for="s in speakers" :key="s.name" :value="s.name">{{ s.name }}</option>
      </select>
    </label>
    <label>固化语速
      <input type="number" v-model.number="form.tts_speed" step="0.1" min="0.5" max="2" />
    </label>
    <label>朗读指示
      <input v-model="form.tts_instruct" placeholder="如：用温柔的语气说" />
    </label>
    <label>LLM 模型
      <input v-model="form.llm_model" />
    </label>
    <label>章节字数下限 <input type="number" v-model.number="form.chapter_low_chars" /></label>
    <label>章节字数上限 <input type="number" v-model.number="form.chapter_high_chars" /></label>
    <button @click="save">保存设置</button>
    <span v-if="saved" class="ok">已保存</span>
  </div>
</template>

<style scoped>
label { display: block; margin-bottom: 10px; }
.ok { color: #080; margin-left: 8px; }
</style>
```

- [ ] **Step 10: 类型检查与提交**

Run: `cd frontend && npx vue-tsc --noEmit && npx vitest run`
Expected: 类型检查通过，测试通过

```bash
git add frontend
git commit -m "feat: frontend views and components"
```

---

### Task 12: 集成、README 与全流程验收

**Files:**
- Create: `README.md`
- Modify: `backend/app/services/tts/mock.py`（如需要）

**Interfaces:**
- 产出：可运行的本地应用（后端 `uvicorn app.main:app`，前端 `npm run dev`），README 含安装/配置/启动/验收步骤。

- [ ] **Step 1: 创建 README.md**

```markdown
# PDF 转语音

把 PDF 书籍转化为可听的有声书：解析章节 → dsv4-flash 口语化改写 → Qwen3-TTS 合成音频与字幕。

## 架构
- 后端：FastAPI（`backend/`），pymupdf 解析、LLM 改写、TTS 适配层、SQLite 任务库
- 前端：Vue 3 + Vite + TS（`frontend/`）
- 产物：`data/books/<book_id>/chapters/<chapter_id>/` 下 `speech.md`、`audio.wav`、`chapter.srt`、`chapter.vtt`、`segments.json`、`parts/`

## 快速开始
1. `cp .env.example .env`，填入 `OPENAI_API_KEY`（opencode dsv4-flash）
2. 后端：`cd backend && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000`
3. 前端：`cd frontend && npm install && npm run dev`，浏览器打开 `http://localhost:5173`
4. 上传 PDF → 解析章节 → 口语化改写 → 合成语音

## 接入本机 qwen-tts-webui（需 NVIDIA GPU）
1. 按 https://github.com/licyk/qwen-tts-webui 安装并启动：`python launch.py --api --server-name 0.0.0.0 --server-port 7860`
2. 前端「设置」将引擎切到 `qwen_webui`，首次合成会自动下载模型

## 测试
- 后端：`cd backend && python -m pytest`
- 前端：`cd frontend && npm run test`
```

- [ ] **Step 2: 校验 mock 引擎的语速一致性**

确认 `backend/app/services/tts/mock.py` 的 `synthesize`：`duration` **不**受 `speed` 参数影响（调速统一由 `job_manager._synthesize_chapter` 的 `speed_wav` 后处理，避免双重变速）。若 Task 5 实现时未遵守，按下面代码修正：

```python
    async def synthesize(self, text: str, *, voice: str | None = None,
                         speed: float = 1.0, language: str | None = None,
                         instruct: str | None = None) -> AudioResult:
        duration = max(1.0, len(text) * 0.08)  # 忽略 speed，统一走 post-processing
        data = _sine_wav(duration)
        return AudioResult(data=data, duration=duration, format="wav")
```

- [ ] **Step 3: 后端全量测试**

Run: `cd backend && python -m pytest -q`
Expected: 全部 PASS

- [ ] **Step 4: 前端构建与测试**

Run: `cd frontend && npm run build && npm run test`
Expected: 构建成功，测试通过

- [ ] **Step 5: 手动全流程验收（mock 引擎）**

1. 启动后端 + 前端；
2. 上传 `data/samples/agentic-ai-guide-zh-v1.1.0.pdf`；
3. 点击「解析章节」，确认章节树出现且每章有 `source.md`；
4. 点击「口语化改写」（需 `.env` 已配置 dsv4-flash 密钥），确认 `speech.md` 生成、任务可取消/续跑；
5. 点击「合成语音」（mock），确认 `audio.wav`、`chapter.srt`、`chapter.vtt` 生成，播放器可播放、字幕同步、倍速可用；
6. 编辑某章 `speech.md` → 重建 → 仅该章音频变化；
7. 删除书籍，确认目录整体删除。

- [ ] **Step 6: 真机 TTS 验收（GPU 开启后）**

1. 开启 5060 GPU，`nvidia-smi` 确认可见；
2. 启动 qwen-tts-webui：`python launch.py --api --server-name 0.0.0.0 --server-port 7860`；
3. 前端「设置」切到 `qwen_webui`，选模型/声音；
4. 对一章执行「重建」，确认真实语音 + 字幕 + 换声/调速生效。

- [ ] **Step 7: 提交**

```bash
git add README.md backend frontend
git commit -m "docs: add README; finalize integration"
```
