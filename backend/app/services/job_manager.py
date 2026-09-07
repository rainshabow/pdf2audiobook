import asyncio
import json
import shutil
from pathlib import Path
from typing import Awaitable, Callable

from app import store
from app.config import RuntimeSettings, SettingsStore, Settings
from app.services import audio, pdf_extractor, rewriter, segmenter, tts_normalize
from app.services.pool import run_windowed
from app.services.tts.base import TTSAdapter
from app.services.tts.mock import MockTTSAdapter
from app.services.tts.qwen_webui import QwenWebUIAdapter

JobType = str  # parse | rewrite | synthesize | rebuild
ProgressCb = Callable[[float], Awaitable[None]]


class JobManager:
    def __init__(self, data_dir: Path, settings_store: SettingsStore,
                 tts_factory: Callable[[RuntimeSettings, Settings], TTSAdapter] | None = None,
                 rewriter_factory: Callable[[RuntimeSettings, Settings, int], rewriter.Rewriter] | None = None,
                 settings: Settings | None = None):
        self._data_dir = data_dir
        self._settings_store = settings_store
        self._settings = settings or Settings()
        self._db = store.JobDB(data_dir / "jobs.db")
        # 双通道：llm（parse/rewrite，LLM/CPU 资源）与 tts（synthesize/rebuild，GPU 资源）
        self._queue_llm: asyncio.Queue[tuple[str, JobType, str, str | None]] = asyncio.Queue()
        self._queue_tts: asyncio.Queue[tuple[str, JobType, str, str | None]] = asyncio.Queue()
        self._cancel_flags: set[str] = set()
        self._queued: set[str] = set()  # 已入队、尚未被 worker 取出的任务
        self._worker_tasks: list[asyncio.Task] = []
        self._current_job_id: dict[str, str | None] = {"llm": None, "tts": None}
        self._current_adapter: dict[str, TTSAdapter | None] = {"llm": None, "tts": None}
        self._tts_factory = tts_factory or _default_tts_factory
        self._rewriter_factory = rewriter_factory or _default_rewriter_factory

    @staticmethod
    def _lane(job_type: JobType) -> str:
        return "tts" if job_type in ("synthesize", "rebuild") else "llm"

    def start_worker(self) -> None:
        if not self._worker_tasks:
            # 上次进程被强杀/重启后遗留的 running/pending 行不再有 worker 处理，
            # 启动时统一置为 cancelled，避免出现“取消无效”的僵尸任务
            self._db.cancel_stale()
            self._worker_tasks = [
                asyncio.create_task(self._worker("llm", self._queue_llm)),
                asyncio.create_task(self._worker("tts", self._queue_tts)),
            ]

    async def shutdown(self) -> None:
        """把在途/排队任务置为终态后停止 worker，避免重启后遗留 running/pending 行。"""
        if not self._worker_tasks:
            return
        for lane, jid in self._current_job_id.items():
            if jid:
                self._db.update_job(jid, status="cancelled")
        for queue in (self._queue_llm, self._queue_tts):
            while True:
                try:
                    jid, *_ = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                self._queued.discard(jid)
                self._db.update_job(jid, status="cancelled")
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks = []

    def start(self, job_type: JobType, book_id: str, chapter_id: str | None = None,
              concurrency: int | None = None) -> str:
        jid = store.new_book_id()
        rs = self._settings_store.load()
        snap = _rs_to_dict(rs)
        if job_type == "rewrite":
            snap["rewrite_concurrency"] = (concurrency if concurrency is not None
                                           else rs.rewrite_concurrency)
        elif self._lane(job_type) == "tts":
            snap["tts_concurrency"] = (concurrency if concurrency is not None
                                       else rs.tts_concurrency)
        self._db.create_job(jid, book_id, chapter_id, job_type,
                            json.dumps(snap, ensure_ascii=False))
        queue = self._queue_tts if self._lane(job_type) == "tts" else self._queue_llm
        queue.put_nowait((jid, job_type, book_id, chapter_id))
        self._queued.add(jid)
        return jid

    def get_job(self, job_id: str) -> dict | None:
        return self._db.get_job(job_id)

    def list_jobs(self) -> list[dict]:
        return self._db.list_jobs()

    def resume(self, job_id: str) -> str:
        """为失败/已取消的任务创建续跑任务（沿用原任务设置快照，从断点继续）。

        - rewrite：按段缓存（rewrite_checkpoint）跳过已完成分段
        - synthesize/rebuild：按分片文件（parts/{idx}_{hash}.wav）跳过已合成句子
        """
        job = self._db.get_job(job_id)
        if job is None:
            raise KeyError(f"任务不存在: {job_id}")
        if job["status"] not in ("failed", "cancelled"):
            raise ValueError(f"仅失败或已取消的任务可续跑（当前状态：{job['status']}）")
        if job["type"] not in ("rewrite", "synthesize", "rebuild"):
            raise ValueError(f"任务类型 {job['type']} 不支持断点续跑")
        try:
            snap = json.loads(job.get("settings_snapshot") or "{}")
        except Exception:
            snap = {}
        if not isinstance(snap, dict) or not snap:
            snap = _rs_to_dict(self._settings_store.load())
        new_id = store.new_book_id()
        self._db.create_job(new_id, job["book_id"], job["chapter_id"], job["type"],
                            json.dumps(snap, ensure_ascii=False))
        queue = self._queue_tts if self._lane(job["type"]) == "tts" else self._queue_llm
        queue.put_nowait((new_id, job["type"], job["book_id"], job["chapter_id"]))
        self._queued.add(new_id)
        return new_id

    def cancel(self, job_id: str) -> None:
        job = self._db.get_job(job_id)
        if job is None or job["status"] in ("done", "failed", "cancelled"):
            return  # 不存在或已终态：不加入 flags，也不触发 interrupt
        # 排队中：直接从队列移除并立即置为 cancelled，无需等前一个任务结束
        if self._dequeue(job_id):
            self._db.update_job(job_id, status="cancelled",
                                error="任务已取消")
            return
        lane = self._lane(job["type"])
        if self._current_job_id.get(lane) == job_id:
            self._cancel_flags.add(job_id)
            if self._current_adapter.get(lane) is not None:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    return  # 无运行事件循环时跳过 interrupt
                loop.create_task(self._current_adapter[lane].interrupt())
            return
        # 既不在队列也不在当前任务：属于被强杀进程遗留的僵尸行，
        # 当前 worker 永远不会处理它，直接置为 cancelled
        self._db.update_job(job_id, status="cancelled",
                            error="服务重启，遗留任务已取消")

    def _dequeue(self, job_id: str) -> bool:
        """从两个任务队列中移除指定任务（同步执行，无 await 竞态）。"""
        removed = False
        for queue in (self._queue_llm, self._queue_tts):
            kept: list = []
            while True:
                try:
                    item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if item[0] == job_id:
                    removed = True
                else:
                    kept.append(item)
            for item in kept:
                queue.put_nowait(item)
        if removed:
            self._queued.discard(job_id)
        return removed

    async def _worker(self, lane: str,
                      queue: asyncio.Queue[tuple[str, JobType, str, str | None]]) -> None:
        while True:
            jid, job_type, book_id, chapter_id = await queue.get()
            self._queued.discard(jid)
            self._current_job_id[lane] = jid
            self._current_adapter[lane] = None
            self._db.update_job(jid, status="running", error=None)
            try:
                if job_type == "parse":
                    await self._run_parse(book_id, jid)
                elif job_type == "rewrite":
                    await self._run_rewrite(book_id, chapter_id, jid)
                elif job_type in ("synthesize", "rebuild"):
                    await self._run_synthesize(book_id, chapter_id, jid)
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
                self._current_job_id[lane] = None
                self._current_adapter[lane] = None

    # ---------- parse ----------
    async def _run_parse(self, book_id: str, job_id: str | None = None) -> None:
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
            await self._maybe_cancel(job_id)
        chapters = segmenter.adaptive_merge(candidates, counts,
                                            rs.chapter_low_chars, rs.chapter_high_chars)
        # 超长章节按 TOC 二级标题拆分（拆分后按新范围重新提取计数）
        chapters = segmenter.split_oversize(chapters, meta["toc"], counts,
                                            rs.chapter_high_chars)
        # 末章页尾钳制到实际页数（避免 10**6 占位）；标题优先用印刷目录编号
        for ch in chapters:
            ch["page_end"] = min(ch["page_end"], meta["page_count"])
        printed_toc = pdf_extractor.extract_printed_toc(pdf_path)
        chapters = segmenter.number_chapters(chapters, printed_toc)
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
    async def _run_rewrite(self, book_id: str, chapter_id: str | None = None,
                              job_id: str | None = None) -> None:
        chapters = self._chapters(book_id, chapter_id)
        rs = self._settings_store.load()
        job = self._db.get_job(job_id or "") or {}
        try:
            snap = json.loads(job.get("settings_snapshot") or "{}")
        except Exception:
            snap = {}
        concurrency = int(snap.get("rewrite_concurrency") or rs.rewrite_concurrency)
        rw = self._rewriter_factory(rs, self._settings, concurrency)
        for i, ch in enumerate(chapters):
            async def on_progress(p: float) -> None:
                overall = (i + p) / len(chapters)
                await self._maybe_cancel(job_id)
                self._db.update_job(job_id or "", progress=overall)
            await rw.rewrite_chapter(book_id, ch, on_progress)
            ch_dir = store.chapter_dir(self._data_dir, book_id, ch["id"])
            ch["status"] = "rewritten"
            store.save_json(ch_dir / "status.json", ch)
            self._save_chapters(book_id, chapters)

    # ---------- synthesize / rebuild ----------
    async def _run_synthesize(self, book_id: str, chapter_id: str | None = None,
                                job_id: str | None = None) -> None:
        chapters = self._chapters(book_id, chapter_id)
        rs = self._settings_store.load()
        job = self._db.get_job(job_id or "") or {}
        try:
            snap = json.loads(job.get("settings_snapshot") or "{}")
        except Exception:
            snap = {}
        raw_concurrency = snap.get("tts_concurrency")
        concurrency = int(raw_concurrency if raw_concurrency is not None
                          else rs.tts_concurrency)
        adapter = self._tts_factory(rs, self._settings)
        self._current_adapter["tts"] = adapter
        try:
            for i, ch in enumerate(chapters):
                ch_dir = store.chapter_dir(self._data_dir, book_id, ch["id"])
                speech_path = ch_dir / "speech.md"
                if not speech_path.exists():
                    raise FileNotFoundError(f"缺少 speech.md: {speech_path}")
                segments = await self._synthesize_chapter(
                    adapter, ch_dir, speech_path, rs, i, len(chapters), job_id,
                    concurrency=concurrency)
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
                                  ch_idx: int, total: int,
                                  job_id: str | None = None,
                                  concurrency: int = 1) -> list[dict]:
        text = speech_path.read_text(encoding="utf-8")
        # 句子级切分：每个 TTS 单元对应一个字幕句，可获得精确的句级起止时间
        parts = audio.split_utterances(text)
        if not parts:
            raise ValueError("本章无内容可合成")
        parts_dir = ch_dir / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        # 预扫描：区分可复用分片与缺失分片
        items: list[dict] = []
        for idx, seg_text in enumerate(parts):
            # 归一化只用于“送给 TTS 的朗读文本”，text 字段仍保留 speech.md 原文（字幕用）
            spoken = tts_normalize.normalize_for_tts(seg_text)
            h = audio.text_hash(spoken)
            part_path = parts_dir / f"{idx:04d}_{h}.wav"
            if part_path.exists():
                items.append({"idx": idx, "text": seg_text, "spoken": spoken,
                              "hash": h, "path": part_path,
                              "duration": audio.wav_duration(part_path.read_bytes())})
            else:
                items.append({"idx": idx, "text": seg_text, "spoken": spoken,
                              "hash": h, "path": part_path, "duration": None})
        missing = [(i, it) for i, it in enumerate(items) if it["duration"] is None]
        batch_size = max(1, rs.tts_batch_size)
        ref_bytes: bytes | None = None
        if rs.tts_mode == "clone" and rs.tts_clone_ref_audio:
            ref_path = self._data_dir / rs.tts_clone_ref_audio
            if not ref_path.exists():
                raise FileNotFoundError(f"克隆参考音频不存在: {ref_path}")
            ref_bytes = ref_path.read_bytes()
        if not missing:
            self._db.update_job(job_id or "",
                                progress=(ch_idx + 1) / total)
        else:
            # 滑动窗口并发：固定数量 worker 消费“请求”队列，任一完成立即调度下一个；
            # 并发 -1 = 不限窗口大小（仅由适配器 RPM 限速）。
            # 队列单元 = 一次适配器请求：mimo 每次 HTTP 请求只合成一句 → 按句入队；
            # qwen 支持 segment_gen 一次提交多句 → 保留该优化，按“批处理句数”入队。
            unit_size = 1 if rs.tts_engine == "mimo" else max(1, batch_size)
            units = [missing[b:b + unit_size]
                     for b in range(0, len(missing), unit_size)]
            abort = asyncio.Event()
            errors: list[Exception] = []
            done_count = len(items) - len(missing)
            submitted = 0

            async def _run_unit(unit: list[tuple[int, dict]]) -> None:
                nonlocal done_count
                await self._maybe_cancel(job_id)
                if abort.is_set():
                    return
                texts = [it["spoken"] for _, it in unit]
                try:
                    if ref_bytes is not None:
                        results = await adapter.synthesize_clone_batch(
                            texts, ref_audio=ref_bytes,
                            ref_text=rs.tts_clone_ref_text)
                    else:
                        results = await adapter.synthesize_batch(
                            texts, voice=rs.tts_speaker,
                            instruct=rs.tts_instruct)
                except _JobCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001
                    # 取消后引擎返回“任务已中断”等错误应归类为取消而非失败
                    if job_id and job_id in self._cancel_flags:
                        raise _JobCancelled from exc
                    errors.append(exc)
                    abort.set()
                    return
                if len(results) != len(unit):
                    errors.append(RuntimeError(
                        f"引擎返回音频数 {len(results)} != 请求数 {len(unit)}"))
                    abort.set()
                    return
                for (_, it), res in zip(unit, results):
                    it["path"].write_bytes(res.data)
                    it["duration"] = res.duration
                done_count += len(unit)
                self._db.update_job(
                    job_id or "",
                    progress=(ch_idx + done_count / len(items)) / total)

            def _on_submit(unit: list[tuple[int, dict]]) -> None:
                nonlocal submitted
                # 提交即按句数推进，避免长批次时进度卡在 0%
                submitted += len(unit)
                self._db.update_job(
                    job_id or "",
                    progress=(ch_idx + submitted / len(items)) / total)

            await run_windowed(units, concurrency, _run_unit, on_submit=_on_submit)
            if errors:
                raise errors[0]
        segments: list[dict] = []
        cursor = 0.0
        for it in items:
            duration = it["duration"]
            if duration is None:
                raise RuntimeError(f"分片缺失: {it['path']}")
            segments.append({"index": it["idx"] + 1, "text": it["text"], "hash": it["hash"],
                             "start": round(cursor, 3), "end": round(cursor + duration, 3)})
            cursor += duration
        self._write_chapter_audio(ch_dir, segments, rs)
        return segments

    def _write_chapter_audio(self, ch_dir: Path, segments: list[dict],
                             rs: RuntimeSettings) -> None:
        """按 segments 引用的分片重建 audio.wav/字幕并清理陈旧分片。"""
        parts_dir = ch_dir / "parts"
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

    async def regenerate_segment(self, book_id: str, chapter_id: str,
                                 index: int) -> list[dict]:
        """重新合成第 index 句（从 1 起），并重建整章音频与字幕时间轴。"""
        if self._current_job_id.get("tts"):
            raise RegenerateConflict(
                "当前有语音合成任务正在运行，请等待其结束后再重新生成单句")
        bdir = store.book_dir(self._data_dir, book_id)
        ch_dir = store.chapter_dir(self._data_dir, book_id, chapter_id)
        seg_path = ch_dir / "segments.json"
        if not seg_path.exists():
            raise FileNotFoundError("本章尚未合成，无逐句数据")
        segments = store.load_json(seg_path, [])
        seg = next((s for s in segments if s.get("index") == index), None)
        if seg is None:
            raise KeyError(f"句子不存在: {index}")
        parts_dir = ch_dir / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        # 其余分片必须完整，否则整章时间轴已失效，应整章重新合成
        for s in segments:
            if not (parts_dir / f"{s['index'] - 1:04d}_{s['hash']}.wav").exists():
                raise RegenerateConflict("本章分片不完整，请先整章重新合成")
        rs = self._settings_store.load()
        spoken = tts_normalize.normalize_for_tts(seg["text"])
        h = audio.text_hash(spoken)
        part_path = parts_dir / f"{index - 1:04d}_{h}.wav"
        ref_bytes: bytes | None = None
        if rs.tts_mode == "clone" and rs.tts_clone_ref_audio:
            ref_path = self._data_dir / rs.tts_clone_ref_audio
            if not ref_path.exists():
                raise FileNotFoundError(f"克隆参考音频不存在: {ref_path}")
            ref_bytes = ref_path.read_bytes()
        adapter = self._tts_factory(rs, self._settings)
        try:
            if ref_bytes is not None:
                res = await adapter.synthesize_clone(
                    spoken, ref_audio=ref_bytes, ref_text=rs.tts_clone_ref_text)
            else:
                res = await adapter.synthesize(
                    spoken, voice=rs.tts_speaker, instruct=rs.tts_instruct)
        finally:
            close = getattr(adapter, "aclose", None)
            if close is not None:
                await close()
        part_path.write_bytes(res.data)
        seg["hash"] = h
        # 用每个分片的真实时长重排整章时间轴，再统一重建音频/字幕
        cursor = 0.0
        for s in segments:
            part = parts_dir / f"{s['index'] - 1:04d}_{s['hash']}.wav"
            duration = audio.wav_duration(part.read_bytes())
            s["start"] = round(cursor, 3)
            cursor += duration
            s["end"] = round(cursor, 3)
        self._write_chapter_audio(ch_dir, segments, rs)
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
        """按 id 合并回全量章节列表，避免单章任务覆盖丢失其他章节。"""
        bdir = store.book_dir(self._data_dir, book_id)
        full = store.load_json(bdir / "chapters.json", {"chapters": []})["chapters"]
        by_id = {c["id"]: c for c in chapters}
        seen = set()
        updated = []
        for c in full:
            if c["id"] in by_id:
                updated.append({**c, **by_id[c["id"]]})
                seen.add(c["id"])
            else:
                updated.append(c)
        for c in chapters:
            if c["id"] not in seen:
                updated.append(c)
        store.save_json(bdir / "chapters.json", {"chapters": updated})

    async def _maybe_cancel(self, job_id: str | None = None) -> None:
        if job_id and job_id in self._cancel_flags:
            raise _JobCancelled()


class _JobCancelled(Exception):
    pass


class RegenerateConflict(RuntimeError):
    """单句重新生成与当前状态冲突（合成任务在途 / 本章分片不完整）。"""
    pass


def _rs_to_dict(rs: RuntimeSettings) -> dict:
    return {k: v for k, v in rs.__dict__.items()}


def _default_tts_factory(rs: RuntimeSettings, settings: Settings) -> TTSAdapter:
    if rs.tts_engine == "qwen_webui":
        return QwenWebUIAdapter(settings.tts_api_url, rs.tts_model)
    if rs.tts_engine == "mimo":
        from app.services.tts.mimo import MimoTTSAdapter
        return MimoTTSAdapter(settings.mimo_base_url, rs.tts_model,
                              api_key=settings.mimo_api_key, rpm=rs.tts_rpm)
    return MockTTSAdapter()


def _default_rewriter_factory(rs: RuntimeSettings, settings: Settings,
                              concurrency: int = 20) -> rewriter.Rewriter:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=settings.openai_base_url,
                         api_key=settings.openai_api_key)
    return rewriter.Rewriter(client, rs.llm_model, settings.data_dir,
                             concurrency=concurrency)
