import io
import json
from pathlib import Path

import fitz
import httpx
import pytest
import pytest_asyncio

from app import store
from app.config import Settings
from app.main import create_app


def _tiny_pdf_bytes() -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "第一章 开始", fontsize=18, fontname='china-s')
    doc.set_toc([[1, "第一章 开始", 1]])
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


@pytest_asyncio.fixture()
async def client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    # httpx ASGITransport 不会驱动 lifespan，这里手动进入以启动/停止 JobManager worker
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as c:
            c.app = app  # 便于测试访问 app.state
            yield c


@pytest.mark.asyncio
async def test_upload_list_detail(client):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    assert r.status_code == 200
    book = r.json()
    assert book["book_id"]
    assert book["status"] == "uploaded"
    r = await client.get("/api/books")
    assert len(r.json()) == 1
    r = await client.get(f"/api/books/{book['book_id']}")
    # 上传文件被保存为 source.pdf，但 title 回退用原始文件名 stem（"book"）
    assert r.json()["title"] == "book"
    assert r.json()["created_at"] != ""


@pytest.mark.asyncio
async def test_parse_then_edit_then_rebuild(client, tmp_path):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    r = await client.post(f"/api/books/{book['book_id']}/parse")
    assert r.status_code == 200
    job_id = r.json()["id"]
    await _wait(client, job_id)
    detail = (await client.get(f"/api/books/{book['book_id']}")).json()
    assert detail["status"] == "parsed"
    assert detail["title"] == "book"  # 解析后仍保留原始文件名标题
    assert len(detail["chapters"]) == 1
    ch = detail["chapters"][0]["id"]
    # 编辑 speech.md
    r = await client.put(
        f"/api/books/{book['book_id']}/chapters/{ch}/speech.md",
        content="第一句。\n\n第二句。", headers={"Content-Type": "text/plain"})
    assert r.status_code == 200
    got = await client.get(f"/api/books/{book['book_id']}/chapters/{ch}/speech.md")
    assert "第一句" in got.text
    # 重建（mock 引擎）
    r = await client.post(f"/api/books/{book['book_id']}/chapters/{ch}/rebuild")
    job_id = r.json()["id"]
    await _wait(client, job_id)
    ch_dir = store.chapter_dir(tmp_path, book["book_id"], ch)
    assert (ch_dir / "audio.wav").exists()
    assert (ch_dir / "chapter.vtt").exists()
    r = await client.get(f"/api/books/{book['book_id']}/chapters/{ch}/audio")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")


@pytest.mark.asyncio
async def test_settings_and_tts_lists(client):
    r = await client.get("/api/settings")
    assert r.json()["tts_engine"] == "mock"
    r = await client.put("/api/settings", json={"tts_engine": "mock",
                                                "tts_model": "m", "tts_speed": 1.5})
    assert r.status_code == 200
    r = await client.get("/api/tts/models")
    assert r.json()[0]["name"] == "mock-voice"
    r = await client.get("/api/tts/speakers")
    assert r.json()[0]["name"] == "测试音色"


@pytest.mark.asyncio
async def test_delete_book(client, tmp_path):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    r = await client.delete(f"/api/books/{book['book_id']}")
    assert r.status_code == 200
    assert not store.book_dir(tmp_path, book["book_id"]).exists()


@pytest.mark.asyncio
async def test_bad_upload_and_missing_resources(client, tmp_path):
    # 非 PDF 文件名 → 400，且不污染列表
    r = await client.post("/api/books", files={
        "file": ("bad.txt", b"not a pdf", "text/plain")})
    assert r.status_code == 400
    # 伪造 .pdf（内容非 PDF）→ 400，失败路径清理，不产生孤儿目录
    r = await client.post("/api/books", files={
        "file": ("fake.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 400
    assert (await client.get("/api/books")).json() == []
    assert list((tmp_path / "books").iterdir()) == []
    # 正常上传后：不存在章节的 audio / chapter.vtt → 404
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    r = await client.get(f"/api/books/{book['book_id']}/chapters/ghost/audio")
    assert r.status_code == 404
    r = await client.get(f"/api/books/{book['book_id']}/chapters/ghost/chapter.vtt")
    assert r.status_code == 404
    # 不存在书籍的 speech.md PUT → 404，且不产生书籍目录
    r = await client.put("/api/books/nope/chapters/x/speech.md",
                         content="x", headers={"Content-Type": "text/plain"})
    assert r.status_code == 404
    assert not store.book_dir(tmp_path, "nope").exists()
    # cancel 不存在任务 → 404
    r = await client.post("/api/jobs/nope/cancel")
    assert r.status_code == 404


async def _wait(client, job_id: str, timeout: float = 30.0):
    import asyncio
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get("/api/jobs")
        job = next((j for j in r.json() if j["id"] == job_id), None)
        if job and job["status"] in ("done", "failed", "cancelled"):
            assert job["status"] == "done", job
            return
        await asyncio.sleep(0.05)
    raise AssertionError("任务超时")

@pytest.mark.asyncio
async def test_traversal_ids_rejected(client, tmp_path):
    """非法 book_id/chapter_id 在端点入口被 validate_id 拒绝，且不产生/不读取越界文件。"""
    before = {p.name for p in tmp_path.iterdir()}
    # 白名单外的 ID（Windows 反斜杠穿越、编码点号、点号）→ 400
    for url in [
        "/api/books/..%5C..%5Cetc",
        "/api/books/..%2E%2E%5Cetc",
        "/api/books/..\\..\\etc",
        "/api/books/a%2Eb",
    ]:
        r = await client.get(url)
        assert r.status_code == 400, (url, r.text)
        assert r.json()["detail"] == "非法 ID"
    # PUT speech.md 的 book_id 穿越 → 400
    r = await client.put("/api/books/..%5C..%5Cetc/chapters/x/speech.md",
                         content="x", headers={"Content-Type": "text/plain"})
    assert r.status_code == 400
    # chapter_id 穿越（audio / speech.md）→ 400
    for url in [
        "/api/books/b1/chapters/..%5C..%5Cmeta.json/audio",
        "/api/books/b1/chapters/..%2E%2E%5Cmeta.json/speech.md",
    ]:
        r = await client.get(url)
        assert r.status_code == 400, (url, r.text)
    # %2F 与裸 .. 会被 httpx/Starlette 在路由层规范化拦截（404），同样不得越界
    for url in [
        "/api/books/..",
        "/api/books/..%2F..%2Fetc",
        "/api/books/b1/chapters/..%2F..%2Fmeta.json/audio",
    ]:
        r = await client.get(url)
        assert r.status_code in (400, 404), (url, r.text)
    # 未产生/未读取越界文件：data 目录内容不变，books 下无任何书籍目录
    assert {p.name for p in tmp_path.iterdir()} == before
    assert list((tmp_path / "books").iterdir()) == []
    assert not store.book_dir(tmp_path, "b1").exists()


@pytest.mark.asyncio
async def test_rewrite_synthesize_require_parse(client):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    # 未解析时 rewrite / synthesize → 400 "请先解析章节"
    for ep in ("rewrite", "synthesize"):
        r = await client.post(f"/api/books/{book['book_id']}/{ep}")
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "请先解析章节"


@pytest.mark.asyncio
async def test_rebuild_unknown_chapter_404(client):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    r = await client.post(f"/api/books/{book['book_id']}/chapters/ghost/rebuild")
    assert r.status_code == 404
    assert r.json()["detail"] == "章节不存在"


@pytest.mark.asyncio
async def test_get_speech_missing_book_404(client):
    r = await client.get("/api/books/nope/chapters/x/speech.md")
    assert r.status_code == 404
    assert r.json()["detail"] == "书籍不存在"


@pytest.mark.asyncio
async def test_list_books_sorted_by_created_at_desc(client, tmp_path):
    import asyncio
    r = await client.post("/api/books", files={
        "file": ("a.pdf", _tiny_pdf_bytes(), "application/pdf")})
    first = r.json()["book_id"]
    await asyncio.sleep(0.01)
    r = await client.post("/api/books", files={
        "file": ("b.pdf", _tiny_pdf_bytes(), "application/pdf")})
    second = r.json()["book_id"]
    books = (await client.get("/api/books")).json()
    assert [b["book_id"] for b in books] == [second, first]
    # 无 created_at 的旧书籍排在最后
    old = store.book_dir(tmp_path, "old")
    old.mkdir(parents=True)
    store.save_json(old / "meta.json", {"book_id": "old", "title": "旧书",
                                        "author": "", "page_count": 1})
    books = (await client.get("/api/books")).json()
    assert [b["book_id"] for b in books] == [second, first, "old"]




@pytest.mark.asyncio
async def test_tts_adapter_closed_after_lists(tmp_path):
    from app.config import Settings
    from app.main import create_app

    class _Adapter:
        def __init__(self) -> None:
            self.closed = 0

        async def list_models(self) -> list[dict]:
            return [{"name": "m", "type": "custom"}]

        async def list_speakers(self) -> list[dict]:
            return [{"name": "s"}]

        async def aclose(self) -> None:
            self.closed += 1

    adapter = _Adapter()
    app = create_app(Settings(data_dir=tmp_path))
    async with app.router.lifespan_context(app):
        app.state.build_tts_adapter = lambda: adapter
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as c:
            assert (await c.get("/api/tts/models")).status_code == 200
            assert (await c.get("/api/tts/speakers")).status_code == 200
    assert adapter.closed == 2


@pytest.mark.asyncio
async def test_rewrite_chapter_endpoint(client, tmp_path):
    """按章节改写：返回 rewrite 任务（chapter_id 正确），可单章完成。"""
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    jid = (await client.post(f"/api/books/{book['book_id']}/parse")).json()["id"]
    await _wait(client, jid)
    detail = (await client.get(f"/api/books/{book['book_id']}")).json()
    ch = detail["chapters"][0]["id"]

    class _FakeRewriter:
        def __init__(self, data_dir):
            self.data_dir = data_dir

        async def rewrite_chapter(self, book_id, chapter, on_progress):
            await on_progress(0.0)
            ch_dir = store.chapter_dir(self.data_dir, book_id, chapter["id"])
            ch_dir.mkdir(parents=True, exist_ok=True)
            (ch_dir / "speech.md").write_text("口语化结果", encoding="utf-8")
            await on_progress(1.0)

    client.app.state.job_manager._rewriter_factory = lambda rs, s, concurrency=20: _FakeRewriter(tmp_path)
    r = await client.post(f"/api/books/{book['book_id']}/chapters/{ch}/rewrite")
    assert r.status_code == 200
    job = r.json()
    assert job["type"] == "rewrite"
    assert job["chapter_id"] == ch
    await _wait(client, job["id"])
    assert (tmp_path / "books" / book["book_id"] / "chapters" / ch / "speech.md").exists()


@pytest.mark.asyncio
async def test_rewrite_unknown_chapter_404(client):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    jid = (await client.post(f"/api/books/{book['book_id']}/parse")).json()["id"]
    await _wait(client, jid)
    r = await client.post(f"/api/books/{book['book_id']}/chapters/ch-999/rewrite")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_source_md(client, tmp_path):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    jid = (await client.post(f"/api/books/{book['book_id']}/parse")).json()["id"]
    await _wait(client, jid)
    detail = (await client.get(f"/api/books/{book['book_id']}")).json()
    ch = detail["chapters"][0]["id"]
    r = await client.get(f"/api/books/{book['book_id']}/chapters/{ch}/source.md")
    assert r.status_code == 200
    assert "第一章 开始" in r.text
    r = await client.get(f"/api/books/{book['book_id']}/chapters/ch-999/source.md")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_synthesize_chapter_endpoint(client, tmp_path):
    """分章合成：POST /chapters/{ch}/synthesize → 任务完成 → audio.wav 生成。"""
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    jid = (await client.post(f"/api/books/{book['book_id']}/parse")).json()["id"]
    await _wait(client, jid)
    detail = (await client.get(f"/api/books/{book['book_id']}")).json()
    ch = detail["chapters"][0]["id"]
    await client.put(
        f"/api/books/{book['book_id']}/chapters/{ch}/speech.md",
        content="第一句。\n\n第二句。", headers={"Content-Type": "text/plain"})
    r = await client.post(f"/api/books/{book['book_id']}/chapters/{ch}/synthesize")
    assert r.status_code == 200
    job = r.json()
    assert job["type"] == "synthesize"
    assert job["chapter_id"] == ch
    await _wait(client, job["id"])
    ch_dir = store.chapter_dir(tmp_path, book["book_id"], ch)
    assert (ch_dir / "audio.wav").exists()
    # 未知章节 404
    r = await client.post(f"/api/books/{book['book_id']}/chapters/ch-999/synthesize")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_rewrite_concurrency_param(client, tmp_path):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    jid = (await client.post(f"/api/books/{book['book_id']}/parse")).json()["id"]
    await _wait(client, jid)
    detail = (await client.get(f"/api/books/{book['book_id']}")).json()
    ch = detail["chapters"][0]["id"]

    class _FakeRewriter:
        async def rewrite_chapter(self, book_id, chapter, on_progress):
            ch_dir = store.chapter_dir(tmp_path, book_id, chapter["id"])
            ch_dir.mkdir(parents=True, exist_ok=True)
            (ch_dir / "speech.md").write_text("结果", encoding="utf-8")
            await on_progress(1.0)

    client.app.state.job_manager._rewriter_factory = lambda rs, s, concurrency=20: _FakeRewriter()
    r = await client.post(f"/api/books/{book['book_id']}/chapters/{ch}/rewrite?concurrency=5")
    assert r.status_code == 200
    job = r.json()
    assert job["type"] == "rewrite"
    snap = client.app.state.job_manager.get_job(job["id"])["settings_snapshot"]
    assert json.loads(snap)["rewrite_concurrency"] == 5
    await _wait(client, job["id"])


@pytest.mark.asyncio
async def test_upload_clone_audio_and_settings_fields(client, tmp_path):
    r = await client.post("/api/settings/clone-audio",
                          files={"file": ("ref.wav", b"RIFF-fake", "audio/wav")})
    assert r.status_code == 200
    assert (tmp_path / "clone_ref_audio.wav").exists()
    r = await client.get("/api/settings")
    s = r.json()
    assert s["tts_mode"] == "custom"
    assert s["rewrite_concurrency"] == 20
    assert s["tts_batch_size"] == 10
    r = await client.put("/api/settings", json={
        **s, "tts_mode": "clone", "tts_clone_ref_audio": "clone_ref_audio.wav",
        "rewrite_concurrency": 8, "tts_batch_size": 5, "tts_speed": 1.25})
    assert r.status_code == 200
    got = (await client.get("/api/settings")).json()
    assert got["tts_mode"] == "clone"
    assert got["tts_clone_ref_audio"] == "clone_ref_audio.wav"
    assert got["rewrite_concurrency"] == 8
    assert got["tts_batch_size"] == 5


@pytest.mark.asyncio
async def test_restore_chapter_to_source(client, tmp_path):
    r = await client.post("/api/books", files={
        "file": ("book.pdf", _tiny_pdf_bytes(), "application/pdf")})
    book = r.json()
    jid = (await client.post(f"/api/books/{book['book_id']}/parse")).json()["id"]
    await _wait(client, jid)
    detail = (await client.get(f"/api/books/{book['book_id']}")).json()
    ch = detail["chapters"][0]["id"]
    src = (await client.get(
        f"/api/books/{book['book_id']}/chapters/{ch}/source.md")).text
    # 先写入修改后的 speech.md
    await client.put(f"/api/books/{book['book_id']}/chapters/{ch}/speech.md",
                     content="人工修改后的文本", headers={"Content-Type": "text/plain"})
    r = await client.post(f"/api/books/{book['book_id']}/chapters/{ch}/restore")
    assert r.status_code == 200
    sp = (await client.get(
        f"/api/books/{book['book_id']}/chapters/{ch}/speech.md")).text
    assert sp == src  # 已还原为原文
    prev = (tmp_path / "books" / book["book_id"] / "chapters" / ch / "speech.previous.md")
    assert prev.exists()
    assert "人工修改后的文本" in prev.read_text(encoding="utf-8")
    # 未解析书籍 → 404
    r = await client.post("/api/books/nonexistent/chapters/ch-001/restore")
    assert r.status_code == 404
