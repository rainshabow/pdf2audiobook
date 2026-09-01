import json
from pathlib import Path
from app import store


def test_init_and_dirs(tmp_path: Path):
    store.init_store(tmp_path)
    assert (tmp_path / "books").is_dir()
    book = store.book_dir(tmp_path, "abc")
    assert book == tmp_path / "books" / "abc"
    ch = store.chapter_dir(tmp_path, "abc", "ch-001")
    assert ch == tmp_path / "books" / "abc" / "chapters" / "ch-001"


def test_json_roundtrip(tmp_path: Path):
    store.init_store(tmp_path)
    p = tmp_path / "meta.json"
    store.save_json(p, {"a": 1})
    assert store.load_json(p, {}) == {"a": 1}
    assert store.load_json(tmp_path / "missing.json", {"x": 2}) == {"x": 2}


def test_new_book_id_unique():
    assert store.new_book_id() != store.new_book_id()


def test_jobdb_crud(tmp_path: Path):
    db = store.JobDB(tmp_path / "jobs.db")
    db.create_job(job_id="j1", book_id="b1", chapter_id=None,
                  job_type="parse", settings_snapshot="{}")
    job = db.get_job("j1")
    assert job["status"] == "pending"
    db.update_job("j1", status="running", progress=0.5)
    assert db.get_job("j1")["progress"] == 0.5
    assert len(db.list_jobs()) == 1
    db.delete_job("j1")
    assert db.get_job("j1") is None
