from app.services import segmenter


def test_segment_from_toc_top_level():
    toc = [
        {"level": 1, "title": "I 基础", "page": 38},
        {"level": 2, "title": "1 LLM 架构与优化方法", "page": 39},
        {"level": 2, "title": "2 分词", "page": 60},
        {"level": 1, "title": "II 进阶", "page": 90},
        {"level": 2, "title": "3 注意力机制", "page": 91},
    ]
    chapters = segmenter.segment_from_toc(toc)
    # 顶层 chapter 为基本单元：I 基础(38-89)、II 进阶(90-末)
    assert len(chapters) == 2
    assert chapters[0]["title"] == "I 基础"
    assert chapters[0]["page_start"] == 38
    assert chapters[0]["page_end"] == 89
    assert chapters[1]["page_start"] == 90


def test_adaptive_merge_small_adjacent():
    chapters = [
        {"id": "c1", "title": "A", "page_start": 1, "page_end": 5},
        {"id": "c2", "title": "B", "page_start": 6, "page_end": 10},
        {"id": "c3", "title": "C", "page_start": 11, "page_end": 30},
    ]
    counts = {"c1": 1000, "c2": 2000, "c3": 8000}
    merged = segmenter.adaptive_merge(chapters, counts, low=5000, high=15000)
    # 三个小节合计 11000 字：贪心合并直到达到下限
    assert len(merged) == 1
    assert merged[0]["title"] == "A + B + C"
    assert merged[0]["char_count"] == 11000
    assert merged[0]["page_end"] == 30


def test_adaptive_merge_no_split_when_under_high():
    chapters = [{"id": "c1", "title": "A", "page_start": 1, "page_end": 20}]
    merged = segmenter.adaptive_merge(chapters, {"c1": 12000}, low=5000, high=15000)
    assert len(merged) == 1


def test_detect_headings():
    from app.services.pdf_extractor import ExtractedBlock
    blocks = [
        ExtractedBlock(page=1, kind="heading", text="第1章 开始", font_size=16, bold=True),
        ExtractedBlock(page=1, kind="text", text="正文", font_size=12, bold=False),
        ExtractedBlock(page=2, kind="heading", text="1.1 子节", font_size=14, bold=True),
    ]
    heads = segmenter.detect_headings(blocks)
    assert heads == [(1, "第1章 开始"), (2, "1.1 子节")]


def test_split_oversize_splits_by_level2():
    chapters = [{"id": "ch-001", "title": "大章", "level": 1,
                 "page_start": 1, "page_end": 100, "char_count": 20000}]
    toc = [
        {"level": 1, "title": "大章", "page": 1},
        {"level": 2, "title": "一、小标题A", "page": 10},
        {"level": 2, "title": "二、小标题B", "page": 50},
    ]
    out = segmenter.split_oversize(chapters, toc, {"ch-001": 20000}, high=15000)
    assert len(out) == 2
    assert out[0]["id"] == "ch-001-1"
    assert out[0]["title"] == "一、小标题A"
    assert out[0]["level"] == 2
    assert out[0]["page_start"] == 1  # 首个子章节从父章节起始页开始，含引言页
    assert out[0]["page_end"] == 49
    assert out[1]["id"] == "ch-001-2"
    assert out[1]["title"] == "二、小标题B"
    assert out[1]["page_start"] == 50
    assert out[1]["page_end"] == 100


def test_split_oversize_keeps_oversize_without_level2():
    chapters = [{"id": "ch-001", "title": "大章", "level": 1,
                 "page_start": 1, "page_end": 100, "char_count": 20000}]
    toc = [{"level": 1, "title": "大章", "page": 1}]
    out = segmenter.split_oversize(chapters, toc, {"ch-001": 20000}, high=15000)
    assert len(out) == 1
    assert out[0]["id"] == "ch-001"


def test_split_oversize_keeps_under_high():
    chapters = [{"id": "ch-001", "title": "章", "level": 1,
                 "page_start": 1, "page_end": 100, "char_count": 10000}]
    toc = [{"level": 2, "title": "小节", "page": 10}]
    out = segmenter.split_oversize(chapters, toc, {"ch-001": 10000}, high=15000)
    assert len(out) == 1
    assert out[0]["id"] == "ch-001"


def test_split_oversize_merges_and_splits_in_one_pass():
    # 合并后的小章（id 含 +）不超限保持；超长大章按 level-2 拆分
    chapters = [
        {"id": "a+b", "title": "A + B", "level": 1,
         "page_start": 1, "page_end": 10, "char_count": 8000},
        {"id": "ch-002", "title": "大章", "level": 1,
         "page_start": 11, "page_end": 50, "char_count": 20000},
    ]
    toc = [{"level": 2, "title": "子节", "page": 20}]
    out = segmenter.split_oversize(chapters, toc, {"a+b": 8000, "ch-002": 20000}, high=15000)
    assert [c["id"] for c in out] == ["a+b", "ch-002-1"]


def test_number_chapters_adds_sequential_to_plain_titles():
    chapters = [
        {"id": "ch-001", "title": "引言", "level": 1},
        {"id": "ch-002", "title": "正文", "level": 1},
    ]
    out = segmenter.number_chapters(chapters)
    assert out[0]["title"] == "1. 引言"
    assert out[1]["title"] == "2. 正文"


def test_number_chapters_keeps_existing_numbers():
    chapters = [
        {"id": "ch-001", "title": "1 LLM 架构与优化方法", "level": 1},
        {"id": "ch-002", "title": "第2章 分词", "level": 1},
        {"id": "ch-003", "title": "一、引言", "level": 1},
        {"id": "ch-004", "title": "I 基础", "level": 1},
        {"id": "ch-005", "title": "全书", "level": 1},
    ]
    out = segmenter.number_chapters(chapters)
    assert out[0]["title"] == "1 LLM 架构与优化方法"
    assert out[1]["title"] == "第2章 分词"
    assert out[2]["title"] == "一、引言"
    assert out[3]["title"] == "I 基础"
    assert out[4]["title"] == "5. 全书"


def test_number_chapters_prefixes_subsections_with_parent_dot_sub():
    chapters = [
        {"id": "ch-001", "title": "大章", "level": 1},
        {"id": "ch-001-1", "title": "子节A", "level": 2},
        {"id": "ch-001-2", "title": "子节B", "level": 2},
        {"id": "ch-002", "title": "下一章", "level": 1},
        {"id": "ch-002-1", "title": "子节C", "level": 2},
    ]
    out = segmenter.number_chapters(chapters)
    assert out[0]["title"] == "1. 大章"
    assert out[1]["title"] == "1.1 子节A"
    assert out[2]["title"] == "1.2 子节B"
    assert out[3]["title"] == "2. 下一章"
    assert out[4]["title"] == "2.1 子节C"


def test_number_chapters_handles_merged_title():
    chapters = [{"id": "ch-001+ch-002", "title": "A + B", "level": 1}]
    out = segmenter.number_chapters(chapters)
    assert out[0]["title"] == "1. A + B"


def test_number_chapters_uses_printed_page_title_match():
    chapters = [{"id": "ch-007-9", "title": "LLM 智能体训练", "level": 2,
                 "page_start": 220, "page_end": 247, "anchor_page": 220}]
    printed = [{"number": "12", "title": "LLM 智能体训练", "page": 220}]
    out = segmenter.number_chapters(chapters, printed)
    assert out[0]["title"] == "12 LLM 智能体训练"


def test_number_chapters_title_only_match_does_not_override_numbered():
    chapters = [{"id": "ch-006-1", "title": "LLM 架构与优化方法", "level": 2,
                 "page_start": 38, "page_end": 106, "anchor_page": 39}]
    printed = [{"number": "1", "title": "LLM 架构与优化方法", "page": 999}]
    out = segmenter.number_chapters(chapters, printed)
    assert out[0]["title"] == "1 LLM 架构与优化方法"


def test_number_chapters_keeps_numbered_without_print_match():
    chapters = [{"id": "ch-006-2", "title": "2.2 面向 LLM 的系统基础", "level": 2,
                 "page_start": 107, "anchor_page": 107}]
    out = segmenter.number_chapters(chapters, [])
    assert out[0]["title"] == "2.2 面向 LLM 的系统基础"
