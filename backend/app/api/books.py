import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile

from app import store
from app.models import Book, BookDetail, JobInfo

router = APIRouter()


def _ctx(request: Request):
    s = request.app.state
    return s.data_dir, s.job_manager


def _validate_id(book_id: str) -> str:
    try:
        return store.validate_id(book_id)
    except ValueError:
        raise HTTPException(400, "非法 ID") from None


def _book_kwargs(meta: dict) -> dict:
    return {k: v for k, v in meta.items() if k in Book.model_fields}


@router.post("", response_model=Book)
async def upload_book(request: Request, file: UploadFile):
    data_dir, _ = _ctx(request)
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "仅支持 PDF 文件")
    data = await file.read()
    # 写盘前先用字节流校验，避免非法文件落地（Windows 上 fitz.open 失败后会锁住文件句柄，rmtree 无法清理）
    import pymupdf as fitz
    try:
        fitz.open(stream=data, filetype="pdf").close()
    except Exception:
        raise HTTPException(400, "仅支持 PDF 文件")
    book_id = store.new_book_id()
    bdir = store.book_dir(data_dir, book_id)
    bdir.mkdir(parents=True)
    dest = bdir / "source.pdf"
    try:
        dest.write_bytes(data)
        from app.services.pdf_extractor import extract_meta
        meta = extract_meta(dest)
    except Exception:
        shutil.rmtree(bdir, ignore_errors=True)
        raise HTTPException(400, "仅支持 PDF 文件")
    meta.update({"book_id": book_id, "status": "uploaded", "toc": [],
                 "created_at": datetime.now(timezone.utc).isoformat()})
    # 元数据无标题时回退到原始文件名（不再显示 source.pdf 的 stem "source"）
    if not meta.get("title") or meta["title"] == dest.stem:
        meta["title"] = Path(file.filename or "book").stem
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
    books.sort(key=lambda b: b.created_at or "", reverse=True)
    return books


@router.get("/{book_id}", response_model=BookDetail)
async def get_book(request: Request, book_id: str):
    data_dir, _ = _ctx(request)
    book_id = _validate_id(book_id)
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
    book_id = _validate_id(book_id)
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
async def start_rewrite(request: Request, book_id: str,
                        concurrency: int = Query(20, ge=1)):
    return await _start(request, "rewrite", book_id, require_parsed=True,
                        concurrency=concurrency)


@router.post("/{book_id}/synthesize", response_model=JobInfo)
async def start_synthesize(request: Request, book_id: str,
                           concurrency: int | None = Query(None)):
    _check_tts_concurrency(concurrency)
    return await _start(request, "synthesize", book_id, require_parsed=True,
                        concurrency=concurrency)


def _check_tts_concurrency(concurrency: int | None) -> None:
    """合成并发：≥1 或 -1（-1 表示不限制并发，仅按 RPM 限速）。"""
    if concurrency is not None and concurrency != -1 and concurrency < 1:
        raise HTTPException(400, "合成并发需为 -1（不限）或 ≥1")


async def _start(request: Request, job_type: str, book_id: str, *,
                   require_parsed: bool = False, concurrency: int | None = None):
    data_dir, jm = _ctx(request)
    book_id = _validate_id(book_id)
    bdir = store.book_dir(data_dir, book_id)
    if not bdir.exists():
        raise HTTPException(404, "书籍不存在")
    if require_parsed and not (bdir / "chapters.json").exists():
        raise HTTPException(400, "请先解析章节")
    jid = jm.start(job_type, book_id, concurrency=concurrency)
    return JobInfo(**jm.get_job(jid))
