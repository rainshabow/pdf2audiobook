import shutil

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app import store
from app.models import Book, BookDetail, JobInfo

router = APIRouter()


def _ctx(request: Request):
    s = request.app.state
    return s.data_dir, s.job_manager


def _book_kwargs(meta: dict) -> dict:
    return {k: v for k, v in meta.items() if k in Book.model_fields}


@router.post("", response_model=Book)
async def upload_book(request: Request, file: UploadFile):
    data_dir, _ = _ctx(request)
    book_id = store.new_book_id()
    bdir = store.book_dir(data_dir, book_id)
    bdir.mkdir(parents=True)
    dest = bdir / "source.pdf"
    dest.write_bytes(await file.read())
    from app.services.pdf_extractor import extract_meta
    meta = extract_meta(dest)
    meta.update({"book_id": book_id, "status": "uploaded", "toc": []})
    store.save_json(bdir / "meta.json", meta)
    return Book(**_book_kwargs(meta), chapter_count=0)


@router.get("", response_model=list[Book])
async def list_books(request: Request):
    data_dir, _ = _ctx(request)
    books = []
    for bdir in sorted((data_dir / "books").iterdir()):
        if not bdir.is_dir():
            continue
        meta = store.load_json(bdir / "meta.json", {})
        chapters = store.load_json(bdir / "chapters.json", {"chapters": []})["chapters"]
        books.append(Book(**_book_kwargs(meta), chapter_count=len(chapters)))
    return books


@router.get("/{book_id}", response_model=BookDetail)
async def get_book(request: Request, book_id: str):
    data_dir, _ = _ctx(request)
    bdir = store.book_dir(data_dir, book_id)
    if not bdir.exists():
        raise HTTPException(404, "书籍不存在")
    meta = store.load_json(bdir / "meta.json", {})
    chapters = store.load_json(bdir / "chapters.json", {"chapters": []})["chapters"]
    for ch in chapters:
        status = store.load_json(bdir / "chapters" / ch["id"] / "status.json", {})
        ch["status"] = status.get("status", "pending")
        ch["audio_duration"] = status.get("audio_duration", 0.0)
    return BookDetail(**meta, chapters=chapters)


@router.delete("/{book_id}")
async def delete_book(request: Request, book_id: str):
    data_dir, _ = _ctx(request)
    bdir = store.book_dir(data_dir, book_id).resolve()
    root = (data_dir / "books").resolve()
    if not bdir.is_relative_to(root):
        raise HTTPException(400, "非法路径")
    if bdir.exists():
        shutil.rmtree(bdir)
    return {"ok": True}


@router.post("/{book_id}/parse", response_model=JobInfo)
async def start_parse(request: Request, book_id: str):
    return await _start(request, "parse", book_id)


@router.post("/{book_id}/rewrite", response_model=JobInfo)
async def start_rewrite(request: Request, book_id: str):
    return await _start(request, "rewrite", book_id)


@router.post("/{book_id}/synthesize", response_model=JobInfo)
async def start_synthesize(request: Request, book_id: str):
    return await _start(request, "synthesize", book_id)


async def _start(request: Request, job_type: str, book_id: str):
    data_dir, jm = _ctx(request)
    bdir = store.book_dir(data_dir, book_id)
    if not bdir.exists():
        raise HTTPException(404, "书籍不存在")
    jid = jm.start(job_type, book_id)
    return JobInfo(**jm.get_job(jid))
