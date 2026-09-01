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
