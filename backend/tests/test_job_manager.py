import asyncio
import io
import json
import struct
import wave
from pathlib import Path

import pymupdf as fitz
import pytest

from app import store
from app.config import RuntimeSettings, SettingsStore
from app.services import audio, job_manager
from app.services.tts.base import AudioResult, TTSAdapter
from app.services.tts.mock import MockTTSAdapter


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
        page.insert_text((72, 72), text, fontsize=18, fontname='china-s')
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
    # 两段加长文本，确保不被合并成一段
    ch = store.chapter_dir(data_dir, "b2", "ch-001")
    (ch / "speech.md").write_text(
        "第一句。" + "长" * 300 + "\n\n第二句。" + "长" * 300, encoding="utf-8")
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
        # 句子级切分：每段 = “首句 + 无句读长尾”两个语音单元
        assert len(segs) == 4
        assert segs[1]["start"] >= segs[0]["end"]
        assert audio.wav_duration((ch / "audio.wav").read_bytes()) > 0
        # 独立字幕文件逐句标注起止
        srt = (ch / "chapter.srt").read_text(encoding="utf-8")
        assert "00:00:00" in srt and "-->" in srt
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
    ch0 = store.chapter_dir(data_dir, "b4", "ch-001")
    (ch0 / "speech.md").write_text(
        "第一句。" + "长" * 200 + "\n\n第二句。" + "长" * 200, encoding="utf-8")
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


class _InterruptedTTS(TTSAdapter):
    """引擎在 interrupt 后返回“任务已中断”错误（模拟 qwen 被取消时的表现）。"""

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
        raise RuntimeError("qwen-tts-webui 错误 500: 生成失败: 500: 任务已中断")

    async def interrupt(self) -> None:
        self._release.set()


@pytest.mark.asyncio
async def test_cancel_running_job_interrupt_error_marks_cancelled(data_dir):
    """取消后引擎报“任务已中断”应归类为 cancelled 而非 failed。"""
    _make_book(data_dir, "b6b")
    adapter = _InterruptedTTS()
    jm = job_manager.JobManager(data_dir, SettingsStore(data_dir),
                                tts_factory=lambda rs, settings: adapter)
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b6b")
        await asyncio.wait_for(adapter.started.wait(), timeout=5)
        jm.cancel(jid)
        job = await _wait_done(jm, jid)
        assert job["status"] == "cancelled", job
        assert "任务已中断" not in (job["error"] or "")
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_cancel_queued_job_is_immediate(data_dir):
    """排队中的任务被取消时直接从队列移除，无需等当前任务结束。"""
    _make_book(data_dir, "b6c")
    blocking = _BlockingTTS()
    jm = job_manager.JobManager(data_dir, SettingsStore(data_dir),
                                tts_factory=lambda rs, settings: blocking)
    jm.start_worker()
    try:
        jid1 = jm.start("synthesize", "b6c")
        await asyncio.wait_for(blocking.started.wait(), timeout=5)
        jid2 = jm.start("synthesize", "b6c")  # 排在 jid1 后面
        assert jm.get_job(jid2)["status"] == "pending"
        jm.cancel(jid2)
        assert jm.get_job(jid2)["status"] == "cancelled"
        assert jm.get_job(jid1)["status"] == "running"  # jid1 不受影响
        await blocking.interrupt()
        job1 = await _wait_done(jm, jid1)
        assert job1["status"] == "done", job1
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_cancel_stale_running_job_marks_cancelled(data_dir):
    """DB 中存在但不属于当前队列/任务的僵尸行：cancel 应立即置为 cancelled。"""
    jm = job_manager.JobManager(data_dir, SettingsStore(data_dir))
    jm.start_worker()
    try:
        jid = store.new_book_id()
        jm._db.create_job(jid, "b-stale", None, "synthesize", "{}")
        jm._db.update_job(jid, status="running")
        jm.cancel(jid)
        job = jm.get_job(jid)
        assert job["status"] == "cancelled"
        assert "服务重启" in (job["error"] or "")
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_startup_cancels_stale_rows(data_dir):
    """进程重启后启动 worker 时，自动清理上次遗留的 running/pending 行。"""
    jm1 = job_manager.JobManager(data_dir, SettingsStore(data_dir))
    jid = store.new_book_id()
    jm1._db.create_job(jid, "b-stale2", None, "synthesize", "{}")
    jm1._db.update_job(jid, status="running")

    jm2 = job_manager.JobManager(data_dir, SettingsStore(data_dir))
    jm2.start_worker()
    try:
        assert jm2.get_job(jid)["status"] == "cancelled"
    finally:
        await jm2.shutdown()


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
        assert sub["page_start"] == 1  # 含第一章引言页
        assert sub["page_end"] == 2
        intro = (bdir / "chapters" / "ch-001-1" / "source.md").read_text(encoding="utf-8")
        assert "第一章 开始" in intro
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


@pytest.mark.asyncio
async def test_parse_job_adds_sequence_numbers_to_titles(data_dir):
    """无编号 TOC 的书籍解析后，章节标题带序号（1. / 2.）。"""
    pdf = data_dir / "book_unnumbered.pdf"
    doc = fitz.open()
    for text in ["开头", "正文"]:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=18, fontname='china-s')
    doc.set_toc([[1, "开头", 1], [1, "正文", 2]])
    doc.save(str(pdf))
    doc.close()

    bdir = store.book_dir(data_dir, "b11")
    bdir.mkdir(parents=True)
    (bdir / "source.pdf").write_bytes(pdf.read_bytes())

    ss = SettingsStore(data_dir)
    ss.save(RuntimeSettings(chapter_low_chars=1, chapter_high_chars=10**9))
    jm = job_manager.JobManager(data_dir, ss)
    jm.start_worker()
    try:
        jid = jm.start("parse", "b11")
        job = await _wait_done(jm, jid)
        assert job["status"] == "done", job
        chapters = store.load_json(bdir / "chapters.json", {})["chapters"]
        titles = [c["title"] for c in chapters]
        assert titles == ["1. 开头", "2. 正文"]
        # 末章页尾必须钳制到实际页数，而非 10**6 占位
        assert chapters[-1]["page_end"] == 2
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_rewrite_single_chapter_preserves_others(data_dir):
    """单章改写不得覆盖 chapters.json 中的其他章节。"""
    _make_book(data_dir, "b20", with_speech=False)
    # b20 只有 ch-001；构造含两章的 chapters.json
    bdir = store.book_dir(data_dir, "b20")
    (bdir / "chapters" / "ch-002").mkdir(parents=True, exist_ok=True)
    store.save_json(bdir / "chapters.json", {"chapters": [
        {"id": "ch-001", "title": "第一章", "level": 1, "page_start": 1,
         "page_end": 3, "char_count": 30, "status": "pending"},
        {"id": "ch-002", "title": "第二章", "level": 1, "page_start": 4,
         "page_end": 6, "char_count": 30, "status": "pending"},
    ]})
    (bdir / "chapters" / "ch-001" / "source.md").write_text("第一章原文", encoding="utf-8")
    (bdir / "chapters" / "ch-002" / "source.md").write_text("第二章原文", encoding="utf-8")

    class _FakeRewriter:
        async def rewrite_chapter(self, book_id, chapter, on_progress):
            ch_dir = store.chapter_dir(data_dir, book_id, chapter["id"])
            ch_dir.mkdir(parents=True, exist_ok=True)
            (ch_dir / "speech.md").write_text("口语化结果", encoding="utf-8")
            await on_progress(1.0)

    jm = job_manager.JobManager(
        data_dir, SettingsStore(data_dir),
        rewriter_factory=lambda rs, s, concurrency=20: _FakeRewriter(),  # type: ignore[arg-type]
    )
    jm.start_worker()
    try:
        jid = jm.start("rewrite", "b20", "ch-001")
        job = await _wait_done(jm, jid)
        assert job["status"] == "done", job
        chapters = store.load_json(bdir / "chapters.json", {})["chapters"]
        assert [c["id"] for c in chapters] == ["ch-001", "ch-002"]
        by_id = {c["id"]: c for c in chapters}
        assert by_id["ch-001"]["status"] == "rewritten"
        assert by_id["ch-002"]["status"] == "pending"
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_synthesize_single_chapter_preserves_others(data_dir):
    """单章合成不得覆盖 chapters.json 中的其他章节。"""
    _make_book(data_dir, "b21", with_speech=False)
    bdir = store.book_dir(data_dir, "b21")
    (bdir / "chapters" / "ch-002").mkdir(parents=True, exist_ok=True)
    store.save_json(bdir / "chapters.json", {"chapters": [
        {"id": "ch-001", "title": "第一章", "level": 1, "page_start": 1,
         "page_end": 3, "char_count": 30, "status": "pending"},
        {"id": "ch-002", "title": "第二章", "level": 1, "page_start": 4,
         "page_end": 6, "char_count": 30, "status": "pending"},
    ]})
    (bdir / "chapters" / "ch-001" / "speech.md").write_text("第一句。\n\n第二句。", encoding="utf-8")

    jm = job_manager.JobManager(data_dir, SettingsStore(data_dir))
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b21", "ch-001")
        job = await _wait_done(jm, jid)
        assert job["status"] == "done", job
        chapters = store.load_json(bdir / "chapters.json", {})["chapters"]
        assert [c["id"] for c in chapters] == ["ch-001", "ch-002"]
        by_id = {c["id"]: c for c in chapters}
        assert by_id["ch-001"]["status"] == "synthesized"
        assert by_id["ch-002"]["status"] == "pending"
    finally:
        await jm.shutdown()


class _RecordingBatchTTS(MockTTSAdapter):
    """记录批量调用次数的 mock 引擎。"""

    def __init__(self):
        super().__init__()
        self.batch_calls = 0
        self.clone_calls = 0
        self.submitted_texts: list[list[str]] = []

    async def synthesize_batch(self, texts, *, voice=None, language=None, instruct=None):
        self.batch_calls += 1
        self.submitted_texts.append(list(texts))
        return [await self.synthesize(t, voice=voice, language=language, instruct=instruct)
                for t in texts]

    async def synthesize_clone_batch(self, texts, *, ref_audio, ref_text=None, language=None):
        self.clone_calls += 1
        self.submitted_texts.append(list(texts))
        return [await self.synthesize(t) for t in texts]


class _TrackingConcurrentTTS(MockTTSAdapter):
    """记录同一时刻并发合成请求数（模拟云端/网络时延）。"""

    def __init__(self, delay: float = 0.1):
        super().__init__()
        self.delay = delay
        self._lock = asyncio.Lock()
        self.inflight = 0
        self.max_inflight = 0

    async def synthesize(self, text, *, voice=None, speed=1.0, language=None,
                         instruct=None):
        async with self._lock:
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            await asyncio.sleep(self.delay)
            return await super().synthesize(text, voice=voice, speed=speed,
                                            language=language, instruct=instruct)
        finally:
            async with self._lock:
                self.inflight -= 1


@pytest.mark.asyncio
async def test_synthesize_uses_batches(data_dir):
    _make_book(data_dir, "b30")
    ch = store.chapter_dir(data_dir, "b30", "ch-001")
    (ch / "speech.md").write_text(
        "\n\n".join(f"第{i}句内容" + "长" * 480 for i in range(5)), encoding="utf-8")
    ss = SettingsStore(data_dir)
    rs = ss.load()
    rs.tts_batch_size = 2
    ss.save(rs)

    adapter = _RecordingBatchTTS()
    jm = job_manager.JobManager(data_dir, ss, tts_factory=lambda rs, s: adapter)
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b30")
        job = await _wait_done(jm, jid)
        assert job["status"] == "done", job
        # 5 句 / 批 2 → 3 次批量调用
        assert adapter.batch_calls == 3
        assert (ch / "audio.wav").exists()
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_synthesize_normalizes_spoken_text_but_keeps_subtitles(data_dir):
    """送 TTS 的文本做默认归一化（LLM→L L M），但 speech.md/字幕仍保留原文。"""
    _make_book(data_dir, "b41")
    ch = store.chapter_dir(data_dir, "b41", "ch-001")
    (ch / "speech.md").write_text(
        "LLM 与 ID。\n\nOpenAI 与 vLLM 用于生产。", encoding="utf-8")
    ss = SettingsStore(data_dir)
    adapter = _RecordingBatchTTS()
    jm = job_manager.JobManager(data_dir, ss, tts_factory=lambda rs, s: adapter)
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b41")
        job = await _wait_done(jm, jid)
        assert job["status"] == "done", job

        # speech.md 不被改写
        assert "LLM 与 ID。" in (ch / "speech.md").read_text(encoding="utf-8")

        # 字幕/segments 使用原文
        segs = store.load_json(ch / "segments.json", [])
        joined = "\n".join(s["text"] for s in segs)
        assert "LLM" in joined and "ID" in joined and "vLLM" in joined

        # 送 TTS 的是归一化后的朗读文本
        flat = [t for batch in adapter.submitted_texts for t in batch]
        spoken_all = "\n".join(flat)
        assert "L L M" in spoken_all and "I D" in spoken_all and "V L L M" in spoken_all
        assert "LLM" not in spoken_all and "ID" not in spoken_all and "vLLM" not in spoken_all
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_synthesize_concurrency_parallel_batches(data_dir):
    _make_book(data_dir, "b40")
    ch = store.chapter_dir(data_dir, "b40", "ch-001")
    # 8 个分片，批大小 1 → 8 个独立请求，并发上限 4
    (ch / "speech.md").write_text(
        "\n\n".join(f"第{i}句内容。" + "长" * 480 for i in range(8)),
        encoding="utf-8")
    ss = SettingsStore(data_dir)
    rs = ss.load()
    rs.tts_batch_size = 1
    rs.tts_concurrency = 1  # 任务级 concurrency=4 应覆盖默认值
    ss.save(rs)

    adapter = _TrackingConcurrentTTS(delay=0.1)
    jm = job_manager.JobManager(data_dir, ss, tts_factory=lambda rs, s: adapter)
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b40", concurrency=4)
        job = await _wait_done(jm, jid)
        assert job["status"] == "done", job
        snap = json.loads(jm.get_job(jid)["settings_snapshot"])
        assert snap["tts_concurrency"] == 4
        assert adapter.max_inflight == 4
        assert (ch / "audio.wav").exists()
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_synthesize_clone_mode_uses_clone_batch(data_dir):
    _make_book(data_dir, "b31")
    ch = store.chapter_dir(data_dir, "b31", "ch-001")
    (ch / "speech.md").write_text("克隆第一句。\n\n克隆第二句。", encoding="utf-8")
    ref = data_dir / "clone_ref_audio.wav"
    ref.write_bytes(b"RIFF-fake-wav")
    ss = SettingsStore(data_dir)
    rs = ss.load()
    rs.tts_mode = "clone"
    rs.tts_clone_ref_audio = "clone_ref_audio.wav"
    ss.save(rs)

    adapter = _RecordingBatchTTS()
    jm = job_manager.JobManager(data_dir, ss, tts_factory=lambda rs, s: adapter)
    jm.start_worker()
    try:
        jid = jm.start("synthesize", "b31")
        job = await _wait_done(jm, jid)
        assert job["status"] == "done", job
        assert adapter.clone_calls >= 1
        assert adapter.batch_calls == 0
        assert (ch / "audio.wav").exists()
    finally:
        await jm.shutdown()


@pytest.mark.asyncio
async def test_rewrite_concurrency_stored_in_snapshot(data_dir):
    _make_book(data_dir, "b32", with_speech=False)
    bdir = store.book_dir(data_dir, "b32")
    (bdir / "chapters" / "ch-001" / "source.md").write_text("表格：\n|A|B|\n|1|2|", encoding="utf-8")
    jm = job_manager.JobManager(
        data_dir, SettingsStore(data_dir),
        rewriter_factory=lambda rs, s, concurrency=20: _FakeRewriter(),  # type: ignore[arg-type]
    )
    jid = jm.start("rewrite", "b32", "ch-001", concurrency=7)
    snap = jm.get_job(jid)["settings_snapshot"]
    import json as _json
    assert _json.loads(snap)["rewrite_concurrency"] == 7


@pytest.mark.asyncio
async def test_rewrite_and_synthesize_run_concurrently(data_dir):
    """改写（LLM 通道）与合成（TTS 通道）互不阻塞，可并行。"""
    _make_book(data_dir, "b40", with_speech=True)
    bdir = store.book_dir(data_dir, "b40")
    (bdir / "chapters" / "ch-001" / "source.md").write_text("表格：\n|A|B|\n|1|2|", encoding="utf-8")
    # 第二个书用于合成
    _make_book(data_dir, "b41", with_speech=True)

    release = asyncio.Event()

    class _BlockingRewriter:
        async def rewrite_chapter(self, book_id, chapter, on_progress):
            await release.wait()  # 阻塞改写任务
            ch_dir = store.chapter_dir(data_dir, book_id, chapter["id"])
            (ch_dir / "speech.md").write_text("改写完成", encoding="utf-8")
            await on_progress(1.0)

    jm = job_manager.JobManager(
        data_dir, SettingsStore(data_dir),
        rewriter_factory=lambda rs, s, concurrency=20: _BlockingRewriter(),  # type: ignore[arg-type]
    )
    jm.start_worker()
    try:
        rw_id = jm.start("rewrite", "b40", "ch-001")
        # 等改写进入阻塞状态
        for _ in range(50):
            if jm.get_job(rw_id)["status"] == "running":
                break
            await asyncio.sleep(0.05)
        assert jm.get_job(rw_id)["status"] == "running"
        # 启动合成（另一本书），应能在改写被阻塞时完成
        sy_id = jm.start("synthesize", "b41")
        sy_job = await _wait_done(jm, sy_id)
        assert sy_job["status"] == "done", sy_job
        # 改写此时仍在运行（未被合成阻塞/取消）
        assert jm.get_job(rw_id)["status"] == "running"
        release.set()
        rw_job = await _wait_done(jm, rw_id)
        assert rw_job["status"] == "done", rw_job
    finally:
        release.set()
        await jm.shutdown()
