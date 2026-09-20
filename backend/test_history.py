import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.database import init_database, list_analyses
from backend.main import app


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "history.db"
        env = patch.dict(os.environ, {"DATABASE_PATH": str(self.path)})
        env.start()
        self.addCleanup(env.stop)

    def test_history_persists_and_isolates_visitors(self):
        with TestClient(app) as client:
            response = client.post("/api/analyze", json={"text": "今天很开心"})
            self.assertEqual(response.status_code, 200)
            sid = client.cookies.get("session_id")
            self.assertTrue(sid)
            history = client.get("/api/history").json()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["text"], "今天很开心")
            for limit in (0, -1, 101):
                self.assertEqual(client.get(f"/api/history?limit={limit}").status_code, 422)
        with TestClient(app) as other:
            self.assertEqual(other.get("/api/history").json(), [])
        with TestClient(app) as returning:
            returning.cookies.set("session_id", sid)
            self.assertEqual(len(returning.get("/api/history").json()), 1)

    def test_old_schema_is_migrated_without_exposing_records(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                "CREATE TABLE analysis_history (id INTEGER PRIMARY KEY, text TEXT, "
                "score REAL, label TEXT, pinyin TEXT, created_at TEXT)"
            )
            connection.execute(
                "INSERT INTO analysis_history VALUES (1, 'old', 0.5, 'neutral', '', '2026-01-01')"
            )
            connection.commit()
        init_database()
        init_database()
        self.assertEqual(list_analyses("new-visitor"), [])
        with TestClient(app) as client:
            self.assertEqual(client.post("/api/analyze", json={"text": "今天很开心"}).status_code, 200)
            self.assertEqual(len(client.get("/api/history").json()), 1)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis_history").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
