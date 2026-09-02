from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse

from app import store
from app.models import JobInfo

router = APIRouter()


def _validate_id(book_id: str) -> str:
    try:
        return store.validate_id(book_id)
    except ValueError:
        raise HTTPException(400, "非法 ID") from None


@router.get("/{chapter_id}/speech.md")
async def get_speech(request: Request, book_id: str, chapter_id: str):
    data_dir = _data_dir(request)
    book_id = _validate_id(book_id)
    chapter_id = _validate_id(chapter_id)
    if not store.book_dir(data_dir, book_id).exists():
        raise HTTPException(404, "书籍不存在")
    path = store.chapter_dir(data_dir, book_id, chapter_id) / "speech.md"
    if not path.exists():
        return PlainTextResponse("", media_type="text/markdown; charset=utf-8")
    return PlainTextResponse(path.read_text(encoding="utf-8"),
                             media_type="text/markdown; charset=utf-8")


@router.get("/{chapter_id}/source.md")
async def get_source(request: Request, book_id: str, chapter_id: str):
    data_dir = _data_dir(request)
    book_id = _validate_id(book_id)
    chapter_id = _validate_id(chapter_id)
    if not store.book_dir(data_dir, book_id).exists():
        raise HTTPException(404, "书籍不存在")
    path = store.chapter_dir(data_dir, book_id, chapter_id) / "source.md"
    if not path.exists():
        raise HTTPException(404, "原始文本不存在，请先解析")
    return PlainTextResponse(path.read_text(encoding="utf-8"),
                             media_type="text/markdown; charset=utf-8")


@router.put("/{chapter_id}/speech.md")
async def save_speech(request: Request, book_id: str, chapter_id: str):
    data_dir = _data_dir(request)
    book_id = _validate_id(book_id)
    chapter_id = _validate_id(chapter_id)
    if not store.book_dir(data_dir, book_id).exists():
        raise HTTPException(404, "书籍不存在")
    body = (await request.body()).decode("utf-8")
    ch_dir = store.chapter_dir(data_dir, book_id, chapter_id)
    ch_dir.mkdir(parents=True, exist_ok=True)
    speech_path = ch_dir / "speech.md"
    if speech_path.exists():
        (ch_dir / "speech.previous.md").write_text(
            speech_path.read_text(encoding="utf-8"), encoding="utf-8")
    speech_path.write_text(body, encoding="utf-8")
    return {"ok": True}


@router.post("/{chapter_id}/restore")
async def restore_chapter(request: Request, book_id: str, chapter_id: str):
    """把 speech.md 还原为最初的原文 source.md（还原前自动备份当前文本）。"""
    data_dir = _data_dir(request)
    book_id = _validate_id(book_id)
    chapter_id = _validate_id(chapter_id)
    ch_dir = store.chapter_dir(data_dir, book_id, chapter_id)
    if not store.book_dir(data_dir, book_id).exists():
        raise HTTPException(404, "书籍不存在")
    source_path = ch_dir / "source.md"
    if not source_path.exists():
        raise HTTPException(404, "原始文本不存在，请先解析")
    speech_path = ch_dir / "speech.md"
    if speech_path.exists():
        # 备份当前文本，避免误操作丢失
        (ch_dir / "speech.previous.md").write_text(
            speech_path.read_text(encoding="utf-8"), encoding="utf-8")
    speech_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {"ok": True, "restored_from": "source.md"}


@router.post("/{chapter_id}/synthesize", response_model=JobInfo)
async def synthesize_chapter(request: Request, book_id: str, chapter_id: str,
                             concurrency: int | None = Query(None, ge=1)):
    data_dir = _data_dir(request)
    book_id = _validate_id(book_id)
    chapter_id = _validate_id(chapter_id)
    bdir = store.book_dir(data_dir, book_id)
    if not bdir.exists():
        raise HTTPException(404, "书籍不存在")
    chapters = store.load_json(bdir / "chapters.json", {"chapters": []})["chapters"]
    if not any(c["id"] == chapter_id for c in chapters):
        raise HTTPException(404, "章节不存在")
    jm = request.app.state.job_manager
    jid = jm.start("synthesize", book_id, chapter_id, concurrency=concurrency)
    return JobInfo(**jm.get_job(jid))


@router.post("/{chapter_id}/rewrite", response_model=JobInfo)
async def rewrite_chapter(request: Request, book_id: str, chapter_id: str,
                          concurrency: int = Query(20, ge=1)):
    data_dir = _data_dir(request)
    book_id = _validate_id(book_id)
    chapter_id = _validate_id(chapter_id)
    bdir = store.book_dir(data_dir, book_id)
    if not bdir.exists():
        raise HTTPException(404, "书籍不存在")
    chapters = store.load_json(bdir / "chapters.json", {"chapters": []})["chapters"]
    if not any(c["id"] == chapter_id for c in chapters):
        raise HTTPException(404, "章节不存在")
    jm = request.app.state.job_manager
    jid = jm.start("rewrite", book_id, chapter_id, concurrency=concurrency)
    return JobInfo(**jm.get_job(jid))


@router.post("/{chapter_id}/rebuild", response_model=JobInfo)
async def rebuild_chapter(request: Request, book_id: str, chapter_id: str,
                          concurrency: int | None = Query(None, ge=1)):
    data_dir = _data_dir(request)
    book_id = _validate_id(book_id)
    chapter_id = _validate_id(chapter_id)
    bdir = store.book_dir(data_dir, book_id)
    if not bdir.exists():
        raise HTTPException(404, "书籍不存在")
    chapters = store.load_json(bdir / "chapters.json", {"chapters": []})["chapters"]
    if not any(c["id"] == chapter_id for c in chapters):
        raise HTTPException(404, "章节不存在")
    jm = request.app.state.job_manager
    jid = jm.start("rebuild", book_id, chapter_id, concurrency=concurrency)
    return JobInfo(**jm.get_job(jid))


@router.get("/{chapter_id}/audio")
async def get_audio(request: Request, book_id: str, chapter_id: str):
    data_dir = _data_dir(request)
    book_id = _validate_id(book_id)
    chapter_id = _validate_id(chapter_id)
    path = store.chapter_dir(data_dir, book_id, chapter_id) / "audio.wav"
    if not path.exists():
        raise HTTPException(404, "音频不存在，请先合成")
    return FileResponse(path, media_type="audio/wav")


@router.get("/{chapter_id}/chapter.vtt")
async def get_vtt(request: Request, book_id: str, chapter_id: str):
    data_dir = _data_dir(request)
    book_id = _validate_id(book_id)
    chapter_id = _validate_id(chapter_id)
    path = store.chapter_dir(data_dir, book_id, chapter_id) / "chapter.vtt"
    if not path.exists():
        raise HTTPException(404, "字幕不存在")
    return FileResponse(path, media_type="text/vtt; charset=utf-8")


def _data_dir(request: Request):
    return request.app.state.data_dir
