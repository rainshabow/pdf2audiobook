import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import pdf_extractor as pe
from app.services.pdf_extractor import (
    ExtractedBlock,
    blocks_to_markdown,
    extract_blocks,
    extract_meta,
    extract_toc,
)

SAMPLE = Path(__file__).resolve().parents[1].parent / "data" / "samples" / "agentic-ai-guide-zh-v1.1.0.pdf"


# ---------- 示例 PDF（存在时） ----------

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


@pytest.mark.skipif(not SAMPLE.exists(), reason="示例 PDF 未提供")
def test_extract_blocks_sample_strips_running_header():
    # 正文页抽取结果不得包含运行页眉 "H. Roitman…"
    blocks = extract_blocks(SAMPLE, 40, 42)
    texts = [b.text for b in blocks]
    assert texts
    assert not any("H. Roitman" in t for t in texts)
    # 页脚页码（整块纯数字）不应出现
    assert not any(re.fullmatch(r"\d+", t) for t in texts)


# ---------- blocks_to_markdown ----------

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


# ---------- 页眉/页脚/页码噪音 ----------

def test_is_noise_marks_digits_and_separators():
    assert pe._is_noise("123")
    assert pe._is_noise("— 42 —")
    assert pe._is_noise("- - -")
    assert pe._is_noise(". . . . . .")
    assert not pe._is_noise("第一章 开始")
    assert not pe._is_noise("H. Roitman—智能体AI 漫游指南：从基础到系统")
    assert not pe._is_noise("1.2.3")


def test_strip_toc_dot_leader():
    assert pe._clean_line("7.3 TRL 实现. . . . . . 173") == "7.3 TRL 实现"
    assert pe._clean_line("1.1LLM 工作原理：直觉概览. . . . . . . . . . 39") == "1.1LLM 工作原理：直觉概览"
    assert pe._clean_line("这是正文，没有点线。") == "这是正文，没有点线。"
    assert pe._clean_line(". . . . . .") == ""
    assert pe._clean_line("25") == ""


def test_in_margin_bands():
    assert pe._in_margin((179.3, 21.9, 415.5, 32.6), 841.89)  # 页眉
    assert pe._in_margin((294.8, 806.6, 300.2, 817.5), 841.89)  # 页脚页码
    assert not pe._in_margin((61.2, 125.8, 170.2, 150.6), 841.89)  # 正文
    assert not pe._in_margin((102.7, 55.5, 534.1, 139.8), 841.89)  # 目录内容


class _FakeTable:
    def __init__(self, rows, bbox):
        self._rows = rows
        self.bbox = bbox

    def extract(self):
        return self._rows


class _FakeTableFinder:
    def __init__(self, tables):
        self.tables = tables


class _FakePage:
    def __init__(self, dict_blocks, tables=(), height=841.89):
        self._blocks = dict_blocks
        self._tables = tables
        self.rect = SimpleNamespace(height=height)

    def find_tables(self):
        return _FakeTableFinder(self._tables)

    def get_text(self, mode):
        assert mode == "dict"
        return {"blocks": self._blocks}


class _FakeDoc:
    def __init__(self, pages):
        self._pages = pages
        self.page_count = len(pages)
        self.metadata = {"title": "fake", "author": ""}

    def __getitem__(self, index):
        return self._pages[index]

    def close(self):
        pass


def _text_block(bbox, text, size=10.0, bold=False):
    return {
        "type": 0,
        "bbox": bbox,
        "lines": [{"bbox": bbox, "spans": [{"text": text, "size": size, "flags": 16 if bold else 0}]}],
    }


def test_extract_blocks_drops_header_footer_and_page_number(monkeypatch):
    page = _FakePage(dict_blocks=[
        _text_block((179.3, 21.9, 415.5, 32.6), "H. Roitman—智能体AI 漫游指南：从基础到系统"),
        _text_block((61.2, 200.0, 500.0, 220.0), "这是正文内容。"),
        _text_block((294.8, 806.6, 300.2, 817.5), "10"),
    ])
    fake_doc = _FakeDoc([page])
    monkeypatch.setattr(pe.fitz, "open", lambda path: fake_doc)
    blocks = extract_blocks(Path("fake.pdf"), 1, 1)
    texts = [b.text for b in blocks]
    assert not any("H. Roitman" in t for t in texts)
    assert not any(re.fullmatch(r"\d+", t) for t in texts)
    assert any("这是正文内容" in t for t in texts)


def test_collect_running_lines_detects_repeated_margin_line(monkeypatch):
    header = _text_block((179.3, 21.9, 415.5, 32.6), "H. Roitman—智能体AI 漫游指南：从基础到系统")
    body = _text_block((61.2, 300.0, 500.0, 320.0), "正文行")
    fake_doc = _FakeDoc([_FakePage(dict_blocks=[header, body]),
                         _FakePage(dict_blocks=[header, body])])
    running = pe._collect_running_lines(fake_doc, 1, 2)
    assert ("H. Roitman—智能体AI 漫游指南：从基础到系统", 21.9) in running
    assert ("正文行", 300.0) not in running


# ---------- 表格提取 ----------

def test_extract_blocks_table_block_no_duplication(monkeypatch):
    table_bbox = (100.0, 100.0, 300.0, 200.0)
    table = _FakeTable([["h1", "h2"], ["a", "b"]], table_bbox)
    page = _FakePage(
        dict_blocks=[
            _text_block((105.0, 105.0, 150.0, 120.0), "h1"),  # 与表格相交
            _text_block((400.0, 400.0, 500.0, 420.0), "这是表格外的正文。"),
        ],
        tables=[table],
    )
    fake_doc = _FakeDoc([page])
    monkeypatch.setattr(pe.fitz, "open", lambda path: fake_doc)
    blocks = extract_blocks(Path("fake.pdf"), 1, 1)
    table_blocks = [b for b in blocks if b.kind == "table"]
    text_blocks = [b for b in blocks if b.kind == "text"]
    assert len(table_blocks) == 1
    assert "| h1 | h2 |" in table_blocks[0].text
    assert "| a | b |" in table_blocks[0].text
    # 与表格 bbox 相交的文本块被跳过（不重复）；表格外文本保留
    assert not any("h1" in b.text for b in text_blocks)
    assert any("这是表格外的正文" in b.text for b in text_blocks)
