import asyncio
import json
import shutil
from pathlib import Path
from typing import Awaitable, Callable

from app import store
from app.config import RuntimeSettings, SettingsStore, Settings
from app.services import audio, pdf_extractor, rewriter, segmenter
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
        """把在途/排队任务置为终态后停止 worker，避免重启后遗留 running/pending 行。"""
        if self._worker_task is None:
            return
        if self._current_job_id:
            self._db.update_job(self._current_job_id, status="cancelled")
        while True:
            try:
                jid, *_ = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._db.update_job(jid, status="cancelled")
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
        job = self._db.get_job(job_id)
        if job is None or job["status"] in ("done", "failed", "cancelled"):
            return  # 不存在或已终态：不加入 flags，也不触发 interrupt
        self._cancel_flags.add(job_id)
        if self._current_job_id == job_id and self._current_adapter is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return  # 无运行事件循环时跳过 interrupt
            loop.create_task(self._current_adapter.interrupt())

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
                self._db.update_job(jid, status="failed",
                                    error=f"{type(exc).__name__}: {exc}")
            finally:
                self._cancel_flags.discard(jid)
                self._current_job_id = None
                self._current_adapter = None

    # ---------- parse ----------
    async def _run_parse(self, book_id: str) -> None:
        bdir = store.book_dir(self._data_dir, book_id)
        pdf_path = bdir / "source.pdf"
        meta = pdf_extractor.extract_meta(pdf_path)
        # 保留上传时回退的原始文件名标题，避免解析覆盖为 source.pdf 的 stem
        prev_meta = store.load_json(bdir / "meta.json", {})
        if prev_meta.get("title"):
            meta["title"] = prev_meta["title"]
        meta.update({"book_id": book_id, "status": "parsed",
                     "toc": pdf_extractor.extract_toc(pdf_path)})
        candidates = segmenter.build_candidates(pdf_path, meta)
        rs = self._settings_store.load()
        counts: dict[str, int] = {}
        for ch in candidates:
            blocks = pdf_extractor.extract_blocks(pdf_path, ch["page_start"], ch["page_end"])
            counts[ch["id"]] = len(pdf_extractor.blocks_to_markdown(blocks))
            await self._maybe_cancel()
        chapters = segmenter.adaptive_merge(candidates, counts,
                                            rs.chapter_low_chars, rs.chapter_high_chars)
        # 超长章节按 TOC 二级标题拆分（拆分后按新范围重新提取计数）
        chapters = segmenter.split_oversize(chapters, meta["toc"], counts,
                                            rs.chapter_high_chars)
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
                await self._maybe_cancel()
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
        try:
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
        finally:
            close = getattr(adapter, "aclose", None)
            if close is not None:
                await close()

    async def _synthesize_chapter(self, adapter: TTSAdapter, ch_dir: Path,
                                  speech_path: Path, rs: RuntimeSettings,
                                  ch_idx: int, total: int) -> list[dict]:
        text = speech_path.read_text(encoding="utf-8")
        parts = audio.split_speech_text(text, max_chars=500)
        if not parts:
            raise ValueError("本章无内容可合成")
        parts_dir = ch_dir / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        segments: list[dict] = []
        cursor = 0.0
        for idx, seg_text in enumerate(parts):
            await self._maybe_cancel()
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
        # 只拼接当前 segments 引用的分片，避免改写 speech.md 后陈旧 parts 混入 audio.wav
        part_bytes = [(parts_dir / f"{s['index'] - 1:04d}_{s['hash']}.wav").read_bytes()
                      for s in segments]
        wav = audio.concat_wavs(part_bytes, self._data_dir / "tmp")
        if abs(rs.tts_speed - 1.0) > 1e-6:
            wav = audio.speed_wav(wav, rs.tts_speed, self._data_dir / "tmp")
            for s in segments:
                s["start"] = round(s["start"] / rs.tts_speed, 3)
                s["end"] = round(s["end"] / rs.tts_speed, 3)
        # 清理未被当前 segments 引用的旧分片（保留增量复用语义）
        used = {f"{s['index'] - 1:04d}_{s['hash']}.wav" for s in segments}
        for old in parts_dir.glob("*.wav"):
            if old.name not in used:
                old.unlink()
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

    async def _maybe_cancel(self) -> None:
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
