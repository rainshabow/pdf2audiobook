import asyncio
from pathlib import Path

import pymupdf as fitz
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

