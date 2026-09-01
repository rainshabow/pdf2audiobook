import asyncio
import io
import struct
import wave
from pathlib import Path

import pymupdf as fitz
import pytest

from app import store
from app.config import RuntimeSettings, SettingsStore
from app.services import audio, job_manager
from app.services.tts.base import AudioResult, TTSAdapter


class _BlockingTTS(TTSAdapter):
    """synthesize 阻塞直到 interrupt/release，用于模拟运行中任务的取消。"""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self._release = asyncio.Event()

    async def list_models(self) -> list[dict]:
        return []

    async def list_speakers(self) -> list[dict]:
        return []

    async def synthesize(self, text: str, *, voice: str | None = None,
                         speed: float = 1.0, language: str | None = None,
                         instruct: str | None = None) -> AudioResult:
        self.started.set()
        await self._release.wait()
        return AudioResult(data=_tiny_wav(), duration=1.0)

    async def interrupt(self) -> None:
        self._release.set()


def _tiny_wav(duration: float = 0.1) -> bytes:
    rate = 24000
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(rate * duration))
    return buf.getvalue()


def _make_pdf(path: Path) -> None:
    doc = fitz.open()
    for pno, text in enumerate(["第一章 开始", "这是第一页正文。", "第二章 进阶"], start=1):
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=18)
    doc.set_toc([[1, "第一章 开始", 1], [1, "第二章 进阶", 3]])
    doc.save(str(path))
    doc.close()


def _make_pdf_with_level2(path: Path) -> None:
    """含 level-2 TOC 的多页 PDF：第一章(1-3 页) 下有两个二级标题。"""
    doc = fitz.open()
    for text in ["第一章 开始", "1.1 子节一", "1.2 子节二", "第二章 结束"]:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=18)
    doc.set_toc([
        [1, "第一章 开始", 1],
        [2, "1.1 子节一", 2],
        [2, "1.2 子节二", 3],
        [1, "第二章 结束", 4],
    ])
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


@pytest.mark.asyncio
async def test_rebuild_drops_stale_parts(data_dir):
    _make_book(data_dir, "b4")
    jm = job_manager.JobManager(data_dir, SettingsStore(data_dir))
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b4")
        await _wait_done(jm, jid)
        ch = store.chapter_dir(data_dir, "b4", "ch-001")
        dur1 = audio.wav_duration((ch / "audio.wav").read_bytes())
        # 改写 speech.md 为不同内容（更短，仅一段）后 rebuild
        (ch / "speech.md").write_text("第三句。", encoding="utf-8")
        jid2 = jm.start("rebuild", "b4")
        await _wait_done(jm, jid2)
        assert jm.get_job(jid2)["status"] == "done"
        segs2 = store.load_json(ch / "segments.json", [])
        dur2 = audio.wav_duration((ch / "audio.wav").read_bytes())
        assert len(segs2) == 1
        # 音频时长对应当前 segments，而非旧分片累加
        assert abs(dur2 - (segs2[0]["end"] - segs2[0]["start"])) < 0.01
        assert dur2 != dur1
        # 旧 parts 已被清理：目录里只剩当前 segments 引用的分片
        part_files = sorted(ch.glob("parts/*.wav"))
        assert len(part_files) == 1
        assert part_files[0].name == f"{segs2[0]['index'] - 1:04d}_{segs2[0]['hash']}.wav"
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_synthesize_missing_speech_fails(data_dir):
    _make_book(data_dir, "b5", with_speech=False)
    jm = job_manager.JobManager(data_dir, SettingsStore(data_dir))
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b5")
        job = await _wait_done(jm, jid)
        assert job["status"] == "failed"
        assert "FileNotFoundError" in job["error"]
        assert "speech.md" in job["error"]
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_cancel_running_job(data_dir):
    _make_book(data_dir, "b6")
    adapter = _BlockingTTS()
    jm = job_manager.JobManager(data_dir, SettingsStore(data_dir),
                                tts_factory=lambda rs, settings: adapter)
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b6")
        await asyncio.wait_for(adapter.started.wait(), timeout=5)
        jm.cancel(jid)
        job = await _wait_done(jm, jid)
        assert job["status"] == "cancelled"
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_shutdown_marks_inflight_and_queued_jobs_cancelled(data_dir):
    _make_book(data_dir, "b7")
    adapter = _BlockingTTS()
    jm = job_manager.JobManager(data_dir, SettingsStore(data_dir),
                                tts_factory=lambda rs, settings: adapter)
    jm.start_worker()
    jid1 = jm.start("synthesize", "b7")  # 在途：阻塞在 adapter.synthesize
    await asyncio.wait_for(adapter.started.wait(), timeout=5)
    jid2 = jm.start("synthesize", "b7")  # 排队
    jid3 = jm.start("synthesize", "b7")  # 排队
    await jm.shutdown()
    assert jm.get_job(jid1)["status"] == "cancelled"
    assert jm.get_job(jid2)["status"] == "cancelled"
    assert jm.get_job(jid3)["status"] == "cancelled"


async def _wait_done(jm: job_manager.JobManager, jid: str, timeout: float = 30.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = jm.get_job(jid)
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(f"任务未在 {timeout}s 内结束: {jm.get_job(jid)}")


@pytest.mark.asyncio
async def test_parse_job_splits_oversize_by_level2(data_dir):
    """超长章节按 TOC 二级标题拆分：chapters.json 出现 ch-001-1/ch-001-2 子章节。"""
    pdf = data_dir / "book.pdf"
    _make_pdf_with_level2(pdf)
    bdir = store.book_dir(data_dir, "b9")
    bdir.mkdir(parents=True)
    (bdir / "source.pdf").write_bytes(pdf.read_bytes())

    ss = SettingsStore(data_dir)
    ss.save(RuntimeSettings(chapter_low_chars=1, chapter_high_chars=1))
    jm = job_manager.JobManager(data_dir, ss)
    jm.start_worker()
    try:
        jid = jm.start("parse", "b9")
        job = await _wait_done(jm, jid)
        assert job["status"] == "done", job
        chapters = store.load_json(bdir / "chapters.json", {})["chapters"]
        ids = [c["id"] for c in chapters]
        assert "ch-001-1" in ids
        assert "ch-001-2" in ids
        sub = next(c for c in chapters if c["id"] == "ch-001-1")
        assert sub["page_start"] == 2
        assert sub["page_end"] == 2
        assert (bdir / "chapters" / "ch-001-1" / "source.md").exists()
        assert (bdir / "chapters" / "ch-001-2" / "source.md").exists()
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_synthesize_empty_speech_fails_with_clear_error(data_dir):
    _make_book(data_dir, "b10")
    ch = store.chapter_dir(data_dir, "b10", "ch-001")
    (ch / "speech.md").write_text("", encoding="utf-8")
    jm = job_manager.JobManager(data_dir, SettingsStore(data_dir))
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b10")
        job = await _wait_done(jm, jid)
        assert job["status"] == "failed"
        assert "本章无内容可合成" in job["error"]
    finally:
        await jm.shutdown()
