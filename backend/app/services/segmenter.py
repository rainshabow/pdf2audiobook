import re
from pathlib import Path

from app.services import pdf_extractor
from app.store import new_book_id

_CHAPTER_PREFIX_RE = re.compile(r"^(第[一二三四五六七八九十百千0-9]+[章节部篇]|\d+(\.\d+)*\s)")

_ALREADY_NUMBERED_RE = re.compile(
    r"^(\d+(\.\d+)*[\s、．.]|第[一二三四五六七八九十百千0-9]+[章节部篇]|"
    r"[一二三四五六七八九十百千]+[、．.\s]|"
    r"(?=[IVXLCDM])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})[\s、．.])"
)

_SUB_ID_RE = re.compile(r"^ch-\d{3}([+]ch-\d{3})*-\d+$")


def segment_from_toc(toc: list[dict], page_count: int | None = None) -> list[dict]:
    """以顶层章节为基本单元；顶层之间自动补页范围。"""
    if not toc:
        return []
    top_level = min(e["level"] for e in toc)
    top = [e for e in toc if e["level"] == top_level]
    chapters: list[dict] = []
    for i, entry in enumerate(top):
        page_end = (top[i + 1]["page"] - 1) if i + 1 < len(top) else (page_count or 10**6)
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
    """合并过小相邻章节；超过 high 的章节留给 split_oversize 按二级标题拆分。"""
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


def split_oversize(chapters: list[dict], toc: list[dict], char_counts: dict[str, int],
                   high: int) -> list[dict]:
    """把超过 high 上限的章节按 TOC 二级标题拆分为子章节（递归一次）。

    无 level-2 条目的超长章节保持原样；子章节 id 用 `父id-序号`（如 ch-001-1），
    首个二级标题前的章首/引言页归属第一个子章节（page_start 取父章节起始页），
    char_count 由调用方按新范围重新提取。
    """
    out: list[dict] = []
    for ch in chapters:
        count = int(char_counts.get(ch["id"], ch.get("char_count", 0)))
        ch["char_count"] = count
        if count <= high:
            out.append(ch)
            continue
        sub_titles = sorted(
            (e for e in toc
             if e["level"] == 2 and ch["page_start"] <= e["page"] <= ch["page_end"]),
            key=lambda e: e["page"],
        )
        if not sub_titles:
            out.append(ch)  # 无 level-2 条目：不拆分，保持原样
            continue
        for i, entry in enumerate(sub_titles):
            page_end = (sub_titles[i + 1]["page"] - 1
                        if i + 1 < len(sub_titles) else ch["page_end"])
            # 首个二级标题前的章首/引言页归属第一个子章节，避免内容丢失
            page_start = ch["page_start"] if i == 0 else entry["page"]
            out.append({
                "id": f"{ch['id']}-{i + 1}",
                "title": entry["title"].strip(),
                "level": 2,
                "page_start": page_start,
                "page_end": page_end,
                "char_count": 0,
                "anchor_page": entry["page"],  # 标题锚点页（用于与印刷目录编号对齐）
            })
    return out


def build_candidates(pdf_path: Path, meta: dict) -> list[dict]:
    """TOC 优先；无 TOC 时用字号检测兜底（返回单一大章节）。"""
    toc = pdf_extractor.extract_toc(pdf_path)
    if toc:
        return segment_from_toc(toc, page_count=meta["page_count"])
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



def number_chapters(chapters: list[dict], printed_toc: list[dict] | None = None) -> list[dict]:
    """为章节标题补充序号/章节号（就地修改 title）。

    - 顶层章节：按顺序补 `N. ` 前缀；标题已含编号（`1. `、`1.1 `、`第N章/节/部/篇`、
      `一、`、罗马数字等）则保留原编号。
    - 子章节（id 含 `-`，来自超长章节拆分）：补 `父序号.子序号 ` 前缀。
    """
    printed_by_page_title: dict[tuple[int, str], str] = {}
    printed_by_title: dict[str, str] = {}
    for e in printed_toc or []:
        tkey = (e.get("title") or "").replace(" ", "").replace("\u3000", "")
        if not tkey:
            continue
        num = e.get("number")
        pg = e.get("page")
        if pg is not None and num and (pg, tkey) not in printed_by_page_title:
            printed_by_page_title[(pg, tkey)] = num
        if num and tkey not in printed_by_title:
            printed_by_title[tkey] = num

    def norm(s: str) -> str:
        return s.replace(" ", "").replace("\u3000", "")

    top_no = 0
    for ch in chapters:
        title = ch.get("title", "").strip()
        cid = str(ch.get("id", ""))
        is_sub = bool(_SUB_ID_RE.match(cid))
        if not is_sub:
            top_no += 1  # 顶层章节计数与是否已编号无关
        anchor = int(ch.get("anchor_page", ch.get("page_start", 0)) or 0)
        nkey = norm(title)
        # 页码+标题双重匹配：印刷目录权威，可覆盖已编号标题
        printed_no = printed_by_page_title.get((anchor, nkey))
        if not printed_no:
            printed_no = printed_by_title.get(nkey)
            if printed_no and _ALREADY_NUMBERED_RE.match(title):
                printed_no = None  # 仅标题匹配时不覆盖已有编号
        if printed_no:
            ch["title"] = f"{printed_no} {title}"
            continue
        if title and _ALREADY_NUMBERED_RE.match(title):
            continue
        # 子章节 id 形如 ch-001-1 / ch-001+ch-002-1（父 id 合法 + '-数字' 结尾）
        if is_sub:
            sub = cid.rsplit("-", 1)[1]
            sub_no = int(sub) if sub.isdigit() else 0
            prefix = f"{top_no}.{sub_no}"  # top_no 此时已是父章节序号
            if title:
                ch["title"] = f"{prefix} {title}"
        else:
            if title:
                ch["title"] = f"{top_no}. {title}"
    return chapters

def _chapter_id(idx: int) -> str:
    return f"ch-{idx:03d}"
