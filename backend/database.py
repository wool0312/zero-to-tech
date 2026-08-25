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
                text TEXT NOT NULL,
                score REAL NOT NULL CHECK (score >= 0 AND score <= 1),
                label TEXT NOT NULL,
                pinyin TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_history_created_at
            ON analysis_history(created_at DESC)
            """
        )


def insert_analysis(record: dict[str, Any]) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO analysis_history (
                text,
                score,
                label,
                pinyin,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record["text"],
                record["score"],
                record["label"],
                record["pinyin"],
                record["created_at"],
            ),
        )
        return int(cursor.lastrowid)


def list_analyses(limit: int = 10) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, text, score, label, pinyin, created_at
            FROM analysis_history
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
