from pathlib import Path

import pytest

from app.services.pdf_extractor import (
    ExtractedBlock,
    blocks_to_markdown,
    extract_blocks,
    extract_meta,
    extract_toc,
)

SAMPLE = Path(__file__).resolve().parents[1].parent / "data" / "samples" / "agentic-ai-guide-zh-v1.1.0.pdf"


@pytest.mark.skipif(not SAMPLE.exists(), reason="示例 PDF 未提供")
def test_extract_meta_sample():
    meta = extract_meta(SAMPLE)
    assert meta["page_count"] >= 590
    assert meta["title"]


@pytest.mark.skipif(not SAMPLE.exists(), reason="示例 PDF 未提供")
def test_extract_toc_sample():
    toc = extract_toc(SAMPLE)
    assert len(toc) > 50
    assert toc[0]["level"] >= 1
    assert toc[0]["page"] >= 1


@pytest.mark.skipif(not SAMPLE.exists(), reason="示例 PDF 未提供")
def test_extract_blocks_page3():
    # 第 3 页是目录页，包含多个 heading/text 块
    blocks = extract_blocks(SAMPLE, 3, 3)
    assert len(blocks) > 0
    assert all(isinstance(b, ExtractedBlock) for b in blocks)
    assert any(b.text for b in blocks)


def test_blocks_to_markdown_marks_headings():
    blocks = [
        ExtractedBlock(page=1, kind="heading", text="第一章 开始", font_size=18, bold=True),
        ExtractedBlock(page=1, kind="text", text="这是正文。", font_size=12, bold=False),
        ExtractedBlock(page=1, kind="table", text="a|b\n1|2", font_size=10, bold=False),
    ]
    md = blocks_to_markdown(blocks)
    assert md.startswith("# 第一章 开始")
    assert "这是正文。" in md
    assert "a|b" in md


def test_blocks_to_markdown_skips_empty():
    assert blocks_to_markdown([]) == ""
