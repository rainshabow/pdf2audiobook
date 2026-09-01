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
        await on_progress(0.0)
        for i, sec in enumerate(sections):
            h = _hash(sec)
            cached = None if h not in done else _try_load_done(ch_dir, h)
            if cached is not None:
                outputs.append(cached)
                await on_progress((i + 1) / total)
                continue
            done.discard(h)  # 缓存缺失/为空视为未完成，重新生成
            result = await self._call_llm(sec)
            _save_done(ch_dir, h, result)
            done.add(h)
            outputs.append(result)
            store.save_json(checkpoint_path, {"done": sorted(done)})
            await on_progress((i + 1) / total)
        (ch_dir / "speech.md").write_text(_join(outputs), encoding="utf-8")
        if total == 0:
            await on_progress(1.0)

    async def _call_llm(self, section: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"原文：\n```text\n{section}\n```"},
            ],
            temperature=0.3,
        )
        content = resp.choices[0].message.content or ""
        if not content.strip():
            raise RuntimeError("LLM 返回空结果")
        return content


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _save_done(ch_dir: Path, h: str, text: str) -> None:
    ch_dir.mkdir(parents=True, exist_ok=True)
    (ch_dir / f".rewrite_{h}.md").write_text(text, encoding="utf-8")


def _try_load_done(ch_dir: Path, h: str) -> str | None:
    try:
        text = (ch_dir / f".rewrite_{h}.md").read_text(encoding="utf-8")
    except OSError:
        return None
    return text or None


def _join(parts: list[str]) -> str:
    return "\n\n".join(p.strip() for p in parts if p.strip())
