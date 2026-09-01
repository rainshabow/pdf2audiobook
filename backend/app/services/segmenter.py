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
