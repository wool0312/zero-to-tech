import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent / "data" / "app.db"


def get_database_path() -> Path:
    configured_path = os.getenv("DATABASE_PATH")
    if not configured_path:
        return DEFAULT_DATABASE_PATH

    database_path = Path(configured_path).expanduser()
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    return database_path.resolve()

@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        with connection:
            yield connection
    finally:
        connection.close()


def init_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                text TEXT NOT NULL,
                score REAL NOT NULL CHECK (score >= 0 AND score <= 1),
                label TEXT NOT NULL,
                pinyin TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(analysis_history)")}
        if "session_id" not in columns:
            # 保留旧记录，但不能把归属未知的记录分配给新访客。
            connection.execute("ALTER TABLE analysis_history ADD COLUMN session_id TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_history_session_created "
            "ON analysis_history(session_id, created_at)"
        )


def insert_analysis(session_id: str, record: dict[str, Any]) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO analysis_history (
                session_id,
                text,
                score,
                label,
                pinyin,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                record["text"],
                record["score"],
                record["label"],
                record["pinyin"],
                record["created_at"],
            ),
        )
        return int(cursor.lastrowid)


def list_analyses(session_id: str, limit: int = 10) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, text, score, label, pinyin, created_at
            FROM analysis_history
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]
