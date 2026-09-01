from fastapi import APIRouter, HTTPException, Request
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
    (ch_dir / "speech.md").write_text(body, encoding="utf-8")
    return {"ok": True}


@router.post("/{chapter_id}/rebuild", response_model=JobInfo)
async def rebuild_chapter(request: Request, book_id: str, chapter_id: str):
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
    jid = jm.start("rebuild", book_id, chapter_id)
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
