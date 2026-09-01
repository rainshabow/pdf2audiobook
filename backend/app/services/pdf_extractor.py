import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz  # PyMuPDF（1.28+ 建议用 pymupdf 命名导入，避免 fitz 弃用警告）


@dataclass
class ExtractedBlock:
    page: int
    kind: str  # heading | text | list | table | code | image | formula
    text: str
    font_size: float = 0.0
    bold: bool = False


_HEADING_RE = re.compile(r"^(\d+(\.\d+)*[\.\s、．]|第[一二三四五六七八九十百千0-9]+[章节部篇]|[A-Z]\.\s)")
# 行尾点线 + 页码，如目录页的 "7.3 TRL 实现. . . . . . 173"
_TOC_LEADER_RE = re.compile(r"(?:\.\s*){2,}\s*\d{1,4}\s*$")
# 行尾纯点线（目录点线，页码在单独一行时）
_TRAILING_DOTS_RE = re.compile(r"(?:\.\s){2,}\.?\s*$")
# 页眉/页脚带：块起点距页面顶部 < _TOP_MARGIN，或距页面底部 < _BOTTOM_MARGIN 即视为页眉/页脚。
# 示例 PDF 页面高约 842pt：运行页眉 y≈22，页脚页码 y≈807，正文从 y≈55 开始、y≈791 结束。
_TOP_MARGIN = 45.0
_BOTTOM_MARGIN = 40.0


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
        first = max(1, page_start)
        last = min(page_end, doc.page_count)
        running_lines = _collect_running_lines(doc, first, last)
        blocks: list[ExtractedBlock] = []
        for pno in range(first, last + 1):
            page = doc[pno - 1]
            page_height = float(page.rect.height)
            table_regions = _extract_tables(page, pno, blocks)
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") == 1:  # 图片
                    blocks.append(ExtractedBlock(page=pno, kind="image",
                                                 text="[图片]", font_size=0, bold=False))
                    continue
                bbox = block.get("bbox")
                if bbox and _in_margin(bbox, page_height):
                    continue  # 页眉/页脚/页码：按 bbox 顶部/底部页边距丢弃
                if bbox and _intersects_any(bbox, table_regions):
                    continue  # 表格区域内的文本由表格块提供，避免重复
                line_texts: list[str] = []
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    text = _clean_line("".join(s["text"] for s in spans))
                    if not text:
                        continue
                    y0 = line.get("bbox", (0.0, 0.0, 0.0, 0.0))[1]
                    if (text, round(y0, 1)) in running_lines:
                        continue  # 跨页重复的相同行（运行页眉/页脚）
                    if _margin_noise(text, y0, page_height):
                        continue  # 页边距带内的数字/分隔线（页脚页码等）
                    line_texts.append(text)
                if not line_texts:
                    continue
                text = "\n".join(line_texts)
                spans = [s for line in block.get("lines", []) for s in line.get("spans", [])]
                size = max(s["size"] for s in spans)
                bold = any(s["flags"] & 16 for s in spans)  # bit 4 = bold
                kind = _classify(text, size, bold)
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


def _collect_running_lines(doc, page_start: int, page_end: int) -> set[tuple[str, float]]:
    """识别跨页重复的相同行（运行页眉/页脚）。

    同一行文本在 >=2 页的同一纵向位置重复出现，且该位置落在页边距带内，
    才视为运行页眉/页脚——正文里在相同位置重复的代码/短文本（如 ")"、"self,"）不会被误伤。
    返回 (文本, 取整 y0) 集合。
    """
    occ: dict[tuple[str, float], set[int]] = {}
    for pno in range(page_start, page_end + 1):
        page = doc[pno - 1]
        page_height = float(page.rect.height)
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") == 1:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = _clean_line("".join(s["text"] for s in spans))
                if not text:
                    continue
                y0 = line.get("bbox", (0.0, 0.0, 0.0, 0.0))[1]
                if _margin_noise(text, y0, page_height) or not _in_margin_y(y0, page_height):
                    continue
                occ.setdefault((text, round(y0, 1)), set()).add(pno)
    return {key for key, pages in occ.items() if len(pages) >= 2}


def _extract_tables(page, pno: int, blocks: list[ExtractedBlock]) -> list[tuple[float, float, float, float]]:
    """把页内 find_tables() 结果转成 markdown 表格块；返回表格 bbox 列表用于跳过重叠文本块。"""
    regions: list[tuple[float, float, float, float]] = []
    try:
        tables = page.find_tables()
    except Exception:
        return regions
    for table in tables.tables:
        md = _table_to_markdown(table.extract())
        if not md:
            continue  # 空表格：不产出表格块，也不屏蔽其 bbox 内的文本
        blocks.append(ExtractedBlock(page=pno, kind="table", text=md,
                                     font_size=0.0, bold=False))
        regions.append(tuple(table.bbox))
    return regions


def _table_to_markdown(rows) -> str:
    cells = [[str(c).replace("\n", " ").replace("|", "\\|") if c is not None else ""
              for c in row] for row in rows]
    if not cells or not cells[0]:
        return ""
    out = ["| " + " | ".join(cells[0]) + " |",
           "| " + " | ".join("---" for _ in cells[0]) + " |"]
    for row in cells[1:]:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def _in_margin(bbox, page_height: float) -> bool:
    return _in_margin_y(bbox[1], page_height)


def _in_margin_y(y0: float, page_height: float) -> bool:
    return y0 < _TOP_MARGIN or y0 > page_height - _BOTTOM_MARGIN


def _margin_noise(text: str, y0: float, page_height: float) -> bool:
    """页边距带内的数字/分隔线行（如页脚页码）视为噪音；正文中的纯数字行保留。"""
    return _in_margin_y(y0, page_height) and re.fullmatch(r"[\d\s\-—|]+", text) is not None


def _intersects_any(bbox, regions: list[tuple[float, float, float, float]]) -> bool:
    if not regions:
        return False
    x0, y0, x1, y1 = bbox
    for rx0, ry0, rx1, ry1 in regions:
        if not (x1 <= rx0 or rx1 <= x0 or y1 <= ry0 or ry1 <= y0):
            return True
    return False


def _clean_line(text: str) -> str:
    text = text.strip()
    text = _TOC_LEADER_RE.sub("", text)
    text = _TRAILING_DOTS_RE.sub("", text).rstrip()
    if not text or _is_noise(text):
        return ""
    return text


def _is_noise(text: str) -> bool:
    # 纯点线（目录点线）。数字/分隔线过滤限定到页边距带（见 _margin_noise），
    # 正文中的纯数字行（如年份 "2026"）不再被丢弃。
    return re.fullmatch(r"[.\s]+", text) is not None


def _classify(text: str, size: float, bold: bool) -> str:
    if size >= 12 and bold and _HEADING_RE.match(text):
        return "heading"
    if "|" in text:
        return "table"
    if text.startswith(("```", "def ", "class ", "import ", "const ", "function")):
        return "code"
    return "text"
