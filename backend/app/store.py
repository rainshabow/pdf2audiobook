import json
import re
import sqlite3
import threading
import uuid
from pathlib import Path

_DATA_DIR_NAME = "books"

VALID_ID_RE = re.compile(r"^[A-Za-z0-9_+\-]+$")


def validate_id(book_id: str) -> str:
    """校验书籍/章节 ID 只含白名单字符，非法时抛 ValueError。"""
    if not isinstance(book_id, str) or VALID_ID_RE.fullmatch(book_id) is None:
        raise ValueError("非法 ID")
    return book_id


def init_store(data_dir: Path) -> None:
    (data_dir / _DATA_DIR_NAME).mkdir(parents=True, exist_ok=True)
    (data_dir / "tmp").mkdir(parents=True, exist_ok=True)


def book_dir(data_dir: Path, book_id: str) -> Path:
    return data_dir / _DATA_DIR_NAME / book_id


def chapter_dir(data_dir: Path, book_id: str, chapter_id: str) -> Path:
    return book_dir(data_dir, book_id) / "chapters" / chapter_id


def save_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def new_book_id() -> str:
    return uuid.uuid4().hex[:12]


class JobDB:
    """SQLite 任务库（同步 + 锁，本地单进程足够）。"""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                chapter_id TEXT,
                type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                progress REAL NOT NULL DEFAULT 0,
                error TEXT,
                settings_snapshot TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def create_job(self, job_id: str, book_id: str, chapter_id: str | None,
                   job_type: str, settings_snapshot: str) -> None:
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (id, book_id, chapter_id, type, settings_snapshot, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (job_id, book_id, chapter_id, job_type, settings_snapshot, now, now),
            )
            self._conn.commit()

    def update_job(self, job_id: str, **fields: object) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = [fields[k] for k in fields] + [_now(), job_id]
        with self._lock:
            self._conn.execute(
                f"UPDATE jobs SET {cols}, updated_at = ? WHERE id = ?", values
            )
            self._conn.commit()

    def get_job(self, job_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return _row_to_dict(row)

    def list_jobs(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def cancel_stale(self) -> int:
        """进程启动时将上次进程遗留的 running/pending 行置为 cancelled。"""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE jobs SET status = 'cancelled', error = '服务重启，遗留任务已取消', updated_at = ? "
                "WHERE status IN ('pending', 'running')", (_now(),))
            self._conn.commit()
        return cur.rowcount

    def delete_job(self, job_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            self._conn.commit()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


_COLUMNS = ["id", "book_id", "chapter_id", "type", "status",
            "progress", "error", "settings_snapshot", "created_at", "updated_at"]


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    return {name: row[i] for i, name in enumerate(_COLUMNS)}
