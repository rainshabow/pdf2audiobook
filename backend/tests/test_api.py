import io
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
    doc.new_page().insert_text((72, 72), "第一章 开始", fontsize=18)
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
    # 上传文件被保存为 source.pdf，extract_meta 无标题时回退为文件名 stem
    assert r.json()["title"] == "source"


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
