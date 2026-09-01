import pytest
from openai import AsyncOpenAI

from app.services import rewriter


def test_split_sections_respects_max_chars():
    text = "第一节。\n" + "长" * 3000 + "。\n第二节内容。"
    sections = rewriter.Rewriter.split_sections(text, max_chars=1000)
    assert len(sections) >= 2
    assert all(len(s) <= 1200 for s in sections)  # 允许少量溢出


def test_split_sections_keeps_all_content():
    text = "A。" * 50
    joined = "".join(rewriter.Rewriter.split_sections(text, max_chars=100))
    assert joined.replace("。", "") == "A" * 50


def test_system_prompt_contains_fidelity_rules():
    assert "高保真" in rewriter.SYSTEM_PROMPT
    assert "表格" in rewriter.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_rewrite_chapter_uses_client_and_writes_files(data_dir, monkeypatch):
    from app import store
    ch_dir = store.chapter_dir(data_dir, "b1", "ch-001")
    ch_dir.mkdir(parents=True)
    (ch_dir / "source.md").write_text("表格：A|B\n1|2\n", encoding="utf-8")
    chapter = {"id": "ch-001", "title": "测试章", "page_start": 1, "page_end": 2}

    class FakeCompletions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return type("R", (), {"choices": [type("C", (), {"message": type(
                "M", (), {"content": "口语化结果"})()})]})()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    fake = FakeClient()
    rw = rewriter.Rewriter(fake, "dsv4-flash", data_dir)  # type: ignore[arg-type]
    progress = []

    async def on_progress(p):
        progress.append(p)

    await rw.rewrite_chapter("b1", chapter, on_progress)
    assert (ch_dir / "speech.md").exists()
    assert "口语化结果" in (ch_dir / "speech.md").read_text(encoding="utf-8")
    cp = store.load_json(ch_dir / "rewrite_checkpoint.json", {})
    assert cp["done"]  # 非空
    assert progress[0] == 0.0
    assert progress[-1] == 1.0
    kwargs = fake.chat.completions.calls[0]
    assert kwargs["model"] == "dsv4-flash"
    assert kwargs["temperature"] == 0.3
    roles = [m["role"] for m in kwargs["messages"]]
    assert roles == ["system", "user"]
    assert kwargs["messages"][0]["content"] == rewriter.SYSTEM_PROMPT
    assert "表格：A|B" in kwargs["messages"][1]["content"]


@pytest.mark.asyncio
async def test_rewrite_chapter_resumes_from_checkpoint(data_dir):
    import hashlib

    from app import store
    ch_dir = store.chapter_dir(data_dir, "b1", "ch-002")
    ch_dir.mkdir(parents=True)
    src = "甲。" * 1300 + "\n\n" + "乙。" * 1300  # 两段超长，必然切成多段且内容互异
    sections = rewriter.Rewriter.split_sections(src)
    assert len(sections) >= 2
    h0 = hashlib.sha256(sections[0].encode("utf-8")).hexdigest()[:16]
    (ch_dir / f".rewrite_{h0}.md").write_text("已改写第一段", encoding="utf-8")
    store.save_json(ch_dir / "rewrite_checkpoint.json", {"done": [h0]})
    (ch_dir / "source.md").write_text(src, encoding="utf-8")

    class FakeCompletions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return type("R", (), {"choices": [type("C", (), {"message": type(
                "M", (), {"content": "改写后续段"})()})]})()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    fake = FakeClient()
    rw = rewriter.Rewriter(fake, "dsv4-flash", data_dir)  # type: ignore[arg-type]

    async def noop(p):
        pass

    await rw.rewrite_chapter("b1", {"id": "ch-002"}, noop)
    text = (ch_dir / "speech.md").read_text(encoding="utf-8")
    assert "已改写第一段" in text
    assert "改写后续段" in text
    assert len(fake.chat.completions.calls) == len(sections) - 1  # 只调用未完成段


@pytest.mark.asyncio
async def test_rewrite_chapter_missing_source_raises(data_dir):
    rw = rewriter.Rewriter(None, "dsv4-flash", data_dir)  # type: ignore[arg-type]

    async def noop(p):
        pass

    with pytest.raises(FileNotFoundError):
        await rw.rewrite_chapter("b1", {"id": "ch-missing"}, noop)


@pytest.mark.asyncio
async def test_rewrite_chapter_empty_llm_result_raises_and_not_cached(data_dir):
    from app import store
    ch_dir = store.chapter_dir(data_dir, "b1", "ch-003")
    ch_dir.mkdir(parents=True)
    (ch_dir / "source.md").write_text("内容。\n", encoding="utf-8")

    class FakeCompletions:
        async def create(self, **kwargs):
            return type("R", (), {"choices": [type("C", (), {"message": type(
                "M", (), {"content": ""})()})]})()
    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()
    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    rw = rewriter.Rewriter(FakeClient(), "dsv4-flash", data_dir)  # type: ignore[arg-type]

    async def noop(p):
        pass

    with pytest.raises(RuntimeError, match="空结果"):
        await rw.rewrite_chapter("b1", {"id": "ch-003"}, noop)
    assert not (ch_dir / "rewrite_checkpoint.json").exists()  # 空结果不写 checkpoint
    assert not list(ch_dir.glob(".rewrite_*.md"))  # 空结果不写缓存
    assert not (ch_dir / "speech.md").exists()  # 任务失败，不产出 speech.md


@pytest.mark.asyncio
async def test_rewrite_chapter_empty_source_reports_full_progress(data_dir):
    from app import store
    ch_dir = store.chapter_dir(data_dir, "b1", "ch-004")
    ch_dir.mkdir(parents=True)
    (ch_dir / "source.md").write_text("", encoding="utf-8")

    rw = rewriter.Rewriter(None, "dsv4-flash", data_dir)  # type: ignore[arg-type]
    progress = []

    async def on_progress(p):
        progress.append(p)

    await rw.rewrite_chapter("b1", {"id": "ch-004"}, on_progress)
    assert progress == [0.0, 1.0]
    assert (ch_dir / "speech.md").read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
async def test_rewrite_chapter_resume_with_missing_cache_regenerates(data_dir):
    import hashlib

    from app import store
    ch_dir = store.chapter_dir(data_dir, "b1", "ch-005")
    ch_dir.mkdir(parents=True)
    src = "甲。" * 1300 + "\n\n" + "乙。" * 1300
    sections = rewriter.Rewriter.split_sections(src)
    h0 = hashlib.sha256(sections[0].encode("utf-8")).hexdigest()[:16]
    store.save_json(ch_dir / "rewrite_checkpoint.json", {"done": [h0]})  # 缓存文件缺失
    (ch_dir / "source.md").write_text(src, encoding="utf-8")

    class FakeCompletions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return type("R", (), {"choices": [type("C", (), {"message": type(
                "M", (), {"content": "重写结果"})()})]})()
    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()
    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    fake = FakeClient()
    rw = rewriter.Rewriter(fake, "dsv4-flash", data_dir)  # type: ignore[arg-type]

    async def noop(p):
        pass

    await rw.rewrite_chapter("b1", {"id": "ch-005"}, noop)
    assert len(fake.chat.completions.calls) == len(sections)  # 缺缓存段被重新生成
    text = (ch_dir / "speech.md").read_text(encoding="utf-8")
    assert text.count("重写结果") == len(sections)

